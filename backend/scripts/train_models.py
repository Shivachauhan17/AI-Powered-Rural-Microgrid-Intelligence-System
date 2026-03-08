#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║        AI Microgrid — Model Training Script                  ║
║        Team: Data Mavericks | Shiva Chauhan                  ║
╠══════════════════════════════════════════════════════════════╣
║  Run this ONCE before starting the server for the first time ║
║  or whenever you want to retrain on new data.                ║
║                                                              ║
║  Usage:                                                      ║
║    cd backend                                                ║
║    python scripts/train_models.py                            ║
║    python scripts/train_models.py --retrain   (force)        ║
║    python scripts/train_models.py --days 180  (more data)    ║
╚══════════════════════════════════════════════════════════════╝
"""

import sys
import time
import argparse
import logging
from pathlib import Path

# Add parent dir to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("train")


def main():
    parser = argparse.ArgumentParser(description="Train and save AI Microgrid forecasting models")
    parser.add_argument("--retrain",  action="store_true", help="Force retrain even if models exist")
    parser.add_argument("--days",     type=int, default=120, help="Training days (default: 120)")
    parser.add_argument("--demand-only", action="store_true", help="Only train demand models")
    parser.add_argument("--solar-only",  action="store_true", help="Only train solar model")
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  AI Rural Microgrid — Model Training")
    print("  Team: Data Mavericks | Shiva Chauhan")
    print("=" * 60)
    print()

    # Check dependencies
    try:
        import xgboost
        import joblib
        import numpy
        print(f"  ✅ xgboost  {xgboost.__version__}")
        print(f"  ✅ joblib   {joblib.__version__}")
        print(f"  ✅ numpy    {numpy.__version__}")
    except ImportError as e:
        print(f"\n  ❌ Missing dependency: {e}")
        print("  Run: pip install xgboost joblib numpy scikit-learn\n")
        sys.exit(1)

    print()
    total_start = time.time()

    # ── Train Demand Forecasters ─────────────────────────────────────────
    if not args.solar_only:
        print(f"[1/2] Training Demand Forecasting Models ({args.days} days each)")
        print(f"      One XGBoost model per consumer (13 total)")
        print()

        from app.models.demand_forecaster import forecaster, HOUSE_PROFILES, MODEL_DIR

        print(f"      Models will be saved to: {MODEL_DIR}/")
        print()

        forecaster.train_and_save(
            house_ids=list(HOUSE_PROFILES.keys()),
            n_days=args.days
        )
        print()

    # ── Train Solar Forecaster ───────────────────────────────────────────
    if not args.demand_only:
        print(f"[2/2] Training Solar Generation Forecasting Model")
        print(f"      XGBoost model with weather/cloud features")
        print()

        from app.models.solar_forecaster import solar_forecaster

        solar_forecaster.train_and_save(n_days=args.days, capacity_kw=30.0)
        print()

    # ── Summary ──────────────────────────────────────────────────────────
    elapsed = time.time() - total_start

    from app.models.demand_forecaster import MODEL_DIR as MD
    saved_files = list(MD.glob("*.joblib"))

    print("=" * 60)
    print("  TRAINING COMPLETE")
    print("=" * 60)
    print(f"  Total time    : {elapsed:.1f}s")
    print(f"  Models saved  : {len(saved_files)} files in {MD}/")
    print()

    for f in sorted(saved_files):
        size_kb = f.stat().st_size / 1024
        print(f"    📦 {f.name:<35} {size_kb:.1f} KB")

    print()
    print("  Next step: Start the server")
    print("  cd backend && uvicorn app.main:app --reload --port 8000")
    print()

    # Show registry
    try:
        import json
        registry_path = MD / "model_registry.json"
        if registry_path.exists():
            with open(registry_path) as f:
                reg = json.load(f)
            print(f"  Registry: {registry_path}")
            print(f"  Trained at: {reg.get('trained_at', '—')}")
            print()
    except Exception:
        pass


if __name__ == "__main__":
    main()
