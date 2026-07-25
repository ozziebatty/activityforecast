"""Cosmetic helpers for the terminal report: icons, a sky/condition summary,
UV colour coding, and a plain-ASCII score bar. None of this feeds back into
scoring - it's purely a visual read of the same `context.py` window data.
"""

from __future__ import annotations

ACTIVITY_ICONS = {
    "climbing": "\U0001F9D7",       # person climbing
    "hiking": "\U0001F97E",         # hiking boot
    "swimming": "\U0001F3CA",       # swimmer
    "snorkelling": "\U0001F93F",    # diving mask
    "scuba": "\U0001F419",          # octopus (no dedicated scuba emoji)
    "surfing": "\U0001F3C4",        # surfer
    "kayaking_sea": "\U0001F6F6",   # canoe
    "kayaking_freshwater": "\U0001F6F6",
    "kitesurfing": "\U0001FA81",    # kite
    "kite_practice": "\U0001FA81",  # kite (land-based practice, same glyph)
    "sailing": "\U000026F5",        # sailboat
    "city_touring": "\U0001F3D9",   # cityscape
    "beach_day": "\U0001F3D6",      # beach with umbrella
}

RESET = "\033[0m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_DIM = "\033[2m"


def activity_icon(activity_key: str) -> str:
    return ACTIVITY_ICONS.get(activity_key, "\U0001F3C1")


def sky_summary(window: dict) -> str:
    if window.get("storm_present"):
        return "⛈️ Storm"
    rain = window.get("rain_total") or 0
    if rain > 0.5:
        return "\U0001F327️ Rain"
    cloud = window.get("cloud_cover_avg")
    if cloud is None:
        return "❓ Unknown"
    if cloud >= 70:
        return "☁️ Cloudy"
    if cloud >= 30:
        return "\U0001F324️ Partly cloudy"
    return "☀️ Clear"


def uv_summary(uv_max) -> str:
    if uv_max is None:
        return ""
    if uv_max >= 11:
        dot = "\U0001F7E3"  # extreme - purple, matching the standard UV Index scale
    elif uv_max >= 8:
        dot = "\U0001F7E0"  # very high
    elif uv_max >= 6:
        dot = "\U0001F7E1"  # high
    else:
        dot = "\U0001F7E2"  # low/moderate
    return f"UV {uv_max:.0f}{dot}"


def condition_line(window: dict) -> str:
    parts = [sky_summary(window)]
    if window.get("temperature_max") is not None:
        parts.append(f"\U0001F321️ {window['temperature_max']:.0f}°C")
    if window.get("wind_speed_max") is not None:
        parts.append(f"\U0001F4A8 {window['wind_speed_max'] / 1.852:.0f}kt")
    uv = uv_summary(window.get("uv_max"))
    if uv:
        parts.append(uv)
    if window.get("wave_height_max") is not None:
        parts.append(f"\U0001F30A {window['wave_height_max']:.1f}m")
    if window.get("sea_surface_temperature_avg") is not None:
        parts.append(f"sea {window['sea_surface_temperature_avg']:.0f}°C")
    return "   ".join(parts)


def score_bar(score: float, width: int = 12) -> str:
    score = max(0.0, min(100.0, score))
    filled = round(score / 100 * width)
    return "█" * filled + "░" * (width - filled)


def score_color(score: float) -> str:
    if score >= 70:
        return _GREEN
    if score >= 40:
        return _YELLOW
    return _RED


def dim(text: str) -> str:
    return f"{_DIM}{text}{RESET}"
