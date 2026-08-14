"""Fetches live hourly forecast (and marine) data from Open-Meteo.

Open-Meteo is free, needs no API key, and (unlike most weather APIs) also
serves marine data - wave height, swell, even sea surface temperature -
which covers surfing/kitesurfing/kayaking/snorkelling scoring without a
second provider. See https://open-meteo.com/en/docs and
https://open-meteo.com/en/docs/marine-weather-api

Hourly (not daily) data is used throughout so that scoring can weight
conditions during an activity's actual time-of-day window more heavily
than conditions outside it - see context.py.
"""

from __future__ import annotations

import datetime as dt
import time
from zoneinfo import ZoneInfo

import requests

SYDNEY_TZ = ZoneInfo("Australia/Sydney")

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"

HOURLY_WEATHER_VARS = [
    "temperature_2m",
    "precipitation",
    "precipitation_probability",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "uv_index",
    "visibility",
    "cloud_cover",
    "relative_humidity_2m",
    "weather_code",
]

HOURLY_MARINE_VARS = [
    "wave_height",
    "wind_wave_height",
    "swell_wave_height",
    "swell_wave_period",
    "sea_surface_temperature",
]

# History pulled alongside the forecast, so "rain in the last 24/48/72h"
# factors (wet rock, murky water) have real data to work from rather than
# just the scored day itself.
PAST_DAYS = 3


_RETRY_STATUS_CODES = {429, 502, 503, 504}
_MAX_ATTEMPTS = 3


def _fetch_hourly(url: str, lat: float, lon: float, forecast_days: int, variables: list[str]) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(variables),
        "timezone": "auto",
        "past_days": PAST_DAYS,
        "forecast_days": forecast_days,
    }
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(url, params=params, timeout=25)
        except requests.exceptions.RequestException:
            # A read timeout/connection error raises before any response arrives, so it
            # never reaches the status-code retry check below - without this, one slow
            # request anywhere in the batch failed outright on attempt 1 with no retry at
            # all, unlike a 429/502/503/504 (which at least got a response to retry on).
            if attempt == _MAX_ATTEMPTS:
                raise
            time.sleep(1.5 * attempt)
            continue
        transient = resp.status_code in _RETRY_STATUS_CODES
        if not transient or attempt == _MAX_ATTEMPTS:
            resp.raise_for_status()
            return resp.json()["hourly"]
        time.sleep(1.5 * attempt)  # brief backoff - most locations run through several of these concurrently
    raise AssertionError("unreachable")  # loop always returns or raises above


def _index_by_timestamp(hourly: dict, variables: list[str]) -> dict[str, dict]:
    times = hourly["time"]
    return {ts: {var: hourly[var][i] for var in variables} for i, ts in enumerate(times)}


def build_hourly_days(location: dict, forecast_days: int) -> dict[str, dict]:
    """Returns {date_str: {"hours": [...], "month": int, "rain_prior_24h": .., ...}}
    for today..today+forecast_days-1. Weather and marine hourly series are
    merged by matching timestamp (not position) since the marine API has no
    `past_days`, so its series starts at a different offset than weather's.
    """
    weather = _fetch_hourly(FORECAST_URL, location["lat"], location["lon"], forecast_days, HOURLY_WEATHER_VARS)
    weather_by_ts = _index_by_timestamp(weather, HOURLY_WEATHER_VARS)

    marine_by_ts: dict[str, dict] = {}
    if location.get("marine"):
        marine = _fetch_hourly(MARINE_URL, location["lat"], location["lon"], forecast_days, HOURLY_MARINE_VARS)
        marine_by_ts = _index_by_timestamp(marine, HOURLY_MARINE_VARS)

    empty_marine = {var: None for var in HOURLY_MARINE_VARS}
    hours_by_date: dict[str, list[dict]] = {}
    for ts in weather["time"]:
        date_str, hour_str = ts.split("T")
        hour_record = dict(weather_by_ts[ts])
        hour_record.update(marine_by_ts.get(ts, empty_marine))
        hour_record["hour"] = int(hour_str[:2])
        hours_by_date.setdefault(date_str, []).append(hour_record)

    daily_rain_total = {
        date_str: sum((h["precipitation"] or 0) for h in hours) for date_str, hours in hours_by_date.items()
    }

    sorted_dates = sorted(hours_by_date)
    # Sydney's date, not the machine's - GitHub Actions runners default to UTC, and Sydney
    # (UTC+10/+11) rolls over to the next calendar date 10-11h before UTC does. Using the
    # naive local date there meant the boundary between "history" and "today" was off by a
    # day for a chunk of each day, silently dropping the actual next day from the results
    # (while an already-past day lingered as if it were still current).
    today_str = dt.datetime.now(SYDNEY_TZ).date().isoformat()
    today_index = sorted_dates.index(today_str) if today_str in sorted_dates else PAST_DAYS

    days = {}
    for i, date_str in enumerate(sorted_dates):
        if i < today_index:
            continue  # these dates exist only to give us rain history, not to score
        days[date_str] = {
            "hours": hours_by_date[date_str],
            "month": dt.date.fromisoformat(date_str).month,
            "rain_prior_24h": daily_rain_total.get(sorted_dates[i - 1]) if i - 1 >= 0 else None,
            "rain_prior_48h": sum(daily_rain_total.get(d, 0) for d in sorted_dates[max(0, i - 2):i]) if i >= 1 else None,
            "rain_prior_72h": sum(daily_rain_total.get(d, 0) for d in sorted_dates[max(0, i - 3):i]) if i >= 1 else None,
        }
    return days
