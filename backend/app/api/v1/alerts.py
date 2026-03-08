import uuid
from datetime import datetime
from fastapi import APIRouter
from typing import List

from app.schemas.schemas import Alert, AlertLevel
from app.utils.data_generator import get_current_stats, HOUSE_PROFILES, generate_demand_forecast

router = APIRouter(prefix="/alerts", tags=["Alerts"])


def _generate_live_alerts() -> List[Alert]:
    """Generate alerts based on current system state."""
    alerts = []
    stats = get_current_stats()
    
    # Battery low warning
    if stats["battery_soc_pct"] < 25:
        alerts.append(Alert(
            id=str(uuid.uuid4())[:8],
            level=AlertLevel.CRITICAL,
            message=f"Battery SOC critically low at {stats['battery_soc_pct']:.1f}%. Initiate load shedding!",
            house_id=None,
            timestamp=datetime.now()
        ))
    elif stats["battery_soc_pct"] < 40:
        alerts.append(Alert(
            id=str(uuid.uuid4())[:8],
            level=AlertLevel.WARNING,
            message=f"Battery SOC at {stats['battery_soc_pct']:.1f}%. Consider reducing non-critical loads.",
            house_id=None,
            timestamp=datetime.now()
        ))
    
    # Deficit alert
    if stats["deficit_kw"] > 5:
        alerts.append(Alert(
            id=str(uuid.uuid4())[:8],
            level=AlertLevel.CRITICAL,
            message=f"Energy deficit of {stats['deficit_kw']:.1f} kW. Blackout risk is HIGH!",
            house_id=None,
            timestamp=datetime.now()
        ))
    elif stats["deficit_kw"] > 2:
        alerts.append(Alert(
            id=str(uuid.uuid4())[:8],
            level=AlertLevel.WARNING,
            message=f"Demand exceeds solar by {stats['deficit_kw']:.1f} kW. Drawing from battery.",
            house_id=None,
            timestamp=datetime.now()
        ))
    
    # House-level alerts
    hour = datetime.now().hour
    for hid, profile in HOUSE_PROFILES.items():
        if profile["priority"] == "critical":
            demand = generate_demand_forecast(hid)[hour]
            if demand > profile["base"] * 2:
                alerts.append(Alert(
                    id=str(uuid.uuid4())[:8],
                    level=AlertLevel.WARNING,
                    message=f"{hid.upper()} demand spike: {demand:.2f} kW (2x normal). Verify equipment.",
                    house_id=hid,
                    timestamp=datetime.now()
                ))
    
    # Surplus info alert
    if stats["surplus_kw"] > 5:
        alerts.append(Alert(
            id=str(uuid.uuid4())[:8],
            level=AlertLevel.INFO,
            message=f"Solar surplus of {stats['surplus_kw']:.1f} kW. Battery charging at full rate.",
            house_id=None,
            timestamp=datetime.now()
        ))
    
    # Default good state
    if not alerts:
        alerts.append(Alert(
            id=str(uuid.uuid4())[:8],
            level=AlertLevel.INFO,
            message="✅ All systems normal. Solar generation meeting demand. Battery healthy.",
            house_id=None,
            timestamp=datetime.now()
        ))
    
    return alerts


@router.get("/", response_model=List[Alert], summary="Get current system alerts")
async def get_alerts():
    """Returns active alerts for operator and SMS notification system."""
    return _generate_live_alerts()


@router.post("/sms/test", summary="Send test alert (simulated — no Twilio needed)")
async def send_test_sms(phone: str = "+919999999999"):
    """
    Simulates an SMS alert for demo purposes.
    To enable real SMS: add TWILIO_* vars to .env
    """
    stats = get_current_stats()
    msg = (
        f"[MicroGrid Alert] Solar: {stats['current_solar_kw']}kW | "
        f"Demand: {stats['current_demand_kw']}kW | "
        f"Battery: {stats['battery_soc_pct']}% | "
        f"Status: {stats['blackout_risk'].upper()}"
    )
    return {
        "status": "simulated",
        "to": phone,
        "message": msg,
        "note": "Real SMS disabled in demo mode. Set TWILIO_* env vars to enable."
    }