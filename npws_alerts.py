"""Best-effort NSW NPWS park alerts/closures check via their public RSS feed.

https://www.nationalparks.nsw.gov.au/api/rssfeed/get lists one <item> per
park/reserve that currently has at least one active alert - <title> is just
the bare park name, the actual alert text is HTML inside <description>
(prefixed with a `<strong>category: headline</strong>`), and <category> is
a clean tag like "Closed parks" or "Closed areas". There's no per-park query
param, so this fetches the whole feed once per report and matches locations
against it by park name - see `park_alert_match` in locations.yaml. Only
NPWS-managed NSW parks show up here; Commonwealth parks (e.g. Booderee at
the southern end of Jervis Bay) aren't covered.
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET

import requests

FEED_URL = "https://www.nationalparks.nsw.gov.au/api/rssfeed/get"

_STRONG_RE = re.compile(r"<strong>(.*?)</strong>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_summary(description: str, category: str) -> str:
    match = _STRONG_RE.search(description or "")
    text = match.group(1) if match else (description or "")
    text = html.unescape(_TAG_RE.sub("", text)).strip()
    prefix = f"{category}: "
    if category and text.lower().startswith(prefix.lower()):
        text = text[len(prefix):]
    return text


def fetch_alerts() -> list[dict]:
    """Returns [{"park": ..., "category": ..., "summary": ...}, ...] - one
    per park currently carrying an active alert. Returns [] on any failure -
    this is a nice-to-have cross-check, not core to scoring, so a feed
    outage shouldn't break the whole report."""
    try:
        resp = requests.get(FEED_URL, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        alerts = []
        for item in root.iter("item"):
            park = (item.findtext("title") or "").strip()
            category = (item.findtext("category") or "").strip()
            description = item.findtext("description") or ""
            alerts.append({"park": park, "category": category, "summary": _clean_summary(description, category)})
        return alerts
    except Exception:
        return []


def find_alert(match_terms: list[str], alerts: list[dict]) -> dict | None:
    """First alert whose park name *starts with* one of `match_terms`
    (case-insensitive). NPWS park names in this feed are exact, so anchoring
    to the start avoids false positives like "Royal National Park" matching
    inside "Mount Royal National Park" - a different, unrelated park."""
    for alert in alerts:
        low = alert["park"].lower()
        if any(low.startswith(term.lower()) for term in match_terms):
            return alert
    return None


def is_closure(alert: dict) -> bool:
    return "closed" in alert["category"].lower()
