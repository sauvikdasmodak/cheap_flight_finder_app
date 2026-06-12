from __future__ import annotations

from datetime import date, datetime, timedelta
from random import Random

from .models import FlightOption, Segment


def demo_search(origin: str, destination: str, departure_date: date, currency: str = "CAD") -> list[FlightOption]:
    """Generate realistic-looking demo options without calling a live API."""
    rng = Random(f"{origin}-{destination}-{departure_date}")
    base = 550 + rng.randint(-120, 220)
    depart = datetime.combine(departure_date, datetime.min.time()) + timedelta(hours=8 + rng.randint(0, 8))
    arrive = depart + timedelta(hours=2 + rng.randint(0, 8), minutes=30)

    direct = FlightOption(
        strategy="Direct / normal search",
        route=f"{origin} → {destination}",
        price=round(float(base), 2),
        currency=currency,
        total_duration="PT6H30M",
        stops=0,
        provider="Demo",
        notes=["Demo data only"],
        segments=[
            Segment(origin, destination, depart.isoformat(timespec="minutes"), arrive.isoformat(timespec="minutes"), "XX", "101", "PT6H30M")
        ],
    )

    hub = "LIS" if destination not in {"LIS", "MAD"} else "DUB"
    split_depart = depart + timedelta(hours=1)
    hub_arrive = split_depart + timedelta(hours=4, minutes=10)
    hub_depart = hub_arrive + timedelta(hours=5, minutes=20)
    final_arrive = hub_depart + timedelta(hours=3, minutes=50)
    split = FlightOption(
        strategy="Split ticket via hub",
        route=f"{origin} → {hub} + {hub} → {destination}",
        price=round(float(base * 0.78), 2),
        currency=currency,
        total_duration="Self-transfer: verify exact duration",
        stops=1,
        provider="Demo",
        risk_score=45,
        notes=["Separate tickets", "Long connection buffer included", "Demo data only"],
        segments=[
            Segment(origin, hub, split_depart.isoformat(timespec="minutes"), hub_arrive.isoformat(timespec="minutes"), "XX", "204", "PT4H10M"),
            Segment(hub, destination, hub_depart.isoformat(timespec="minutes"), final_arrive.isoformat(timespec="minutes"), "YY", "718", "PT3H50M"),
        ],
    )

    alt_origin = "BUF" if origin == "YYZ" else origin
    alt = FlightOption(
        strategy="Nearby / repositioning airport",
        route=f"{alt_origin} → {destination}",
        price=round(float(base * 0.86), 2),
        currency=currency,
        total_duration="PT7H05M",
        stops=1,
        provider="Demo",
        risk_score=25,
        notes=["Check ground transport cost", "Demo data only"],
        segments=[
            Segment(alt_origin, destination, depart.isoformat(timespec="minutes"), (arrive + timedelta(hours=1)).isoformat(timespec="minutes"), "ZZ", "909", "PT7H05M")
        ],
    )

    return [direct, split, alt]
