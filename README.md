# SkyCast Weather App

A responsive full-stack weather dashboard built with Python (FastAPI), HTML, CSS, JavaScript, Open-Meteo, and MongoDB Atlas.

## Features

- Current weather conditions and metrics
- City lookup using Open-Meteo geocoding
- 12-hour hourly outlook
- 7-day forecast
- Recent search history stored locally, or in MongoDB when configured
- Responsive dark dashboard
- Input validation and API error handling

## Requirements

- Python 3.10+
- Internet connection
- Optional: MongoDB Atlas cluster and connection URI

## Run locally (macOS)

```bash
cd weather_app
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and replace the sample `MONGO_URI` with your MongoDB Atlas connection string. If you leave `MONGO_URI` blank, searches are saved locally in `weather_history.db`.

Start the app:

```bash
uvicorn app:app --reload
```

Open http://127.0.0.1:5000

## MongoDB Atlas setup

1. Create a free cluster at https://www.mongodb.com/atlas/database.
2. Create a database user and save its password securely.
3. In Network Access, allow your current IP address (avoid `0.0.0.0/0` for a production database).
4. Select Connect → Drivers → Python and copy the connection URI.
5. Put the URI in `.env` as `MONGO_URI=...`. URL-encode special characters in the password.
6. Restart the app and search for a city. The database `weather_app` and collection `search_history` are created on first insert.

## API endpoints

- `GET /api/weather?city=New%20Delhi` — geocoding, current weather, hourly and daily forecast
- `GET /api/history` — most recent saved searches

## Notes

- Weather data is provided by Open-Meteo. Review its current terms and attribution requirements before public deployment.
- This is a learning MVP. Before production, disable development reload, add rate limiting, tests, logging, and appropriate privacy controls.
- MongoDB credentials must remain in `.env`; never commit them to Git.
