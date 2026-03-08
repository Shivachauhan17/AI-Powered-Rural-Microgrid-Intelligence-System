from datetime import datetime
from fastapi import APIRouter
from app.models.energy_optimizer import (
    ConsumerProfile, run_optimization,
    compute_fairness_index, compute_unmet_pct,
    MIN_GUARANTEE,
)
from app.schemas.schemas import (
    OptimizeRequest, OptimizationResult, AllocationResult, BlackoutRisk,
)
from app.utils.data_generator import HOUSE_PROFILES, generate_demand_forecast, generate_solar_forecast

router = APIRouter(prefix="/optimize", tags=["Optimization"])

PRIORITY_ORDER = {"critical": 0, "high": 1, "normal": 2}


def _build_result(solar_kw: float, battery_soc: float, battery_cap: float,
                  max_discharge: float, demands: dict) -> OptimizationResult:
    consumers = [
        ConsumerProfile(
            consumer_id       = cid,
            demand_kw         = demand,
            priority          = HOUSE_PROFILES.get(cid, {}).get("priority", "normal"),
            min_guarantee_pct = MIN_GUARANTEE[HOUSE_PROFILES.get(cid, {}).get("priority", "normal")],
        )
        for cid, demand in demands.items()
    ]

    usable_soc    = max(0, battery_soc - 20.0) / 100.0
    battery_kw    = min(max_discharge, usable_soc * battery_cap)
    allocs        = run_optimization(consumers, solar_kw, battery_kw)
    demands_map   = {c.consumer_id: c.demand_kw for c in consumers}
    fairness      = compute_fairness_index(allocs, demands_map)
    unmet         = compute_unmet_pct(allocs, demands_map)
    total_avail   = solar_kw + battery_kw
    total_demand  = sum(demands_map.values())
    total_alloc   = sum(allocs.values())

    results = []
    for c in sorted(consumers, key=lambda x: PRIORITY_ORDER[x.priority]):
        alloc_kw = allocs.get(c.consumer_id, 0.0)
        sat      = (alloc_kw / c.demand_kw * 100) if c.demand_kw > 0 else 100.0
        status   = "full" if sat >= 95 else ("partial" if sat >= 60 else "critical-low")
        results.append(AllocationResult(
            consumer_id      = c.consumer_id,
            demanded_kw      = round(c.demand_kw, 3),
            allocated_kw     = alloc_kw,
            satisfaction_pct = round(sat, 1),
            priority         = c.priority,
            status           = status,
        ))

    if unmet > 30:
        risk = BlackoutRisk.HIGH
        rec  = "⚠️ Critical shortage! Activate load shedding for non-essential houses."
    elif unmet > 10:
        risk = BlackoutRisk.MEDIUM
        rec  = "🔶 Moderate shortage. Reduce non-essential loads."
    else:
        risk = BlackoutRisk.LOW
        rec  = "✅ Supply is healthy. All critical loads covered."

    return OptimizationResult(
        timestamp                 = datetime.now(),
        total_available_kw        = round(total_avail, 2),
        total_demanded_kw         = round(total_demand, 2),
        total_allocated_kw        = round(total_alloc, 2),
        battery_discharge_used_kw = round(battery_kw, 2),
        allocations               = results,
        fairness_index            = fairness,
        unmet_demand_pct          = unmet,
        blackout_risk             = risk,
        recommendation            = rec,
    )


@router.post("/allocate", response_model=OptimizationResult)
async def run_energy_optimization(request: OptimizeRequest):
    """Run LP optimization with supplied inputs."""
    return _build_result(
        solar_kw      = request.solar_available_kw,
        battery_soc   = request.battery_soc_pct,
        battery_cap   = request.battery_capacity_kwh,
        max_discharge = request.max_discharge_rate_kw,
        demands       = request.demands,
    )


@router.get("/simulate", response_model=OptimizationResult)
async def simulate_optimization():
    """
    Simulate with current sensor readings.
    Demo hour fixed to 19:00 (evening peak) to show realistic shortages.
    """
    DEMO_HOUR = 19
    solar   = generate_solar_forecast(30.0)
    demands = {hid: generate_demand_forecast(hid)[DEMO_HOUR] for hid in HOUSE_PROFILES}
    return _build_result(
        solar_kw      = solar[DEMO_HOUR],
        battery_soc   = 40.0,
        battery_cap   = 50.0,
        max_discharge = 5.0,
        demands       = demands,
    )
