"""Renders scored results as a self-contained static HTML report.

Design intent: a trailhead information board crossed with a marine
forecast bulletin, not a generic SaaS dashboard - Zilla Slab (routed-sign
character) for headings and the score numerals, Public Sans (built for
civic/information use) for body text and stat chips, a eucalypt/harbour
palette instead of the usual cream-and-terracotta, and a small custom
pictogram set (svg_icons.py) instead of emoji so it renders identically
everywhere.

The whole file - fonts included - is embedded as data URIs, so it opens
standalone with no network access and is safe to publish as a Claude
Artifact as-is.
"""

from __future__ import annotations

import base64
import datetime as dt
import html
import re
from pathlib import Path

from svg_icons import sprite_defs, use

FONTS_DIR = Path(__file__).resolve().parent / "assets" / "fonts"

DISPLAY_NAMES = {
    "kayaking_sea": "kayaking (sea)",
    "kayaking_freshwater": "kayaking (sheltered)",
    "kite_practice": "kite practice",
    "beach_day": "beach day",
}

ACTIVITY_ICON = {
    "climbing": "climbing",
    "hiking": "hiking",
    "swimming": "swimming",
    "snorkelling": "snorkelling",
    "scuba": "scuba",
    "surfing": "surfing",
    "kayaking_sea": "kayaking",
    "kayaking_freshwater": "kayaking",
    "kitesurfing": "kitesurfing",
    "kite_practice": "kitesurfing",
    "sailing": "sailing",
    "city_touring": "city_touring",
    "beach_day": "beach_day",
}

# Cards (and the Sports checklist) group by activity category in this order
# rather than sorting by score, so the same sport always lands in the same
# place on the page instead of jumping around day to day. Anything not
# listed (e.g. "swimming", currently unused - see README) sorts after
# everything named here, in whatever order it's encountered.
ACTIVITY_ORDER = [
    "hiking", "climbing", "kite_practice", "city_touring", "beach_day",
    "surfing", "sailing", "kitesurfing", "kayaking_sea", "kayaking_freshwater",
    "snorkelling", "scuba",
]
ACTIVITY_ORDER_INDEX = {key: i for i, key in enumerate(ACTIVITY_ORDER)}


def _activity_sort_key(activity_key: str) -> int:
    return ACTIVITY_ORDER_INDEX.get(activity_key, len(ACTIVITY_ORDER))

BONUS_ICON = {
    "whales": "whale",
    "offshore/clean": "wind",
    "flat water": "wave",
    "bluebottles likely": "bluebottle",
    "bluebottles likely (peak)": "bluebottle",
}

STATUS_LABELS = {"great": "Great", "good": "Good", "acceptable": "Acceptable", "marginal": "Marginal", "poor": "Poor"}

# Short display labels for the scoring breakdown's factor column - the raw
# config/open_meteo variable names (e.g. "sea_surface_temperature_avg") ran
# long enough to crowd out the points columns next to them. Anything not
# listed falls back to a de-slugged version of the raw name (see _factor_label).
FACTOR_LABELS = {
    "friction_index": "friction",
    "gust_ratio": "gustiness",
    "rain_24_to_72h": "rain (24-72h)",
    "rain_prior_24h": "rain (24h)",
    "rain_prior_48h": "rain (48h)",
    "rain_probability_max": "rain chance",
    "rain_total": "rain",
    "sea_surface_temperature_avg": "sea temp",
    "swell_period_avg": "swell period",
    "swell_wave_height_max": "swell height",
    "temperature_avg": "temperature",
    "uv_max": "UV",
    "visibility_min": "visibility",
    "wave_height_max": "wave height",
    "wind_speed_max": "wind speed",
    "wind_wave_height_max": "wind waves",
}


def _factor_label(variable: str, scope: str = "window") -> str:
    """A couple of activities (hiking, climbing) score the same variable
    twice at different scopes - e.g. rain during the hike window (heavily
    weighted) and rain for the rest of the day outside it (lightly weighted,
    for muddy trail conditions on the way in/out). Same variable, same
    label, would otherwise show as two identical, unexplained "rain" rows -
    so a non-default scope gets a suffix; the default "window" scope (the
    vast majority of rows) stays unsuffixed."""
    label = FACTOR_LABELS.get(variable, variable.replace("_", " "))
    if scope == "outside_window":
        return f"{label} (rest of day)"
    if scope == "full_day":
        return f"{label} (all day)"
    return label


def _kt(kmh):
    return None if kmh is None else kmh / 1.852


def _score_color(v10) -> str:
    """v10 is the 0-10 displayed score - reuses the same 5-tier grading as
    the card meter/dot so the trend chart colour lines up with what you'd
    see on the card itself."""
    return f"var(--score-{score_status(v10 * 10)})"


# (key, label, unit, decimals, getter, colour-picker) - drives the per-card
# "Forecast trend" dropdown. A metric is skipped entirely for a given
# location/activity if none of its days have data for it (e.g. wave height
# at an inland spot). Total score leads (and is the default shown) since
# that's usually what you actually opened the widget to check; the getter
# reads "score_total" which _render_trend_widget injects per day (score
# isn't part of the window context - it's the overall scored result).
METRICS = [
    ("score", "Total score", "/10", 1, lambda w: (w["score_total"] / 10) if w.get("score_total") is not None else None, _score_color),
    ("temp", "Temperature", "°C", 0, lambda w: w.get("temperature_max"), lambda v: "#d85c3f"),
    ("rain_prob", "Chance of rain", "%", 0, lambda w: w.get("rain_probability_max"), lambda v: "#4a86c9"),
    ("uv", "UV index", "", 0, lambda w: w.get("uv_max"), lambda v: f"var(--{uv_status(v)})"),
    ("wind", "Wind speed", " kt", 0, lambda w: _kt(w.get("wind_speed_max")), lambda v: "#2f9a92"),
    ("wave", "Wave height", " m", 1, lambda w: w.get("wave_height_max"), lambda v: "#2f8fbf"),
    ("sea_temp", "Sea temperature", "°C", 0, lambda w: w.get("sea_surface_temperature_avg"), lambda v: "#1f6f96"),
]

# Same idea as METRICS but reading raw hourly fields (open_meteo.py's HOURLY_*
# names) instead of the window-aggregated ones, for the per-card "Hourly
# detail" widget on the soonest couple of days. Chance of rain leads (and is
# the default shown) since it's usually the first thing you actually want to
# check hour-by-hour. No "Total score" here - the overall score is a whole-
# window figure, not something that varies meaningfully hour to hour.
HOURLY_METRICS = [
    ("rain_prob", "Chance of rain", "%", 0, lambda h: h.get("precipitation_probability"), lambda v: "#4a86c9"),
    ("temp", "Temperature", "°C", 0, lambda h: h.get("temperature_2m"), lambda v: "#d85c3f"),
    ("uv", "UV index", "", 0, lambda h: h.get("uv_index"), lambda v: f"var(--{uv_status(v)})"),
    ("wind", "Wind speed", " kt", 0, lambda h: _kt(h.get("wind_speed_10m")), lambda v: "#2f9a92"),
    ("wave", "Wave height", " m", 1, lambda h: h.get("wave_height"), lambda v: "#2f8fbf"),
    ("sea_temp", "Sea temperature", "°C", 0, lambda h: h.get("sea_surface_temperature"), lambda v: "#1f6f96"),
]

# The hourly widget only shows this range so all bars fit without scrolling -
# outside typical daylight/activity hours is rarely what you're checking for.
HOURLY_DISPLAY_RANGE = range(7, 22)  # 7am-9pm inclusive


def _hour_label(hour: int) -> str:
    if hour == 0:
        return "12"
    if hour <= 12:
        return str(hour)
    return str(hour - 12)


def display_name(activity_key: str) -> str:
    return DISPLAY_NAMES.get(activity_key, activity_key.replace("_", " "))


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _b64_font(filename: str) -> str:
    return base64.b64encode((FONTS_DIR / filename).read_bytes()).decode("ascii")


def _font_faces() -> str:
    faces = [
        ("Public Sans", 400, "PublicSans-Regular.woff2"),
        ("Public Sans", 600, "PublicSans-SemiBold.woff2"),
        ("Zilla Slab", 500, "ZillaSlab-Medium.woff2"),
        ("Zilla Slab", 700, "ZillaSlab-Bold.woff2"),
    ]
    blocks = []
    for family, weight, filename in faces:
        data = _b64_font(filename)
        blocks.append(
            f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:normal;"
            f"font-display:swap;src:url(data:font/woff2;base64,{data}) format('woff2');}}"
        )
    return "\n".join(blocks)


def sky_state(window: dict) -> tuple[str, str]:
    if window.get("storm_present"):
        return "sky-storm", "Storm"
    rain = window.get("rain_total") or 0
    if rain > 0.5:
        return "sky-rain", "Rain"
    cloud = window.get("cloud_cover_avg")
    if cloud is None:
        return "sky-cloudy", "Unknown"
    if cloud >= 70:
        return "sky-cloudy", "Cloudy"
    if cloud >= 30:
        return "sky-partly", "Partly cloudy"
    return "sky-clear", "Clear"


def uv_status(uv_max):
    if uv_max is None:
        return "good"
    if uv_max >= 11:
        return "uv-extreme"   # standard international UV Index scale reserves violet/purple for Extreme (11+)
    if uv_max >= 8:
        return "serious"
    if uv_max >= 6:
        return "warning"
    return "good"


def score_status(score: float) -> str:
    """Score is on the internal 0-100 scale; thresholds are the /10-displayed
    boundaries (9.5/8.5/7.5/6.5) x10."""
    if score >= 95:
        return "great"
    if score >= 85:
        return "good"
    if score >= 75:
        return "acceptable"
    if score >= 65:
        return "marginal"
    return "poor"


def _stat_chips(window: dict) -> str:
    chips = []
    sky_icon, sky_label = sky_state(window)
    chips.append(f'<span class="chip">{use(sky_icon)}{sky_label}</span>')
    if window.get("temperature_max") is not None:
        chips.append(f'<span class="chip">{use("temp")}{window["temperature_max"]:.0f}°C</span>')
    if window.get("wind_speed_max") is not None:
        chips.append(f'<span class="chip">{use("wind")}{_kt(window["wind_speed_max"]):.0f} kt</span>')
    uv = window.get("uv_max")
    if uv is not None:
        status = uv_status(uv)
        chips.append(f'<span class="chip">{use("uv", style=f"color:var(--{status})")}UV {uv:.0f}</span>')
    if window.get("wave_height_max") is not None:
        chips.append(f'<span class="chip">{use("wave")}{window["wave_height_max"]:.1f} m</span>')
    if window.get("sea_surface_temperature_avg") is not None:
        chips.append(f'<span class="chip">{use("sea-temp")}{window["sea_surface_temperature_avg"]:.0f}°C</span>')
    return "".join(chips)


def _bonus_pills(result: dict) -> str:
    if not result["bonuses_hit"]:
        return ""
    pills = []
    for bonus in result["bonuses_hit"]:
        name, points = bonus["name"], bonus["points"]
        icon_name = BONUS_ICON.get(name, "sparkle")
        variant = "pill-penalty" if points < 0 else "pill"
        pills.append(f'<span class="{variant}">{use(icon_name)}{html.escape(name)}</span>')
    return f'<div class="bonuses">{"".join(pills)}</div>'


def _breakdown(result: dict) -> str:
    if not result["breakdown"]:
        return ""
    rows = []
    for entry in result["breakdown"]:
        value = entry["value"]
        value_str = "—" if value is None else (f"{value:.2f}" if isinstance(value, float) else str(value))
        points_str = "n/a" if entry["points"] is None else f"{entry['points']:.2f}"
        max_str = "n/a" if entry["max_points"] is None else f"{entry['max_points']:.2f}"
        label = entry["variable"] if entry["kind"] == "bonus" else _factor_label(entry["variable"], entry.get("scope", "window"))
        rows.append(
            f"<tr><td>{html.escape(label)}</td>"
            f"<td>{value_str}</td><td>{points_str}</td><td>{max_str}</td></tr>"
        )
    return (
        '<details class="breakdown"><summary>Scoring</summary>'
        '<table><colgroup><col class="col-factor"><col><col><col></colgroup>'
        '<thead><tr><th>factor</th><th>value</th><th>points</th><th>max</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></details>"
    )


def _render_card(loc_name: str, activity_key: str, result: dict, window: dict, hourly_widget: str = "") -> str:
    icon = ACTIVITY_ICON.get(activity_key, "hiking")
    label = display_name(activity_key)
    driving_attr = "1" if window.get("requires_driving") else "0"

    if result["gated"]:
        return f"""
        <article class="card card-gated" data-activity="{activity_key}" data-driving="{driving_attr}">
          <div class="card-head">
            <span class="activity-icon">{use(icon)}</span>
            <div class="card-title"><h3>{html.escape(label)}</h3><p>{html.escape(loc_name)}</p></div>
          </div>
          <div class="gate-banner">{use("warning")}<span>{html.escape(result['gate_reason'])}</span></div>
          <div class="chips">{_stat_chips(window)}</div>
        </article>"""

    status = score_status(result["score"])
    alert_banner = ""
    if result.get("park_alert"):
        closed = result.get("park_alert_closed")
        variant = "alert-details-closed" if closed else "alert-details"
        summary_label = "NPWS closure" if closed else "NPWS alert"
        # A dropdown rather than an always-open banner - still visibly flags that there
        # IS an alert (and how serious) without spending permanent card height on the
        # full text, which can run to a full sentence or two.
        alert_banner = (
            f'<details class="{variant}"><summary>{use("alert-park")}{summary_label}</summary>'
            f"<p>{html.escape(result['park_alert'])}</p></details>"
        )
    return f"""
    <article class="card" data-activity="{activity_key}" data-driving="{driving_attr}">
      <div class="card-head">
        <span class="activity-icon">{use(icon)}</span>
        <div class="card-title"><h3>{html.escape(label)}</h3><p>{html.escape(loc_name)}</p></div>
        <div class="score">{result['score'] / 10:.1f}</div>
      </div>
      <div class="meter-row">
        <div class="meter-track"><div class="meter-fill status-{status}" style="width:{result['score']:.1f}%"></div></div>
        <span class="status-chip"><span class="dot status-{status}"></span>{STATUS_LABELS[status]}</span>
      </div>
      <div class="chips">{_stat_chips(window)}</div>
      {_bonus_pills(result)}
      {alert_banner}
      {hourly_widget}
      {_breakdown(result)}
    </article>"""


def _render_day(date_str: str, rows: list, open_by_default: bool, hourly_lookup: dict) -> str:
    weekday = dt.date.fromisoformat(date_str).strftime("%A")
    cards = []
    for loc, key, res, win in rows:
        hourly_widget = ""
        hours = hourly_lookup.get((loc, date_str))
        if hours:
            widget_id = f"hourly-{_slug(loc)}-{key}-{date_str}"
            hourly_widget = _render_hourly_widget(widget_id, hours)
        cards.append(_render_card(loc, key, res, win, hourly_widget))
    open_attr = " open" if open_by_default else ""
    return f"""
    <details class="day"{open_attr}>
      <summary class="day-head"><span class="day-date">{date_str}</span><span class="day-weekday">{weekday}</span></summary>
      <div class="card-grid">{"".join(cards)}</div>
    </details>"""


def _render_metric_bars(
    pairs: list, unit: str, decimals: int, color_fn, label_fn, extra_class: str = "", show_unit: bool = True,
    label_every: int = 1,
) -> str:
    """`label_every` can thin out the time/day label under each bar for a
    widget with a lot of bars - unused (every label shown) by both current
    callers, but left in case a future widget needs it.

    Bars and labels render as two separate flex rows (not one bar+label
    column each) so a label is never part of the fixed-height bar row - a
    wrapped/overflowing label used to shrink the flex space left for its
    bar, distorting the chart. Both rows use the same per-cell flex/gap so
    columns still line up."""
    present = [v for _, v in pairs if v is not None]
    chart_max = (max(present) * 1.15) if present and max(present) > 0 else 1
    bar_cells, label_cells = [], []
    for i, (x, value) in enumerate(pairs):
        x_label = label_fn(x) if i % label_every == 0 else ""
        label_cells.append(f'<span class="trend-day">{x_label}</span>')
        if value is None:
            bar_cells.append(
                '<div class="trend-bar-cell"><span class="trend-value">–</span>'
                '<div class="trend-track"></div></div>'
            )
            continue
        height_pct = max(4, round(value / chart_max * 100))
        color = color_fn(value)
        value_str = f"{value:.{decimals}f}{unit if show_unit else ''}"
        bar_cells.append(
            f'<div class="trend-bar-cell"><span class="trend-value">{value_str}</span>'
            f'<div class="trend-track"><div class="trend-bar" style="height:{height_pct}%;background:{color}"></div></div></div>'
        )
    classes = f"trend-bars {extra_class}".strip()
    return (
        f'<div class="{classes}">'
        f'<div class="trend-bars-row">{"".join(bar_cells)}</div>'
        f'<div class="trend-labels-row">{"".join(label_cells)}</div>'
        f"</div>"
    )


def _day_label(date_str: str) -> str:
    return dt.date.fromisoformat(date_str).strftime("%a %d")


def _unit_label(label: str, unit: str) -> str:
    unit = unit.strip()
    return f"{label} ({unit})" if unit else label


def _render_trend_widget(widget_id: str, day_rows: list) -> str:
    """`day_rows` is [(date_str, window, score), ...] - score is injected
    into each window as "score_total" so the "Total score" metric can read
    it via the same getter interface as every other metric. The unit (and
    for the score metric, the "/10") lives on the dropdown option rather
    than repeated over every one of the ~7 bars in the row."""
    merged_days = [(date_str, {**window, "score_total": score}) for date_str, window, score in day_rows]
    charts, options = [], []
    for key, label, unit, decimals, getter, color_fn in METRICS:
        pairs = [(date_str, getter(window)) for date_str, window in merged_days]
        if not any(v is not None for _, v in pairs):
            continue
        hidden_attr = "" if not charts else " hidden"
        bars_html = _render_metric_bars(pairs, unit, decimals, color_fn, _day_label, show_unit=False)
        charts.append(f'<div class="trend-chart" data-metric="{key}"{hidden_attr}>{bars_html}</div>')
        options.append(f'<option value="{key}">{_unit_label(label, unit)}</option>')

    if not charts:
        return ""

    onchange = (
        f"document.getElementById('{widget_id}').querySelectorAll('.trend-chart')"
        ".forEach(c => c.hidden = c.dataset.metric !== this.value)"
    )
    return f"""
    <div class="trend" id="{widget_id}">
      <div class="trend-head">
        <span class="trend-title">{use("chart")}Forecast trend</span>
        <select class="trend-select" onchange="{onchange}">{"".join(options)}</select>
      </div>
      {"".join(charts)}
    </div>"""


def _render_hourly_widget(widget_id: str, hours: list) -> str:
    """A collapsed-by-default per-card widget with an hourly (not daily)
    bar chart - only built for the soonest couple of days (see render()),
    since fetching/rendering this for the whole forecast window would be
    a lot of markup for days that are still ~a week of uncertainty away.
    The unit lives on the dropdown option (e.g. "Wind speed (kt)") rather
    than repeated over every one of the ~15 bars in the row. Every hour gets
    a label, just the bare hour number (no am/pm) - reads fine since the
    bars are already in time order left to right."""
    sorted_hours = [h for h in sorted(hours, key=lambda h: h["hour"]) if h["hour"] in HOURLY_DISPLAY_RANGE]
    charts, options = [], []
    for key, label, unit, decimals, getter, color_fn in HOURLY_METRICS:
        pairs = [(h["hour"], getter(h)) for h in sorted_hours]
        if not any(v is not None for _, v in pairs):
            continue
        hidden_attr = "" if not charts else " hidden"
        bars_html = _render_metric_bars(
            pairs, unit, decimals, color_fn, _hour_label, extra_class="trend-bars-hourly", show_unit=False,
        )
        charts.append(f'<div class="trend-chart" data-metric="{key}"{hidden_attr}>{bars_html}</div>')
        options.append(f'<option value="{key}">{_unit_label(label, unit)}</option>')

    if not charts:
        return ""

    onchange = (
        f"document.getElementById('{widget_id}').querySelectorAll('.trend-chart')"
        ".forEach(c => c.hidden = c.dataset.metric !== this.value)"
    )
    return f"""
    <details class="trend-details" id="{widget_id}">
      <summary class="trend-summary">{use("chart")}Hourly breakdown</summary>
      <div class="trend-body">
        <select class="trend-select" onchange="{onchange}">{"".join(options)}</select>
        {"".join(charts)}
      </div>
    </details>"""


def _render_filter_bar(results: list) -> str:
    """Two checklist blocks under the header: which sports to show (only
    activities actually present in this run's results, so it's never more
    cluttered than what's relevant), and whether to include locations that
    aren't easily reachable from Sydney by public transport (unticked by
    default - see the `requires_driving` flag in locations.yaml). Both are
    plain vertical bulleted lists rather than a wrapping row of pills, and
    both persist client-side (localStorage) via the script at the bottom of
    the page, so they survive a --serve Refresh and reopening a static
    report."""
    activity_keys = sorted({activity_key for _, _, activity_key, _, _ in results}, key=_activity_sort_key)
    if not activity_keys:
        return ""
    options = []
    for key in activity_keys:
        icon = ACTIVITY_ICON.get(key, "hiking")
        label = display_name(key)
        options.append(
            f'<label class="filter-option"><input type="checkbox" data-activity="{key}" checked>'
            f"{use(icon)}{html.escape(label)}</label>"
        )
    return f"""
    <div class="filter-bar" id="sport-filter">
      <div class="filter-bar-inner">
        <div class="filter-block filter-block-sports">
          <span class="filter-label">Sports</span>
          <div class="filter-options filter-options-grid">{"".join(options)}</div>
        </div>
        <div class="filter-block">
          <span class="filter-label">Access</span>
          <div class="filter-options">
            <label class="filter-option"><input type="checkbox" id="driving-toggle">{use("car")}Include drive-only spots</label>
          </div>
        </div>
      </div>
    </div>"""


_FILTER_SCRIPT = """
<script>
(function () {
  var ACTIVITY_KEY = 'wp-activity-filter';
  var DRIVING_KEY = 'wp-driving-included';
  var checkboxes = Array.prototype.slice.call(document.querySelectorAll('#sport-filter input[data-activity]'));
  var drivingToggle = document.getElementById('driving-toggle');
  if (!checkboxes.length && !drivingToggle) return;

  function loadState() {
    try { return JSON.parse(localStorage.getItem(ACTIVITY_KEY) || '{}'); } catch (e) { return {}; }
  }
  function saveState(state) {
    try { localStorage.setItem(ACTIVITY_KEY, JSON.stringify(state)); } catch (e) { /* private browsing etc - just don't persist */ }
  }
  function loadDriving() {
    try { return localStorage.getItem(DRIVING_KEY) === '1'; } catch (e) { return false; }
  }
  function saveDriving(included) {
    try { localStorage.setItem(DRIVING_KEY, included ? '1' : '0'); } catch (e) { /* private browsing etc */ }
  }

  function apply() {
    var state = loadState();
    var active = {};
    checkboxes.forEach(function (cb) {
      var key = cb.dataset.activity;
      var checked = state.hasOwnProperty(key) ? state[key] : true;
      cb.checked = checked;
      active[key] = checked;
      cb.closest('.filter-option').classList.toggle('is-active', checked);
    });
    var drivingIncluded = loadDriving();
    if (drivingToggle) {
      drivingToggle.checked = drivingIncluded;
      drivingToggle.closest('.filter-option').classList.toggle('is-active', drivingIncluded);
    }
    document.querySelectorAll('main [data-activity]').forEach(function (el) {
      var activityOk = active[el.dataset.activity] !== false;
      var drivingOk = drivingIncluded || el.dataset.driving !== '1';
      el.style.display = (activityOk && drivingOk) ? '' : 'none';
    });
    document.querySelectorAll('.day').forEach(function (day) {
      var anyVisible = Array.prototype.slice.call(day.querySelectorAll('.card')).some(function (c) {
        return c.style.display !== 'none';
      });
      day.style.display = anyVisible ? '' : 'none';
    });
    document.querySelectorAll('.trends-section').forEach(function (section) {
      var anyVisible = Array.prototype.slice.call(section.querySelectorAll('.trend-card')).some(function (c) {
        return c.style.display !== 'none';
      });
      section.style.display = anyVisible ? '' : 'none';
    });
  }

  checkboxes.forEach(function (cb) {
    cb.addEventListener('change', function () {
      var state = loadState();
      state[cb.dataset.activity] = cb.checked;
      saveState(state);
      apply();
    });
  });
  if (drivingToggle) {
    drivingToggle.addEventListener('change', function () {
      saveDriving(drivingToggle.checked);
      apply();
    });
  }

  apply();
})();
</script>"""


def _render_trends_section(results: list) -> str:
    groups: dict[tuple, list] = {}
    for date_str, loc_name, activity_key, result, window in results:
        groups.setdefault((loc_name, activity_key), []).append((date_str, window, result.get("score")))
    for rows in groups.values():
        rows.sort(key=lambda r: r[0])

    cards = []
    # Grouped by activity category (see ACTIVITY_ORDER), same as the day card grids,
    # rather than plain alphabetical, so a sport lands in the same place here too.
    for (loc_name, activity_key), day_rows in sorted(groups.items(), key=lambda g: (_activity_sort_key(g[0][1]), g[0])):
        widget_id = f"trend-{_slug(loc_name)}-{activity_key}"
        widget = _render_trend_widget(widget_id, day_rows)
        if not widget:
            continue
        icon = ACTIVITY_ICON.get(activity_key, "hiking")
        label = display_name(activity_key)
        driving_attr = "1" if day_rows and day_rows[0][1].get("requires_driving") else "0"
        cards.append(f"""
        <div class="trend-card" data-activity="{activity_key}" data-driving="{driving_attr}">
          <div class="card-head">
            <span class="activity-icon">{use(icon)}</span>
            <div class="card-title"><h3>{html.escape(label)}</h3><p>{html.escape(loc_name)}</p></div>
          </div>
          {widget}
        </div>""")

    if not cards:
        return ""

    return f"""
    <details class="trends-section">
      <summary class="trends-head"><span>{use("chart")}Forecast trends</span></summary>
      <div class="trends-grid">{"".join(cards)}</div>
    </details>"""


CSS_BODY = """
:root {
  --ground:#eef1ea; --surface:#ffffff; --surface-2:#f5f7f2;
  --ink:#12201f; --ink-soft:#45534f; --muted:#7c8a83;
  --line:rgba(18,32,31,0.12);
  --accent:#0b6e73; --accent-soft:#dcecec;
  --good:#0ca30c; --warning:#fab219; --serious:#ec835a; --critical:#d03b3b; --uv-extreme:#8b5cf6;
  --critical-soft:#fbe4e2; --warning-soft:#fdf0d6;
  --meter-track:#e4e8df;
  /* Overall score grading (5 tiers, distinct from the --good/--warning/--serious/--critical/--uv-extreme
     roles above which are reserved for UV severity and gate/alert banners). */
  --score-great:#0ca30c; --score-good:#6fa617; --score-acceptable:#d9a412;
  --score-marginal:#e8792f; --score-poor:#d03b3b;
}
/* Light is the default regardless of OS/browser preference - only an explicit
   data-theme="dark" (e.g. a viewer's theme toggle) switches to dark. */
:root[data-theme="dark"] {
  --ground:#0f1513; --surface:#171f1d; --surface-2:#1c2624;
  --ink:#eef1ea; --ink-soft:#b7c2bd; --muted:#7e8b86;
  --line:rgba(238,241,234,0.14);
  --accent:#3fb0b6; --accent-soft:#163634;
  --critical-soft:#3a1f1c; --warning-soft:#3a2f14;
  --meter-track:#26302d;
  --score-great:#0ca30c; --score-good:#6fa617; --score-acceptable:#d9a412;
  --score-marginal:#e8792f; --score-poor:#d03b3b;
}
:root[data-theme="light"] {
  --ground:#eef1ea; --surface:#ffffff; --surface-2:#f5f7f2;
  --ink:#12201f; --ink-soft:#45534f; --muted:#7c8a83;
  --line:rgba(18,32,31,0.12);
  --accent:#0b6e73; --accent-soft:#dcecec;
  --critical-soft:#fbe4e2; --warning-soft:#fdf0d6;
  --meter-track:#e4e8df;
  --score-great:#0ca30c; --score-good:#6fa617; --score-acceptable:#d9a412;
  --score-marginal:#e8792f; --score-poor:#d03b3b;
}

* { box-sizing:border-box; }
body {
  margin:0; background:var(--ground); color:var(--ink);
  font-family:'Public Sans', system-ui, -apple-system, "Segoe UI", sans-serif;
  line-height:1.45; -webkit-font-smoothing:antialiased;
}
h1, h2, h3 { font-family:'Zilla Slab', Georgia, serif; margin:0; text-wrap:balance; }
a { color:var(--accent); }

.masthead { border-bottom:3px solid var(--accent); background:var(--surface); padding:30px 24px 24px; }
.masthead-inner { max-width:1180px; margin:0 auto; display:flex; align-items:flex-end; justify-content:space-between; gap:20px; flex-wrap:wrap; }
.masthead-text { flex:1; min-width:240px; }
.masthead h1 { font-size:clamp(26px,4vw,38px); font-weight:700; letter-spacing:.2px; }
.tagline { margin:8px 0 0; color:var(--ink-soft); font-size:14.5px; max-width:65ch; }

.filter-bar { background:var(--surface); border-bottom:1px solid var(--line); }
.filter-bar-inner { max-width:1180px; margin:0 auto; padding:14px 24px; display:flex; gap:36px; flex-wrap:wrap; }
.filter-block { min-width:160px; }
.filter-block-sports { flex:1 1 480px; }
.filter-label { display:block; font-size:11.5px; font-weight:600; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; margin-bottom:7px; }
.filter-options { display:flex; flex-direction:column; align-items:flex-start; gap:5px; }
/* Sports has ~10+ entries - spread across columns instead of one tall column, so the
   bar stays a couple of rows deep rather than something you have to scroll past. Columns
   are wide enough for the longest label ("kayaking (sheltered)") on one line - narrower
   columns let long labels wrap to a second line, which made some rows taller than others. */
.filter-options-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(190px, 1fr)); gap:6px 18px; }
.filter-option {
  display:flex; align-items:center; gap:7px; font-size:13px; color:var(--ink-soft);
  cursor:pointer; user-select:none; padding:1px 0; white-space:nowrap;
}
.filter-option input { margin:0; accent-color:var(--accent); }
.filter-option .icon-glyph { width:15px; height:15px; color:var(--muted); }
.filter-option.is-active { color:var(--accent); font-weight:600; }
.filter-option.is-active .icon-glyph { color:var(--accent); }

main { max-width:1180px; margin:0 auto; padding:8px 24px 40px; }

.day { margin-top:20px; }
.day-head {
  display:flex; align-items:baseline; gap:12px; cursor:pointer; user-select:none;
  background:var(--accent); color:#fff; padding:9px 18px; border-radius:8px 8px 0 0;
  font-weight:500; list-style:none;
}
.day-head::-webkit-details-marker { display:none; }
.day-head::before { content:"\\25B8"; font-size:13px; transition:transform .15s ease; }
.day[open] > .day-head::before { transform:rotate(90deg); }
.day-head:focus-visible { outline:2px solid var(--ink); outline-offset:-2px; }
.day:not([open]) .day-head { border-radius:8px; }
.day-date { font-size:19px; }
.day-weekday { font-size:12.5px; text-transform:uppercase; letter-spacing:.09em; opacity:.88; font-family:'Public Sans', sans-serif; font-weight:600; }

.card-grid {
  display:grid; grid-template-columns:repeat(auto-fill, minmax(260px, 1fr)); gap:10px;
  background:var(--surface-2); border:1px solid var(--line); border-top:none; border-radius:0 0 8px 8px;
  padding:12px;
}

.card { background:var(--surface); border:1px solid var(--line); border-radius:9px; padding:10px 13px; display:flex; flex-direction:column; gap:7px; }
.card-gated { border-color:var(--critical); }
.card-head { display:flex; align-items:flex-start; gap:9px; }
.activity-icon .icon-glyph { width:28px; height:28px; color:var(--accent); flex:none; }
.card-title { flex:1; min-width:0; padding-top:1px; }
.card-title h3 { font-size:14.5px; font-weight:500; }
.card-title p { margin:1px 0 0; font-size:11.5px; color:var(--ink-soft); }
.score { font-family:'Zilla Slab', Georgia, serif; font-weight:700; font-size:23px; line-height:1; color:var(--ink); padding-left:4px; }
.score::after { content:"/10"; font-size:11.5px; font-weight:600; color:var(--muted); margin-left:2px; font-family:'Public Sans', sans-serif; }

.meter-row { display:flex; align-items:center; gap:8px; }
.meter-track { flex:1; height:6px; border-radius:5px; background:var(--meter-track); overflow:hidden; }
.meter-fill { height:100%; border-radius:5px; transition:width .5s ease; }
.meter-fill.status-great { background:var(--score-great); }
.meter-fill.status-good { background:var(--score-good); }
.meter-fill.status-acceptable { background:var(--score-acceptable); }
.meter-fill.status-marginal { background:var(--score-marginal); }
.meter-fill.status-poor { background:var(--score-poor); }
@media (prefers-reduced-motion: reduce) { .meter-fill { transition:none; } }

.status-chip { font-size:12px; color:var(--ink-soft); display:inline-flex; align-items:center; white-space:nowrap; }
.dot { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:6px; }
.dot.status-great { background:var(--score-great); }
.dot.status-good { background:var(--score-good); }
.dot.status-acceptable { background:var(--score-acceptable); }
.dot.status-marginal { background:var(--score-marginal); }
.dot.status-poor { background:var(--score-poor); }

.chips { display:flex; flex-wrap:wrap; gap:5px 7px; }
.chip {
  display:inline-flex; align-items:center; gap:5px; font-size:12px; color:var(--ink-soft);
  background:var(--surface-2); border:1px solid var(--line); border-radius:999px; padding:3px 9px 3px 6px;
  font-variant-numeric:tabular-nums;
}
.chip .icon-glyph { width:16px; height:16px; color:var(--muted); }

.bonuses { display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
.pill, .pill-penalty {
  display:inline-flex; align-items:center; gap:5px; font-size:12px; font-weight:600;
  border-radius:999px; padding:3px 10px 3px 7px;
}
.pill { color:var(--accent); background:var(--accent-soft); }
.pill-penalty { color:var(--critical); background:var(--critical-soft); }
.pill .icon-glyph, .pill-penalty .icon-glyph { width:15px; height:15px; }

.gate-banner {
  display:flex; align-items:center; gap:9px; border-radius:8px; padding:9px 12px; font-size:13px; font-weight:600;
  background:var(--critical-soft); color:var(--critical);
}
.gate-banner .icon-glyph { width:20px; height:20px; flex:none; }

/* NPWS alert - a dropdown rather than an always-open banner (see _render_card), but the
   summary row itself is always visible so you still see at a glance whether a card has
   one, and how serious, without spending the space of the full text. */
details.alert-details, details.alert-details-closed { margin-top:-1px; }
.alert-details summary, .alert-details-closed summary {
  display:inline-flex; align-items:center; gap:6px; cursor:pointer; user-select:none; list-style:none;
  font-size:12px; font-weight:600;
}
.alert-details summary { color:#c9821a; }
.alert-details-closed summary { color:var(--critical); }
.alert-details summary::-webkit-details-marker, .alert-details-closed summary::-webkit-details-marker { display:none; }
.alert-details summary::before, .alert-details-closed summary::before { content:"\\25B8\\0020"; }
.alert-details[open] summary::before, .alert-details-closed[open] summary::before { content:"\\25BE\\0020"; }
.alert-details summary:focus-visible, .alert-details-closed summary:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
.alert-details summary .icon-glyph, .alert-details-closed summary .icon-glyph { width:15px; height:15px; }
.alert-details summary .icon-glyph { color:#c9821a; }
.alert-details-closed summary .icon-glyph { color:var(--critical); }
.alert-details p, .alert-details-closed p { margin:5px 0 0; font-size:12px; color:var(--ink-soft); }

details.breakdown { margin-top:-2px; }
details.breakdown summary {
  cursor:pointer; font-size:12px; color:var(--muted); list-style:none; user-select:none;
}
details.breakdown summary::-webkit-details-marker { display:none; }
details.breakdown summary::before { content:"\\25B8\\0020"; }
details.breakdown[open] summary::before { content:"\\25BE\\0020"; }
details.breakdown summary:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
details.breakdown table { width:100%; border-collapse:collapse; margin-top:6px; font-size:10px; table-layout:fixed; }
/* The factor column holds names like "wind speed" or "swell height" - a plain equal
   4-way split left it truncated. It still gets extra width, but not so much that the
   numeric columns (especially points, the one you're actually scanning) get crowded. */
details.breakdown col.col-factor { width:38%; }
details.breakdown th, details.breakdown td { text-align:left; padding:2px 4px; border-bottom:1px solid var(--line); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
details.breakdown th { color:var(--muted); font-weight:600; text-transform:uppercase; font-size:9px; letter-spacing:.04em; }
details.breakdown td:nth-child(2), details.breakdown td:nth-child(3), details.breakdown td:nth-child(4) { font-variant-numeric:tabular-nums; }

.trends-section { margin-top:28px; }
.trends-head {
  display:flex; align-items:center; gap:8px; cursor:pointer; user-select:none; list-style:none;
  font-family:'Zilla Slab', Georgia, serif; font-size:19px; font-weight:500; color:var(--ink);
  padding:10px 2px; border-bottom:2px solid var(--line);
}
.trends-head::-webkit-details-marker { display:none; }
.trends-head .icon-glyph { width:22px; height:22px; color:var(--accent); }
.trends-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(340px, 1fr)); gap:14px; padding-top:16px; }
.trend-card { background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:14px 16px; display:flex; flex-direction:column; gap:10px; }

.trend-head { display:flex; align-items:center; justify-content:space-between; gap:10px; }
.trend-title { display:inline-flex; align-items:center; gap:6px; font-size:12.5px; font-weight:600; color:var(--ink-soft); }
.trend-title .icon-glyph { width:15px; height:15px; color:var(--muted); }
.trend-select {
  font:inherit; font-size:12.5px; color:var(--ink); background:var(--surface-2); border:1px solid var(--line);
  border-radius:6px; padding:4px 8px;
}
/* Bars and their time/day labels are two separate flex rows (see
   _render_metric_bars) rather than stacked inside one column per bar - that
   way a long/wrapped label can never eat into the fixed-height row above it
   and shrink the bar it belongs to. Both rows share the same per-cell
   flex-basis and gap so the two rows still line up column-for-column. */
.trend-bars { display:flex; flex-direction:column; gap:4px; }
.trend-bars-row { display:flex; align-items:flex-end; gap:6px; height:110px; }
.trend-bar-cell { display:flex; flex-direction:column; align-items:center; justify-content:flex-end; flex:1; height:100%; min-width:0; }
.trend-value { font-size:10.5px; color:var(--ink-soft); margin-bottom:4px; font-variant-numeric:tabular-nums; white-space:nowrap; }
.trend-track { flex:1; width:100%; max-width:26px; display:flex; align-items:flex-end; }
.trend-bar { width:100%; border-radius:4px 4px 0 0; min-height:2px; }
.trend-labels-row { display:flex; gap:6px; }
.trend-day {
  flex:1; min-width:0; text-align:center; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
  font-size:9.5px; color:var(--muted); text-transform:uppercase; letter-spacing:.03em;
}

/* Hourly breakdown: a collapsed-by-default per-card widget, same bar mechanics
   as the daily trend but with one bar per hour, packed into the card width
   (no horizontal scroll) - narrower columns and shorter labels ("7a" not
   "7am") keep it fitting without needing to wrap or truncate. */
details.trend-details { margin-top:-2px; }
.trend-summary {
  display:inline-flex; align-items:center; gap:6px; cursor:pointer; user-select:none; list-style:none;
  font-size:12px; font-weight:600; color:var(--ink-soft);
}
.trend-summary::-webkit-details-marker { display:none; }
.trend-summary::before { content:"\\25B8\\0020"; }
details.trend-details[open] .trend-summary::before { content:"\\25BE\\0020"; }
.trend-summary:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
.trend-summary .icon-glyph { width:15px; height:15px; color:var(--muted); }
.trend-body { margin-top:8px; display:flex; flex-direction:column; gap:8px; }
.trend-bars-hourly .trend-bars-row, .trend-bars-hourly .trend-labels-row { gap:2px; }
.trend-bars-hourly .trend-value { font-size:8px; }
.trend-bars-hourly .trend-day { font-size:7px; }
.trend-bars-hourly .trend-track { max-width:none; }

footer { max-width:1180px; margin:26px auto 0; padding:0 24px; color:var(--muted); font-size:12px; }

.icon-glyph { fill:none; stroke:currentColor; stroke-width:1.6; stroke-linecap:round; stroke-linejoin:round; width:20px; height:20px; flex:none; }
.refresh-btn {
  display:inline-flex; align-items:center; gap:7px; font:inherit; font-weight:600; font-size:13.5px;
  color:#fff; background:var(--accent); border:none; border-radius:999px; padding:8px 16px; cursor:pointer;
}
.refresh-btn:hover { filter:brightness(1.08); }
.refresh-btn:focus-visible { outline:2px solid var(--ink); outline-offset:2px; }
.refresh-btn .icon-glyph { width:16px; height:16px; }
"""


SOONEST_DAYS_FOR_HOURLY = 2


def render(results: list, generated_label: str, hourly_lookup: dict | None = None, live: bool = False) -> str:
    """`results` is main.py's list of (date_str, location_name, activity_key,
    result, window_ctx) tuples. `hourly_lookup` is main.py's
    {(location_name, date_str): [hour_record, ...]} - used for the per-card
    "Hourly breakdown" widget, built only for the soonest
    `SOONEST_DAYS_FOR_HOURLY` days (rendering it for the whole forecast
    window would be a lot of markup for days still a week of uncertainty
    away). `live=True` (used by `--serve`) adds a Refresh button that
    reloads the page - meaningless on a static file (there's no server to
    hit for fresh data), so it's omitted there."""
    hourly_lookup = hourly_lookup or {}
    by_date: dict[str, list] = {}
    for date_str, loc_name, activity_key, result, window in results:
        by_date.setdefault(date_str, []).append((loc_name, activity_key, result, window))
    for rows in by_date.values():
        # Grouped by activity category (see ACTIVITY_ORDER) rather than sorted purely by
        # score, so the same sport lands in the same place on the page every day instead
        # of jumping around as scores shift - score still breaks ties within a category.
        rows.sort(key=lambda r: (_activity_sort_key(r[1]), -(r[2]["score"] or 0)))

    sorted_dates = sorted(by_date)
    soonest_dates = set(sorted_dates[:SOONEST_DAYS_FOR_HOURLY])
    hourly_for_soonest = {k: v for k, v in hourly_lookup.items() if k[1] in soonest_dates}
    sections = "".join(
        _render_day(d, by_date[d], open_by_default=(i == 0), hourly_lookup=hourly_for_soonest)
        for i, d in enumerate(sorted_dates)
    )
    trends = _render_trends_section(results)
    filter_bar = _render_filter_bar(results)
    css = _font_faces() + CSS_BODY

    refresh_button = (
        f'<button class="refresh-btn" onclick="location.reload()">{use("refresh")}Refresh</button>' if live else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NSW Outdoor Conditions</title>
<style>{css}</style>
</head>
<body>
{sprite_defs()}
<header class="masthead"><div class="masthead-inner">
  <div class="masthead-text">
    <h1>NSW Outdoor Conditions</h1>
    <p class="tagline">Live conditions scored per activity and spot, weighted to each activity's actual time-of-day window. Generated {html.escape(generated_label)}.</p>
  </div>
  {refresh_button}
</div></header>
{filter_bar}
<main>{sections if sections else '<p style="padding:32px 0;color:var(--muted)">No results for the current filters.</p>'}{trends}</main>
<footer><p>Data: Open-Meteo (weather + marine forecast). Scores are a planning aid, not a safety authority - always check current conditions, advisories, and your own judgement before heading out.</p></footer>
{_FILTER_SCRIPT}
</body>
</html>"""
