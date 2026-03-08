"""
Solar Generation Forecaster — XGBoost, pickle persistence.
File: app/models/saved_models/solar_model.pkl
"""
import json
import pickle
import logging
import time
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

from app.utils.data_generator import generate_solar_forecast

MODEL_DIR  = Path(__file__).parent / "saved_models"
MODEL_PATH = MODEL_DIR / "solar_model.pkl"
META_PATH  = MODEL_DIR / "solar_model_meta.json"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

FEATURE_NAMES = [
    "hour", "hour_sin", "hour_cos",
    "month_sin", "month_cos",
    "cloud_cover", "is_peak_solar",
    "lag_1h", "lag_24h", "rolling_mean_3h",
]


def _feats(hour: int, month: int, cloud: float, history: List[float]) -> np.ndarray:
    h_sin = np.sin(2 * np.pi * hour / 24);  h_cos = np.cos(2 * np.pi * hour / 24)
    m_sin = np.sin(2 * np.pi * month / 12); m_cos = np.cos(2 * np.pi * month / 12)
    l1   = history[-1]  if len(history) >= 1  else 0.0
    l24  = history[-24] if len(history) >= 24 else l1
    rm3  = float(np.mean(history[-3:])) if len(history) >= 3 else l1
    return np.array([
        hour, h_sin, h_cos, m_sin, m_cos, cloud,
        1.0 if 10 <= hour <= 15 else 0.0,
        l1, l24, rm3,
    ], dtype=np.float32)


def _training_data(n_days: int = 120, capacity_kw: float = 30.0):
    X_all, y_all, hist = [], [], []
    for day in range(n_days):
        cloud  = np.random.uniform(0.05, 0.60)
        month  = ((day // 30) % 12) + 1
        hourly = generate_solar_forecast(capacity_kw, cloud_cover=cloud)
        for h, gen in enumerate(hourly):
            if hist:
                X_all.append(_feats(h, month, cloud, hist))
                y_all.append(gen)
            hist.append(gen)
    return np.array(X_all, dtype=np.float32), np.array(y_all, dtype=np.float32)


class SolarForecaster:
    def __init__(self):
        self.model  = None
        self._ready = False
        self.meta: Dict = {}

    def load_or_train(self, force: bool = False):
        if not XGBOOST_AVAILABLE:
            return
        if not force and MODEL_PATH.exists():
            self._load()
        else:
            logger.info("Training solar model…")
            self.train_and_save()

    def train_and_save(self, n_days: int = 120, capacity_kw: float = 30.0):
        if not XGBOOST_AVAILABLE:
            return
        t0   = time.time()
        X, y = _training_data(n_days, capacity_kw)
        sp   = int(len(X) * 0.85)

        model = XGBRegressor(
            n_estimators=200, max_depth=5, learning_rate=0.08,
            subsample=0.85, colsample_bytree=0.8,
            random_state=42, verbosity=0, n_jobs=-1,
        )
        model.fit(X[:sp], y[:sp], eval_set=[(X[sp:], y[sp:])], verbose=False)

        yp   = np.maximum(0, model.predict(X[sp:]))
        mae  = float(np.mean(np.abs(y[sp:] - yp)))
        rmse = float(np.sqrt(np.mean((y[sp:] - yp) ** 2)))

        with open(MODEL_PATH, "wb") as f:
            pickle.dump(model, f, protocol=pickle.HIGHEST_PROTOCOL)

        self.meta = {
            "model_file":    MODEL_PATH.name,
            "model_format":  "pickle",
            "trained_at":    datetime.now().isoformat(),
            "n_features":    X.shape[1],
            "feature_names": FEATURE_NAMES,
            "val_mae_kw":    round(mae, 4),
            "val_rmse_kw":   round(rmse, 4),
            "train_time_s":  round(time.time() - t0, 2),
        }
        with open(META_PATH, "w") as f:
            json.dump(self.meta, f, indent=2)

        self.model  = model
        self._ready = True
        logger.info(f"✅ solar_model.pkl saved | MAE={mae:.4f} | RMSE={rmse:.4f}")

    def _load(self):
        try:
            with open(MODEL_PATH, "rb") as f:
                self.model = pickle.load(f)
            if META_PATH.exists():
                with open(META_PATH) as f:
                    self.meta = json.load(f)
            self._ready = True
            logger.info("Solar model loaded from disk.")
        except Exception as e:
            logger.error(f"Failed to load solar model: {e}")

    def forecast(self, capacity_kw: float = 30.0, cloud_cover: Optional[float] = None) -> List[float]:
        if cloud_cover is None:
            cloud_cover = np.random.uniform(0.05, 0.40)
        if not self._ready:
            return generate_solar_forecast(capacity_kw, cloud_cover)
        now  = datetime.now()
        hist = generate_solar_forecast(capacity_kw, cloud_cover=0.2)
        preds = []
        for step in range(24):
            h   = (now.hour + step) % 24
            row = _feats(h, now.month, cloud_cover, hist)
            val = float(self.model.predict(row.reshape(1, -1))[0])
            val = round(max(0.0, val), 3)
            preds.append(val)
            hist.append(val)
        return preds

    def get_meta(self) -> Dict:
        return {"model_ready": self._ready, "model_path": str(MODEL_PATH), **self.meta}


solar_forecaster = SolarForecaster()
