"""Turns raw hourly day data into the per-scope context that scoring.py reads.

Each activity cares about a specific slice of the day (a dawn surf check, a
midday hike, an afternoon sea-breeze kite session) - configured per-activity
(and overridable per-location) as a `time_window`. This module reduces a
day's hourly values into three views:

  window          hours inside the activity's time window
  outside_window  the rest of the day (e.g. evening rain after a climb)
  full_day        every hour

so config/activities.yaml can pick whichever is relevant for a given factor
via its `scope` field (default "window"), and conditions forecast outside
the active window get penalised much less by construction.

It also derives a few fields that need location context rather than pure
weather data: `offshore_wind_present` (checked against the location's
`offshore_directions` sectors - used as a clean-wave bonus for surfing and a
hard safety gate for kitesurfing) and `pollution_advisory` (a manually-set
flag, since no reliable free live feed for NSW beach water-quality
advisories was available at build time - see README).
"""

from __future__ import annotations

STORM_WEATHER_CODES = {95, 96, 99}

DEFAULT_TIME_WINDOW = {"start": 6, "end": 18}

# Nov-Apr - when sustained onshore wind is most likely to blow bluebottles onto NSW beaches.
BLUEBOTTLE_SEASON_MONTHS = {11, 12, 1, 2, 3, 4}

# Heavy/recent rain drives river-mouth runoff (turbid water, displaced baitfish) that's a
# well-known correlate of elevated shark activity near NSW beaches - mm thresholds for
# "today's rain", "rain in the last 24h", and "rain in the last 72h" respectively.
SHARK_RUNOFF_RAIN_MM = 10
SHARK_RUNOFF_PRIOR_24H_MM = 15
SHARK_RUNOFF_PRIOR_72H_MM = 25
# Jun-Oct - peak whale migration. Whale carcasses draw sharks in close to shore, a pattern
# NSW authorities specifically warn about - matches activities.yaml's "whales peak" bonus.
SHARK_WHALE_CARCASS_MONTHS = {6, 7, 8, 9, 10}


def _clean(values):
    return [v for v in values if v is not None]


def _avg(values):
    return sum(values) / len(values) if values else None


def _split_hours(hours: list[dict], start: int, end: int) -> tuple[list[dict], list[dict]]:
    inside = [h for h in hours if start <= h["hour"] < end]
    outside = [h for h in hours if not (start <= h["hour"] < end)]
    return inside, outside


def summarise_hours(hours: list[dict]) -> dict:
    """Reduces a list of hourly records to the aggregate values that
    factors/gates/risk_factors read. Any field is None if none of the
    hours had data for it (e.g. marine variables at a non-marine location)."""
    if not hours:
        return {}

    temps = _clean(h["temperature_2m"] for h in hours)
    precip = _clean(h["precipitation"] for h in hours)
    precip_prob = _clean(h["precipitation_probability"] for h in hours)
    wind = _clean(h["wind_speed_10m"] for h in hours)
    gusts = _clean(h["wind_gusts_10m"] for h in hours)
    uv = _clean(h["uv_index"] for h in hours)
    visibility = _clean(h["visibility"] for h in hours)
    cloud = _clean(h["cloud_cover"] for h in hours)
    humidity = _clean(h["relative_humidity_2m"] for h in hours)
    codes = _clean(h["weather_code"] for h in hours)
    wave = _clean(h.get("wave_height") for h in hours)
    wind_wave = _clean(h.get("wind_wave_height") for h in hours)
    swell = _clean(h.get("swell_wave_height") for h in hours)
    swell_period = _clean(h.get("swell_wave_period") for h in hours)
    sst = _clean(h.get("sea_surface_temperature") for h in hours)
    directions = _clean(h.get("wind_direction_10m") for h in hours)

    wind_speed_avg = _avg(wind)
    wind_gust_max = max(gusts) if gusts else None
    temperature_avg = _avg(temps)
    humidity_avg = _avg(humidity)

    return {
        "temperature_avg": temperature_avg,
        "temperature_max": max(temps) if temps else None,
        "temperature_min": min(temps) if temps else None,
        "rain_total": sum(precip) if precip else 0.0,
        "rain_probability_max": max(precip_prob) if precip_prob else None,
        "wind_speed_avg": wind_speed_avg,
        "wind_speed_max": max(wind) if wind else None,
        "wind_gust_max": wind_gust_max,
        # gustiness: how much gusts exceed the average wind - a steadier
        # (lower ratio) day is safer/more predictable, esp. for kitesurfing.
        "gust_ratio": (wind_gust_max / wind_speed_avg) if wind_speed_avg else None,
        "uv_max": max(uv) if uv else None,
        "visibility_min": min(visibility) if visibility else None,
        "cloud_cover_avg": _avg(cloud),
        "humidity_avg": humidity_avg,
        # humidity only counts against climbing friction once it's actually
        # warm enough for it to matter - folds "hot + humid = greasy rock"
        # into one factor rather than scoring humidity in isolation.
        "friction_index": humidity_avg if (humidity_avg is not None and temperature_avg is not None and temperature_avg >= 20) else 0,
        "storm_present": 1 if codes and STORM_WEATHER_CODES & set(codes) else 0,
        "wave_height_max": max(wave) if wave else None,
        "wind_wave_height_max": max(wind_wave) if wind_wave else None,
        "swell_wave_height_max": max(swell) if swell else None,
        "swell_period_avg": _avg(swell_period),
        "sea_surface_temperature_avg": _avg(sst),
        "_wind_directions": directions,
    }


def direction_in_sectors(degrees, sectors) -> bool:
    """True if a compass bearing (0-360) falls within any {from, to} sector.
    Handles sectors that wrap past 360/0 (e.g. from: 350, to: 20)."""
    if degrees is None or not sectors:
        return False
    for sector in sectors:
        lo, hi = sector["from"], sector["to"]
        if lo <= hi:
            if lo <= degrees <= hi:
                return True
        elif degrees >= lo or degrees <= hi:
            return True
    return False


def build_day_context(
    day: dict,
    time_window: dict,
    offshore_directions=None,
    pollution_advisory=False,
    whale_watching=False,
    requires_driving=False,
) -> dict:
    """`day` is one entry from open_meteo.build_hourly_days(). Returns
    {"window": {...}, "outside_window": {...}, "full_day": {...}} with
    day-level (month, recent rain) and location-level (wind direction,
    advisory, whale watching, driving-required) fields merged into all
    three, so a factor/gate/bonus can look up any variable regardless of
    which `scope` it uses. `requires_driving` isn't used by any scoring
    rule - it just rides along so html_report.py can filter it in the
    report's "Driving" checkbox.
    """
    start = time_window.get("start", DEFAULT_TIME_WINDOW["start"])
    end = time_window.get("end", DEFAULT_TIME_WINDOW["end"])
    window_hours, outside_hours = _split_hours(day["hours"], start, end)

    scopes = {
        "window": summarise_hours(window_hours),
        "outside_window": summarise_hours(outside_hours),
        "full_day": summarise_hours(day["hours"]),
    }

    rain_prior_72h = day["rain_prior_72h"] or 0
    rain_prior_24h = day["rain_prior_24h"] or 0
    shared = {
        "month": day["month"],
        "rain_prior_24h": day["rain_prior_24h"],
        "rain_prior_48h": day["rain_prior_48h"],
        "rain_prior_72h": day["rain_prior_72h"],
        "rain_24_to_72h": max(0.0, rain_prior_72h - rain_prior_24h),
        "pollution_advisory": 1 if pollution_advisory else 0,
        "whale_watching_spot": 1 if whale_watching else 0,
        "requires_driving": 1 if requires_driving else 0,
    }

    for scope in scopes.values():
        directions = scope.pop("_wind_directions", [])
        scope["offshore_wind_present"] = 1 if any(direction_in_sectors(d, offshore_directions) for d in directions) else 0
        # Heuristic proxy, not a live sighting feed (none exists free) - bluebottles get
        # blown onto NSW beaches by a sustained onshore breeze in the warmer months.
        # Most meaningful where offshore_directions is actually configured; otherwise
        # this degrades to a looser wind-speed + season-only check.
        in_season = day["month"] in BLUEBOTTLE_SEASON_MONTHS
        onshore_breeze = not scope["offshore_wind_present"] and (scope.get("wind_speed_avg") or 0) > 15
        scope["bluebottle_risk"] = 1 if (in_season and onshore_breeze) else 0
        # Heuristic proxy, not a live feed - see SHARK_RUNOFF_*/SHARK_WHALE_CARCASS_MONTHS
        # above. The runoff trigger isn't location-gated (a big rain event raises risk
        # everywhere, harbour/river spots included, just usually less so than an open
        # surf beach - see the smaller bonus weight used for kayaking in activities.yaml);
        # the whale-carcass trigger only fires at spots that actually front open coastal
        # water, same as the whale-watching bonus itself.
        runoff_risk = (
            (scope.get("rain_total") or 0) > SHARK_RUNOFF_RAIN_MM
            or rain_prior_24h > SHARK_RUNOFF_PRIOR_24H_MM
            or rain_prior_72h > SHARK_RUNOFF_PRIOR_72H_MM
        )
        whale_carcass_risk = whale_watching and day["month"] in SHARK_WHALE_CARCASS_MONTHS
        scope["shark_risk"] = 1 if (runoff_risk or whale_carcass_risk) else 0
        scope.update(shared)

    return scopes
