import asyncio
import json
import random
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.utils.data_generator import (
    get_current_stats, generate_solar_forecast,
    generate_demand_forecast, generate_battery_soc_trajectory,
    HOUSE_PROFILES,
)
from app.schemas.schemas import DashboardStats, BlackoutRisk

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

RISK_MAP = {"low": BlackoutRisk.LOW, "medium": BlackoutRisk.MEDIUM, "high": BlackoutRisk.HIGH}


@router.get("/stats", response_model=DashboardStats)
async def get_stats():
    stats        = get_current_stats()
    solar_today  = generate_solar_forecast(30.0)
    total_demand = [
        sum(generate_demand_forecast(hid)[h] for hid in HOUSE_PROFILES)
        for h in range(24)
    ]
    return DashboardStats(
        timestamp          = datetime.now(),
        current_solar_kw   = stats["current_solar_kw"],
        current_demand_kw  = stats["current_demand_kw"],
        battery_soc_pct    = stats["battery_soc_pct"],
        net_energy_kw      = stats["net_energy_kw"],
        deficit_kw         = stats["deficit_kw"],
        surplus_kw         = stats["surplus_kw"],
        active_houses      = stats["active_houses"],
        blackout_risk      = RISK_MAP.get(stats["blackout_risk"], BlackoutRisk.LOW),
        today_solar_kwh    = round(sum(solar_today), 2),
        today_demand_kwh   = round(sum(total_demand), 2),
        savings_pct        = round(random.uniform(28, 42), 1),
    )


@router.get("/24h-profile")
async def get_24h_profile():
    solar        = generate_solar_forecast(30.0)
    total_demand = [
        round(sum(generate_demand_forecast(hid)[h] for hid in HOUSE_PROFILES), 3)
        for h in range(24)
    ]
    battery_soc = generate_battery_soc_trajectory(0.62, solar, total_demand)
    hours = [f"{h:02d}:00" for h in range(24)]
    return {
        "hours":           hours,
        "solar_kw":        solar,
        "demand_kw":       total_demand,
        "battery_soc_pct": battery_soc,
        "net_kw":          [round(solar[i] - total_demand[i], 3) for i in range(24)],
    }


@router.get("/house-allocations")
async def get_house_allocations():
    """Per-house allocation at demo hour 19:00 — shows realistic shortages."""
    DEMO_HOUR    = 19
    solar        = generate_solar_forecast(30.0)
    current_solar = solar[DEMO_HOUR]
    available    = current_solar + 5.0   # 5 kW battery discharge cap

    houses = []
    total_demand = 0.0
    for hid, profile in HOUSE_PROFILES.items():
        demand = generate_demand_forecast(hid)[DEMO_HOUR]
        total_demand += demand
        houses.append({
            "id":       hid,
            "demand_kw":demand,
            "priority": profile["priority"],
        })

    remaining = available
    for h in sorted(houses, key=lambda x: {"critical": 0, "high": 1, "normal": 2}[x["priority"]]):
        alloc = round(min(h["demand_kw"], max(0.0, remaining)), 3)
        h["allocated_kw"]     = alloc
        h["satisfaction_pct"] = round(alloc / max(h["demand_kw"], 0.001) * 100, 1)
        h["status"]           = "on" if h["satisfaction_pct"] >= 50 else "low"
        remaining            -= alloc

    return {
        "timestamp":        datetime.now().isoformat(),
        "current_solar_kw": round(current_solar, 2),
        "total_demand_kw":  round(total_demand, 2),
        "houses":           houses,
    }


@router.websocket("/ws/realtime")
async def realtime_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            stats = get_current_stats()
            await websocket.send_text(json.dumps({
                "timestamp":   datetime.now().strftime("%H:%M:%S"),
                "solar_kw":    stats["current_solar_kw"],
                "demand_kw":   stats["current_demand_kw"],
                "battery_soc": stats["battery_soc_pct"],
                "net_kw":      stats["net_energy_kw"],
            }))
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass
