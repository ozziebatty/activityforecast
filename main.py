#!/usr/bin/env python3
"""NSW outdoor activity weather planner.

Scores every configured location/activity combination for the next few days
using live Open-Meteo hourly forecast (and marine, where relevant) data,
weighted toward each activity's actual time-of-day window. Writes a
self-contained HTML report by default - pass --text for a quick terminal
view instead, or --serve to run a small local server with a live Refresh
button (re-scores on every request instead of writing a static snapshot).

Add spots in config/locations.yaml and tune/add scoring in
config/activities.yaml - this file doesn't need to change for either.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import http.server
import sys
import webbrowser
from pathlib import Path

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
        "--days", type=int, default=7,
        help="How many days ahead to score (default: 7). Open-Meteo gives real weather data out to "
        "16 days, but marine data (wave/swell/sea-temp) thins out to nulls after ~9 - coastal "
        "activities beyond that just lose those factors rather than erroring.",
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


def collect_results(locations, activities_cfg, args):
    results = []  # (date_str, location_name, activity_key, result, window_ctx)
    hourly_lookup = {}  # (location_name, date_str) -> raw hourly records, for the hourly trend charts

    npws_feed = fetch_alerts() if any(loc.get("park_alert_match") for loc in locations) else []
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

            for date_str, day in days.items():
                ctx = build_day_context(day, time_window, offshore_directions, pollution_advisory, whale_watching)
                result = score_activity(ctx, activity_cfg)
                if result["score"] is None:
                    continue

                if park_alert and not result["gated"]:
                    result = {**result, "park_alert": park_alert["summary"], "park_alert_closed": is_closure(park_alert)}

                if not result["gated"] and result["score"] < args.min_score:
                    continue

                results.append((date_str, location["name"], activity_key, result, ctx["window"]))

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


def _generated_label() -> str:
    return dt.datetime.now().strftime("%a %d %b, %I:%M%p").lstrip("0").replace(" 0", " ")


def serve(locations, activities_cfg, args):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            results, hourly_lookup = collect_results(locations, activities_cfg, args)
            body = render_html(results, _generated_label(), hourly_lookup, live=True).encode("utf-8")
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
    print(f"Serving live report at {url} (each Refresh re-scores from live weather data; Ctrl+C to stop)")
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

    if args.serve:
        serve(locations, activities_cfg, args)
        return 0

    results, hourly_lookup = collect_results(locations, activities_cfg, args)

    if not results:
        print("No results - check your filters, or that locations.yaml/activities.yaml activity keys line up.")
        return 0

    if args.text:
        print_text_report(results, args.explain, use_color=not args.no_color)
        return 0

    html_doc = render_html(results, _generated_label(), hourly_lookup)
    out_path = Path(args.out).resolve()
    out_path.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {out_path}")
    if args.open:
        webbrowser.open(out_path.as_uri())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
