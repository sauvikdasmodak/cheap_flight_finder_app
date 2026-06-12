from __future__ import annotations

import os
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from flight_finder.amadeus_client import AmadeusFlightClient, FlightSearchError
from flight_finder.demo_data import demo_search
from flight_finder.models import option_to_row
from flight_finder.routing import (
    AIRPORT_PRESETS,
    POPULAR_HUBS,
    apply_baseline_savings,
    clean_codes,
    date_range,
    find_direct_and_nearby,
    find_split_ticket_routes,
)

load_dotenv()

st.set_page_config(page_title="Cheap Flight Finder", page_icon="✈️", layout="wide")

st.title("✈️ Cheap Flight Finder")
st.caption("Find cheaper routes by checking flexible dates, nearby airports, and split-ticket hub combinations.")

with st.expander("Important limitations", expanded=False):
    st.write(
        "Flight prices change fast. This tool helps discover options, but it does not book flights and does not guarantee availability. "
        "For split-ticket itineraries, always verify baggage rules, visa/transit rules, minimum connection time, and missed-connection risk before buying."
    )

provider_env = os.getenv("FLIGHT_PROVIDER", "demo").lower()

with st.sidebar:
    st.header("Search settings")
    provider = st.selectbox(
        "Data provider",
        ["Demo Mode", "Amadeus Live API"],
        index=1 if provider_env == "amadeus" else 0,
        help="Demo Mode works without API keys. Amadeus Live API requires credentials in .env.",
    )

    origin = st.text_input("Origin airport", value="YYZ", max_chars=3).upper()
    destination = st.text_input("Destination airport", value="CCU", max_chars=3).upper()

    preset_origin = st.selectbox("Add origin-area airports", ["None", *AIRPORT_PRESETS.keys()], index=1)
    preset_destination = st.selectbox("Add destination-area airports", ["None", *AIRPORT_PRESETS.keys()], index=5)

    extra_origins = st.text_input("Extra origin airports, comma-separated", value="")
    extra_destinations = st.text_input("Extra destination airports, comma-separated", value="")

    start_date = st.date_input("Departure date from", value=date.today() + timedelta(days=30), min_value=date.today())
    end_date = st.date_input("Departure date to", value=date.today() + timedelta(days=36), min_value=date.today())

    adults = st.number_input("Adults", min_value=1, max_value=9, value=1)
    currency = st.selectbox("Currency", ["CAD", "USD", "INR", "EUR", "GBP"], index=0)
    travel_class = st.selectbox("Cabin", ["ANY", "ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"], index=0)

    st.divider()
    st.subheader("Unconventional route engine")
    use_split = st.checkbox("Check split-ticket hub routes", value=True)
    hub_codes = st.text_area(
        "Hub airports to test",
        value=", ".join(["JFK", "EWR", "BOS", "LHR", "DUB", "LIS", "MAD", "IST", "DOH", "DXB", "DEL"]),
        height=85,
    )
    min_buffer = st.slider("Minimum self-transfer buffer, hours", 3.0, 12.0, 5.0, 0.5)
    max_buffer = st.slider("Maximum self-transfer buffer, hours", 8.0, 36.0, 22.0, 1.0)
    max_days = st.slider("Max flexible departure days to scan", 1, 14, 7)
    max_hubs = st.slider("Max hubs to scan", 1, 15, 8)
    run = st.button("Search flights", type="primary", use_container_width=True)


def build_airport_list(primary: str, preset_name: str, extras: str) -> list[str]:
    codes = clean_codes(primary)
    if preset_name != "None":
        for c in AIRPORT_PRESETS[preset_name]:
            if c not in codes:
                codes.append(c)
    for c in clean_codes(extras):
        if c not in codes:
            codes.append(c)
    return codes[:8]


origins = build_airport_list(origin, preset_origin, extra_origins)
destinations = build_airport_list(destination, preset_destination, extra_destinations)
hubs = clean_codes(hub_codes) or POPULAR_HUBS
scan_dates = date_range(start_date, end_date, max_days=max_days)

col_a, col_b, col_c, col_d = st.columns(4)
col_a.metric("Origin airports", len(origins))
col_b.metric("Destination airports", len(destinations))
col_c.metric("Departure dates", len(scan_dates))
col_d.metric("Hub tests", min(len(hubs), max_hubs) if use_split else 0)

st.write("**Origins:**", ", ".join(origins))
st.write("**Destinations:**", ", ".join(destinations))

if provider == "Amadeus Live API":
    try:
        client = AmadeusFlightClient.from_env()
        st.success("Amadeus credentials found. Live API mode is ready.")
    except FlightSearchError as exc:
        client = None
        st.warning(f"Live API is not configured: {exc}")
else:
    client = None


def search_fn_factory():
    if provider == "Amadeus Live API" and client is not None:
        def _search(o: str, d: str, dep: date):
            return client.search_offers(
                o,
                d,
                dep,
                adults=int(adults),
                currency=currency,
                max_results=8,
                travel_class=travel_class,
            )
        return _search

    def _demo(o: str, d: str, dep: date):
        return demo_search(o, d, dep, currency=currency)
    return _demo


if run:
    if not clean_codes(origin) or not clean_codes(destination):
        st.error("Enter valid 3-letter IATA airport codes, for example YYZ and CCU.")
        st.stop()
    if provider == "Amadeus Live API" and client is None:
        st.error("Add Amadeus credentials to .env or switch to Demo Mode.")
        st.stop()

    search_fn = search_fn_factory()
    progress = st.progress(0, text="Searching normal and nearby airport routes...")

    direct_results = find_direct_and_nearby(
        search_fn,
        requested_origin=origin,
        requested_destination=destination,
        origins=origins,
        destinations=destinations,
        dates=scan_dates,
        max_searches=50,
    )
    progress.progress(45, text="Normal/nearby routes completed. Checking split-ticket options...")

    split_results = []
    if use_split:
        split_results = find_split_ticket_routes(
            search_fn,
            origins=origins[:4],
            destinations=destinations[:4],
            hubs=hubs,
            dates=scan_dates[:max_days],
            min_buffer_hours=float(min_buffer),
            max_buffer_hours=float(max_buffer),
            max_hubs=int(max_hubs),
            max_searches=90,
        )
    progress.progress(85, text="Ranking cheapest options...")

    all_results = apply_baseline_savings(direct_results + split_results, origin, destination)
    all_results = [r for r in all_results if r.price < 999999]
    progress.progress(100, text="Done")

    if not all_results:
        st.error("No results found. Try fewer filters, different dates, or Demo Mode to test the app.")
        st.stop()

    df = pd.DataFrame([option_to_row(o) for o in all_results])
    cheapest = all_results[0]

    st.subheader("Best result")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cheapest price", f"{cheapest.currency} {cheapest.price:,.0f}")
    c2.metric("Strategy", cheapest.strategy)
    c3.metric("Risk score", cheapest.risk_score)
    if cheapest.savings_vs_baseline is not None:
        c4.metric("Savings vs baseline", f"{cheapest.currency} {cheapest.savings_vs_baseline:,.0f}")
    else:
        c4.metric("Savings vs baseline", "N/A")

    st.subheader("Ranked options")
    st.dataframe(df, use_container_width=True, hide_index=True)

    chart_df = df.head(25).copy()
    chart_df["Label"] = chart_df["Strategy"] + " | " + chart_df["Route"]
    fig = px.bar(chart_df, x="Price", y="Label", orientation="h", hover_data=["Risk score", "Stops", "Notes"])
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=max(450, len(chart_df) * 28))
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Itinerary details")
    for idx, option in enumerate(all_results[:20], start=1):
        with st.expander(f"#{idx} — {option.strategy} — {option.currency} {option.price:,.2f} — {option.route}"):
            st.write("**Booking hint:**", option.booking_hint)
            st.write("**Notes:**", "; ".join(option.notes) if option.notes else "None")
            st.code(option.itinerary_text)

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Download results as CSV", csv, "cheap_flight_results.csv", "text/csv")
else:
    st.info("Choose your airports and dates, then click **Search flights**.")

st.divider()
st.caption(
    "This app avoids scraping Google Flights or airline websites. For accurate live prices, use a licensed flight API and confirm final fares on the airline or OTA before purchasing."
)
