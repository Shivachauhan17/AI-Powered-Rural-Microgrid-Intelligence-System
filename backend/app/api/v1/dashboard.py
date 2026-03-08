import asyncio
import json
import random
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app.utils.data_generator import (
    get_current_stats, generate_solar_forecast,
    generate_demand_forecast, generate_battery_soc_trajectory,
    HOUSE_PROFILES
)
from app.schemas.schemas import DashboardStats, BlackoutRisk, RealtimeReading

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStats, summary="Get current dashboard statistics")
async def get_dashboard_stats():
    """Returns current live statistics for the operator dashboard."""
    stats = get_current_stats()
    
    solar_today = generate_solar_forecast(30.0)
    demand_today_per_house = [generate_demand_forecast(hid) for hid in HOUSE_PROFILES.keys()]
    total_demand_today = [sum(d[h] for d in demand_today_per_house) for h in range(24)]
    
    risk_map = {"low": BlackoutRisk.LOW, "medium": BlackoutRisk.MEDIUM, "high": BlackoutRisk.HIGH}
    
    return DashboardStats(
        timestamp=datetime.now(),
        current_solar_kw=stats["current_solar_kw"],
        current_demand_kw=stats["current_demand_kw"],
        battery_soc_pct=stats["battery_soc_pct"],
        net_energy_kw=stats["net_energy_kw"],
        deficit_kw=stats["deficit_kw"],
        surplus_kw=stats["surplus_kw"],
        active_houses=stats["active_houses"],
        blackout_risk=risk_map.get(stats["blackout_risk"], BlackoutRisk.LOW),
        today_solar_kwh=round(sum(solar_today), 2),
        today_demand_kwh=round(sum(total_demand_today), 2),
        savings_pct=round(random.uniform(28, 42), 1),  # Simulated savings vs unmanaged
    )


@router.get("/24h-profile", summary="Get 24-hour energy profile")
async def get_24h_profile():
    """
    Returns complete 24h forecast profile for:
    - Solar generation
    - Total household demand
    - Battery SOC trajectory
    """
    solar = generate_solar_forecast(30.0)
    
    all_house_demands = {hid: generate_demand_forecast(hid) for hid in HOUSE_PROFILES.keys()}
    total_demand = [round(sum(all_house_demands[h][i] for h in HOUSE_PROFILES), 3) for i in range(24)]
    
    battery_soc = generate_battery_soc_trajectory(0.62, solar, total_demand)
    
    hours = [f"{h:02d}:00" for h in range(24)]
    
    return {
        "hours": hours,
        "solar_kw": solar,
        "demand_kw": total_demand,
        "battery_soc_pct": battery_soc,
        "net_kw": [round(solar[i] - total_demand[i], 3) for i in range(24)],
    }


@router.get("/house-allocations", summary="Get per-house allocation summary")
async def get_house_allocations():
    # Use evening peak hour for realistic shortage demonstration
    DEMO_HOUR = 19

    solar = generate_solar_forecast(30.0)
    current_solar = solar[DEMO_HOUR]   # ~2-4 kW

    houses = []
    total_demand = 0.0

    for hid, profile in HOUSE_PROFILES.items():
        demand = generate_demand_forecast(hid)[DEMO_HOUR]
        total_demand += demand
        houses.append({
            "id":       hid,
            "name":     hid.replace("_", " ").title(),
            "demand_kw": round(demand, 3),
            "priority": profile["priority"],
        })

    # Battery adds only 5 kW — total ~7-9 kW against ~22 kW demand
    available = round(current_solar + 5.0, 2)
    remaining = available

    for h in sorted(houses, key=lambda x: {"critical": 0, "high": 1, "normal": 2}[x["priority"]]):
        alloc = round(min(h["demand_kw"], max(0.0, remaining)), 3)
        h["allocated_kw"]    = alloc
        h["satisfaction_pct"] = round(alloc / max(h["demand_kw"], 0.001) * 100, 1)
        remaining = round(remaining - alloc, 3)
        h["status"] = (
            "full"    if h["satisfaction_pct"] >= 95 else
            "partial" if h["satisfaction_pct"] >= 50 else
            "low"
        )

    return {
        "timestamp":         datetime.now().isoformat(),
        "current_solar_kw":  round(current_solar, 2),
        "total_available_kw": available,
        "total_demand_kw":   round(total_demand, 2),
        "houses":            houses,
    }

@router.websocket("/ws/realtime")
async def realtime_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time energy monitoring.
    Pushes readings every 5 seconds.
    """
    await websocket.accept()
    try:
        while True:
            stats = get_current_stats()
            reading = {
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "solar_kw": stats["current_solar_kw"],
                "demand_kw": stats["current_demand_kw"],
                "battery_soc": stats["battery_soc_pct"],
                "net_kw": stats["net_energy_kw"],
            }
            await websocket.send_text(json.dumps(reading))
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass
