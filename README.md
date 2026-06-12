# Cheap Flight Finder

A Python Streamlit website that searches for cheap flights using flexible dates, nearby airports, and unconventional split-ticket hub routes.

## What it does

- Searches normal routes such as `YYZ → CCU`
- Searches nearby / repositioning airports such as `YTZ`, `YHM`, `BUF`
- Searches split-ticket routes through hubs such as `DUB`, `LIS`, `IST`, `DOH`, `DXB`, `DEL`
- Ranks options by price, risk score, stops, and estimated savings vs baseline
- Exports results to CSV
- Runs in Demo Mode without any API key
- Supports live prices through the Amadeus Flight Offers Search API

## Important warning

Split-ticket routes can be cheaper, but they are riskier. If one leg is delayed, the second airline may not protect you. Always check:

- baggage re-check requirements
- visa/transit rules
- minimum connection time
- overnight layover risk
- airport change risk
- final fare on the airline or online travel agency before purchase

This app does not book tickets.

## Windows setup

Open PowerShell in the extracted folder and run:

```powershell
py -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

If `py` is not found, install Python from python.org and enable **Add python.exe to PATH** during installation.

## Mac/Linux setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Live API setup: Amadeus

1. Create an Amadeus for Developers account.
2. Create an app and copy the API key and secret.
3. Copy `.env.example` to `.env`.
4. Add your credentials:

```env
FLIGHT_PROVIDER=amadeus
AMADEUS_CLIENT_ID=your_client_id_here
AMADEUS_CLIENT_SECRET=your_client_secret_here
AMADEUS_ENV=test
```

Then restart the Streamlit app.

## How to use

Example for Toronto to Kolkata:

- Origin: `YYZ`
- Destination: `CCU`
- Origin-area airports: `Toronto area`
- Destination-area airports: `Kolkata / East India`
- Hub airports: `JFK, EWR, BOS, LHR, DUB, LIS, MAD, IST, DOH, DXB, DEL`
- Minimum self-transfer buffer: `5 hours`

Start with 5–7 flexible days and 6–8 hubs. Large searches can hit API limits.

## Notes on data coverage

The Amadeus sandbox/test environment may return limited routes or synthetic test-like data depending on your account. Production-quality coverage usually requires production access. The app is designed so you can later add other providers in the `flight_finder` package.
