from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

RUN_FAMILIES = {"inside_zone", "outside_zone", "duo", "power", "draw"}
PASS_FAMILIES = {"quick_game", "dropback_pass", "screen", "play_action", "fade_iso"}

# opponents' 35 ≈ 52-yard attempt — makeable for most kickers
FG_RANGE_YARDLINE = 35


# ──────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class GameContext:
    """Everything an OC would see at the line of scrimmage."""

    # ── Core situation ────────────────────────────────────────────────────────
    down: int
    distance: int
    yardline: int
    territory: str  # "own" | "opponents"

    # ── Game script ───────────────────────────────────────────────────────────
    score_diff: int = 0  # positive = offense winning
    quarter: int = 2
    seconds_remaining: int = 1800
    own_timeouts: int = 3
    opp_timeouts: int = 3

    # ── Defensive pre-snap read ───────────────────────────────────────────────
    def_personnel: str = "unknown"  # base | nickel | dime | goal_line | unknown
    box_count: int = 7
    coverage_shell: str = "unknown"  # cover_0|cover_1|cover_2|cover_3|cover_4|quarters|unknown
    blitz_likely: bool = False
    safeties: str = "unknown"  # single_high | two_high | unknown

    # ── Environment ───────────────────────────────────────────────────────────
    weather: str = "clear"  # clear | wind | rain | snow
    wind_mph: int = 0
    turf: str = "turf"  # grass | turf

    # ── Personnel & matchup ───────────────────────────────────────────────────
    personnel_group: str = "11"  # 10 | 11 | 12 | 21 | 22
    mismatch: Optional[str] = None  # free text, e.g. "slot CB is undersized"
    qb_limited: bool = False

    # ── Drive state ───────────────────────────────────────────────────────────
    plays_this_drive: int = 0
    shown_concepts: List[str] = field(default_factory=list)
    run_plays_this_drive: int = 0  # used by play-action qualifier

    # ── Game mode ─────────────────────────────────────────────────────────────
    game_mode: str = "normal"  # normal | must_score | drain_clock | two_minute | two_point


@dataclass
class ActualPlayResult:
    """
    Post-play truth recorded when the user logs a play.

    Separate from ``PredictedPlayResult`` (pre-snap projection on recommendations only).
    Use ``format_actual_play_result_description`` for a one-line summary from these fields.
    """

    concept_name: str = ""
    family: str = ""
    play_type: str = ""  # run | pass | qb_scramble | two_point | …
    result_type: str = ""  # first_down | interception | incomplete | sack | …
    yards_gained: int = 0
    ball_carrier_or_target: str = ""
    target_position: Optional[str] = None
    target_role_label: str = ""  # e.g. slot, TE, X receiver — for phrasing
    pass_result: str = ""  # complete | incomplete | intercepted | sack | ""
    scramble: bool = False
    first_down: bool = False
    touchdown: bool = False
    turnover: bool = False
    turnover_kind: str = ""  # interception | fumble | ""
    sack: bool = False
    penalty: bool = False
    penalty_yards: int = 0
    notes: str = ""
    description: str = ""  # formatted summary; filled at log time if empty


# Backwards-compatible name for drive logging (same shape as ``ActualPlayResult``).
PlayResult = ActualPlayResult


def play_type_for_family(family: str) -> str:
    f = str(family)
    if f in RUN_FAMILIES:
        return "run"
    if f in PASS_FAMILIES:
        return "pass"
    if f == "two_point":
        return "two_point"
    return f


def ball_carrier_and_target_from_play(play: dict, family: str) -> tuple[str, Optional[str]]:
    """
    Design-time primary from the call sheet (not the pre-snap projection).

    Returns (ball_carrier_or_target, target_position).
    """
    pt = play_type_for_family(family)
    routes = play.get("routes") or {}
    if pt == "run":
        scheme = str(play.get("run_scheme") or "").lower()
        if "qb" in scheme and "sneak" in scheme:
            return "QB", None
        return "RB", None
    if routes:
        pos = str(next(iter(routes.keys())))
        return pos, pos
    return "", None

