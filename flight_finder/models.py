from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # Amadeus usually returns local datetimes like 2026-07-10T22:45:00
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class Segment:
    origin: str
    destination: str
    departure: str
    arrival: str
    carrier: str = ""
    flight_number: str = ""
    duration: str = ""

    @property
    def flight_label(self) -> str:
        number = f"{self.carrier}{self.flight_number}".strip()
        return number or "N/A"


@dataclass
class FlightOption:
    strategy: str
    route: str
    price: float
    currency: str
    total_duration: str
    stops: int
    segments: list[Segment] = field(default_factory=list)
    provider: str = ""
    notes: list[str] = field(default_factory=list)
    booking_hint: str = "Search exact dates/legs on airline or OTA"
    raw: dict[str, Any] = field(default_factory=dict)
    risk_score: int = 0
    savings_vs_baseline: float | None = None

    @property
    def first_departure(self) -> str:
        return self.segments[0].departure if self.segments else ""

    @property
    def last_arrival(self) -> str:
        return self.segments[-1].arrival if self.segments else ""

    @property
    def itinerary_text(self) -> str:
        if not self.segments:
            return self.route
        parts = []
        for s in self.segments:
            parts.append(
                f"{s.origin} → {s.destination} | {s.departure} → {s.arrival} | {s.flight_label}"
            )
        return "\n".join(parts)


def option_to_row(option: FlightOption) -> dict[str, Any]:
    return {
        "Strategy": option.strategy,
        "Route": option.route,
        "Price": option.price,
        "Currency": option.currency,
        "Savings vs baseline": option.savings_vs_baseline,
        "Stops": option.stops,
        "Risk score": option.risk_score,
        "Departure": option.first_departure,
        "Arrival": option.last_arrival,
        "Duration": option.total_duration,
        "Notes": "; ".join(option.notes),
    }
