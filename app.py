import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import uvicorn

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
app = FastAPI()
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI", "").strip()
collection = None
LOCAL_DB_PATH = BASE_DIR / "weather_history.db"


def initialize_local_history():
    with sqlite3.connect(LOCAL_DB_PATH) as database:
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                city TEXT NOT NULL,
                country TEXT NOT NULL DEFAULT '',
                searched_at TEXT NOT NULL,
                temperature REAL,
                description TEXT NOT NULL DEFAULT ''
            )
            """
        )


initialize_local_history()

if MONGO_URI:
    try:
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2500)
        mongo_client.admin.command("ping")
        collection = mongo_client["weather_app"]["search_history"]
        print("MongoDB connected.")
    except Exception as exc:
        print(f"MongoDB is not available; history will not be saved. Details: {exc}")

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle",
    53: "Moderate drizzle", 55: "Dense drizzle", 56: "Freezing drizzle",
    57: "Dense freezing drizzle", 61: "Slight rain", 63: "Moderate rain",
    65: "Heavy rain", 66: "Freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    77: "Snow grains", 80: "Slight rain showers", 81: "Moderate rain showers",
    82: "Violent rain showers", 85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail"
}

def weather_label(code):
    return WEATHER_CODES.get(code, "Unknown conditions")

def weather_icon(code):
    if code == 0:
        return "☀️"
    if code in (1, 2):
        return "🌤️"
    if code in (3, 45, 48):
        return "☁️"
    if code in range(51, 68) or code in (80, 81, 82):
        return "🌧️"
    if code in range(71, 78) or code in (85, 86):
        return "❄️"
    if code in (95, 96, 99):
        return "⛈️"
    return "🌡️"


def save_history(weather):
    record = {
        "city": weather["location"]["name"],
        "country": weather["location"]["country"],
        "searched_at": datetime.now(timezone.utc),
        "temperature": weather["current"]["temperature"],
        "description": weather["current"]["description"],
    }
    if collection is not None:
        collection.insert_one(record)
        return

    with sqlite3.connect(LOCAL_DB_PATH) as database:
        database.execute(
            """
            INSERT INTO search_history
                (city, country, searched_at, temperature, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                record["city"],
                record["country"],
                record["searched_at"].isoformat(),
                record["temperature"],
                record["description"],
            ),
        )


def local_history():
    with sqlite3.connect(LOCAL_DB_PATH) as database:
        database.row_factory = sqlite3.Row
        rows = database.execute(
            """
            SELECT city, country, temperature, description, searched_at
            FROM search_history
            ORDER BY id DESC
            LIMIT 8
            """
        ).fetchall()
    return [dict(row) for row in rows]

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})

@app.get("/api/weather")
def get_weather(city: str = ""):
    city = city.strip()
    if not city:
        return JSONResponse({"error": "Please enter a city name."}, status_code=400)

    try:
        geo_response = requests.get(
            GEOCODING_URL,
            params={"name": city, "count": 1, "language": "en", "format": "json"},
            timeout=10,
        )
        geo_response.raise_for_status()
        geo_data = geo_response.json()
        results = geo_data.get("results") or []
        if not results:
            return JSONResponse(
                {"error": f'Could not find "{city}". Try another city.'},
                status_code=404,
            )

        place = results[0]
        forecast_response = requests.get(
            FORECAST_URL,
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,weather_code,wind_speed_10m,surface_pressure",
                "hourly": "temperature_2m,precipitation_probability,weather_code",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,uv_index_max",
                "timezone": "auto",
                "forecast_days": 7,
            },
            timeout=12,
        )
        forecast_response.raise_for_status()
        data = forecast_response.json()

        current = data["current"]
        hourly = data.get("hourly", {})
        daily = data.get("daily", {})
        weather = {
            "location": {
                "name": place.get("name", city),
                "admin1": place.get("admin1", ""),
                "country": place.get("country", ""),
                "timezone": data.get("timezone", "auto"),
            },
            "current": {
                "temperature": current.get("temperature_2m"),
                "feels_like": current.get("apparent_temperature"),
                "humidity": current.get("relative_humidity_2m"),
                "wind_speed": current.get("wind_speed_10m"),
                "pressure": current.get("surface_pressure"),
                "precipitation": current.get("precipitation"),
                "code": current.get("weather_code"),
                "description": weather_label(current.get("weather_code")),
                "icon": weather_icon(current.get("weather_code")),
                "time": current.get("time"),
            },
            "hourly": [
                {
                    "time": hourly.get("time", [])[i],
                    "temperature": hourly.get("temperature_2m", [])[i],
                    "precipitation_probability": (
                        hourly.get("precipitation_probability", [None] * len(hourly.get("time", [])))[i]
                    ),
                    "code": hourly.get("weather_code", [None] * len(hourly.get("time", [])))[i],
                    "description": weather_label(hourly.get("weather_code", [None] * len(hourly.get("time", [])))[i]),
                    "icon": weather_icon(hourly.get("weather_code", [None] * len(hourly.get("time", [])))[i]),
                }
                for i in range(min(12, len(hourly.get("time", []))))
            ],
            "daily": [
                {
                    "date": daily.get("time", [])[i],
                    "max": daily.get("temperature_2m_max", [])[i],
                    "min": daily.get("temperature_2m_min", [])[i],
                    "code": daily.get("weather_code", [None] * len(daily.get("time", [])))[i],
                    "description": weather_label(daily.get("weather_code", [None] * len(daily.get("time", [])))[i]),
                    "icon": weather_icon(daily.get("weather_code", [None] * len(daily.get("time", [])))[i]),
                    "uv_index": daily.get("uv_index_max", [None] * len(daily.get("time", [])))[i],
                    "sunrise": daily.get("sunrise", [None] * len(daily.get("time", [])))[i],
                    "sunset": daily.get("sunset", [None] * len(daily.get("time", [])))[i],
                }
                for i in range(min(7, len(daily.get("time", []))))
            ],
        }

        try:
            save_history(weather)
        except (OSError, sqlite3.Error, PyMongoError) as exc:
            logger.warning("Could not save search history: %s", exc)

        return weather
    except requests.RequestException:
        return JSONResponse(
            {"error": "Weather service is temporarily unavailable. Please try again."},
            status_code=502,
        )
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        logger.exception("Unexpected weather response: %s", exc)
        return JSONResponse(
            {"error": "The weather service returned an unexpected response."},
            status_code=502,
        )

@app.get("/api/cities")
def get_city_suggestions(query: str = ""):
    query = query.strip()
    if len(query) < 2:
        return {"cities": []}

    try:
        response = requests.get(
            GEOCODING_URL,
            params={"name": query, "count": 6, "language": "en", "format": "json"},
            timeout=5,
        )
        response.raise_for_status()
        results = response.json().get("results") or []
        return {
            "cities": [
                {
                    "name": place.get("name", ""),
                    "admin1": place.get("admin1", ""),
                    "country": place.get("country", ""),
                }
                for place in results
            ]
        }
    except (requests.RequestException, ValueError, TypeError):
        return {"cities": []}


@app.get("/api/history")
def get_history():
    if collection is None:
        try:
            return {"history": local_history()}
        except (OSError, sqlite3.Error):
            return JSONResponse({"history": [], "message": "Could not load search history."}, status_code=500)

    try:
        docs = collection.find({}, {"_id": 0}).sort("searched_at", -1).limit(8)
        history = []
        for doc in docs:
            searched_at = doc.get("searched_at")
            history.append({
                "city": doc.get("city", ""),
                "country": doc.get("country", ""),
                "temperature": doc.get("temperature"),
                "description": doc.get("description", ""),
                "searched_at": searched_at.isoformat() if searched_at else None,
            })
        return {"history": history}
    except PyMongoError:
        return JSONResponse({"history": [], "message": "Could not load search history."}, status_code=500)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "5000")))
