"""
XGBoost Demand Forecaster — with full model persistence.

Flow:
  1. On startup → try to load saved models from disk (models/saved_models/)
  2. If no saved models exist → train fresh and save to disk
  3. Models survive server restarts (loaded in < 1s instead of re-training)
  4. Run scripts/train_models.py to force retrain and save new models
  5. Model metadata (training date, metrics, version) stored in model_registry.json
"""

import os
import json
import time
import logging
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Optional dependencies ──────────────────────────────────────────────────
try:
    from xgboost import XGBRegressor
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    logger.warning("XGBoost not installed. Run: pip install xgboost")

try:
    import joblib
    JOBLIB_AVAILABLE = True
except ImportError:
    JOBLIB_AVAILABLE = False
    logger.warning("joblib not installed. Run: pip install joblib")

from app.utils.data_generator import generate_demand_forecast, HOUSE_PROFILES

# ── Paths ──────────────────────────────────────────────────────────────────
MODEL_DIR = Path(__file__).parent / "saved_models"
REGISTRY_PATH = MODEL_DIR / "model_registry.json"
MODEL_VERSION = "1.0.0"

MODEL_DIR.mkdir(parents=True, exist_ok=True)

# ── Feature Engineering ────────────────────────────────────────────────────
FEATURE_NAMES = [
    "hour", "hour_sin", "hour_cos",
    "day_of_week", "dow_sin", "dow_cos",
    "month_sin", "month_cos",
    "lag_1h", "lag_24h", "lag_48h",
    "rolling_mean_6h", "rolling_std_6h",
    "rolling_mean_12h",
    "is_daytime",        # 1 if 6 <= hour <= 22
    "is_morning_peak",   # 1 if 6 <= hour <= 9
    "is_evening_peak",   # 1 if 17 <= hour <= 22
    "is_weekend",        # 1 if day_of_week >= 5
]

def build_features(hour: int, day_of_week: int, month: int, history: List[float]) -> np.ndarray:
    """
    Build a rich feature vector for one prediction step.
    Adds cyclic encodings, lag features, rolling stats, and domain flags.
    """
    h_sin = np.sin(2 * np.pi * hour / 24)
    h_cos = np.cos(2 * np.pi * hour / 24)
    d_sin = np.sin(2 * np.pi * day_of_week / 7)
    d_cos = np.cos(2 * np.pi * day_of_week / 7)
    m_sin = np.sin(2 * np.pi * month / 12)
    m_cos = np.cos(2 * np.pi * month / 12)

    n = len(history)
    lag_1  = history[-1]  if n >= 1  else 0.5
    lag_24 = history[-24] if n >= 24 else lag_1
    lag_48 = history[-48] if n >= 48 else lag_24

    window_6  = history[-6:]  if n >= 6  else history
    window_12 = history[-12:] if n >= 12 else history

    roll_mean_6  = float(np.mean(window_6))
    roll_std_6   = float(np.std(window_6))
    roll_mean_12 = float(np.mean(window_12))

    is_daytime      = 1.0 if 6 <= hour <= 22 else 0.0
    is_morning_peak = 1.0 if 6 <= hour <= 9  else 0.0
    is_evening_peak = 1.0 if 17 <= hour <= 22 else 0.0
    is_weekend      = 1.0 if day_of_week >= 5 else 0.0

    return np.array([
        hour, h_sin, h_cos,
        day_of_week, d_sin, d_cos,
        m_sin, m_cos,
        lag_1, lag_24, lag_48,
        roll_mean_6, roll_std_6, roll_mean_12,
        is_daytime, is_morning_peak, is_evening_peak, is_weekend,
    ], dtype=np.float32)


def generate_training_data(house_id: str, n_days: int = 120) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate n_days of synthetic training data for a house.
    In production: replace with real CSV/DB query from smart meters.
    """
    X_rows, y_vals = [], []
    # Build a rolling history buffer spanning multiple days
    history_buffer: List[float] = []

    for day in range(n_days):
        dow   = day % 7
        month = ((day // 30) % 12) + 1
        daily = generate_demand_forecast(house_id, hours=24, noise_factor=0.10)

        for h, demand in enumerate(daily):
            if len(history_buffer) > 0:
                feats = build_features(h, dow, month, history_buffer)
                X_rows.append(feats)
                y_vals.append(demand)
            history_buffer.append(demand)

    return np.array(X_rows, dtype=np.float32), np.array(y_vals, dtype=np.float32)


# ── Registry helpers ───────────────────────────────────────────────────────
def _load_registry() -> Dict:
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH) as f:
            return json.load(f)
    return {"version": MODEL_VERSION, "models": {}, "trained_at": None}


def _save_registry(registry: Dict):
    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2, default=str)


def _model_path(house_id: str) -> Path:
    return MODEL_DIR / f"{house_id}.joblib"


# ── Core class ─────────────────────────────────────────────────────────────
class DemandForecaster:
    """
    XGBoost demand forecaster with full disk persistence.

    Startup sequence:
      load_or_train() → tries to load from disk first, trains if missing.
    """

    def __init__(self):
        self.models: Dict[str, "XGBRegressor"] = {}
        self.registry: Dict = _load_registry()
        self._ready = False

    # ── Public API ────────────────────────────────────────────────────────

    def load_or_train(self, force_retrain: bool = False):
        """
        Load models from disk if they exist, otherwise train and save.
        Called once at server startup (from main.py lifespan).
        """
        if not XGBOOST_AVAILABLE or not JOBLIB_AVAILABLE:
            logger.warning("XGBoost or joblib missing — using statistical fallback for forecasting.")
            self._ready = False
            return

        missing = [hid for hid in HOUSE_PROFILES if not _model_path(hid).exists()]

        if force_retrain or missing:
            if force_retrain:
                logger.info("Force retrain requested. Training all models from scratch...")
            else:
                logger.info(f"Models missing for: {missing}. Training now...")
            self.train_and_save(house_ids=list(HOUSE_PROFILES.keys()) if force_retrain else missing)

        # Load all models from disk
        self._load_from_disk()

    def train_and_save(self, house_ids: Optional[List[str]] = None, n_days: int = 120):
        """
        Train XGBoost models for given house IDs and save to disk.
        Can be called from the training script or via API trigger.
        """
        if not XGBOOST_AVAILABLE or not JOBLIB_AVAILABLE:
            logger.error("Cannot train: xgboost or joblib not installed.")
            return

        house_ids = house_ids or list(HOUSE_PROFILES.keys())
        registry = _load_registry()
        registry["version"] = MODEL_VERSION
        registry["trained_at"] = datetime.now().isoformat()

        for house_id in house_ids:
            logger.info(f"  Training model for: {house_id} ({n_days} days data)...")
            t0 = time.time()

            X, y = generate_training_data(house_id, n_days=n_days)

            # Train/test split for metrics
            split = int(len(X) * 0.85)
            X_train, X_val = X[:split], X[split:]
            y_train, y_val = y[:split], y[split:]

            model = XGBRegressor(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.08,
                subsample=0.85,
                colsample_bytree=0.8,
                min_child_weight=3,
                reg_alpha=0.1,
                reg_lambda=1.0,
                random_state=42,
                verbosity=0,
                n_jobs=-1,
            )
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                verbose=False,
            )

            # Compute validation metrics
            y_pred = model.predict(X_val)
            mae  = float(np.mean(np.abs(y_val - y_pred)))
            rmse = float(np.sqrt(np.mean((y_val - y_pred) ** 2)))
            mape = float(np.mean(np.abs((y_val - y_pred) / np.maximum(y_val, 0.01))) * 100)

            # Save model to disk
            save_path = _model_path(house_id)
            joblib.dump(model, save_path, compress=3)

            elapsed = time.time() - t0
            registry["models"][house_id] = {
                "path":         str(save_path),
                "trained_at":   datetime.now().isoformat(),
                "n_train_days": n_days,
                "n_features":   X.shape[1],
                "feature_names": FEATURE_NAMES,
                "val_mae_kw":   round(mae, 4),
                "val_rmse_kw":  round(rmse, 4),
                "val_mape_pct": round(mape, 2),
                "train_time_s": round(elapsed, 2),
                "model_version": MODEL_VERSION,
            }
            logger.info(f"    ✅ {house_id}: MAE={mae:.4f} kW | RMSE={rmse:.4f} kW | MAPE={mape:.2f}% | {elapsed:.1f}s")

        _save_registry(registry)
        self.registry = registry
        logger.info(f"All models saved to {MODEL_DIR}/")

    def _load_from_disk(self):
        """Load all saved .joblib model files into memory."""
        loaded = 0
        for house_id in HOUSE_PROFILES:
            path = _model_path(house_id)
            if path.exists():
                try:
                    self.models[house_id] = joblib.load(path)
                    loaded += 1
                except Exception as e:
                    logger.error(f"Failed to load model for {house_id}: {e}")
            else:
                logger.warning(f"No saved model found for {house_id}")

        self._ready = loaded > 0
        logger.info(f"Loaded {loaded}/{len(HOUSE_PROFILES)} models from disk.")

    # ── Forecasting ───────────────────────────────────────────────────────

    def forecast(self, house_id: str, hours: int = 24) -> List[float]:
        """Return next `hours` demand predictions for a house."""
        if self._ready and house_id in self.models:
            return self._ml_forecast(house_id, hours)
        logger.warning(f"No trained model for {house_id}, using statistical fallback.")
        return generate_demand_forecast(house_id, hours)

    def _ml_forecast(self, house_id: str, hours: int) -> List[float]:
        """Roll the trained XGBoost model forward hour by hour."""
        model = self.models[house_id]
        now = datetime.now()

        # Seed history with past 48h of simulated readings
        history: List[float] = generate_demand_forecast(house_id, hours=48, noise_factor=0.04)

        preds = []
        for step in range(hours):
            hour = (now.hour + step) % 24
            day_of_week = (now.weekday() + (now.hour + step) // 24) % 7
            feats = build_features(hour, day_of_week, now.month, history)
            val = float(model.predict(feats.reshape(1, -1))[0])
            val = round(max(0.05, val), 3)
            preds.append(val)
            history.append(val)

        return preds

    def forecast_all_houses(self, hours: int = 24) -> Dict[str, List[float]]:
        return {hid: self.forecast(hid, hours) for hid in HOUSE_PROFILES}

    # ── Metrics ───────────────────────────────────────────────────────────

    def get_prediction_metrics(self, house_id: str) -> Dict:
        """
        Return validation metrics stored at training time.
        Falls back to computing live metrics if registry entry missing.
        """
        # Prefer stored metrics from training (more reliable than live estimate)
        stored = self.registry.get("models", {}).get(house_id)
        if stored:
            return {
                "house_id":    house_id,
                "mae_kw":      stored.get("val_mae_kw", 0.0),
                "rmse_kw":     stored.get("val_rmse_kw", 0.0),
                "mape_pct":    stored.get("val_mape_pct", 0.0),
                "model_type":  "XGBoost" if self._ready else "Statistical",
                "trained_at":  stored.get("trained_at", "—"),
                "n_train_days": stored.get("n_train_days", 0),
            }

        # Live fallback
        actual    = np.array(generate_demand_forecast(house_id, hours=24, noise_factor=0.0))
        predicted = np.array(self.forecast(house_id, hours=24))
        return {
            "house_id":    house_id,
            "mae_kw":      round(float(np.mean(np.abs(actual - predicted))), 4),
            "rmse_kw":     round(float(np.sqrt(np.mean((actual - predicted) ** 2))), 4),
            "mape_pct":    round(float(np.mean(np.abs((actual - predicted) / np.maximum(actual, 0.01))) * 100), 2),
            "model_type":  "XGBoost" if self._ready else "Statistical",
            "trained_at":  "—",
            "n_train_days": 0,
        }

    def get_registry_info(self) -> Dict:
        """Return full model registry (for /models/info endpoint)."""
        return {
            "model_dir":   str(MODEL_DIR),
            "version":     self.registry.get("version", MODEL_VERSION),
            "trained_at":  self.registry.get("trained_at"),
            "total_models": len(self.models),
            "models_ready": self._ready,
            "models":      self.registry.get("models", {}),
        }


# ── Singleton (lazy-initialized in main.py lifespan) ──────────────────────
forecaster = DemandForecaster()
