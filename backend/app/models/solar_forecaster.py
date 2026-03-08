"""
Solar Generation Forecaster — XGBoost with disk persistence.

Predicts hourly solar output based on:
  - Time of day (cyclic encoding)
  - Month / season
  - Cloud cover estimate
  - Historical generation lags

Saved model: models/saved_models/solar_forecaster.joblib
"""

import os
import json
import time
import logging
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    from xgboost import XGBRegressor
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

try:
    import joblib
    JOBLIB_AVAILABLE = True
except ImportError:
    JOBLIB_AVAILABLE = False

from app.utils.data_generator import generate_solar_forecast

MODEL_DIR  = Path(__file__).parent / "saved_models"
MODEL_PATH = MODEL_DIR / "solar_forecaster.joblib"
META_PATH  = MODEL_DIR / "solar_model_meta.json"

MODEL_DIR.mkdir(parents=True, exist_ok=True)

SOLAR_FEATURE_NAMES = [
    "hour", "hour_sin", "hour_cos",
    "month_sin", "month_cos",
    "cloud_cover",
    "is_peak_solar",    # 10am – 3pm
    "lag_1h", "lag_24h",
    "rolling_mean_3h",
]


def _solar_features(hour: int, month: int, cloud_cover: float, history: List[float]) -> np.ndarray:
    h_sin = np.sin(2 * np.pi * hour / 24)
    h_cos = np.cos(2 * np.pi * hour / 24)
    m_sin = np.sin(2 * np.pi * month / 12)
    m_cos = np.cos(2 * np.pi * month / 12)

    is_peak   = 1.0 if 10 <= hour <= 15 else 0.0
    lag_1     = history[-1]  if len(history) >= 1  else 0.0
    lag_24    = history[-24] if len(history) >= 24 else lag_1
    roll_mean = float(np.mean(history[-3:])) if len(history) >= 3 else lag_1

    return np.array([
        hour, h_sin, h_cos,
        m_sin, m_cos,
        cloud_cover,
        is_peak,
        lag_1, lag_24, roll_mean,
    ], dtype=np.float32)


def _generate_solar_training_data(n_days: int = 120, capacity_kw: float = 30.0):
    X_rows, y_vals = [], []
    history_buffer: List[float] = []

    for day in range(n_days):
        cloud  = np.random.uniform(0.05, 0.60)
        month  = ((day // 30) % 12) + 1
        hourly = generate_solar_forecast(capacity_kw, cloud_cover=cloud)

        for h, gen in enumerate(hourly):
            if len(history_buffer) > 0:
                feats = _solar_features(h, month, cloud, history_buffer)
                X_rows.append(feats)
                y_vals.append(gen)
            history_buffer.append(gen)

    return np.array(X_rows, dtype=np.float32), np.array(y_vals, dtype=np.float32)


class SolarForecaster:
    """XGBoost solar generation forecaster with joblib persistence."""

    def __init__(self):
        self.model = None
        self._ready = False
        self.meta: Dict = {}

    def load_or_train(self, force_retrain: bool = False):
        if not XGBOOST_AVAILABLE or not JOBLIB_AVAILABLE:
            logger.warning("XGBoost/joblib missing — using statistical solar forecast.")
            return

        if not force_retrain and MODEL_PATH.exists():
            self._load_from_disk()
        else:
            logger.info("Training solar forecasting model...")
            self.train_and_save()

    def train_and_save(self, n_days: int = 120, capacity_kw: float = 30.0):
        if not XGBOOST_AVAILABLE or not JOBLIB_AVAILABLE:
            return

        t0 = time.time()
        X, y = _generate_solar_training_data(n_days, capacity_kw)

        split = int(len(X) * 0.85)
        X_train, X_val = X[:split], X[split:]
        y_train, y_val = y[:split], y[split:]

        model = XGBRegressor(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.08,
            subsample=0.85,
            colsample_bytree=0.8,
            random_state=42,
            verbosity=0,
            n_jobs=-1,
        )
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

        y_pred = np.maximum(0, model.predict(X_val))
        mae  = float(np.mean(np.abs(y_val - y_pred)))
        rmse = float(np.sqrt(np.mean((y_val - y_pred) ** 2)))

        joblib.dump(model, MODEL_PATH, compress=3)

        self.meta = {
            "trained_at":    datetime.now().isoformat(),
            "n_train_days":  n_days,
            "capacity_kw":   capacity_kw,
            "n_features":    X.shape[1],
            "feature_names": SOLAR_FEATURE_NAMES,
            "val_mae_kw":    round(mae, 4),
            "val_rmse_kw":   round(rmse, 4),
            "train_time_s":  round(time.time() - t0, 2),
        }
        with open(META_PATH, "w") as f:
            json.dump(self.meta, f, indent=2)

        self.model  = model
        self._ready = True
        logger.info(f"  ✅ Solar model: MAE={mae:.4f} kW | RMSE={rmse:.4f} kW | {self.meta['train_time_s']}s")

    def _load_from_disk(self):
        try:
            self.model  = joblib.load(MODEL_PATH)
            self._ready = True
            if META_PATH.exists():
                with open(META_PATH) as f:
                    self.meta = json.load(f)
            logger.info("Solar forecaster loaded from disk.")
        except Exception as e:
            logger.error(f"Failed to load solar model: {e}")

    def forecast(self, capacity_kw: float = 30.0, cloud_cover: Optional[float] = None) -> List[float]:
        if cloud_cover is None:
            cloud_cover = np.random.uniform(0.05, 0.40)

        if not self._ready:
            return generate_solar_forecast(capacity_kw, cloud_cover)

        now     = datetime.now()
        history: List[float] = generate_solar_forecast(capacity_kw, cloud_cover=0.2)  # seed history

        preds = []
        for step in range(24):
            hour  = (now.hour + step) % 24
            feats = _solar_features(hour, now.month, cloud_cover, history)
            val   = float(self.model.predict(feats.reshape(1, -1))[0])
            val   = round(max(0.0, val), 3)
            preds.append(val)
            history.append(val)

        return preds

    def get_meta(self) -> Dict:
        return {
            "model_ready":  self._ready,
            "model_path":   str(MODEL_PATH),
            **self.meta
        }


solar_forecaster = SolarForecaster()
