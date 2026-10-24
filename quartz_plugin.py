"""
quartz_plugin.py
Weather Plugin for Quartz AI Assistant
Author: Ali Mehdi
Version: 1.0.0

No API key required.
Uses wttr.in for weather data.
"""

import requests

PLUGIN_INFO = {
    "name":        "Quartz Weather Plugin",
    "version":     "1.0.0",
    "author":      "Ali Mehdi",
    "description": "Real-time weather and "
                   "forecast for any city",
    "commands":    [
        "get_weather",
        "weather_forecast",
    ],
}


# ── Register / Unregister ─────────────────────────────

def register():
    print(
        "[Weather Plugin] "
        "Activated successfully!")


def unregister():
    print("[Weather Plugin] Deactivated.")


# ── Current weather ───────────────────────────────────

def get_weather(
        city: str = "Istanbul") -> str:
    """
    Get current weather for any city.
    No API key needed.
    """
    try:
        url = (
            f"https://wttr.in/{city}"
            f"?format=j1"
        )
        resp = requests.get(url, timeout=8)

        if resp.status_code != 200:
            return _simple_weather(city)

        data    = resp.json()
        current = data["current_condition"][0]

        temp_c    = current["temp_C"]
        temp_f    = current["temp_F"]
        feels_c   = current["FeelsLikeC"]
        humidity  = current["humidity"]
        wind_kmph = current["windspeedKmph"]
        wind_dir  = current["winddir16Point"]
        visibility = current["visibility"]
        pressure  = current["pressure"]
        desc      = (
            current["weatherDesc"][0]["value"]
        )
        uv_index  = current.get(
            "uvIndex", "N/A")

        # Location name
        area = data.get(
            "nearest_area", [{}])[0]
        city_name = area.get(
            "areaName",
            [{}])[0].get("value", city)
        country = area.get(
            "country",
            [{}])[0].get("value", "")

        return (
            f"🌍 Weather for "
            f"{city_name}, {country}\n"
            f"──────────────────────────\n"
            f"🌡️  Temperature : "
            f"{temp_c}°C / {temp_f}°F\n"
            f"🤔 Feels Like  : {feels_c}°C\n"
            f"☁️  Condition   : {desc}\n"
            f"💧 Humidity    : {humidity}%\n"
            f"💨 Wind        : "
            f"{wind_kmph} km/h {wind_dir}\n"
            f"👁️  Visibility  : {visibility} km\n"
            f"🔵 Pressure    : {pressure} hPa\n"
            f"☀️  UV Index    : {uv_index}\n"
        )

    except Exception:
        return _simple_weather(city)


# ── Forecast ──────────────────────────────────────────

def weather_forecast(
        city: str = "Istanbul",
        days: int = 3) -> str:
    """
    Get weather forecast for next N days.
    """
    try:
        url = (
            f"https://wttr.in/{city}"
            f"?format=j1"
        )
        resp = requests.get(url, timeout=8)

        if resp.status_code != 200:
            return (
                f"Could not get forecast "
                f"for {city}"
            )

        data         = resp.json()
        weather_days = (
            data.get("weather", [])[:days]
        )

        lines = [
            f"📅 {days}-Day Forecast "
            f"for {city}\n"
            f"──────────────────────────"
        ]

        day_labels = [
            "Today", "Tomorrow",
            "Day After", "Day 4", "Day 5",
        ]

        for i, day in enumerate(weather_days):
            date  = day.get("date", "")
            max_c = day.get("maxtempC", "?")
            min_c = day.get("mintempC", "?")
            avg_c = day.get("avgtempC", "?")

            astro   = day.get(
                "astronomy", [{}])[0]
            sunrise = astro.get(
                "sunrise", "?")
            sunset  = astro.get(
                "sunset", "?")

            hourly = day.get("hourly", [])
            descs  = []
            for h in hourly:
                d = h.get(
                    "weatherDesc",
                    [{}])[0].get("value", "")
                if d and d not in descs:
                    descs.append(d)

            label = (
                day_labels[i]
                if i < len(day_labels)
                else f"Day {i + 1}"
            )
            condition = (
                ", ".join(descs[:2])
                if descs else "N/A"
            )

            lines.append(
                f"\n📆 {label} ({date})\n"
                f"   🌡️  {min_c}°C → {max_c}°C"
                f" (avg {avg_c}°C)\n"
                f"   ☁️  {condition}\n"
                f"   🌅 Sunrise: {sunrise}  "
                f"🌇 Sunset: {sunset}"
            )

        return "\n".join(lines)

    except Exception as exc:
        return f"Forecast error: {exc}"


# ── Simple fallback ───────────────────────────────────

def _simple_weather(city: str) -> str:
    try:
        url = (
            f"https://wttr.in/{city}"
            f"?format=3"
        )
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return f"🌍 {resp.text.strip()}"
        return (
            f"Could not get weather "
            f"for: {city}"
        )
    except Exception as exc:
        return f"Weather unavailable: {exc}"