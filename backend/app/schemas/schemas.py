from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime
from enum import Enum


class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"


class BlackoutRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# --- Request Schemas ---

class OptimizeRequest(BaseModel):
    solar_available_kw: float = Field(..., ge=0, description="Available solar power in kW")
    battery_soc_pct: float = Field(60.0, ge=0, le=100, description="Battery state of charge %")
    battery_capacity_kwh: float = Field(50.0, description="Total battery capacity kWh")
    max_discharge_rate_kw: float = Field(10.0, description="Max battery discharge rate kW")
    demands: Dict[str, float] = Field(..., description="Demand per consumer in kW")


# --- Response Schemas ---

class HourlyForecast(BaseModel):
    house_id: str
    demand_kwh: List[float]
    total_daily_kwh: float
    peak_hour: int
    peak_demand_kw: float
    priority: str


class SolarForecast(BaseModel):
    hourly_generation_kw: List[float]
    total_daily_kwh: float
    peak_generation_kw: float
    peak_hour: int
    cloud_cover_estimate: float


class AllocationResult(BaseModel):
    consumer_id: str
    demanded_kw: float
    allocated_kw: float
    satisfaction_pct: float
    priority: str
    status: str   # "full", "partial", "critical-low"


class OptimizationResult(BaseModel):
    timestamp: datetime
    total_available_kw: float
    total_demanded_kw: float
    total_allocated_kw: float
    battery_discharge_used_kw: float
    allocations: List[AllocationResult]
    fairness_index: float
    unmet_demand_pct: float
    blackout_risk: BlackoutRisk
    recommendation: str


class DashboardStats(BaseModel):
    timestamp: datetime
    current_solar_kw: float
    current_demand_kw: float
    battery_soc_pct: float
    net_energy_kw: float
    deficit_kw: float
    surplus_kw: float
    active_houses: int
    blackout_risk: BlackoutRisk
    today_solar_kwh: float
    today_demand_kwh: float
    savings_pct: float


class RealtimeReading(BaseModel):
    timestamp: str
    solar_kw: float
    demand_kw: float
    battery_soc: float
    net_kw: float


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Alert(BaseModel):
    id: str
    level: AlertLevel
    message: str
    house_id: Optional[str]
    timestamp: datetime
    resolved: bool = False


class ModelMetrics(BaseModel):
    house_id: str
    mae_kw: float
    rmse_kw: float
    mape_pct: float
    model_type: str
