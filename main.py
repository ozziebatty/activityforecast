#!/usr/bin/env python3
"""NSW outdoor activity weather planner.

Scores every configured location/activity combination for the next few days
using live Open-Meteo hourly forecast (and marine, where relevant) data,
weighted toward each activity's actual time-of-day window. Writes a
self-contained HTML report by default - pass --text for a quick terminal
view instead, or --serve to run a small local server with a live Refresh
button (re-scores on every request instead of writing a static snapshot).

Fetching (network-bound, rate-limited) and scoring/rendering (pure local
computation) are separable: --extract-only saves the raw fetched data to a
JSON file and stops there, and --from-extract scores/renders from that file
instead of hitting the network at all - handy for iterating on
activities.yaml/html_report.py against a fixed dataset, or for
visualising the same fetch under several --activity/--min-score filters
without re-fetching each time. Plain `python main.py` still does both
steps in one go, as it always did.

Add spots in config/locations.yaml and tune/add scoring in
config/activities.yaml - this file doesn't need to change for either.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import http.server
import json
import sys
import webbrowser
from pathlib import Path
from zoneinfo import ZoneInfo

from config_loader import load_activities, load_locations
from context import DEFAULT_TIME_WINDOW, build_day_context
from html_report import display_name, render as render_html
from icons import activity_icon, condition_line, dim, score_bar, score_color, RESET
from npws_alerts import fetch_alerts, find_alert, is_closure
from open_meteo import build_hourly_days
from scoring import score_activity


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--days", type=int, default=10,
        help="How many days ahead to score (default: 10). Open-Meteo gives real weather data out to "
        "16 days, but marine data (wave/swell/sea-temp) thins out to nulls after ~9 - coastal "
        "activities beyond that just lose those factors rather than erroring. --days 16 gets the "
        "full window at the cost of a bigger report.html (hourly breakdown is now rendered for "
        "every day, not just the soonest couple, so more days means more markup).",
    )
    parser.add_argument("--activity", help="Only show activities whose key contains this text (e.g. kayaking, surfing)")
    parser.add_argument("--location", help="Only show locations whose name contains this text")
    parser.add_argument("--min-score", type=float, default=0, help="Hide results below this score")
    parser.add_argument("--text", action="store_true", help="Print a terminal report instead of writing HTML")
    parser.add_argument("--out", default="report.html", help="HTML output path (default: report.html)")
    parser.add_argument("--open", action="store_true", help="Open the HTML report in your browser once written")
    parser.add_argument("--serve", action="store_true", help="Run a local server with a live Refresh button instead of writing a file")
    parser.add_argument("--port", type=int, default=8765, help="Port for --serve (default: 8765)")
    parser.add_argument("--explain", action="store_true", help="Terminal mode only: show the factor-by-factor scoring breakdown")
    parser.add_argument("--no-color", action="store_true", help="Terminal mode only: disable ANSI colour in the score bar")
    parser.add_argument(
        "--extract-only", metavar="PATH",
        help="Fetch weather/marine/NPWS data and save it to PATH as JSON, then exit - no scoring or rendering. "
        "Pair with --from-extract to visualise the same fetch repeatedly without hitting the network again.",
    )
    parser.add_argument(
        "--from-extract", metavar="PATH",
        help="Score/render using data previously saved by --extract-only, instead of fetching live data.",
    )
    return parser.parse_args()


def _fetch_all_days(locations, days_ahead):
    """Fetches build_hourly_days() for every location concurrently - each
    call is a couple of sequential HTTP requests (weather + marine), and
    with 10+ locations doing that one at a time is the whole runtime of a
    report (and, for --serve, of every single Refresh click). Capped at 4
    workers rather than higher - Open-Meteo's free tier starts returning 429s
    (rate limited, retried in open_meteo.py) if too many requests land in the
    same instant."""
    days_by_location = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_to_location = {executor.submit(build_hourly_days, loc, days_ahead): loc for loc in locations}
        for future in concurrent.futures.as_completed(future_to_location):
            location = future_to_location[future]
            try:
                days_by_location[location["name"]] = future.result()
            except Exception as exc:
                print(f"! Could not fetch weather for {location['name']}: {exc}", file=sys.stderr)
    return days_by_location


def collect_results(locations, activities_cfg, args, days_by_location=None, npws_feed=None):
    """`days_by_location`/`npws_feed` let a caller supply already-fetched
    data (see --from-extract in main()) instead of hitting the network -
    left as None (the default) to fetch live, same as always."""
    results = []  # (date_str, location_name, activity_key, result, window_ctx)
    hourly_lookup = {}  # (location_name, date_str) -> raw hourly records, for the hourly trend charts

    if npws_feed is None:
        npws_feed = fetch_alerts() if any(loc.get("park_alert_match") for loc in locations) else []
    if days_by_location is None:
        days_by_location = _fetch_all_days(locations, args.days)

    for location in locations:
        activity_items = list(location.get("activities", {}).items())
        if args.activity:
            activity_items = [(k, p) for k, p in activity_items if args.activity.lower() in k.lower()]
        if not activity_items:
            continue

        days = days_by_location.get(location["name"])
        if days is None:
            continue  # already reported by _fetch_all_days

        for date_str, day in days.items():
            hourly_lookup[(location["name"], date_str)] = day["hours"]

        # Informational only, never a scoring gate: the feed matches at whole-park
        # level, but a park can span hundreds of square km, so a "closure" alert
        # elsewhere in the park doesn't necessarily apply to this specific spot
        # (e.g. Blue Mountains NP's Victoria Falls closure has nothing to do with
        # Katoomba). Surfaced as a banner so you can check it yourself instead.
        park_alert = find_alert(location["park_alert_match"], npws_feed) if location.get("park_alert_match") else None

        for activity_key, params in activity_items:
            activity_cfg = activities_cfg.get(activity_key)
            if not activity_cfg:
                print(f"! No scoring config for activity '{activity_key}' (used by {location['name']})", file=sys.stderr)
                continue

            time_window = params.get("time_window") or activity_cfg.get("time_window") or DEFAULT_TIME_WINDOW
            offshore_directions = params.get("offshore_directions")
            pollution_advisory = location.get("pollution_advisory", False)
            whale_watching = location.get("whale_watching", False)
            requires_driving = location.get("requires_driving", False)

            for date_str, day in days.items():
                ctx = build_day_context(
                    day, time_window, offshore_directions, pollution_advisory, whale_watching, requires_driving
                )
                result = score_activity(ctx, activity_cfg)
                if result["score"] is None:
                    continue

                if park_alert and not result["gated"]:
                    result = {**result, "park_alert": park_alert["summary"], "park_alert_closed": is_closure(park_alert)}

                if not result["gated"] and result["score"] < args.min_score:
                    continue

                # Scoring itself stays keyed to the activity's own time-of-day window (a
                # dawn surf check genuinely is a different slice of the day to a midday
                # beach day - see README's "Time-of-day weighting"), but the card's
                # display data (chips, condition line, trend charts) uses full_day so two
                # activities at the same location on the same day show the same
                # temperature/wind/etc - showing each activity's own narrower window there
                # made otherwise-identical days look inconsistent for no obvious reason.
                results.append((date_str, location["name"], activity_key, result, ctx["full_day"]))

    return results, hourly_lookup


def print_text_report(results, explain: bool, use_color: bool):
    by_date = {}
    for date_str, loc_name, activity_key, result, window in results:
        by_date.setdefault(date_str, []).append((loc_name, activity_key, result, window))

    for date_str in sorted(by_date):
        print(f"\n=== {date_str} ===")
        rows = sorted(by_date[date_str], key=lambda r: r[2]["score"], reverse=True)
        for loc_name, activity_key, result, window in rows:
            icon = activity_icon(activity_key)
            label = display_name(activity_key)

            if result["gated"]:
                bar = "░" * 12
                bar = dim(bar) if use_color else bar
                print(f"  {bar}   0.0/10  {icon} {label:22s} {loc_name}")
                print(f"     \U0001F6AB GATED: {result['gate_reason']}")
                print(f"     {condition_line(window)}")
                continue

            bar = score_bar(result["score"])
            if use_color:
                bar = f"{score_color(result['score'])}{bar}{RESET}"
            print(f"  {bar}  {result['score'] / 10:4.1f}/10  {icon} {label:22s} {loc_name}")
            if result.get("park_alert"):
                print(f"     ⚠ NPWS: {result['park_alert']}")
            print(f"     {condition_line(window)}")
            if result["bonuses_hit"]:
                parts = ", ".join(f"{b['name']}({b['points']:+d})" for b in result["bonuses_hit"])
                print(f"     ⭐ {parts}")

            if explain:
                for entry in result["breakdown"]:
                    points_str = "n/a" if entry["points"] is None else f"{entry['points']:.2f}"
                    max_str = "n/a" if entry["max_points"] is None else f"{entry['max_points']:.2f}"
                    print(
                        f"       [{entry['kind']:6s}] {entry['variable']:26s} value={entry['value']!s:>10}  "
                        f"points={points_str}/{max_str}"
                    )


SYDNEY_TZ = ZoneInfo("Australia/Sydney")


def _generated_label(when: dt.datetime | None = None) -> str:
    # Explicitly Sydney time, not whatever timezone the machine running this happens to
    # be in - this is a NSW planner, and GitHub Actions runners default to UTC, which
    # made the "Generated" label on the published report read 10-11h behind actual local time.
    return (when or dt.datetime.now(SYDNEY_TZ)).strftime("%a %d %b, %I:%M%p").lstrip("0").replace(" 0", " ")


def _extract(locations, args) -> dict:
    """The network-bound half of a run: NPWS alerts + every location's
    weather/marine data, bundled with a timestamp so a later --from-extract
    run can label the report with when the data actually came from the
    network, not when it happened to be rendered."""
    npws_feed = fetch_alerts() if any(loc.get("park_alert_match") for loc in locations) else []
    days_by_location = _fetch_all_days(locations, args.days)
    return {"fetched_at": dt.datetime.now(SYDNEY_TZ).isoformat(), "npws_feed": npws_feed, "days_by_location": days_by_location}


def serve(locations, activities_cfg, args, cached: dict | None = None):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if cached is not None:
                days_by_location, npws_feed = cached["days_by_location"], cached["npws_feed"]
                generated_label = _generated_label(dt.datetime.fromisoformat(cached["fetched_at"])) + " (from --from-extract, not live)"
            else:
                days_by_location, npws_feed = None, None
                generated_label = _generated_label()
            results, hourly_lookup = collect_results(locations, activities_cfg, args, days_by_location, npws_feed)
            body = render_html(results, generated_label, hourly_lookup, live=(cached is None)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *log_args):  # noqa: A002 - matches base signature
            pass  # keep the terminal quiet; errors still raise normally

    url = f"http://127.0.0.1:{args.port}/"
    server = http.server.HTTPServer(("127.0.0.1", args.port), Handler)
    refresh_note = "each Refresh re-renders the --from-extract data (no network hit)" if cached is not None else "each Refresh re-scores from live weather data"
    print(f"Serving live report at {url} ({refresh_note}; Ctrl+C to stop)")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass  # stdout doesn't support reconfigure (e.g. some redirected streams) - emoji may not render

    args = parse_args()
    locations = load_locations()
    activities_cfg = load_activities()

    if args.location:
        locations = [loc for loc in locations if args.location.lower() in loc["name"].lower()]
        if not locations:
            print(f"No location matches '{args.location}'")
            return 1

    if args.extract_only:
        extracted = _extract(locations, args)
        out_path = Path(args.extract_only).resolve()
        out_path.write_text(json.dumps(extracted), encoding="utf-8")
        print(f"Wrote {out_path} ({len(extracted['days_by_location'])} location(s)) - "
              f"visualise it with --from-extract {out_path}")
        return 0

    cached = None
    if args.from_extract:
        cached = json.loads(Path(args.from_extract).read_text(encoding="utf-8"))

    if args.serve:
        serve(locations, activities_cfg, args, cached)
        return 0

    if cached is not None:
        generated_label = _generated_label(dt.datetime.fromisoformat(cached["fetched_at"])) + " (from --from-extract, not live)"
        results, hourly_lookup = collect_results(
            locations, activities_cfg, args, cached["days_by_location"], cached["npws_feed"]
        )
    else:
        generated_label = _generated_label()
        results, hourly_lookup = collect_results(locations, activities_cfg, args)

    if not results:
        print("No results - check your filters, or that locations.yaml/activities.yaml activity keys line up.")
        return 0

    if args.text:
        print_text_report(results, args.explain, use_color=not args.no_color)
        return 0

    html_doc = render_html(results, generated_label, hourly_lookup)
    out_path = Path(args.out).resolve()
    out_path.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {out_path}")
    if args.open:
        webbrowser.open(out_path.as_uri())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
