"""
AI-Powered Rural Microgrid Intelligence System
FastAPI Backend
Team: Data Mavericks | Leader: Shiva Chauhan
"""
import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.api.v1 import forecast, optimize, dashboard, alerts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("microgrid")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🌞 AI Microgrid starting up…")
    logger.info(f"Solar: {settings.SOLAR_CAPACITY_KW} kW | Battery: {settings.BATTERY_CAPACITY_KWH} kWh")

    # ── Step 1: Try to pull latest models from S3 (production) ────────────
    if settings.MODEL_S3_BUCKET:
        try:
            import boto3
            import pickle
            from pathlib import Path
            s3        = boto3.client("s3")
            model_dir = Path("app/models/saved_models")
            model_dir.mkdir(parents=True, exist_ok=True)
            prefix    = settings.MODEL_S3_PREFIX

            for key in ["unified_demand_model.pkl", "solar_model.pkl", "model_registry.json"]:
                try:
                    s3.download_file(settings.MODEL_S3_BUCKET, f"{prefix}{key}", str(model_dir / key))
                    logger.info(f"  ⬇ Downloaded {key} from S3")
                except Exception:
                    pass  # will train locally if not found
        except Exception as e:
            logger.warning(f"S3 download skipped: {e}")

    # ── Step 2: Load models into RAM ──────────────────────────────────────
    try:
        from app.models.demand_forecaster import forecaster
        from app.models.solar_forecaster  import solar_forecaster

        forecaster.load_or_train()
        solar_forecaster.load_or_train()

        info = forecaster.get_registry_info()
        logger.info(
            f"✅ Demand model ready: {info.get('models_ready')} | "
            f"Solar model ready: {solar_forecaster._ready} | "
            f"Trained: {info.get('trained_at', '—')}"
        )
    except Exception as e:
        logger.error(f"Model load failed: {e} — using statistical fallback")

    yield
    logger.info("🔌 Microgrid shutting down…")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered energy management for rural microgrids. Team: Data Mavericks.",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    t = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{time.time() - t:.4f}s"
    return response


app.include_router(forecast.router,  prefix=settings.API_V1_STR)
app.include_router(optimize.router,  prefix=settings.API_V1_STR)
app.include_router(dashboard.router, prefix=settings.API_V1_STR)
app.include_router(alerts.router,    prefix=settings.API_V1_STR)


@app.get("/", tags=["System"])
async def root():
    return {"system": settings.APP_NAME, "version": settings.APP_VERSION,
            "docs": "/docs", "health": "/health"}


@app.get("/health", tags=["System"])
async def health():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "solar_capacity_kw": settings.SOLAR_CAPACITY_KW,
        "battery_capacity_kwh": settings.BATTERY_CAPACITY_KWH,
    }


@app.exception_handler(Exception)
async def global_error(request: Request, exc: Exception):
    logger.error(f"Unhandled: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
