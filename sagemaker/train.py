#!/usr/bin/env python3
"""
SageMaker Training Script — AI Microgrid (Unified Single Model)
================================================================
Trains ONE XGBoost model for all 13 consumers + 1 solar model.
Both saved as pickle (.pkl) to /opt/ml/model/ which SageMaker
tars and uploads to S3 automatically.

SageMaker then:
  - Stores the tar.gz in S3
  - Can deploy it to a real-time endpoint using inference.py
  - EC2 downloads and extracts the tar.gz on each deploy

Output files in /opt/ml/model/:
  unified_demand_model.pkl    — single XGBoost for all 13 houses
  solar_model.pkl             — XGBoost for solar generation
  model_registry.json         — metadata, metrics, feature info
"""

import os
import sys
import json
import time
import pickle
import logging
import numpy as np
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("sagemaker-train")

# ── SageMaker standard paths ───────────────────────────────────────────────
SM_MODEL_DIR  = Path(os.environ.get("SM_MODEL_DIR",  "/opt/ml/model"))
SM_INPUT_DIR  = Path(os.environ.get("SM_INPUT_DIR",  "/opt/ml/input/data/training"))
SM_OUTPUT_DIR = Path(os.environ.get("SM_OUTPUT_DIR", "/opt/ml/output"))
SM_PARAM_FILE = Path("/opt/ml/input/config/hyperparameters.json")
SM_MODEL_DIR.mkdir(parents=True, exist_ok=True)

# ── Hyperparameters ────────────────────────────────────────────────────────
params = {}
if SM_PARAM_FILE.exists():
    with open(SM_PARAM_FILE) as f:
        params = json.load(f)

N_DAYS        = int(params.get("n_days",         "120"))
N_ESTIMATORS  = int(params.get("n_estimators",   "300"))
MAX_DEPTH     = int(params.get("max_depth",       "7"))
LEARNING_RATE = float(params.get("learning_rate", "0.07"))
logger.info(f"Params: n_days={N_DAYS}, n_estimators={N_ESTIMATORS}, "
            f"max_depth={MAX_DEPTH}, lr={LEARNING_RATE}")

# ── Dependencies ───────────────────────────────────────────────────────────
try:
    from xgboost import XGBRegressor
    logger.info("✅ xgboost available")
except ImportError as e:
    logger.error(f"Missing: {e}")
    sys.exit(1)

# ── House profiles ─────────────────────────────────────────────────────────
HOUSE_PROFILES = {
    "clinic":   {"base": 3.2, "peak_hour": 10, "peak_mult": 1.8, "priority": "critical"},
    "school":   {"base": 2.5, "peak_hour": 11, "peak_mult": 2.0, "priority": "high"},
    "pump":     {"base": 1.8, "peak_hour": 6,  "peak_mult": 2.5, "priority": "high"},
    "house_1":  {"base": 0.9, "peak_hour": 19, "peak_mult": 2.2, "priority": "normal"},
    "house_2":  {"base": 0.7, "peak_hour": 20, "peak_mult": 1.9, "priority": "normal"},
    "house_3":  {"base": 1.1, "peak_hour": 18, "peak_mult": 2.1, "priority": "normal"},
    "house_4":  {"base": 0.8, "peak_hour": 21, "peak_mult": 1.7, "priority": "normal"},
    "house_5":  {"base": 1.0, "peak_hour": 19, "peak_mult": 2.0, "priority": "normal"},
    "house_6":  {"base": 0.6, "peak_hour": 20, "peak_mult": 1.8, "priority": "normal"},
    "house_7":  {"base": 0.9, "peak_hour": 18, "peak_mult": 2.3, "priority": "normal"},
    "house_8":  {"base": 1.2, "peak_hour": 21, "peak_mult": 1.6, "priority": "normal"},
    "house_9":  {"base": 0.8, "peak_hour": 19, "peak_mult": 2.0, "priority": "normal"},
    "house_10": {"base": 0.7, "peak_hour": 20, "peak_mult": 1.9, "priority": "normal"},
}

HOUSE_ID_ENCODING = {hid: idx for idx, hid in enumerate(sorted(HOUSE_PROFILES.keys()))}


# ── Feature builder (must match inference.py exactly) ─────────────────────
def build_features(house_id, hour, day_of_week, month, history):
    house_enc = float(HOUSE_ID_ENCODING[house_id])
    base_load = float(HOUSE_PROFILES[house_id]["base"])
    h_sin = np.sin(2 * np.pi * hour / 24)
    h_cos = np.cos(2 * np.pi * hour / 24)
    d_sin = np.sin(2 * np.pi * day_of_week / 7)
    d_cos = np.cos(2 * np.pi * day_of_week / 7)
    m_sin = np.sin(2 * np.pi * month / 12)
    m_cos = np.cos(2 * np.pi * month / 12)
    n = len(history)
    lag_1  = history[-1]  if n >= 1  else base_load
    lag_24 = history[-24] if n >= 24 else lag_1
    lag_48 = history[-48] if n >= 48 else lag_24
    w6  = history[-6:]  if n >= 6  else history
    w12 = history[-12:] if n >= 12 else history
    return np.array([
        house_enc,
        hour, h_sin, h_cos,
        day_of_week, d_sin, d_cos,
        m_sin, m_cos,
        lag_1, lag_24, lag_48,
        float(np.mean(w6)), float(np.std(w6)), float(np.mean(w12)),
        1.0 if 6 <= hour <= 22  else 0.0,
        1.0 if 6 <= hour <= 9   else 0.0,
        1.0 if 17 <= hour <= 22 else 0.0,
        1.0 if day_of_week >= 5 else 0.0,
        base_load,
    ], dtype=np.float32)


def gaussian(h, peak, width=3.5):
    return np.exp(-((h - peak) ** 2) / (2 * width ** 2))


def simulate_demand(house_id, noise=0.10):
    p = HOUSE_PROFILES[house_id]
    base, peak_h, peak_m = p["base"], p["peak_hour"], p["peak_mult"]
    out = []
    for h in range(24):
        morning = gaussian(h, 7, 2.5) * 0.5
        evening = gaussian(h, peak_h, 2.0) * (peak_m - 1.0)
        nf = 0.3 if h < 5 else 1.0
        val = base * (1 + morning + evening) * nf
        out.append(max(0.05, val + np.random.normal(0, noise * val)))
    return out


def simulate_solar(capacity_kw=30.0, cloud=0.2):
    out = []
    for h in range(24):
        if h < 6 or h > 19:
            out.append(0.0)
        else:
            peak = capacity_kw * (1 - cloud) * np.exp(-((h - 13) ** 2) / 18)
            out.append(max(0.0, peak + np.random.normal(0, peak * 0.05)))
    return out


# ── Build training datasets ────────────────────────────────────────────────
def build_demand_dataset(n_days):
    """
    All 13 houses pooled → one big dataset.
    In production: read real CSV from SM_INPUT_DIR instead.
    """
    X_all, y_all = [], []
    for house_id in HOUSE_PROFILES:
        history = []
        for day in range(n_days):
            dow   = day % 7
            month = ((day // 30) % 12) + 1
            daily = simulate_demand(house_id)
            for h, demand in enumerate(daily):
                if history:
                    X_all.append(build_features(house_id, h, dow, month, history))
                    y_all.append(demand)
                history.append(demand)
    X = np.array(X_all, dtype=np.float32)
    y = np.array(y_all, dtype=np.float32)
    logger.info(f"Demand dataset: {X.shape[0]:,} rows × {X.shape[1]} features")
    return X, y


def build_solar_dataset(n_days):
    X_all, y_all, hist = [], [], []
    for day in range(n_days):
        cloud = np.random.uniform(0.05, 0.60)
        month = ((day // 30) % 12) + 1
        hourly = simulate_solar(30.0, cloud)
        for h, gen in enumerate(hourly):
            if hist:
                h_sin = np.sin(2 * np.pi * h / 24)
                h_cos = np.cos(2 * np.pi * h / 24)
                m_sin = np.sin(2 * np.pi * month / 12)
                m_cos = np.cos(2 * np.pi * month / 12)
                lag1  = hist[-1]
                lag24 = hist[-24] if len(hist) >= 24 else lag1
                rm3   = float(np.mean(hist[-3:])) if len(hist) >= 3 else lag1
                X_all.append([h, h_sin, h_cos, m_sin, m_cos, cloud,
                               1.0 if 10 <= h <= 15 else 0.0, lag1, lag24, rm3])
                y_all.append(gen)
            hist.append(gen)
    return np.array(X_all, dtype=np.float32), np.array(y_all, dtype=np.float32)


# ── MAIN ───────────────────────────────────────────────────────────────────
def main():
    logger.info("=" * 55)
    logger.info("  AI Microgrid — SageMaker Training (Unified Model)")
    logger.info("=" * 55)

    registry    = {"version": "2.0.0", "trained_at": datetime.now().isoformat(),
                   "sagemaker": True, "model_format": "pickle"}
    total_start = time.time()

    # ── 1. Train unified demand model ──────────────────────────────────
    logger.info(f"\n[1/2] Building demand dataset ({N_DAYS} days × 13 houses)...")
    X, y  = build_demand_dataset(N_DAYS)
    split = int(len(X) * 0.85)

    logger.info(f"      Training XGBoost on {split:,} rows...")
    t0    = time.time()
    model = XGBRegressor(
        n_estimators=N_ESTIMATORS, max_depth=MAX_DEPTH,
        learning_rate=LEARNING_RATE, subsample=0.85,
        colsample_bytree=0.8, min_child_weight=3,
        reg_alpha=0.1, random_state=42, verbosity=0, n_jobs=-1,
    )
    model.fit(X[:split], y[:split], eval_set=[(X[split:], y[split:])], verbose=False)

    y_pred  = model.predict(X[split:])
    mae     = float(np.mean(np.abs(y[split:] - y_pred)))
    rmse    = float(np.sqrt(np.mean((y[split:] - y_pred) ** 2)))
    mape    = float(np.mean(np.abs((y[split:] - y_pred) / np.maximum(y[split:], 0.01))) * 100)
    elapsed = time.time() - t0

    # Save as pickle
    demand_path = SM_MODEL_DIR / "unified_demand_model.pkl"
    with open(demand_path, "wb") as f:
        pickle.dump(model, f, protocol=pickle.HIGHEST_PROTOCOL)

    logger.info(f"  ✅ unified_demand_model.pkl saved "
                f"({demand_path.stat().st_size//1024} KB) | "
                f"MAE={mae:.4f} | RMSE={rmse:.4f} | MAPE={mape:.2f}% | {elapsed:.1f}s")
    print(f"[sagemaker metric] demand_mae={mae:.4f} demand_rmse={rmse:.4f}")

    registry["demand_model"] = {
        "file": "unified_demand_model.pkl",
        "mae_kw": round(mae, 4), "rmse_kw": round(rmse, 4),
        "mape_pct": round(mape, 2), "n_train_rows": split,
        "n_features": X.shape[1], "houses": list(HOUSE_PROFILES.keys()),
        "house_encoding": HOUSE_ID_ENCODING, "train_time_s": round(elapsed, 2),
    }

    # ── 2. Train solar model ───────────────────────────────────────────
    logger.info(f"\n[2/2] Building solar dataset...")
    Xs, ys = build_solar_dataset(N_DAYS)
    sp     = int(len(Xs) * 0.85)
    t0     = time.time()

    solar_model = XGBRegressor(
        n_estimators=N_ESTIMATORS, max_depth=5, learning_rate=LEARNING_RATE,
        subsample=0.85, colsample_bytree=0.8, random_state=42, verbosity=0, n_jobs=-1
    )
    solar_model.fit(Xs[:sp], ys[:sp], eval_set=[(Xs[sp:], ys[sp:])], verbose=False)

    ysp      = np.maximum(0, solar_model.predict(Xs[sp:]))
    sol_mae  = float(np.mean(np.abs(ys[sp:] - ysp)))
    sol_rmse = float(np.sqrt(np.mean((ys[sp:] - ysp) ** 2)))
    elapsed  = time.time() - t0

    solar_path = SM_MODEL_DIR / "solar_model.pkl"
    with open(solar_path, "wb") as f:
        pickle.dump(solar_model, f, protocol=pickle.HIGHEST_PROTOCOL)

    logger.info(f"  ✅ solar_model.pkl saved | MAE={sol_mae:.4f} | {elapsed:.1f}s")
    print(f"[sagemaker metric] solar_mae={sol_mae:.4f} solar_rmse={sol_rmse:.4f}")

    registry["solar_model"] = {
        "file": "solar_model.pkl", "mae_kw": round(sol_mae, 4),
        "rmse_kw": round(sol_rmse, 4), "train_time_s": round(elapsed, 2),
    }

    # ── Save registry ──────────────────────────────────────────────────
    registry["total_train_time_s"] = round(time.time() - total_start, 2)
    with open(SM_MODEL_DIR / "model_registry.json", "w") as f:
        json.dump(registry, f, indent=2)

    # ── Summary ────────────────────────────────────────────────────────
    saved = list(SM_MODEL_DIR.glob("*.pkl"))
    logger.info(f"\n{'='*55}")
    logger.info(f"  TRAINING COMPLETE in {registry['total_train_time_s']}s")
    logger.info(f"  {len(saved)} pickle files saved to {SM_MODEL_DIR}")
    for f in saved:
        logger.info(f"    📦 {f.name}  ({f.stat().st_size//1024} KB)")
    logger.info(f"  SageMaker will tar and upload to S3 automatically")
    logger.info(f"{'='*55}")


if __name__ == "__main__":
    main()
