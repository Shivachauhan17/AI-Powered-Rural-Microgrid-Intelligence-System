from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict
from datetime import datetime

from app.models.demand_forecaster import forecaster
from app.models.solar_forecaster import solar_forecaster
from app.utils.data_generator import HOUSE_PROFILES
from app.schemas.schemas import HourlyForecast, SolarForecast, ModelMetrics

router = APIRouter(prefix="/forecast", tags=["Forecasting"])


@router.get("/demand", response_model=List[HourlyForecast], summary="Get demand forecast for all houses")
async def get_all_demand_forecasts(hours: int = Query(24, ge=1, le=48)):
    """
    Returns next N-hour electricity demand forecast for every consumer (houses, clinic, school, pump).
    Uses XGBoost model trained on historical consumption patterns.
    """
    all_forecasts = forecaster.forecast_all_houses(hours)
    result = []
    
    for house_id, demand_list in all_forecasts.items():
        profile = HOUSE_PROFILES.get(house_id, {})
        peak_hour = int(demand_list.index(max(demand_list)))
        result.append(HourlyForecast(
            house_id=house_id,
            demand_kwh=demand_list,
            total_daily_kwh=round(sum(demand_list), 2),
            peak_hour=peak_hour,
            peak_demand_kw=round(max(demand_list), 3),
            priority=profile.get("priority", "normal")
        ))
    
    return sorted(result, key=lambda x: {"critical": 0, "high": 1, "normal": 2}[x.priority])


@router.get("/demand/{house_id}", response_model=HourlyForecast, summary="Get demand forecast for a specific house")
async def get_house_demand_forecast(house_id: str, hours: int = Query(24, ge=1, le=48)):
    """Returns next N-hour demand forecast for a specific consumer."""
    if house_id not in HOUSE_PROFILES:
        raise HTTPException(status_code=404, detail=f"House '{house_id}' not found. Valid IDs: {list(HOUSE_PROFILES.keys())}")
    
    demand_list = forecaster.forecast(house_id, hours)
    profile = HOUSE_PROFILES[house_id]
    peak_hour = int(demand_list.index(max(demand_list)))
    
    return HourlyForecast(
        house_id=house_id,
        demand_kwh=demand_list,
        total_daily_kwh=round(sum(demand_list), 2),
        peak_hour=peak_hour,
        peak_demand_kw=round(max(demand_list), 3),
        priority=profile.get("priority", "normal")
    )


@router.get("/solar", response_model=SolarForecast, summary="Get solar generation forecast")
async def get_solar_forecast(
    capacity_kw: float = Query(30.0, description="Solar panel capacity in kW"),
    cloud_cover: float = Query(None, ge=0, le=1, description="Cloud cover fraction (0-1)")
):
    """
    Predicts next 24h solar energy generation.
    Uses trained XGBoost model (loaded from saved_models/solar_forecaster.joblib).
    Falls back to statistical curve if model not loaded.
    """
    hourly = solar_forecaster.forecast(capacity_kw=capacity_kw, cloud_cover=cloud_cover)
    peak_hour = int(hourly.index(max(hourly))) if max(hourly) > 0 else 13
    meta = solar_forecaster.get_meta()
    cloud = cloud_cover if cloud_cover is not None else 0.2

    return SolarForecast(
        hourly_generation_kw=hourly,
        total_daily_kwh=round(sum(hourly), 2),
        peak_generation_kw=round(max(hourly), 2),
        peak_hour=peak_hour,
        cloud_cover_estimate=round(cloud, 2)
    )


@router.get("/solar/model-info", summary="Get solar model metadata")
async def get_solar_model_info():
    """Returns metadata about the trained solar forecasting model."""
    return solar_forecaster.get_meta()


@router.get("/metrics", summary="Get model accuracy metrics")
async def get_model_metrics():
    """
    Returns MAE, RMSE, MAPE for each household's forecasting model.
    Metrics are from validation set computed at training time
    (not re-computed on every request).
    """
    metrics = []
    for house_id in HOUSE_PROFILES.keys():
        m = forecaster.get_prediction_metrics(house_id)
        metrics.append(m)
    return metrics


@router.get("/models/info", summary="Get model registry — all trained models info")
async def get_models_info():
    """
    Returns full model registry: which models exist, when they were trained,
    file paths, validation metrics, and feature names.
    """
    return {
        "demand_models": forecaster.get_registry_info(),
        "solar_model":   solar_forecaster.get_meta(),
    }
