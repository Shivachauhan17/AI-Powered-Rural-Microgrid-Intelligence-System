"""
SageMaker Inference Script — AI Microgrid Unified Model
========================================================
This single file handles:
  1. model_fn()    — load model from /opt/ml/model/ when endpoint starts
  2. input_fn()    — parse incoming JSON request
  3. predict_fn()  — run prediction using the loaded model
  4. output_fn()   — format prediction as JSON response

Deploy this with:
    sagemaker/launch_endpoint.py  (creates a real-time endpoint)
    OR call batch transform jobs for bulk predictions

Request format (JSON):
    {
      "house_id": "clinic",
      "hours": 24,
      "current_hour": 14,
      "day_of_week": 0,
      "month": 3,
      "history": [0.5, 0.6, 0.7, ...]   // at least 48 values (kW readings)
    }

    OR batch (list of the above):
    [
      {"house_id": "clinic",  "hours": 24, ...},
      {"house_id": "house_1", "hours": 24, ...}
    ]

Response format (JSON):
    {
      "house_id": "clinic",
      "predictions_kw": [3.1, 3.2, 3.0, ...],   // 24 values
      "total_daily_kwh": 74.5,
      "peak_hour": 10,
      "peak_kw": 4.2,
      "model_version": "2.0.0"
    }
"""

import os
import io
import json
import pickle
import logging
import numpy as np
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ── SageMaker model directory ──────────────────────────────────────────────
MODEL_DIR = Path(os.environ.get("SM_MODEL_DIR", "/opt/ml/model"))

# ── House configuration (must match training) ──────────────────────────────
HOUSE_PROFILES = {
    "clinic":   {"base": 3.2, "priority": "critical"},
    "school":   {"base": 2.5, "priority": "high"},
    "pump":     {"base": 1.8, "priority": "high"},
    "house_1":  {"base": 0.9, "priority": "normal"},
    "house_2":  {"base": 0.7, "priority": "normal"},
    "house_3":  {"base": 1.1, "priority": "normal"},
    "house_4":  {"base": 0.8, "priority": "normal"},
    "house_5":  {"base": 1.0, "priority": "normal"},
    "house_6":  {"base": 0.6, "priority": "normal"},
    "house_7":  {"base": 0.9, "priority": "normal"},
    "house_8":  {"base": 1.2, "priority": "normal"},
    "house_9":  {"base": 0.8, "priority": "normal"},
    "house_10": {"base": 0.7, "priority": "normal"},
}

# Stable integer encoding — must match what was used during training
HOUSE_ID_ENCODING: Dict[str, int] = {
    hid: idx for idx, hid in enumerate(sorted(HOUSE_PROFILES.keys()))
}


# ── Feature builder (identical to demand_forecaster.py) ────────────────────
def build_features(
    house_id: str,
    hour: int,
    day_of_week: int,
    month: int,
    history: List[float]
) -> np.ndarray:
    house_enc = float(HOUSE_ID_ENCODING.get(house_id, 0))
    base_load = float(HOUSE_PROFILES.get(house_id, {}).get("base", 1.0))

    h_sin = np.sin(2 * np.pi * hour / 24)
    h_cos = np.cos(2 * np.pi * hour / 24)
    d_sin = np.sin(2 * np.pi * day_of_week / 7)
    d_cos = np.cos(2 * np.pi * day_of_week / 7)
    m_sin = np.sin(2 * np.pi * month / 12)
    m_cos = np.cos(2 * np.pi * month / 12)

    n      = len(history)
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


def predict_for_house(
    model,
    house_id: str,
    hours: int,
    current_hour: int,
    day_of_week: int,
    month: int,
    history: List[float]
) -> List[float]:
    """Roll model forward hour by hour for one house."""
    history = list(history)  # copy
    preds   = []

    for step in range(hours):
        h   = (current_hour + step) % 24
        dow = (day_of_week + (current_hour + step) // 24) % 7
        feats = build_features(house_id, h, dow, month, history)
        val   = float(model.predict(feats.reshape(1, -1))[0])
        val   = round(max(0.05, val), 3)
        preds.append(val)
        history.append(val)

    return preds


# ══════════════════════════════════════════════════════════════════════════
#  SageMaker handler functions  (these 4 are called by SageMaker SDK)
# ══════════════════════════════════════════════════════════════════════════

def model_fn(model_dir: str):
    """
    Called once when the SageMaker endpoint starts.
    Loads both models from /opt/ml/model/ into memory.
    Returns a dict holding both loaded models.
    """
    model_dir = Path(model_dir)
    models    = {}

    # Load unified demand model (pickle)
    demand_path = model_dir / "unified_demand_model.pkl"
    if demand_path.exists():
        with open(demand_path, "rb") as f:
            models["demand"] = pickle.load(f)
        logger.info(f"✅ Demand model loaded: {demand_path.name} "
                    f"({demand_path.stat().st_size//1024} KB)")
    else:
        logger.error(f"Demand model not found at {demand_path}")

    # Load solar model (pickle)
    solar_path = model_dir / "solar_model.pkl"
    if solar_path.exists():
        with open(solar_path, "rb") as f:
            models["solar"] = pickle.load(f)
        logger.info(f"✅ Solar model loaded: {solar_path.name}")
    else:
        logger.warning(f"Solar model not found at {solar_path}")

    # Load registry for metadata
    registry_path = model_dir / "model_registry.json"
    if registry_path.exists():
        with open(registry_path) as f:
            models["registry"] = json.load(f)

    if not models.get("demand"):
        raise RuntimeError("Could not load demand model — endpoint cannot serve requests")

    return models


def input_fn(request_body: str, content_type: str = "application/json") -> Any:
    """
    Called for every request. Parses the incoming request body.
    Supports single prediction (dict) or batch (list of dicts).
    """
    if content_type != "application/json":
        raise ValueError(f"Unsupported content type: {content_type}. Use application/json")

    data = json.loads(request_body)
    # Normalise single request into a list for uniform handling
    if isinstance(data, dict):
        data = [data]

    return data


def predict_fn(input_data: List[Dict], models: Dict) -> List[Dict]:
    """
    Called after input_fn. Runs predictions for all requests.
    Returns a list of prediction result dicts.
    """
    demand_model = models.get("demand")
    results      = []

    for req in input_data:
        house_id     = req.get("house_id", "house_1")
        hours        = int(req.get("hours", 24))
        current_hour = int(req.get("current_hour", 12))
        day_of_week  = int(req.get("day_of_week", 0))
        month        = int(req.get("month", 6))
        history      = req.get("history", [])

        # Validate house_id
        if house_id not in HOUSE_PROFILES:
            results.append({
                "error": f"Unknown house_id: {house_id}. "
                         f"Valid options: {list(HOUSE_PROFILES.keys())}"
            })
            continue

        # Need at least 1 history value; pad if short
        if len(history) < 1:
            base = HOUSE_PROFILES[house_id]["base"]
            history = [base] * 48

        # Run prediction
        preds = predict_for_house(
            model=demand_model,
            house_id=house_id,
            hours=hours,
            current_hour=current_hour,
            day_of_week=day_of_week,
            month=month,
            history=history,
        )

        peak_kw   = round(max(preds), 3)
        peak_hour = preds.index(peak_kw)

        results.append({
            "house_id":         house_id,
            "priority":         HOUSE_PROFILES[house_id]["priority"],
            "predictions_kw":   preds,
            "total_daily_kwh":  round(sum(preds), 2),
            "peak_hour":        (current_hour + peak_hour) % 24,
            "peak_kw":          peak_kw,
            "hours_predicted":  hours,
            "model_version":    "2.0.0",
            "model_format":     "pickle",
        })

    return results


def output_fn(prediction: List[Dict], accept: str = "application/json") -> str:
    """
    Called after predict_fn. Formats output as JSON string.
    If only one prediction was requested, unwrap from list.
    """
    if len(prediction) == 1:
        return json.dumps(prediction[0])
    return json.dumps(prediction)


# ── Local test — run this file directly to verify everything works ─────────
if __name__ == "__main__":
    import sys

    print("\nTesting SageMaker inference locally...")

    # Find model files
    local_model_dirs = [
        Path("app/models/saved_models"),          # from backend/
        Path("backend/app/models/saved_models"),  # from project root
        Path("/opt/ml/model"),                    # actual SageMaker path
    ]

    model_dir = None
    for d in local_model_dirs:
        if d.exists() and list(d.glob("*.pkl")):
            model_dir = str(d)
            break

    if not model_dir:
        print("❌ No .pkl model files found. Run: python scripts/train_models.py")
        sys.exit(1)

    print(f"Loading models from: {model_dir}")
    models = model_fn(model_dir)
    print(f"Models loaded: {list(models.keys())}")

    # Test prediction
    test_request = json.dumps({
        "house_id":     "clinic",
        "hours":        24,
        "current_hour": 0,
        "day_of_week":  0,
        "month":        3,
        "history":      [3.0, 3.1, 3.2] * 20,  # 60 history points
    })

    parsed  = input_fn(test_request)
    result  = predict_fn(parsed, models)
    output  = output_fn(result)

    res = json.loads(output)
    print(f"\n✅ Test prediction for clinic:")
    print(f"   Predictions (24h): {res['predictions_kw'][:6]}...")
    print(f"   Total daily kWh  : {res['total_daily_kwh']}")
    print(f"   Peak hour        : {res['peak_hour']}:00 ({res['peak_kw']} kW)")
    print(f"   Model version    : {res['model_version']}")

    # Test batch
    batch_request = json.dumps([
        {"house_id": "clinic",  "hours": 6, "current_hour": 10, "day_of_week": 0, "month": 3},
        {"house_id": "school",  "hours": 6, "current_hour": 10, "day_of_week": 0, "month": 3},
        {"house_id": "house_1", "hours": 6, "current_hour": 10, "day_of_week": 0, "month": 3},
    ])
    parsed = input_fn(batch_request)
    result = predict_fn(parsed, models)
    output = output_fn(result)
    batch  = json.loads(output)
    print(f"\n✅ Batch prediction (3 houses, 6 hours each):")
    for r in batch:
        print(f"   {r['house_id']:<12}: {r['predictions_kw']}")

    print("\nAll tests passed ✅\n")
