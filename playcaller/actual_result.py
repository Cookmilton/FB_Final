"""
Structured **actual** play results (post-log) — formatting and classification helpers.

``PredictedPlayResult`` / ``predicted_play_result`` stay recommendation-only; this module
is for logged truth on ``ActualPlayResult``.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from .domain import (
    PASS_FAMILIES,
    RUN_FAMILIES,
    ActualPlayResult,
    ball_carrier_and_target_from_play,
    play_type_for_family,
)
from .situation import classify_logged_outcome


def classify_actual_result_type(
    *,
    yards: int,
    to_go: int,
    earned_first_down: bool,
    touchdown: bool,
    pass_result: str = "",
    turnover_kind: str = "",
    sack: bool = False,
) -> str:
    """Stable ``result_type`` including pass-specific outcomes."""
    pr = (pass_result or "").strip().lower()
    tk = (turnover_kind or "").strip().lower()
    if tk == "interception" or pr == "intercepted":
        return "interception"
    if pr == "incomplete":
        return "incomplete"
    if sack or pr == "sack":
        y = int(yards)
        if touchdown:
            return "touchdown"
        if earned_first_down:
            return "first_down_exact" if y == int(to_go) else "first_down"
        if y == 0:
            return "no_gain"
        return "sack" if y <= -4 else "negative"
    return classify_logged_outcome(
        yards=yards,
        to_go=to_go,
        earned_first_down=earned_first_down,
        touchdown=touchdown,
    )


def earned_first_down_for_advance(actual: ActualPlayResult, distance: int) -> bool:
    """Whether the chains should move — excludes INT, incomplete, sack, turnover."""
    if actual.turnover or (actual.turnover_kind or "").lower() == "interception":
        return False
    pr = (actual.pass_result or "").lower()
    if pr in ("incomplete", "intercepted", "sack"):
        return False
    if actual.sack:
        return False
    return int(actual.yards_gained) >= int(distance)


def _yards_phrase(n: int) -> str:
    n = int(n)
    if n == 1:
        return "1 yard"
    if n == -1:
        return "loss of 1"
    if n < 0:
        return f"loss of {abs(n)}"
    return f"{n} yards"


def _target_tail(a: ActualPlayResult, *, for_interception: bool) -> str:
    label = (a.target_role_label or "").strip()
    if label:
        return f" targeting {label}" if for_interception else f" to {label}"
    pos = (a.target_position or a.ball_carrier_or_target or "").strip().upper()
    if not pos:
        return ""
    if pos == "H":
        phrase = "slot"
    elif pos == "Y":
        phrase = "TE"
    elif pos in ("X", "Z"):
        phrase = f"{pos} receiver"
    elif pos == "RB":
        phrase = "RB"
    elif pos == "QB":
        phrase = "QB"
    else:
        phrase = f"{pos} receiver"
    return f" targeting {phrase}" if for_interception else f" to {phrase}"


def format_actual_play_result_description(a: ActualPlayResult) -> str:
    """
    One-line broadcast-style summary from structured fields.

    If ``a.description`` is set, returns it; otherwise derives from fields.
    """
    if (a.description or "").strip():
        return (a.description or "").strip()

    rtype = (a.result_type or "").strip().lower()
    if rtype == "field_goal":
        return "Field goal good"
    if rtype == "field_goal_miss":
        return "Field goal missed"

    pr = (a.pass_result or "").strip().lower()
    pt = (a.play_type or "").strip().lower()
    tk = (a.turnover_kind or "").strip().lower()

    if tk == "interception" or pr == "intercepted":
        return f"Interception{_target_tail(a, for_interception=True)}".rstrip()

    if a.sack or pr == "sack":
        y = int(a.yards_gained)
        if y < 0:
            return f"Sack for {_yards_phrase(y)}"
        return "Sack for no gain"

    if a.scramble or (pt in ("qb_scramble", "qb_run") and pr != "complete"):
        return f"QB scramble for {_yards_phrase(int(a.yards_gained))}"

    if pt == "run" or (pt not in ("pass", "qb_scramble", "qb_run") and a.family in RUN_FAMILIES):
        carrier = (a.ball_carrier_or_target or "RB").strip() or "RB"
        if a.touchdown:
            return f"Touchdown run by {carrier} for {_yards_phrase(int(a.yards_gained))}"
        return f"Run by {carrier} for {_yards_phrase(int(a.yards_gained))}"

    if pt == "pass" or a.family in PASS_FAMILIES:
        tail = _target_tail(a, for_interception=False)
        if pr == "incomplete":
            return f"Pass incomplete{tail}".rstrip()
        if a.touchdown:
            return f"Touchdown pass{tail} for {_yards_phrase(int(a.yards_gained))}"
        if pr == "complete" or (not pr and int(a.yards_gained) > 0):
            return f"Pass complete{tail} for {_yards_phrase(int(a.yards_gained))}"
        return f"Pass{tail} for {_yards_phrase(int(a.yards_gained))}"

    if a.touchdown:
        return f"Touchdown for {_yards_phrase(int(a.yards_gained))}"
    return f"Play for {int(a.yards_gained):+d} yards"


def role_label_from_position(pos: Optional[str]) -> str:
    if not pos:
        return ""
    u = str(pos).strip().upper()
    if u == "H":
        return "slot"
    if u == "Y":
        return "TE"
    if u in ("X", "Z"):
        return f"{u} receiver"
    if u in ("RB", "QB"):
        return u
    return u


def target_role_label_from_choice(target_choice: str, pos_code: Optional[str]) -> str:
    tc = (target_choice or "").strip()
    if tc.startswith("Auto"):
        return role_label_from_position(pos_code)
    mapping = {
        "X": "X receiver",
        "Z": "Z receiver",
        "H (slot)": "slot",
        "Y (TE)": "TE",
        "RB": "RB",
        "QB": "QB",
    }
    return mapping.get(tc, role_label_from_position(tc))


def carrier_and_position_from_target_choice(
    target_choice: str,
    play: dict,
    family: str,
) -> tuple[str, Optional[str], str]:
    """
    Returns (ball_carrier_or_target, target_position, target_role_label).
    """
    if (target_choice or "").startswith("Auto"):
        bc, tpos = ball_carrier_and_target_from_play(play, family)
        return bc, tpos, role_label_from_position(tpos)

    code_map = {
        "X": ("X", "X"),
        "Z": ("Z", "Z"),
        "H (slot)": ("H", "H"),
        "Y (TE)": ("Y", "Y"),
        "RB": ("RB", None),
        "QB": ("QB", None),
    }
    bc, tpos = code_map.get(target_choice, ("", None))
    lbl = target_role_label_from_choice(target_choice, tpos)
    return bc, tpos, lbl


def resolve_logging_semantics(
    *,
    family: str,
    yards_gained: int,
    outcome_ui: str,
    sack_from_chip: bool,
) -> tuple[str, str, bool, bool, bool, str, str]:
    """
    Derive (play_type, pass_result, sack, scramble, turnover, turnover_kind, result_type_preset)
    from UI. ``result_type_preset`` is ``field_goal``, ``field_goal_miss``, or ``""``.
    """
    y = int(yards_gained)
    base_pt = play_type_for_family(family)
    auto = (outcome_ui or "").startswith("Auto")

    if not auto:
        if outcome_ui == "Complete pass":
            return "pass", "complete", False, False, False, "", ""
        if outcome_ui == "Incomplete pass":
            return "pass", "incomplete", False, False, False, "", ""
        if outcome_ui == "QB scramble":
            return "qb_scramble", "", False, True, False, "", ""
        if outcome_ui == "Run":
            return "run", "", False, False, False, "", ""
        if outcome_ui == "Sack":
            return "pass", "sack", True, False, False, "", ""
        if outcome_ui == "Interception":
            return "pass", "intercepted", False, False, True, "interception", ""
        if outcome_ui == "Field goal good":
            return "field_goal", "", False, False, False, "", "field_goal"
        if outcome_ui == "Field goal missed":
            return "field_goal", "", False, False, False, "", "field_goal_miss"

    if sack_from_chip or (base_pt == "pass" and y <= -4):
        return "pass", "sack", True, False, False, "", ""
    if base_pt == "run":
        return "run", "", False, False, False, "", ""
    if base_pt == "pass":
        if y > 0:
            return "pass", "complete", False, False, False, "", ""
        return "pass", "incomplete", False, False, False, "", ""
    return base_pt, "", False, False, False, "", ""


def assemble_actual_semantics(
    *,
    concept_name: str,
    family: str,
    play: dict,
    yards_gained: int,
    target_choice: str,
    outcome_ui: str,
    sack_from_chip: bool,
    forced_interception: bool = False,
    forced_incomplete: bool = False,
) -> ActualPlayResult:
    """Build semantic ``ActualPlayResult`` before down/distance advance (yards/flags only)."""
    oc = outcome_ui
    if forced_interception:
        oc = "Interception"
    elif forced_incomplete:
        oc = "Incomplete pass"

    yds = int(yards_gained)
    if oc == "Interception":
        yds = 0
    elif oc == "Incomplete pass":
        yds = 0

    pt, pr, sack, scramble, turnover, tk, preset_rt = resolve_logging_semantics(
        family=family,
        yards_gained=yds,
        outcome_ui=oc,
        sack_from_chip=sack_from_chip,
    )
    if forced_interception:
        pt, pr, sack, scramble = "pass", "intercepted", False, False
        turnover, tk = True, "interception"
        yds = 0

    bc, tpos, role_lbl = carrier_and_position_from_target_choice(target_choice, play, family)

    if pt == "run":
        if not bc:
            bc = "RB"
        tpos = None
        role_lbl = role_lbl or "RB"
    elif pt == "qb_scramble":
        bc, tpos, role_lbl = "QB", None, "QB"

    return ActualPlayResult(
        concept_name=concept_name,
        family=family,
        play_type=pt,
        pass_result=pr,
        result_type=preset_rt or "",
        yards_gained=yds,
        ball_carrier_or_target=bc,
        target_position=tpos,
        target_role_label=role_lbl,
        scramble=scramble,
        first_down=False,
        touchdown=False,
        turnover=turnover,
        turnover_kind=tk,
        sack=sack,
        penalty=False,
        penalty_yards=0,
        notes="",
        description="",
    )


def finalize_actual_after_snap(
    base: ActualPlayResult,
    *,
    snap,
    to_go: int,
    earned_first_down: bool,
) -> ActualPlayResult:
    """Set ``result_type``, ``first_down``, ``touchdown``, and formatted ``description``."""
    preset = (base.result_type or "").strip().lower()
    if preset in ("field_goal", "field_goal_miss"):
        rt = preset
    else:
        rt = classify_actual_result_type(
            yards=base.yards_gained,
            to_go=to_go,
            earned_first_down=earned_first_down,
            touchdown=snap.touchdown,
            pass_result=base.pass_result,
            turnover_kind=base.turnover_kind,
            sack=base.sack,
        )
    fd = rt in ("first_down", "first_down_exact", "touchdown")
    out = replace(
        base,
        result_type=rt,
        first_down=fd,
        touchdown=snap.touchdown,
    )
    return replace(out, description=format_actual_play_result_description(out))


__all__ = [
    "assemble_actual_semantics",
    "carrier_and_position_from_target_choice",
    "classify_actual_result_type",
    "earned_first_down_for_advance",
    "finalize_actual_after_snap",
    "format_actual_play_result_description",
    "resolve_logging_semantics",
    "role_label_from_position",
    "target_role_label_from_choice",
]
