from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import List

from app.models.energy_optimizer import (
    ConsumerProfile, run_optimization,
    compute_fairness_index, compute_unmet_demand_pct,
    PRIORITY_WEIGHTS, MIN_GUARANTEE
)
from app.schemas.schemas import (
    OptimizeRequest, OptimizationResult,
    AllocationResult, BlackoutRisk
)
from app.utils.data_generator import HOUSE_PROFILES, generate_demand_forecast, generate_solar_forecast

router = APIRouter(prefix="/optimize", tags=["Optimization"])


def _get_priority(house_id: str) -> str:
    return HOUSE_PROFILES.get(house_id, {}).get("priority", "normal")


@router.post("/allocate", response_model=OptimizationResult, summary="Run energy allocation optimization")
async def run_energy_optimization(request: OptimizeRequest):
    """
    Runs LP optimization to fairly distribute available energy.
    
    Algorithm:
    - Maximizes weighted consumer satisfaction
    - Guarantees minimum supply for critical infrastructure
    - Uses battery as buffer when solar is insufficient
    - Returns Jain's Fairness Index as equity metric
    """
    # Build consumer profiles
    consumers = []
    for cid, demand in request.demands.items():
        priority = _get_priority(cid)
        consumers.append(ConsumerProfile(
            consumer_id=cid,
            demand_kw=demand,
            priority=priority,
            min_guarantee_pct=MIN_GUARANTEE[priority]
        ))
    
    # Calculate battery discharge available
    usable_soc = max(0, request.battery_soc_pct - 20.0) / 100.0  # Keep 20% reserve
    battery_energy_kwh = usable_soc * request.battery_capacity_kwh
    battery_discharge_kw = min(request.max_discharge_rate_kw, battery_energy_kwh)
    
    # Run optimization
    allocations = run_optimization(consumers, request.solar_available_kw, battery_discharge_kw)
    
    demands_map = {c.consumer_id: c.demand_kw for c in consumers}
    fairness = compute_fairness_index(allocations, demands_map)
    unmet_pct = compute_unmet_demand_pct(allocations, demands_map)
    
    total_available = request.solar_available_kw + battery_discharge_kw
    total_demanded = sum(demands_map.values())
    total_allocated = sum(allocations.values())
    
    # Build allocation results
    alloc_results = []
    for c in consumers:
        alloc_kw = allocations.get(c.consumer_id, 0.0)
        satisfaction = (alloc_kw / c.demand_kw * 100) if c.demand_kw > 0 else 100
        
        if satisfaction >= 95:
            status = "full"
        elif satisfaction >= 60:
            status = "partial"
        else:
            status = "critical-low"
        
        alloc_results.append(AllocationResult(
            consumer_id=c.consumer_id,
            demanded_kw=round(c.demand_kw, 3),
            allocated_kw=alloc_kw,
            satisfaction_pct=round(satisfaction, 1),
            priority=c.priority,
            status=status
        ))
    
    # Sort by priority
    priority_order = {"critical": 0, "high": 1, "normal": 2}
    alloc_results.sort(key=lambda x: priority_order[x.priority])
    
    # Blackout risk assessment
    if unmet_pct > 30:
        risk = BlackoutRisk.HIGH
        recommendation = "⚠️ Critical shortage! Activate load shedding for non-essential houses. Alert operator immediately."
    elif unmet_pct > 10:
        risk = BlackoutRisk.MEDIUM
        recommendation = "🔶 Moderate shortage. Reduce non-essential loads. Check if grid backup is available."
    else:
        risk = BlackoutRisk.LOW
        recommendation = "✅ Energy supply is healthy. All critical loads covered. Battery charging on surplus."
    
    return OptimizationResult(
        timestamp=datetime.now(),
        total_available_kw=round(total_available, 2),
        total_demanded_kw=round(total_demanded, 2),
        total_allocated_kw=round(total_allocated, 2),
        battery_discharge_used_kw=round(battery_discharge_kw, 2),
        allocations=alloc_results,
        fairness_index=fairness,
        unmet_demand_pct=unmet_pct,
        blackout_risk=risk,
        recommendation=recommendation
    )


@router.get("/simulate", response_model=OptimizationResult)
async def simulate_optimization():
    """
    Simulates evening peak hour (19:00) — high demand, low solar.
    This always demonstrates the optimizer doing real work regardless of time of day.
    """
    # Evening peak: solar nearly gone, demand at maximum
    DEMO_HOUR = 19

    solar_hourly = generate_solar_forecast(30.0)
    evening_solar = solar_hourly[DEMO_HOUR]  # ~2-4 kW at 7pm

    demands = {}
    for hid in HOUSE_PROFILES.keys():
        demands[hid] = generate_demand_forecast(hid)[DEMO_HOUR]

    request = OptimizeRequest(
        solar_available_kw=evening_solar,
        battery_soc_pct=40.0,           # partially depleted battery
        battery_capacity_kwh=50.0,
        max_discharge_rate_kw=5.0,      # only 5 kW from battery
        demands=demands
    )
    return await run_energy_optimization(request)