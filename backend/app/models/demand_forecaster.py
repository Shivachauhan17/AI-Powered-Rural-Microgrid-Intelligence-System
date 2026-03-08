"""
Unified Demand Forecaster
=========================
ONE XGBoost model for ALL 13 consumers.
house_id is encoded as an integer feature so one model learns everyone.

Model file : app/models/saved_models/unified_demand_model.pkl
Registry   : app/models/saved_models/model_registry.json

Feature vector (20 features):
  0  house_id_encoded   integer 0-12
  1  hour               0-23
  2  hour_sin
  3  hour_cos
  4  day_of_week        0-6
  5  dow_sin
  6  dow_cos
  7  month_sin
  8  month_cos
  9  lag_1h
  10 lag_24h
  11 lag_48h
  12 rolling_mean_6h
  13 rolling_std_6h
  14 rolling_mean_12h
  15 is_daytime
  16 is_morning_peak
  17 is_evening_peak
  18 is_weekend
  19 base_load_kw
"""

import json
import pickle
import logging
import time
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    from xgboost import XGBRegressor
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    logger.warning("xgboost not installed — pip install xgboost")

from app.utils.data_generator import generate_demand_forecast, HOUSE_PROFILES

MODEL_DIR     = Path(__file__).parent / "saved_models"
MODEL_PATH    = MODEL_DIR / "unified_demand_model.pkl"
REGISTRY_PATH = MODEL_DIR / "model_registry.json"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# Stable integer encoding — must never change order
HOUSE_ID_ENCODING: Dict[str, int] = {
    hid: idx for idx, hid in enumerate(sorted(HOUSE_PROFILES.keys()))
}

FEATURE_NAMES = [
    "house_id_encoded", "hour", "hour_sin", "hour_cos",
    "day_of_week", "dow_sin", "dow_cos", "month_sin", "month_cos",
    "lag_1h", "lag_24h", "lag_48h",
    "rolling_mean_6h", "rolling_std_6h", "rolling_mean_12h",
    "is_daytime", "is_morning_peak", "is_evening_peak", "is_weekend",
    "base_load_kw",
]
N_FEATURES = len(FEATURE_NAMES)  # 20


def _build_features(house_id: str, hour: int, dow: int, month: int, history: List[float]) -> np.ndarray:
    enc  = float(HOUSE_ID_ENCODING.get(house_id, 0))
    base = float(HOUSE_PROFILES[house_id]["base"])
    h_sin = np.sin(2 * np.pi * hour / 24);  h_cos = np.cos(2 * np.pi * hour / 24)
    d_sin = np.sin(2 * np.pi * dow  /  7);  d_cos = np.cos(2 * np.pi * dow  /  7)
    m_sin = np.sin(2 * np.pi * month / 12); m_cos = np.cos(2 * np.pi * month / 12)
    n = len(history)
    l1  = history[-1]  if n >= 1  else base
    l24 = history[-24] if n >= 24 else l1
    l48 = history[-48] if n >= 48 else l24
    w6  = history[-6:]  if n >= 6  else history
    w12 = history[-12:] if n >= 12 else history
    return np.array([
        enc, hour, h_sin, h_cos,
        dow, d_sin, d_cos, m_sin, m_cos,
        l1, l24, l48,
        float(np.mean(w6)), float(np.std(w6)), float(np.mean(w12)),
        1.0 if 6 <= hour <= 22  else 0.0,
        1.0 if 6 <= hour <= 9   else 0.0,
        1.0 if 17 <= hour <= 22 else 0.0,
        1.0 if dow >= 5         else 0.0,
        base,
    ], dtype=np.float32)


def _build_training_data(n_days: int = 120) -> Tuple[np.ndarray, np.ndarray]:
    X_all, y_all = [], []
    for house_id in HOUSE_PROFILES:
        history: List[float] = []
        for day in range(n_days):
            dow   = day % 7
            month = ((day // 30) % 12) + 1
            daily = generate_demand_forecast(house_id, hours=24, noise_factor=0.10)
            for h, demand in enumerate(daily):
                if history:
                    X_all.append(_build_features(house_id, h, dow, month, history))
                    y_all.append(demand)
                history.append(demand)
    X = np.array(X_all, dtype=np.float32)
    y = np.array(y_all, dtype=np.float32)
    logger.info(f"Training data: {X.shape[0]:,} rows × {X.shape[1]} features")
    return X, y


class DemandForecaster:
    def __init__(self):
        self.model    = None
        self.registry = {}
        self._ready   = False

    def load_or_train(self, force: bool = False):
        if not XGBOOST_AVAILABLE:
            logger.warning("XGBoost missing — using statistical fallback")
            return
        if not force and MODEL_PATH.exists():
            self._load()
        else:
            logger.info("Training unified demand model…")
            self.train_and_save()

    def train_and_save(self, n_days: int = 120):
        if not XGBOOST_AVAILABLE:
            return
        t0   = time.time()
        X, y = _build_training_data(n_days)
        sp   = int(len(X) * 0.85)

        model = XGBRegressor(
            n_estimators=300, max_depth=7, learning_rate=0.07,
            subsample=0.85, colsample_bytree=0.8, min_child_weight=3,
            reg_alpha=0.1, random_state=42, verbosity=0, n_jobs=-1,
        )
        model.fit(X[:sp], y[:sp], eval_set=[(X[sp:], y[sp:])], verbose=False)

        y_pred = model.predict(X[sp:])
        mae  = float(np.mean(np.abs(y[sp:] - y_pred)))
        rmse = float(np.sqrt(np.mean((y[sp:] - y_pred) ** 2)))
        mape = float(np.mean(np.abs((y[sp:] - y_pred) / np.maximum(y[sp:], 0.01))) * 100)

        with open(MODEL_PATH, "wb") as f:
            pickle.dump(model, f, protocol=pickle.HIGHEST_PROTOCOL)

        self.registry = {
            "model_file":    MODEL_PATH.name,
            "model_format":  "pickle",
            "version":       "2.0.0",
            "trained_at":    datetime.now().isoformat(),
            "n_features":    N_FEATURES,
            "feature_names": FEATURE_NAMES,
            "house_encoding": HOUSE_ID_ENCODING,
            "houses":        list(HOUSE_PROFILES.keys()),
            "n_train_rows":  sp,
            "n_val_rows":    len(X) - sp,
            "n_days":        n_days,
            "val_mae_kw":    round(mae, 4),
            "val_rmse_kw":   round(rmse, 4),
            "val_mape_pct":  round(mape, 2),
            "train_time_s":  round(time.time() - t0, 2),
        }
        with open(REGISTRY_PATH, "w") as f:
            json.dump(self.registry, f, indent=2)

        self.model  = model
        self._ready = True
        sz = MODEL_PATH.stat().st_size // 1024
        logger.info(f"✅ unified_demand_model.pkl saved ({sz} KB) | "
                    f"MAE={mae:.4f} | RMSE={rmse:.4f} | MAPE={mape:.2f}%")

    def _load(self):
        try:
            with open(MODEL_PATH, "rb") as f:
                self.model = pickle.load(f)
            if REGISTRY_PATH.exists():
                with open(REGISTRY_PATH) as f:
                    self.registry = json.load(f)
            self._ready = True
            sz = MODEL_PATH.stat().st_size // 1024
            logger.info(f"Unified demand model loaded ({sz} KB)")
        except Exception as e:
            logger.error(f"Failed to load demand model: {e}")

    # ── Inference ──────────────────────────────────────────────────────────
    def forecast(self, house_id: str, hours: int = 24) -> List[float]:
        if self._ready and self.model is not None:
            return self._ml_forecast(house_id, hours)
        return generate_demand_forecast(house_id, hours)

    def _ml_forecast(self, house_id: str, hours: int) -> List[float]:
        now     = datetime.now()
        history = generate_demand_forecast(house_id, hours=48, noise_factor=0.04)
        preds   = []
        for step in range(hours):
            h   = (now.hour + step) % 24
            dow = (now.weekday() + (now.hour + step) // 24) % 7
            row = _build_features(house_id, h, dow, now.month, history)
            val = float(self.model.predict(row.reshape(1, -1))[0])
            val = round(max(0.05, val), 3)
            preds.append(val)
            history.append(val)
        return preds

    def forecast_all_houses(self, hours: int = 24) -> Dict[str, List[float]]:
        return {hid: self.forecast(hid, hours) for hid in HOUSE_PROFILES}

    def get_prediction_metrics(self, house_id: str) -> Dict:
        return {
            "house_id":     house_id,
            "mae_kw":       self.registry.get("val_mae_kw",   0.0),
            "rmse_kw":      self.registry.get("val_rmse_kw",  0.0),
            "mape_pct":     self.registry.get("val_mape_pct", 0.0),
            "model_type":   "XGBoost (unified)" if self._ready else "Statistical",
            "trained_at":   self.registry.get("trained_at", "—"),
            "model_format": "pickle",
        }

    def get_registry_info(self) -> Dict:
        return {
            **self.registry,
            "total_models":  1,
            "models_ready":  self._ready,
        }


forecaster = DemandForecaster()
