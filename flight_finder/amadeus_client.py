from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import date
from typing import Any

import requests

from .models import FlightOption, Segment


class FlightSearchError(RuntimeError):
    pass


@dataclass
class AmadeusConfig:
    client_id: str
    client_secret: str
    env: str = "test"

    @property
    def base_url(self) -> str:
        # Amadeus uses test.api.amadeus.com for sandbox and api.amadeus.com for production.
        if self.env.lower() == "production":
            return "https://api.amadeus.com"
        return "https://test.api.amadeus.com"


class AmadeusFlightClient:
    def __init__(self, config: AmadeusConfig):
        self.config = config
        self._token: str | None = None
        self._token_expires_at = 0.0

    @classmethod
    def from_env(cls) -> "AmadeusFlightClient":
        client_id = os.getenv("AMADEUS_CLIENT_ID", "").strip()
        client_secret = os.getenv("AMADEUS_CLIENT_SECRET", "").strip()
        env = os.getenv("AMADEUS_ENV", "test").strip() or "test"
        if not client_id or not client_secret:
            raise FlightSearchError("Missing AMADEUS_CLIENT_ID or AMADEUS_CLIENT_SECRET. Use Demo Mode or add credentials to .env.")
        return cls(AmadeusConfig(client_id=client_id, client_secret=client_secret, env=env))

    def _get_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires_at - 60:
            return self._token

        url = f"{self.config.base_url}/v1/security/oauth2/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }
        resp = requests.post(url, data=data, timeout=30)
        if resp.status_code >= 400:
            raise FlightSearchError(f"Amadeus authentication failed: {resp.status_code} {resp.text[:300]}")
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expires_at = now + int(payload.get("expires_in", 1800))
        return self._token

    def search_offers(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        adults: int = 1,
        currency: str = "CAD",
        max_results: int = 8,
        return_date: date | None = None,
        travel_class: str | None = None,
    ) -> list[FlightOption]:
        token = self._get_token()
        url = f"{self.config.base_url}/v2/shopping/flight-offers"
        params: dict[str, Any] = {
            "originLocationCode": origin.upper().strip(),
            "destinationLocationCode": destination.upper().strip(),
            "departureDate": departure_date.isoformat(),
            "adults": adults,
            "currencyCode": currency.upper().strip(),
            "max": max_results,
            "nonStop": "false",
        }
        if return_date:
            params["returnDate"] = return_date.isoformat()
        if travel_class and travel_class != "ANY":
            params["travelClass"] = travel_class

        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(url, headers=headers, params=params, timeout=45)
        if resp.status_code >= 400:
            raise FlightSearchError(f"Flight search failed for {origin}-{destination}: {resp.status_code} {resp.text[:400]}")
        payload = resp.json()
        return parse_amadeus_offers(payload, strategy="Live API search", provider="Amadeus")


def parse_amadeus_offers(payload: dict[str, Any], strategy: str, provider: str) -> list[FlightOption]:
    options: list[FlightOption] = []
    dictionaries = payload.get("dictionaries", {}) or {}
    carriers = dictionaries.get("carriers", {}) or {}

    for item in payload.get("data", []) or []:
        price_data = item.get("price", {}) or {}
        try:
            total = float(price_data.get("grandTotal") or price_data.get("total"))
        except (TypeError, ValueError):
            continue
        currency = price_data.get("currency") or ""
        segments: list[Segment] = []
        total_stops = 0
        itinerary_durations: list[str] = []

        for itinerary in item.get("itineraries", []) or []:
            itinerary_durations.append(itinerary.get("duration", ""))
            itinerary_segments = itinerary.get("segments", []) or []
            if itinerary_segments:
                total_stops += max(0, len(itinerary_segments) - 1)
            for seg in itinerary_segments:
                dep = seg.get("departure", {}) or {}
                arr = seg.get("arrival", {}) or {}
                carrier_code = seg.get("carrierCode", "")
                carrier_name = carriers.get(carrier_code, carrier_code)
                segments.append(
                    Segment(
                        origin=dep.get("iataCode", ""),
                        destination=arr.get("iataCode", ""),
                        departure=dep.get("at", ""),
                        arrival=arr.get("at", ""),
                        carrier=carrier_code,
                        flight_number=seg.get("number", ""),
                        duration=seg.get("duration", ""),
                    )
                )

        route = " → ".join([segments[0].origin] + [s.destination for s in segments]) if segments else "Unknown route"
        carrier_set = sorted({s.carrier for s in segments if s.carrier})
        notes = []
        if carrier_set:
            notes.append("Airlines: " + ", ".join([carriers.get(c, c) for c in carrier_set[:5]]))
        if item.get("lastTicketingDate"):
            notes.append(f"Last ticketing date: {item.get('lastTicketingDate')}")

        options.append(
            FlightOption(
                strategy=strategy,
                route=route,
                price=total,
                currency=currency,
                total_duration=" + ".join([d for d in itinerary_durations if d]),
                stops=total_stops,
                segments=segments,
                provider=provider,
                notes=notes,
                raw=item,
            )
        )
    return options
