"""Generic, config-driven weather scoring engine.

Every activity in config/activities.yaml is built from the same pieces:

  factors       weighted 0-1 sub-scores from one shared "distance from
                ideal range" trapezoid curve (ideal_min/max -> full marks,
                falling linearly to 0 by hard_min/max) - every sport reuses
                this same curve, just with its own numbers.
  risk_factors  like factors, but for the *probability* of an adverse
                condition rather than its severity. Scored with a convex
                (1-p)**exponent curve instead of the trapezoid: exponent 1
                (low sensitivity) is a plain linear penalty, while 2-3+
                (medium/high sensitivity) makes even a modest probability
                disproportionately costly - so a small chance of a
                dangerous condition still meaningfully dents the score for
                risk-averse sports like kitesurfing or sea kayaking.
  gates         hard pass/fail conditions - if any trigger, the score is
                forced to 0 (with a human-readable reason) regardless of
                everything else, e.g. a storm forecast or offshore wind for
                kitesurfing.
  bonuses       extra conditions folded into the same weighted average as
                factors/risk_factors, rather than flat points bolted on
                afterwards - a positive `points` value scores 1.0 (full
                marks) when its condition is met, a negative value scores
                0.0 (a penalty), each carrying a weight of `abs(points)/100`
                into the same weighted_total/weight_sum used everywhere
                else. Not met -> excluded entirely, same as a factor with no
                data (no reward for whales not being in season, no penalty
                for bluebottles not being a risk). This keeps `points`
                proportionally diluted by however many real factors are
                already driving the score, instead of able to paper over a
                genuinely bad factor (e.g. rain during a hike) with a flat
                +10 whale-season points, which is what a plain post-hoc
                addition allowed.

factors/risk_factors/gates/bonuses can each set `scope` to "window"
(default - the activity's configured time-of-day window), "outside_window",
or "full_day". See context.py for how those are built. Gates and bonuses
can list multiple `conditions` (all must be true, i.e. AND) instead of a
single variable/op/value, e.g. climbing's "hot and humid" penalty.
"""

from __future__ import annotations

from typing import Any

_OPS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "in": lambda a, b: a in b,
}

# Maps a named sensitivity tier to the risk curve's exponent. Activities can
# also set an explicit `risk_exponent` instead, for finer tuning.
SENSITIVITY_EXPONENTS = {"low": 1, "medium": 2, "high": 3}


def _factor_score(value, factor: dict):
    """The one shared "distance from ideal range" curve - see module
    docstring. Omit ideal_min/hard_min for a "lower is better" factor
    (e.g. rain), or ideal_max/hard_max for a "higher is better" one."""
    if value is None:
        return None

    ideal_min = factor.get("ideal_min", float("-inf"))
    ideal_max = factor.get("ideal_max", float("inf"))
    hard_min = factor.get("hard_min", ideal_min)
    hard_max = factor.get("hard_max", ideal_max)

    if ideal_min <= value <= ideal_max:
        return 1.0
    if value < ideal_min:
        if value <= hard_min:
            return 0.0
        return (value - hard_min) / (ideal_min - hard_min)
    if value >= hard_max:
        return 0.0
    return (hard_max - value) / (hard_max - ideal_max)


def _risk_score(value, risk_factor: dict):
    """Convex (1-p)**exponent curve where p is a 0-100 probability. Higher
    exponent (higher sensitivity) means the score falls away faster even at
    modest probabilities, instead of the plain linear (exponent=1) penalty
    a probability x severity model would give."""
    if value is None:
        return None
    p = max(0.0, min(1.0, value / 100))
    exponent = risk_factor.get(
        "risk_exponent", SENSITIVITY_EXPONENTS.get(risk_factor.get("sensitivity", "low"), 1)
    )
    return (1 - p) ** exponent


def _condition_met(context: dict, condition: dict) -> bool:
    scope = context.get(condition.get("scope", "window"), {})
    value = scope.get(condition["variable"])
    if value is None:
        return False
    op = _OPS[condition.get("op", "==")]
    return op(value, condition["value"])


def _all_conditions_met(context: dict, conditions: list[dict]) -> bool:
    return bool(conditions) and all(_condition_met(context, c) for c in conditions)


def _check_gates(context: dict, gates: list[dict]):
    for gate in gates:
        if _all_conditions_met(context, gate.get("conditions", [gate])):
            return gate.get("reason", gate.get("name", "hard gate triggered"))
    return None


def score_activity(context: dict, activity_cfg: dict) -> dict[str, Any]:
    """Scores one day/location/activity combination. `context` is the
    {"window", "outside_window", "full_day"} dict built by
    context.build_day_context()."""

    gate_reason = _check_gates(context, activity_cfg.get("gates", []))
    if gate_reason:
        return {
            "score": 0.0,
            "gated": True,
            "gate_reason": gate_reason,
            "bonuses_hit": [],
            "breakdown": [],
        }

    breakdown = []
    weighted_total = 0.0
    weight_sum = 0.0

    for factor in activity_cfg.get("factors", []):
        scope = context.get(factor.get("scope", "window"), {})
        value = scope.get(factor["variable"])
        factor_score = _factor_score(value, factor)
        weight = factor.get("weight", 1.0)
        scope = factor.get("scope", "window")
        breakdown.append({"kind": "factor", "variable": factor["variable"], "scope": scope, "value": value, "score": factor_score, "weight": weight})
        if factor_score is not None:
            weighted_total += factor_score * weight
            weight_sum += weight

    for risk_factor in activity_cfg.get("risk_factors", []):
        scope = context.get(risk_factor.get("scope", "window"), {})
        value = scope.get(risk_factor["variable"])
        risk_score = _risk_score(value, risk_factor)
        weight = risk_factor.get("weight", 1.0)
        scope = risk_factor.get("scope", "window")
        breakdown.append({"kind": "risk", "variable": risk_factor["variable"], "scope": scope, "value": value, "score": risk_score, "weight": weight})
        if risk_score is not None:
            weighted_total += risk_score * weight
            weight_sum += weight

    # Bonuses/penalties fold into the same weighted average as factors above,
    # rather than being added as flat points afterwards - see module
    # docstring for why (a big flat bonus could otherwise mask a genuinely
    # bad factor like rain). Skipped entirely when not met, same as a factor
    # with no data - no reward for an inapplicable bonus, no penalty for an
    # absent risk.
    bonuses_hit = []
    for bonus in activity_cfg.get("bonuses", []):
        if not _all_conditions_met(context, bonus.get("conditions", [bonus])):
            continue
        points = bonus["points"]
        name = bonus.get("name") or bonus.get("variable", "bonus")
        weight = abs(points) / 100.0
        bonus_score = 1.0 if points > 0 else 0.0
        weighted_total += bonus_score * weight
        weight_sum += weight
        breakdown.append({"kind": "bonus", "variable": name, "value": None, "score": bonus_score, "weight": weight})
        bonuses_hit.append({"name": name, "points": points})

    final_score = (weighted_total / weight_sum * 100) if weight_sum else None
    if final_score is not None:
        final_score = max(0.0, min(100.0, final_score))  # defensive only - a weighted average of [0,1] scores can't actually exceed this

    # Rescale each entry's contribution onto the same 0-10 scale as the final
    # score, so the breakdown reads as "points earned out of points possible"
    # rather than an abstract 0-1 score and a raw weight.
    scale = (10 / weight_sum) if weight_sum else 0
    for entry in breakdown:
        if entry["score"] is not None:
            entry["points"] = round(entry["score"] * entry["weight"] * scale, 2)
            entry["max_points"] = round(entry["weight"] * scale, 2)
        else:
            entry["points"] = None
            entry["max_points"] = None

    return {
        "score": final_score,
        "gated": False,
        "gate_reason": None,
        "bonuses_hit": bonuses_hit,
        "breakdown": breakdown,
    }
