"""
AI-Powered Rural Microgrid Intelligence System
FastAPI Backend - Production Ready
Team: Data Mavericks | Leader: Shiva Chauhan
"""
import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app, Counter, Histogram

from app.config import settings
from app.api.v1 import forecast, optimize, dashboard, alerts

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("microgrid")

# --- Prometheus Metrics ---
REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "Request latency", ["endpoint"])


# --- App Lifecycle ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🌞 AI Microgrid System starting up...")
    logger.info(f"Solar capacity: {settings.SOLAR_CAPACITY_KW} kW | Battery: {settings.BATTERY_CAPACITY_KWH} kWh")

    # ── Load ML models from disk ──────────────────────────────────────────
    # Models are trained once via: python scripts/train_models.py
    # On each server start we just load the saved .joblib files (< 1 second)
    # If models are missing they are trained now automatically (takes ~60s)
    try:
        from app.models.demand_forecaster import forecaster
        from app.models.solar_forecaster import solar_forecaster

        logger.info("Loading demand forecasting models from disk...")
        forecaster.load_or_train()          # loads saved_models/*.joblib

        logger.info("Loading solar forecasting model from disk...")
        solar_forecaster.load_or_train()    # loads saved_models/solar_forecaster.joblib

        registry = forecaster.get_registry_info()
        logger.info(f"✅ {registry['total_models']} demand models ready | "
                    f"Solar model ready: {solar_forecaster._ready} | "
                    f"Trained at: {registry.get('trained_at', 'unknown')}")
    except Exception as e:
        logger.error(f"Model loading failed: {e}. API will use statistical fallback.")

    yield
    logger.info("🔌 AI Microgrid System shutting down...")


# --- FastAPI App ---
app = FastAPI(
    title=settings.APP_NAME,
    description="""
## AI-Powered Rural Microgrid Intelligence System

**Team Data Mavericks** | Shiva Chauhan

### What this system does:
- 📊 **Demand Forecasting**: XGBoost model predicts hourly demand per household
- ☀️ **Solar Prediction**: Weather-aware solar generation forecasting  
- ⚡ **Smart Optimization**: LP-based fair energy allocation (PuLP)
- 🔋 **Battery Management**: Intelligent charge/discharge scheduling
- 📱 **SMS Alerts**: Operator notifications in local languages
- 📡 **Real-time WebSocket**: Live energy monitoring dashboard

### Priority System:
🏥 Clinic (Critical) > 🏫 School (High) > 💧 Water Pump (High) > 🏠 Households (Normal)
    """,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Request Timing Middleware ---
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    response.headers["X-Process-Time"] = f"{duration:.4f}s"
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    return response

# --- Prometheus Metrics Endpoint ---
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# --- API Routes ---
app.include_router(forecast.router, prefix=settings.API_V1_STR)
app.include_router(optimize.router, prefix=settings.API_V1_STR)
app.include_router(dashboard.router, prefix=settings.API_V1_STR)
app.include_router(alerts.router, prefix=settings.API_V1_STR)


# --- Root & Health ---
@app.get("/", tags=["System"])
async def root():
    return {
        "system": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "operational",
        "team": "Data Mavericks",
        "docs": "/docs",
        "api": settings.API_V1_STR,
    }


@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint for AWS ALB / ECS."""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "solar_capacity_kw": settings.SOLAR_CAPACITY_KW,
        "battery_capacity_kwh": settings.BATTERY_CAPACITY_KWH,
        "total_consumers": settings.TOTAL_HOUSES + 3,  # houses + clinic + school + pump
    }


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Check server logs."}
    )
