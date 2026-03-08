import uuid
from datetime import datetime
from typing import List
from fastapi import APIRouter
from app.schemas.schemas import Alert, AlertLevel
from app.utils.data_generator import get_current_stats, HOUSE_PROFILES, generate_demand_forecast

router = APIRouter(prefix="/alerts", tags=["Alerts"])


def _live_alerts() -> List[Alert]:
    alerts = []
    stats  = get_current_stats()

    if stats["battery_soc_pct"] < 25:
        alerts.append(Alert(id=str(uuid.uuid4())[:8], level=AlertLevel.CRITICAL,
            message=f"Battery critically low at {stats['battery_soc_pct']:.1f}%. Initiate load shedding!",
            timestamp=datetime.now()))
    elif stats["battery_soc_pct"] < 40:
        alerts.append(Alert(id=str(uuid.uuid4())[:8], level=AlertLevel.WARNING,
            message=f"Battery at {stats['battery_soc_pct']:.1f}%. Consider reducing non-critical loads.",
            timestamp=datetime.now()))

    if stats["deficit_kw"] > 5:
        alerts.append(Alert(id=str(uuid.uuid4())[:8], level=AlertLevel.CRITICAL,
            message=f"Energy deficit {stats['deficit_kw']:.1f} kW. Blackout risk HIGH!",
            timestamp=datetime.now()))
    elif stats["deficit_kw"] > 2:
        alerts.append(Alert(id=str(uuid.uuid4())[:8], level=AlertLevel.WARNING,
            message=f"Demand exceeds solar by {stats['deficit_kw']:.1f} kW. Drawing from battery.",
            timestamp=datetime.now()))

    if stats["surplus_kw"] > 5:
        alerts.append(Alert(id=str(uuid.uuid4())[:8], level=AlertLevel.INFO,
            message=f"Solar surplus of {stats['surplus_kw']:.1f} kW. Battery charging at full rate.",
            timestamp=datetime.now()))

    if not alerts:
        alerts.append(Alert(id=str(uuid.uuid4())[:8], level=AlertLevel.INFO,
            message="✅ All systems normal. Solar meeting demand. Battery healthy.",
            timestamp=datetime.now()))

    return alerts


@router.get("/", response_model=List[Alert])
async def get_alerts():
    return _live_alerts()


@router.post("/sms/test")
async def send_test_sms(phone: str = "+919999999999"):
    """Send test SMS via Twilio. Set TWILIO_* env vars to enable."""
    try:
        from twilio.rest import Client
        from app.config import settings
        if not settings.TWILIO_ACCOUNT_SID:
            stats = get_current_stats()
            return {
                "status":  "simulated",
                "message": f"[Microgrid] Solar:{stats['current_solar_kw']}kW Demand:{stats['current_demand_kw']}kW Battery:{stats['battery_soc_pct']}% Risk:{stats['blackout_risk'].upper()}",
                "to":      phone,
                "note":    "Set TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN in .env to send real SMS",
            }
        stats   = get_current_stats()
        client  = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        msg_txt = (f"[Microgrid] Solar:{stats['current_solar_kw']}kW "
                   f"Demand:{stats['current_demand_kw']}kW "
                   f"Battery:{stats['battery_soc_pct']}% "
                   f"Risk:{stats['blackout_risk'].upper()}")
        msg = client.messages.create(body=msg_txt, from_=settings.TWILIO_FROM_NUMBER, to=phone)
        return {"status": "sent", "sid": msg.sid}
    except ImportError:
        return {"status": "error", "message": "pip install twilio"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
