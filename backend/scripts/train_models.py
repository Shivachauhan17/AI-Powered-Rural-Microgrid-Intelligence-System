#!/usr/bin/env python3
"""
Train models locally before starting the server.

Usage:
    cd backend
    python scripts/train_models.py
    python scripts/train_models.py --retrain    # force retrain
    python scripts/train_models.py --days 180   # more data

Output:
    app/models/saved_models/unified_demand_model.pkl
    app/models/saved_models/solar_model.pkl
    app/models/saved_models/model_registry.json
"""
import sys, time, argparse, logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrain",     action="store_true")
    parser.add_argument("--days",        type=int, default=120)
    parser.add_argument("--demand-only", action="store_true")
    parser.add_argument("--solar-only",  action="store_true")
    args = parser.parse_args()

    print()
    print("=" * 55)
    print("  AI Microgrid — Model Training")
    print("  Single unified model · Pickle format")
    print("=" * 55)

    try:
        import xgboost, numpy
        print(f"  xgboost {xgboost.__version__}  numpy {numpy.__version__}  ✅")
    except ImportError as e:
        print(f"  ❌ {e}\n  Run: pip install -r requirements.txt")
        sys.exit(1)

    total_start = time.time()

    if not args.solar_only:
        print(f"\n[1/2] Unified demand model (all 13 consumers, {args.days} days)…")
        from app.models.demand_forecaster import forecaster, MODEL_PATH
        print(f"      → {MODEL_PATH}")
        forecaster.train_and_save(n_days=args.days)

    if not args.demand_only:
        print(f"\n[2/2] Solar model…")
        from app.models.solar_forecaster import solar_forecaster, MODEL_PATH as SP
        print(f"      → {SP}")
        solar_forecaster.train_and_save(n_days=args.days)

    from app.models.demand_forecaster import MODEL_DIR
    saved = list(MODEL_DIR.glob("*.pkl"))
    print()
    print("=" * 55)
    print(f"  DONE in {time.time()-total_start:.1f}s")
    print(f"  {len(saved)} model file(s):")
    for f in sorted(saved):
        print(f"    📦 {f.name}  ({f.stat().st_size//1024} KB)")
    print()
    print("  Start server:")
    print("  uvicorn app.main:app --reload --port 8000")
    print()


if __name__ == "__main__":
    main()
