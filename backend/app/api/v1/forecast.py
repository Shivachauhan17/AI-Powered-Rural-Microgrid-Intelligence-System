from fastapi import APIRouter, HTTPException, Query
from typing import List
from app.models.demand_forecaster import forecaster
from app.models.solar_forecaster  import solar_forecaster
from app.utils.data_generator     import HOUSE_PROFILES
from app.schemas.schemas          import HourlyForecast, SolarForecast

router = APIRouter(prefix="/forecast", tags=["Forecasting"])


@router.get("/demand", response_model=List[HourlyForecast])
async def get_all_demand(hours: int = Query(24, ge=1, le=48)):
    """Demand forecast for every consumer using the unified XGBoost model."""
    result = []
    for house_id, preds in forecaster.forecast_all_houses(hours).items():
        profile = HOUSE_PROFILES[house_id]
        result.append(HourlyForecast(
            house_id        = house_id,
            demand_kwh      = preds,
            total_daily_kwh = round(sum(preds), 2),
            peak_hour       = int(preds.index(max(preds))),
            peak_demand_kw  = round(max(preds), 3),
            priority        = profile["priority"],
        ))
    return sorted(result, key=lambda x: {"critical": 0, "high": 1, "normal": 2}[x.priority])


@router.get("/demand/{house_id}", response_model=HourlyForecast)
async def get_house_demand(house_id: str, hours: int = Query(24, ge=1, le=48)):
    if house_id not in HOUSE_PROFILES:
        raise HTTPException(404, f"Unknown house_id '{house_id}'. Valid: {list(HOUSE_PROFILES.keys())}")
    preds = forecaster.forecast(house_id, hours)
    return HourlyForecast(
        house_id        = house_id,
        demand_kwh      = preds,
        total_daily_kwh = round(sum(preds), 2),
        peak_hour       = int(preds.index(max(preds))),
        peak_demand_kw  = round(max(preds), 3),
        priority        = HOUSE_PROFILES[house_id]["priority"],
    )


@router.get("/solar", response_model=SolarForecast)
async def get_solar(
    capacity_kw: float = Query(30.0),
    cloud_cover: float = Query(None, ge=0, le=1),
):
    hourly = solar_forecaster.forecast(capacity_kw=capacity_kw, cloud_cover=cloud_cover)
    cloud  = cloud_cover if cloud_cover is not None else 0.2
    return SolarForecast(
        hourly_generation_kw = hourly,
        total_daily_kwh      = round(sum(hourly), 2),
        peak_generation_kw   = round(max(hourly), 2),
        peak_hour            = int(hourly.index(max(hourly))) if max(hourly) > 0 else 13,
        cloud_cover_estimate = round(cloud, 2),
    )


@router.get("/metrics")
async def get_metrics():
    """Model accuracy (MAE/RMSE/MAPE) per house — from registry (global for unified model)."""
    return [forecaster.get_prediction_metrics(hid) for hid in HOUSE_PROFILES]


@router.get("/models/info")
async def get_model_info():
    return {
        "demand_model": forecaster.get_registry_info(),
        "solar_model":  solar_forecaster.get_meta(),
    }
