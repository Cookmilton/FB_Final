"""
Pre-snap **projected** play result only (recommendation-time).

This module must not be used for drive history or field/state advancement.
Logged truth lives in ``ActualPlayResult`` and ``advance_game_state_after_actual``.

Uses the same deterministic RNG seed as ``HeuristicPredictor`` so a given situation
reproduces the same projection. Safe to call for any recommendation dict that
includes ``ctx``, ``play_family``, and ``play``.
"""

from __future__ import annotations

import random
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Tuple

from .domain import RUN_FAMILIES, GameContext
from .heuristic_predictor import HeuristicPredictor
from .result_display import build_projected_headline
from .state import DriveLogger


@dataclass
class PredictedPlayResult:
    """Pre-snap projection for the recommendation card only — never written to the drive log."""

    play_type: str
    target_player_or_role: str
    route: str
    result_type: str
    yards: int
    description: str
    # Machine-friendly receiver code for diagrams (X, H, Y, Z, RB), or None.
    target_position: Optional[str] = None
    headline: str = ""
    success: bool = False
    explosive: bool = False


def _projection_flags(*, result_type: str, yards: int, to_go: int) -> Tuple[bool, bool]:
    """First-down proxy + explosive gain (≥15 on positive plays)."""
    if result_type in ("incomplete", "sack"):
        return False, False
    ok = yards >= int(to_go)
    explosive = yards >= 15 and yards > 0
    return ok, explosive


# Human labels for diagram + copy
_POSITION_ROLE: Dict[str, str] = {
    "X": "X receiver",
    "Z": "Z receiver",
    "H": "slot receiver",
    "Y": "Y receiver (TE)",
    "RB": "RB",
}


def role_label_for_position(pos: str) -> str:
    return _POSITION_ROLE.get(pos.upper(), f"{pos} receiver")


def _rng_for_ctx(ctx: GameContext, drive_log: Optional[DriveLogger]) -> random.Random:
    hp = HeuristicPredictor()
    return random.Random(hp._stable_seed(ctx, drive_log))


def _route_importance(route_desc: str) -> float:
    """Bias primary-read selection toward meaningful patterns."""
    t = route_desc.lower()
    w = 1.0
    if any(k in t for k in ("go", "fade", "clear", "vertical", "seam", "post", "corner")):
        w += 4.0
    if any(k in t for k in ("slant", "stick", "hitch", "flat", "bubble", "glance")):
        w += 3.0
    if any(k in t for k in ("dig", "cross", "out", "in", "comeback", "over", "leak", "shallow")):
        w += 2.5
    if "screen" in t:
        w += 3.0
    if any(k in t for k in ("check", "release", "block", "protect", "fake")):
        w += 0.4
    return w


def pick_primary_receiver(
    play: Dict[str, Any],
    family: str,
    rng: random.Random,
) -> Tuple[str, str]:
    """
    Return (position_code, raw_route_text).

    Screen / obvious RB screen → RB. Fade iso → X if present. Else weighted by route text.
    """
    routes: Dict[str, str] = play.get("routes") or {}
    if not routes:
        return "RB", ""

    rlow = {k: str(v) for k, v in routes.items()}
    if family == "screen" or any("screen" in v.lower() for v in rlow.values()):
        if "RB" in rlow:
            return "RB", rlow["RB"]
    if family == "fade_iso" and "X" in rlow:
        return "X", rlow["X"]

    eligible = [(p, txt) for p, txt in rlow.items() if p in _POSITION_ROLE]
    if not eligible:
        p, txt = next(iter(rlow.items()))
        return str(p), str(txt)

    weights = [_route_importance(txt) for _, txt in eligible]
    pick = rng.choices(eligible, weights=weights, k=1)[0]
    return pick[0], pick[1]


def _run_description(family: str, play: Dict[str, Any], yards: int) -> Tuple[str, str, str, str]:
    scheme = play.get("run_scheme") or play.get("name") or "run"
    scheme_l = scheme.lower()
    if "draw" in scheme_l or family == "draw":
        return "run", "RB", "rush", f"RB draw for {yards} yards"
    if "outside" in scheme_l or family == "outside_zone":
        return "run", "RB", "rush", f"RB outside zone for {yards} yards"
    if family in ("power", "duo") or "power" in scheme_l:
        return "run", "RB", "rush", f"RB {scheme_l.split()[0] if scheme_l else 'power'} run for {yards} yards"
    if "qb" in scheme_l and ("sneak" in scheme_l or "power" in scheme_l):
        return "qb_run", "QB", "rush", f"QB sneak for {yards} yards"
    if "option" in scheme_l or "keep" in scheme_l:
        return "qb_run", "QB", "rush", f"Read option keep by QB for {yards} yards"
    return "run", "RB", "rush", f"RB inside run for {yards} yards"


def _pass_outcome_from_route(
    route_text: str,
    ctx: GameContext,
    rng: random.Random,
) -> Tuple[str, int, str]:
    """
    Return (result_type, yards, route_phrase_for_copy).

    ``route_phrase`` is a short clause like ``slant route`` or ``deep shot``.
    """
    t = route_text.lower()
    # Route flavor for wording
    if any(k in t for k in ("go", "fade", "vertical", "clear", "seam", "shot")):
        route_phrase = "deep shot"
        p_inc = 0.42 + (0.08 if ctx.weather in ("wind", "rain", "snow") else 0)
    elif any(k in t for k in ("post", "corner")):
        route_phrase = "deep route"
        p_inc = 0.34
    elif any(k in t for k in ("slant", "hitch", "stick", "flat", "bubble", "quick")):
        route_phrase = re.sub(r"\s+", " ", route_text.split(",")[0].strip().lower())[:40]
        p_inc = 0.22
    elif "screen" in t:
        route_phrase = "screen"
        p_inc = 0.12
    else:
        route_phrase = re.sub(r"\s+", " ", route_text.split(",")[0].strip().lower())[:40]
        p_inc = 0.28

    p_sack = 0.07
    if ctx.blitz_likely:
        p_sack += 0.11
    if ctx.weather in ("rain", "snow"):
        p_sack += 0.03
    p_scr = 0.05 if ctx.distance >= 6 else 0.03
    if ctx.qb_limited:
        p_scr += 0.04

    r = rng.random()
    if r < p_sack:
        yds = -rng.randint(5, 9)
        return "sack", yds, route_phrase
    r2 = (r - p_sack) / max(1e-6, (1 - p_sack))
    if r2 < p_scr:
        yds = rng.randint(4, 12)
        return "scramble", yds, route_phrase
    r3 = r2 / max(1e-6, (1 - p_scr))
    if r3 < p_inc:
        return "incomplete", 0, route_phrase

    # Completion — yards by route depth
    if "screen" in t or "bubble" in t:
        yds = rng.randint(6, 14)
    elif any(k in t for k in ("go", "fade", "vertical", "clear", "post", "corner", "seam")):
        yds = rng.randint(18, 38)
    elif any(k in t for k in ("dig", "cross", "out", "comeback", "over")):
        yds = rng.randint(9, 18)
    else:
        yds = rng.randint(4, 12)
    cap = max(ctx.distance + 15, 8)
    yds = min(yds, cap)
    return "complete", yds, route_phrase


def _build_pass_description(
    result_type: str,
    yards: int,
    role: str,
    route_phrase: str,
    route_raw: str,
) -> str:
    route_bit = route_raw.strip() if route_raw else route_phrase
    if result_type == "sack":
        return f"Sack for {yards} yards"
    if result_type == "scramble":
        return f"QB scramble for {yards} yards"
    if result_type == "incomplete":
        if "deep" in route_phrase or "shot" in route_phrase:
            return f"Deep shot to {role} incomplete"
        return f"Incomplete pass intended for {role}" + (f" ({route_bit})" if len(route_bit) < 50 else "")
    if "screen" in route_phrase or "screen" in route_raw.lower():
        return f"Screen pass to {role} for {yards} yards"
    if "check" in route_raw.lower():
        return f"Checkdown to {role} for {yards} yards"
    if "deep" in route_phrase or "shot" in route_phrase:
        return f"Pass complete to {role} for {yards} yards on a {route_bit}"
    return f"Pass complete to {role} for {yards} yards"


def compute_predicted_play_result(
    ctx: GameContext,
    family: str,
    play: Dict[str, Any],
    drive_log: Optional[DriveLogger],
) -> PredictedPlayResult:
    rng = _rng_for_ctx(ctx, drive_log)
    if not play or not play.get("name"):
        return PredictedPlayResult(
            play_type="unknown",
            target_player_or_role="",
            route="",
            result_type="unknown",
            yards=0,
            description="Projection unavailable for this call.",
            target_position=None,
            headline="Result: Projection unavailable.",
        )

    if family in RUN_FAMILIES or (family == "two_point" and play.get("run_scheme") and not play.get("routes")):
        y_hi = min(14, max(2, ctx.distance + rng.randint(1, 5)))
        y_lo = max(1, min(4, ctx.distance - 2))
        yards = rng.randint(y_lo, y_hi)
        pt, tgt, rt, desc = _run_description(family, play, yards)
        tpos = "RB" if tgt == "RB" else ("QB" if tgt == "QB" else "RB")
        succ, xpl = _projection_flags(result_type=rt, yards=yards, to_go=ctx.distance)
        hl = build_projected_headline(
            play_type=pt,
            result_type=rt,
            yards=yards,
            target_position=tpos,
            route_raw="",
            play=play,
            play_family=family,
        )
        return PredictedPlayResult(
            play_type=pt,
            target_player_or_role=tgt,
            route="",
            result_type=rt,
            yards=yards,
            description=desc,
            target_position=tpos,
            headline=hl,
            success=succ,
            explosive=xpl,
        )

    pos, route_raw = pick_primary_receiver(play, family, rng)
    role = role_label_for_position(pos)
    rt, yards, route_phrase = _pass_outcome_from_route(route_raw or play.get("why", ""), ctx, rng)
    desc = _build_pass_description(rt, yards, role, route_phrase, route_raw)
    pt = "pass" if rt != "scramble" else "qb_run"
    succ, xpl = _projection_flags(result_type=rt, yards=yards, to_go=ctx.distance)
    hl = build_projected_headline(
        play_type=pt,
        result_type=rt,
        yards=yards,
        target_position=pos,
        route_raw=route_raw,
        play=play,
        play_family=family,
    )

    return PredictedPlayResult(
        play_type=pt,
        target_player_or_role=role,
        route=route_raw[:120] if route_raw else route_phrase,
        result_type=rt,
        yards=yards,
        description=desc,
        target_position=pos,
        headline=hl,
        success=succ,
        explosive=xpl,
    )


def enrich_recommendation_dict(result: Dict[str, Any], drive_log: Optional[DriveLogger]) -> None:
    """Mutates ``result`` with recommendation-only ``predicted_play_result`` (dict)."""
    ctx: Optional[GameContext] = result.get("ctx")
    if ctx is None:
        return
    family = str(result.get("play_family") or "")
    play = result.get("play") or {}
    pred = compute_predicted_play_result(ctx, family, play, drive_log)
    result["predicted_play_result"] = asdict(pred)


__all__ = [
    "PredictedPlayResult",
    "compute_predicted_play_result",
    "enrich_recommendation_dict",
    "pick_primary_receiver",
    "role_label_for_position",
]
