# NSW Outdoor Activity Weather Planner

Pulls live hourly forecast data from [Open-Meteo](https://open-meteo.com)
(free, no API key) and scores each configured location/activity combination
for the next few days, so you can see at a glance where's worth heading
this weekend. Covers hiking, climbing, kite practice (land-based
trainer-kite handling), city touring, beach day, surfing, sailing,
kitesurfing, kayaking (sea and sheltered), snorkelling and scuba across the
Blue Mountains, Sydney, and further afield (Jervis Bay, South West Rocks
and a handful of other national parks).

Open-Meteo was picked because on top of standard weather it also serves
marine data (wave height, swell height/period, sea surface temperature)
with no signup, which covers surfing/kitesurfing/kayaking/snorkelling/scuba
without needing a second provider.

## Setup

```
pip install -r requirements.txt
```

## Run

```
python main.py
```

Writes a self-contained `report.html` (data and fonts embedded, no network
needed to view it) and prints its path - open it in a browser. Two
checklists sit under the header, each a plain vertical list of ticks rather
than a row of pills: **Sports** (only the activities that actually appear
in this run's results, with kayaking unticked by default - see
`DEFAULT_HIDDEN_ACTIVITIES` in html_report.py) and **Access** (a single
"Include drive-only spots" box). Untick a sport and its cards disappear
from every day (a day collapses entirely if nothing's left in it); leave
Access unticked (the
default) and any location flagged `requires_driving` in locations.yaml -
remote national parks, beach towns with no direct train/bus/ferry - is
hidden too, since most day-trip planning starts from "what can I get to on
public transport". Both selections are remembered in the browser
(`localStorage`), so they stay put next time you open a fresh report or hit
Refresh in `--serve` mode - it's per-browser, not written back to any
config file. Cards are grouped by activity category in a fixed order
(hiking, climbing, kite practice, city touring, beach day, surfing,
sailing, kitesurfing, kayaking, snorkelling, scuba - see `ACTIVITY_ORDER`
in html_report.py) rather than sorted purely by score, so the same sport
always lands in the same spot on the page instead of shuffling around as
scores change day to day; score still breaks ties within a category. Each
day is a collapsible dropdown (today open, later days collapsed, so you
don't have to scroll through a week of cards to see today). Each card shows
a severity meter and score out of 10, sky/temp/wind/UV/wave/sea-temp
condition chips, an NPWS alert dropdown if the park has one (collapsed, but
still visibly flags that there's an alert - click to read the full text),
bonus/penalty pills (whale season, bluebottles, etc), a collapsed "Hourly
breakdown" widget (see below), and a click-to-expand "Scoring" breakdown.
There's also a collapsed-by-default "Forecast trends" section at the bottom
with a daily bar chart per location/activity - total score is the default
view, with temperature, chance of rain, UV, wind, wave height and sea
temperature also on the dropdown (unit in the dropdown label, e.g. "Wind
speed (kt)" or "Total score (/10)" - not repeated over every bar), all
plotted across the fetched days.

**Hourly breakdown.** Every card gets an extra "Hourly breakdown" dropdown
with the same metric picker but hour-by-hour bars instead of one-per-day
(chance of rain is the default) - useful for seeing exactly when the rain
or wind picks up. Shown as 7am-9pm, all on one row with no scrolling
needed - same dropdown-label-not-per-bar unit treatment as above, with a
bare hour number (no am/pm) under every single bar; bars and their labels
render as two separate rows so a label can never distort the bar above
it. Built for every day in the forecast, not just the next couple - how
much to trust an hourly forecast a week or more out is a judgement call
for whoever's reading it, not something to decide by hiding the data.

**Wind speed** is shown in knots everywhere (chips, condition line, trend
and hourly wind charts) - the unit sailing/kite/surf forecasts are normally
read in; the activities.yaml thresholds themselves stay in km/h internally,
this is display-only.

**Temperature and other condition chips show the day's full-day figures**
(daytime high for temperature, day-wide wind/wave/etc), not each activity's
own narrower time-of-day window - so surfing and beach day at the same spot
on the same day always show the same numbers on their chips, even though
they score against different hours of the day (see "Time-of-day weighting"
below). The Scoring breakdown still shows exactly what was actually scored,
window and all, if you want that detail.

**Score grading.** The /10 score maps to a 5-band severity read: 9.5+
Great, 8.5-9.5 Good, 7.5-8.5 Acceptable, 6.5-7.5 Marginal, below 6.5 Poor -
shown as both the meter-fill colour and the status dot/label next to it.

Options:

```
python main.py --days 14                # look further ahead (default 10, up to 16, see note below)
python main.py --activity surfing        # only activities whose key contains this text
python main.py --location manly          # only locations matching this text
python main.py --min-score 70            # hide anything below this score (out of 100 internally)
python main.py --out weekend.html        # write somewhere other than report.html
python main.py --open                    # open the report in your browser once written
python main.py --serve                   # run a local server with a live Refresh button (re-scores on each request)
python main.py --text                    # quick terminal view instead of HTML
python main.py --text --explain          # terminal view with the full scoring breakdown
python main.py --extract-only data.json  # fetch only, save the raw data, no scoring/rendering
python main.py --from-extract data.json  # score/render from a saved --extract-only file, no network
```

**Does `python main.py` on its own refresh?** No - it fetches once, writes
`report.html`, and exits; there's no Refresh button in that file, since a
static HTML file has no server behind it to ask for new data. To see fresh
numbers you either re-run `python main.py` (overwrites the same file) or
use `--serve`, which adds an in-page Refresh button that re-fetches live
data on every click.

**Separating fetching from visualising.** `--extract-only PATH` does just
the network half of a run - weather/marine per location plus NPWS alerts -
and saves it to `PATH` as JSON, then exits without scoring or rendering
anything. `--from-extract PATH` does the reverse: scores and renders (as
`--text`, `--serve`, or the default HTML) from that saved file instead of
touching the network at all, so you can re-run it with different
`--activity`/`--location`/`--min-score` filters, or iterate on
activities.yaml/html_report.py, against a fixed dataset as many times as
you like with zero extra API calls. `--from-extract` works with `--serve`
too - each Refresh re-renders the same saved data rather than re-fetching.
The generated-at label on the report reflects when `--extract-only`
actually pulled the data, not when you later visualised it, and is marked
"(from --from-extract, not live)" so it's obvious you're not looking at a
fresh fetch.

**How far ahead can it look?** Open-Meteo gives real forecast data out to
16 days for standard weather, but marine data (wave height, swell, sea
temperature) only goes out to about 9 days before it turns to nulls - so
`--days 16` works fine for inland spots (climbing/hiking), but coastal
activities beyond ~9 days just quietly lose their wave/sea-temp factors
(they still score on wind/rain/temp) rather than erroring. The default of
10 sits just past the marine ceiling, trading a day or two of wave/sea-temp
data at the tail for a meaningfully longer outlook everywhere else.

**What `--serve` actually needs.** It's Python's built-in `http.server`
module - no extra packages beyond what's already in requirements.txt, no
install step, no admin rights. It binds only to `127.0.0.1` (localhost),
never listens on the network, and needs no firewall exception - so it's
not something a network scan would ever see. It's a single lightweight
Python process (tens of MB of RAM) that exists only while the terminal
window is open; closing the terminal (or Ctrl+C) ends it completely, with
nothing left installed, running in the background, or registered to start
automatically. If you'd rather avoid even that on a machine you're
cautious about, you don't need it at all - `python main.py` on its own has
zero ongoing footprint (it fetches, writes `report.html`, and exits); you'd
just re-run it and re-open the file whenever you want fresh numbers,
instead of using `--serve`'s in-browser Refresh button.

Each Refresh re-fetches every location (in parallel, capped at 4 at once
so Open-Meteo's free tier doesn't rate-limit it), so it typically takes
5-15 seconds - occasionally longer if Open-Meteo itself is being slow, in
which case you'll see `! Could not fetch weather for X` in the terminal for
whichever locations timed out that round (they just get skipped for that
refresh, not treated as an error).

## Tuning scores / adding places - no code changes needed

- **config/locations.yaml** - add a spot with its name, lat/lon, `marine:
  true` if it needs wave/swell/sea-temp data, `requires_driving: true` if
  it's not practically reachable from Sydney by train/bus/ferry (drives the
  report's Access checkbox - see above), and which activities apply (a
  dict, since some activities take per-location parameters - see below).
- **config/activities.yaml** - each activity is built from weighted
  `factors` (temperature, rain, wind, wave height, etc, each with an ideal
  range and a "hard" range it falls to zero by), `risk_factors` (same idea
  but for the *probability* of an adverse condition), `gates` (hard
  pass/fail conditions that force the score to 0), and `bonuses` (extra
  conditions folded into that same weighted average - see below - rather
  than flat points bolted on afterwards). Full field reference is in that
  file's header comment and scoring.py's module docstring.

Every card in the HTML report has a "Scoring" dropdown you can click open
to see exactly which factors/risks/bonuses drove a score (as points earned
out of points possible, on the same 0-10 scale as the overall score), and
the reason anything was zeroed out (GATED) - useful while tuning, since you
can compare it against what the weather is actually like. (`--text
--explain` shows the same breakdown in the terminal.) Deliberately plain -
just the factor name, value, points and max, at a small font so the whole
table fits inside the card without pushing it taller.

## How scoring works

**Time-of-day weighting.** Each activity has a `time_window` (e.g. daytime
for surfing, midday for hiking, sea-breeze afternoon for kitesurfing),
overridable per-location. Hourly forecast data is aggregated separately for
hours inside that window, outside it, and across the full day - a factor
can target whichever is relevant via its `scope` field. Rain forecast
during a climbing session matters a lot; the same rain forecast for that
evening, after you're off the rock, barely counts. This only affects
*scoring* - the card's chips/trend charts show the day's full-day figures
regardless of activity, so two activities at the same spot don't show
different numbers just because they check different hours (see above).

**Risk sensitivity.** Rather than `penalty = probability x severity`
(linear), sports where a bad outcome is genuinely dangerous (kitesurfing,
sea kayaking, marginal surf) use a convex `(1-p)^exponent` curve, so even a
20-30% chance of an adverse condition costs disproportionately more than it
would for a low-consequence sport like hiking or climbing. The exponent is
set per-activity via `sensitivity: low/medium/high` (1/2/3) or an explicit
`risk_exponent`.

**Hard gates.** Some conditions aren't a matter of degree - a storm
forecast, offshore wind for kitesurfing (can blow you out to sea), or an
active water-quality advisory all force the score straight to 0 with a
reason, rather than just being one more weighted factor. NPWS park alerts
are deliberately *not* a gate - see Known limitations.

**Bonuses/penalties are weighted, not flat.** A `bonuses` entry (whale
season, bluebottles) folds into the same weighted average as every factor,
rather than being added as flat points after the fact - a positive entry
scores full marks when met, a negative one scores zero, each carrying a
weight of `abs(points)/100`, and it's excluded entirely (no reward or
penalty) when not met. This means a bonus can only ever nudge the score by
an amount proportional to how much else is already driving it - a big flat
"+10 whale season" could previously paper over a genuinely wet, marginal
hike and still show up in the "Great" band; now it nudges a rain-soaked
score up by a point or two at most, not straight back to the top. (There
used to be a "sunny"/"clear skies" bonus on almost every activity too - it's
been removed outright rather than just reweighted, since it was really just
double-crediting clear skies that the other factors, e.g. UV, already
account for.)

**Beginner-oriented defaults.** Wave height, swell, and wind ranges for
snorkelling/scuba/surfing/kayaking/kitesurfing default to what suits a
beginner (smaller/cleaner conditions - surfing's ideal wave height is
~0.3-0.7m), not what an advanced athlete would seek out. Loosen the ranges
in activities.yaml as you progress.

**Seasonal bonuses grade by how "in season" something is.** Whale season
and bluebottle risk both split into a shoulder tier (early/late) and a
bigger peak tier, rather than a single flat bonus for the whole date range
- e.g. whale-watching pays more in the Jun-Oct peak migration/calving
window than in the May/Nov shoulder months.

**One shared curve.** Every factor reuses the same "distance from ideal
range" trapezoid (`_factor_score` in scoring.py) with its own numbers,
rather than bespoke curves per sport.

## Known limitations (by design, not oversights)

- **No live tide data.** There's no free, documented NSW tide API. Each
  surf/kite location has an optional `tide_notes` field for you to fill in
  manually - it's not wired into scoring.
- **No live water-quality advisory feed.** NSW Beachwatch's old bulletin
  endpoints (`environment.nsw.gov.au/beachapp/...`) now redirect to a
  JS-rendered site with no documented public API. `pollution_advisory` in
  locations.yaml is a manual flag you set after checking
  [beachwatch.nsw.gov.au](https://beachwatch.nsw.gov.au) yourself - it's a
  clean hook to wire up a real feed later if you find a stable one.
- **Shark risk is a heuristic, not a sighting feed.** NSW's tagged-shark
  listening network (SharkSmart) is real, but there's no documented public
  API for it - only the app/site UI. `shark_risk` in context.py instead
  flags heavy/recent rain (river-mouth runoff and turbidity are a
  well-known correlate of elevated shark activity) or, at a
  `whale_watching` spot, peak whale migration (Jun-Oct - carcasses draw
  sharks in close to shore, a specific pattern authorities warn about).
  Applied as a bonus/penalty on beach_day, surfing, snorkelling, scuba and
  kayaking (a smaller penalty for kayaking - real but lower exposure than
  swimming/surfing).
- **No true wind/storm probability.** Open-Meteo's free tier gives
  deterministic hourly forecasts plus one genuine probability field,
  `precipitation_probability`. That's what every `risk_factors` block
  uses as its proxy for "conditions could turn" - there's no ensemble wind
  or lightning-probability data without a paid/ensemble API. (Open-Meteo
  does expose a dedicated BOM ACCESS-G model endpoint that could
  cross-check the primary forecast, but BOM's own data delivery is
  currently suspended for a platform upgrade and the endpoint returns
  nulls - worth revisiting later.)
- **Bluebottles are a heuristic, not a sighting feed.** `bluebottle_risk`
  in context.py flags in-season (Nov-Apr) sustained onshore wind as a
  proxy for bluebottles being blown onto the beach - there's no free live
  sighting data to check against instead.
- **NPWS park alerts are informational only, never a scoring gate.** The
  live nationalparks.nsw.gov.au feed matches at whole-park level, and a
  park can span hundreds of square km, so a closure elsewhere in the park
  may have nothing to do with your specific spot (e.g. Blue Mountains NP's
  Victoria Falls closure has nothing to do with Katoomba) - it's shown as
  a banner so you can check it yourself, not used to zero the score.
- **Wind-direction sectors are rough approximations.** The
  `offshore_directions` sectors per beach (used for the surf "clean wave"
  bonus and the kitesurfing hard safety gate) are my best guess at each
  beach's orientation, not verified local knowledge. Check and correct
  them, especially before trusting the kitesurfing gate for anything
  safety-relevant.
- **Kayaking has two profiles**, `kayaking_sea` (strict) and
  `kayaking_freshwater` (relaxed, also used for sheltered harbours/bays
  that aren't literally fresh water) - pick whichever a location's water
  body actually resembles.
- **Whale season only applies where it makes sense.** The bonus is gated on
  a `whale_watching: true` flag in locations.yaml, set only on spots that
  actually look out over open coastal water - not on every location that
  happens to have a "hiking" activity in season.
- **Swimming is defined but unused for now** - the `swimming` block in
  activities.yaml is intact but no location currently lists it as an
  active activity (paused at your request; re-add it to any location's
  `activities` to bring it back, no code changes needed).

## Notes

- Rain-history factors (`rain_prior_24h/48h/72h`) come from Open-Meteo's
  `past_days` data, so "wet rock"/"murky water" scoring reflects actual
  recent rainfall, not just the forecast day itself.
- Snorkelling and scuba are deliberately not at the closest Sydney beaches
  - Jervis Bay and South West Rocks (Fish Rock Cave) for clear water
  further out, plus scuba at Gordons Bay (Coogee) as a well-regarded local
  shore dive.
- The bundled location list also spans several national parks further from
  Sydney for climbing/hiking (Kanangra-Boyd, Wollemi, Kosciuszko, the
  Budawangs, Nowra) - add your own regular spots as you go.
- **Sailing** (RANSA, Rushcutters Bay) is scored like kitesurfing's calmer
  cousin - wants steady moderate wind rather than the strong wind
  kitesurfing needs, and has no wave/marine factors since it's sheltered
  harbour water. **City touring** (Sydney CBD) is the one fully land-based,
  non-athletic activity - it only cares about rain, temperature, UV and
  visibility (for the skyline/harbour views), with no risk/gate logic
  beyond a storm.
- **Kite practice** is trainer-kite handling on land - no board, no water -
  so it wants much lighter wind than kitesurfing proper: ideal is a narrow
  band around 10-14kt, scoring starts at 8kt and falls off again by 22kt,
  since a trainer kite gets twitchy and hard to handle well past that
  (`wind_speed_max` is scored in km/h internally like every other
  activity's wind factor, so activities.yaml stores those kt figures
  converted x1.852 - see the comment on that factor if you're retuning it).
  Set up at Parramatta Park (open riverside parkland, no marine data
  needed) plus Yarra Bay (Kurnell) and Cronulla/Wanda, reusing the
  kitesurfing-suitable beaches already configured rather than guessing at
  new ones.
- **Parramatta River** is a flat-water kayaking spot (`kayaking_freshwater`)
  right by Parramatta Park - no marine data needed, same as the harbour/bay
  kayaking spots.
- **Surfing's time window is daytime** (9am-4pm default), not a dawn-patrol
  check - loosen or shift it per-location in locations.yaml if you actually
  surf at first light.
- **Beach day** is a relaxed day out - sunbathing, paddling, a picnic on
  the sand - rather than swimming laps or chasing swell, so its wave/wind
  tolerance is calmer than `swimming` and UV/wind carry more weight (a
  stiff onshore breeze or harsh sun ruins a beach day even without any
  rain). Set up at Manly, Bondi, Cronulla/Wanda and Jervis Bay (Hyams
  Beach) - the classic Sydney/day-trip swimming beaches.
