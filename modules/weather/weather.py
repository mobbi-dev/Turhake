from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from modules.config import OPENWEATHER_API_KEY


def _weather_emoji(description: str, temp_c: float) -> str:
    desc_lower = description.lower()
    if "rain" in desc_lower:
        emoji = "🌧️"
    elif "snow" in desc_lower:
        emoji = "❄️"
    elif "clear" in desc_lower or "sun" in desc_lower:
        emoji = "☀️"
    elif "cloud" in desc_lower:
        emoji = "☁️"
    else:
        emoji = "🌤️"
    if temp_c > 25:
        emoji += " 🔥"
    return emoji


def _safe_get_temp(data: dict) -> Optional[float]:
    try:
        return data["main"]["temp"]
    except (KeyError, TypeError, IndexError):
        return None


def _safe_get_description(data: dict) -> Optional[str]:
    try:
        return data["weather"][0]["description"]
    except (KeyError, TypeError, IndexError):
        return None


def _get_weather_data(url: str) -> Optional[dict]:
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if data.get("cod") and str(data["cod"]) != "200":
            return None
        return data
    except Exception:
        return None


def get_weather(city):
    try:
        if not OPENWEATHER_API_KEY:
            return "❌ OpenWeather API key is missing. Add `OPENWEATHER_API_KEY` to `.env`."

        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric&lang=en"
        data = _get_weather_data(url)
        if data is None:
            return f"Weather lookup failed: city {city} was not found."

        temp_c = _safe_get_temp(data)
        if temp_c is None:
            return "Weather lookup failed: incomplete API response."
        temp_c = round(temp_c)
        description = _safe_get_description(data) or ""

        emoji = _weather_emoji(description, temp_c)
        return f"{city.capitalize()}: {temp_c}°C {emoji} ({description})"
    except Exception:
        return "Weather lookup failed."


def get_weather_tomorrow(city):
    try:
        if not OPENWEATHER_API_KEY:
            return "❌ OpenWeather API key is missing. Add `OPENWEATHER_API_KEY` to `.env`."

        url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={OPENWEATHER_API_KEY}&units=metric&lang=en"
        data = _get_weather_data(url)
        if data is None:
            return f"Weather lookup failed: city {city} was not found."

        tomorrow_date = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
        forecasts = [item for item in data["list"] if item["dt_txt"].startswith(tomorrow_date)]

        if not forecasts:
            return f"No weather forecast was found for tomorrow in {city}."

        avg_temp = sum(f["main"]["temp"] for f in forecasts) / len(forecasts)
        description = forecasts[0]["weather"][0]["description"]
        emoji = _weather_emoji(description, avg_temp)

        formatted_date = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%d.%m.%Y")
        return f"{city.capitalize()} tomorrow {formatted_date}: {round(avg_temp)}°C {emoji} ({description})"
    except Exception:
        return "Weather lookup failed."


def get_weather_week(city):
    try:
        if not OPENWEATHER_API_KEY:
            return "❌ OpenWeather API key is missing. Add `OPENWEATHER_API_KEY` to `.env`."

        url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={OPENWEATHER_API_KEY}&units=metric&lang=en"
        data = _get_weather_data(url)
        if data is None:
            return f"Weather lookup failed: city {city} was not found."

        daily = {}
        for item in data["list"]:
            date = item["dt_txt"].split()[0]
            daily.setdefault(date, []).append(item)

        message = f"📅 Weekly weather forecast: {city.capitalize()}\n"
        for date, items in list(daily.items())[:5]:
            avg_temp = sum(f["main"]["temp"] for f in items) / len(items)
            desc = items[0]["weather"][0]["description"]
            emoji = _weather_emoji(desc, avg_temp)

            date_obj = datetime.strptime(date, "%Y-%m-%d")
            weekday_en = date_obj.strftime("%A")
            message += f"{weekday_en} - {date_obj.strftime('%d.%m.%Y')}: {round(avg_temp)}°C {emoji} ({desc})\n"
        return message
    except Exception:
        return "Weekly weather lookup failed."


def get_hourly_weather(city):
    try:
        if not OPENWEATHER_API_KEY:
            return "❌ OpenWeather API key is missing. Add `OPENWEATHER_API_KEY` to `.env`."

        url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={OPENWEATHER_API_KEY}&units=metric&lang=en"
        data = _get_weather_data(url)
        if data is None:
            return f"Weather lookup failed: city {city} was not found."

        now_utc = datetime.now(timezone.utc)
        target_hours = [0, 3, 6, 9]
        forecasts = []
        for offset in target_hours:
            target_time = now_utc + timedelta(hours=offset)
            closest = min(data["list"], key=lambda x: abs(datetime.fromtimestamp(x["dt"], tz=timezone.utc) - target_time))
            forecasts.append((offset, closest))

        message = f"Weather forecast for {city.capitalize()} for the next few hours:\n"
        for offset, forecast in forecasts:
            temp = round(forecast["main"]["temp"])
            description = forecast["weather"][0]["description"].lower()
            emoji = _weather_emoji(description, temp)

            message += f"{'now' if offset == 0 else f'+{offset}h'}: {temp}°C {emoji} ({description})\n"

        return message
    except Exception:
        return "Weather lookup failed."
