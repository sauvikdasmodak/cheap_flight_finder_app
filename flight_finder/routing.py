from __future__ import annotations

from datetime import date, datetime, timedelta
from itertools import product
from typing import Callable, Iterable

from .models import FlightOption, Segment, parse_iso_datetime

SearchFn = Callable[[str, str, date], list[FlightOption]]


AIRPORT_PRESETS: dict[str, list[str]] = {
    "Toronto area": ["YYZ", "YTZ", "YHM", "BUF"],
    "New York area": ["JFK", "EWR", "LGA", "SWF", "PHL"],
    "Chicago area": ["ORD", "MDW", "MKE"],
    "London area": ["LHR", "LGW", "STN", "LTN", "LCY"],
    "Paris area": ["CDG", "ORY", "BVA"],
    "Kolkata / East India": ["CCU", "BBI", "DAC"],
    "Delhi / North India": ["DEL", "IXC", "JAI"],
    "Mumbai / West India": ["BOM", "PNQ", "AMD"],
}

POPULAR_HUBS = [
    "JFK", "EWR", "ORD", "ATL", "BOS", "LAX", "SFO", "SEA", "YUL", "YYZ",
    "LHR", "LGW", "DUB", "LIS", "MAD", "CDG", "AMS", "FRA", "MUC", "IST",
    "DOH", "DXB", "AUH", "ADD", "DEL", "BOM", "SIN", "HKG", "NRT", "ICN",
]


def clean_codes(value: str | Iterable[str] | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        parts = value.replace("\n", ",").split(",")
    else:
        parts = list(value)
    output: list[str] = []
    for part in parts:
        code = str(part).strip().upper()
        if len(code) == 3 and code.isalpha() and code not in output:
            output.append(code)
    return output


def date_range(start: date, end: date, max_days: int = 10) -> list[date]:
    if end < start:
        end = start
    days = []
    current = start
    while current <= end and len(days) < max_days:
        days.append(current)
        current += timedelta(days=1)
    return days


def label_strategy(option: FlightOption, requested_origin: str, requested_destination: str) -> FlightOption:
    first = option.segments[0].origin if option.segments else requested_origin
    last = option.segments[-1].destination if option.segments else requested_destination
    if first == requested_origin and last == requested_destination:
        option.strategy = "Normal route"
        option.risk_score += 0
    else:
        option.strategy = "Nearby / repositioning airport"
        option.risk_score += 25
        option.notes.append("Airport differs from requested origin/destination; include ground transport cost")
    return option


def find_direct_and_nearby(
    search_fn: SearchFn,
    requested_origin: str,
    requested_destination: str,
    origins: list[str],
    destinations: list[str],
    dates: list[date],
    max_searches: int = 40,
) -> list[FlightOption]:
    results: list[FlightOption] = []
    count = 0
    for origin, destination, dep_date in product(origins, destinations, dates):
        if origin == destination:
            continue
        count += 1
        if count > max_searches:
            break
        try:
            found = search_fn(origin, destination, dep_date)
        except Exception as exc:  # caller displays partial results and errors
            results.append(
                FlightOption(
                    strategy="Search error",
                    route=f"{origin} → {destination}",
                    price=999999.0,
                    currency="",
                    total_duration="",
                    stops=0,
                    notes=[str(exc)[:180]],
                    risk_score=99,
                )
            )
            continue
        for opt in found[:4]:
            results.append(label_strategy(opt, requested_origin, requested_destination))
    return results


def _connection_hours(first_leg: FlightOption, second_leg: FlightOption) -> float | None:
    if not first_leg.segments or not second_leg.segments:
        return None
    arr = parse_iso_datetime(first_leg.segments[-1].arrival)
    dep = parse_iso_datetime(second_leg.segments[0].departure)
    if not arr or not dep:
        return None
    return (dep - arr).total_seconds() / 3600


def combine_split_ticket(
    first_leg: FlightOption,
    second_leg: FlightOption,
    min_buffer_hours: float,
    max_buffer_hours: float,
) -> FlightOption | None:
    buffer = _connection_hours(first_leg, second_leg)
    if buffer is not None and (buffer < min_buffer_hours or buffer > max_buffer_hours):
        return None

    if not first_leg.segments or not second_leg.segments:
        return None
    hub = first_leg.segments[-1].destination
    if second_leg.segments[0].origin != hub:
        return None

    currency = first_leg.currency or second_leg.currency
    if first_leg.currency and second_leg.currency and first_leg.currency != second_leg.currency:
        return None

    segments: list[Segment] = [*first_leg.segments, *second_leg.segments]
    price = first_leg.price + second_leg.price
    route = f"{segments[0].origin} → {hub} + {hub} → {segments[-1].destination}"
    notes = [
        "Separate tickets: missed connection protection may not apply",
        "Re-check baggage and visa/transit rules before booking",
    ]
    if buffer is not None:
        notes.append(f"Self-transfer buffer: {buffer:.1f} hours")
    risk = 45
    if buffer is not None and buffer < 6:
        risk += 15
    if buffer is not None and buffer > 12:
        risk += 10
        notes.append("Long layover / possible overnight connection")

    return FlightOption(
        strategy="Split ticket via hub",
        route=route,
        price=round(price, 2),
        currency=currency,
        total_duration="Self-transfer itinerary",
        stops=max(1, first_leg.stops + second_leg.stops + 1),
        segments=segments,
        provider=f"{first_leg.provider}+{second_leg.provider}",
        notes=notes,
        risk_score=risk,
        booking_hint="Book each leg separately only after checking baggage, visa, and delay risk",
    )


def find_split_ticket_routes(
    search_fn: SearchFn,
    origins: list[str],
    destinations: list[str],
    hubs: list[str],
    dates: list[date],
    min_buffer_hours: float = 5.0,
    max_buffer_hours: float = 22.0,
    max_hubs: int = 8,
    max_searches: int = 80,
) -> list[FlightOption]:
    results: list[FlightOption] = []
    hubs = [h for h in hubs[:max_hubs] if h not in origins and h not in destinations]
    cache: dict[tuple[str, str, date], list[FlightOption]] = {}
    searches = 0

    def cached_search(origin: str, destination: str, dep_date: date) -> list[FlightOption]:
        nonlocal searches
        key = (origin, destination, dep_date)
        if key not in cache:
            searches += 1
            if searches > max_searches:
                return []
            try:
                cache[key] = search_fn(origin, destination, dep_date)[:3]
            except Exception:
                cache[key] = []
        return cache[key]

    for origin, destination, hub, dep_date in product(origins, destinations, hubs, dates):
        if len({origin, destination, hub}) < 3:
            continue
        leg1_options = cached_search(origin, hub, dep_date)
        # Try same-day and next-day second leg. This catches long-layover repositioning deals.
        leg2_options = cached_search(hub, destination, dep_date) + cached_search(hub, destination, dep_date + timedelta(days=1))
        for leg1 in leg1_options:
            for leg2 in leg2_options:
                combo = combine_split_ticket(leg1, leg2, min_buffer_hours, max_buffer_hours)
                if combo:
                    results.append(combo)
    return results


def apply_baseline_savings(options: list[FlightOption], requested_origin: str, requested_destination: str) -> list[FlightOption]:
    valid = [o for o in options if o.price < 999999]
    normal = [
        o for o in valid
        if o.segments and o.segments[0].origin == requested_origin and o.segments[-1].destination == requested_destination
    ]
    baseline = min([o.price for o in normal], default=None)
    for opt in options:
        if baseline and opt.price < 999999:
            opt.savings_vs_baseline = round(baseline - opt.price, 2)
    return sorted(valid, key=lambda o: (o.price, o.risk_score, o.stops))
