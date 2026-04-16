"""
Structured play metadata for weighted selection (optional keys on each play dict).

Resolution order for attribute ``attr``:
1. ``play[attr]`` if present
2. ``NAME_ATTR_OVERRIDES[(family, play[\"name\"])][attr]``
3. ``FAMILY_ATTR_DEFAULTS[family][attr]``
4. ``GLOBAL_ATTR_DEFAULTS[attr]``
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from .domain import RUN_FAMILIES, GameContext
from .features import ModelInput

AttrKey = str
Family = str

GLOBAL_ATTR_DEFAULTS: Dict[AttrKey, float] = {
    "red_zone_fit": 0.48,
    "short_yardage_fit": 0.45,
    "backed_up_fit": 0.5,
    "medium_fit": 0.52,
    "long_fit": 0.48,
    "goal_line_fit": 0.5,
    "blitz_answer": 0.45,
    "explosive_potential": 0.38,
    "risk_level": 0.42,
    "man_beater": 0.48,
    "zone_beater": 0.48,
    "fourth_down_fit": 0.42,
    "clock_safe": 0.46,
}

FAMILY_ATTR_DEFAULTS: Dict[str, Dict[AttrKey, float]] = {
    "quick_game": {
        "blitz_answer": 0.58,
        "clock_safe": 0.55,
        "zone_beater": 0.54,
        "medium_fit": 0.58,
        "long_fit": 0.42,
        "risk_level": 0.32,
    },
    "dropback_pass": {
        "explosive_potential": 0.52,
        "medium_fit": 0.56,
        "long_fit": 0.58,
        "man_beater": 0.5,
        "zone_beater": 0.52,
        "blitz_answer": 0.35,
        "clock_safe": 0.35,
        "risk_level": 0.48,
    },
    "screen": {
        "blitz_answer": 0.62,
        "long_fit": 0.5,
        "explosive_potential": 0.45,
        "clock_safe": 0.48,
        "zone_beater": 0.46,
    },
    "play_action": {
        "explosive_potential": 0.55,
        "man_beater": 0.52,
        "red_zone_fit": 0.58,
        "blitz_answer": 0.4,
        "clock_safe": 0.38,
        "risk_level": 0.52,
    },
    "fade_iso": {
        "red_zone_fit": 0.72,
        "short_yardage_fit": 0.55,
        "explosive_potential": 0.48,
        "man_beater": 0.58,
        "risk_level": 0.55,
    },
    "inside_zone": {
        "short_yardage_fit": 0.58,
        "red_zone_fit": 0.52,
        "clock_safe": 0.62,
        "backed_up_fit": 0.55,
        "blitz_answer": 0.42,
        "risk_level": 0.35,
    },
    "outside_zone": {
        "medium_fit": 0.55,
        "long_fit": 0.46,
        "clock_safe": 0.52,
        "explosive_potential": 0.42,
    },
    "duo": {
        "short_yardage_fit": 0.72,
        "red_zone_fit": 0.62,
        "fourth_down_fit": 0.58,
        "clock_safe": 0.52,
        "blitz_answer": 0.38,
    },
    "power": {
        "short_yardage_fit": 0.75,
        "red_zone_fit": 0.65,
        "goal_line_fit": 0.78,
        "fourth_down_fit": 0.62,
        "clock_safe": 0.55,
        "explosive_potential": 0.32,
    },
    "draw": {
        "blitz_answer": 0.58,
        "long_fit": 0.58,
        "medium_fit": 0.52,
        "clock_safe": 0.4,
    },
    "two_point": {
        "short_yardage_fit": 0.7,
        "red_zone_fit": 0.85,
        "risk_level": 0.5,
    },
}

# Fine-tune classic concepts without editing every library row.
NAME_ATTR_OVERRIDES: Dict[Tuple[str, str], Dict[AttrKey, float]] = {
    ("quick_game", "Stick"): {"short_yardage_fit": 0.62, "clock_safe": 0.58, "blitz_answer": 0.6},
    ("quick_game", "Spacing"): {"zone_beater": 0.62, "clock_safe": 0.56, "medium_fit": 0.55},
    ("quick_game", "Slant-Flat"): {"blitz_answer": 0.64, "man_beater": 0.58, "medium_fit": 0.54},
    ("dropback_pass", "Dagger"): {"explosive_potential": 0.62, "long_fit": 0.65, "medium_fit": 0.58},
    ("dropback_pass", "Drive"): {"zone_beater": 0.58, "medium_fit": 0.62, "clock_safe": 0.42},
    ("dropback_pass", "Y-Cross"): {"explosive_potential": 0.6, "zone_beater": 0.56},
    ("screen", "RB Middle Screen"): {"blitz_answer": 0.68, "long_fit": 0.55},
    ("screen", "Trips Bubble"): {"blitz_answer": 0.55, "clock_safe": 0.5},
    ("play_action", "Boot Flood"): {"explosive_potential": 0.52, "man_beater": 0.54},
    ("play_action", "Y-Leak"): {"red_zone_fit": 0.78, "explosive_potential": 0.65},
    ("inside_zone", "Inside Zone Strong"): {"medium_fit": 0.55, "short_yardage_fit": 0.55},
    ("outside_zone", "Outside Zone Weak"): {"medium_fit": 0.58, "long_fit": 0.48},
    ("duo", "Duo"): {"short_yardage_fit": 0.75, "fourth_down_fit": 0.62},
    ("power", "Power O"): {"short_yardage_fit": 0.8, "goal_line_fit": 0.82},
    ("draw", "Shotgun Draw"): {"blitz_answer": 0.62, "long_fit": 0.6},
    ("fade_iso", "Boundary Fade"): {"red_zone_fit": 0.75, "man_beater": 0.62},
    ("two_point", "Rub / Pick Slant"): {"man_beater": 0.68, "red_zone_fit": 0.9},
    ("two_point", "QB Power / Sneak"): {"short_yardage_fit": 0.92, "risk_level": 0.35},
    ("two_point", "Shovel / RPO Bubble"): {"blitz_answer": 0.55, "zone_beater": 0.5},
}

BUCKET_FIT_ATTR = {
    "red_zone": "red_zone_fit",
    "short_yardage": "short_yardage_fit",
    "backed_up": "backed_up_fit",
    "medium_yardage": "medium_fit",
    "long_yardage": "long_fit",
}


def _attr(
    play: Dict[str, Any],
    family: str,
    attr: str,
) -> float:
    raw = play.get(attr)
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    name = str(play.get("name") or "")
    ovr = NAME_ATTR_OVERRIDES.get((family, name), {}).get(attr)
    if ovr is not None:
        return float(ovr)
    if family in FAMILY_ATTR_DEFAULTS and attr in FAMILY_ATTR_DEFAULTS[family]:
        return float(FAMILY_ATTR_DEFAULTS[family][attr])
    return float(GLOBAL_ATTR_DEFAULTS.get(attr, 0.5))


def play_selection_weight(
    play: Dict[str, Any],
    *,
    family: str,
    ctx: GameContext,
    bucket: str,
    model_input: Optional[ModelInput] = None,
    legacy_bonus: float = 0.0,
) -> float:
    """
    Relative weight for ``rng.choices`` among plays in the same family.
    Keeps influence modest so family-level scores remain primary.
    """
    w = 1.0 + legacy_bonus

    fit_attr = BUCKET_FIT_ATTR.get(bucket, "medium_fit")
    # Goal-line boost inside red zone bucket
    if bucket == "red_zone" and ctx.territory == "opponents" and ctx.yardline <= 5:
        gl = _attr(play, family, "goal_line_fit")
        w *= 1.0 + (gl - 0.5) * 0.45

    fit = _attr(play, family, fit_attr)
    w *= 1.0 + (fit - 0.5) * 0.55

    if ctx.blitz_likely:
        ba = _attr(play, family, "blitz_answer")
        w *= 1.0 + (ba - 0.5) * 0.5

    cov = ctx.coverage_shell or ""
    if cov in ("cover_0", "cover_1"):
        mb = _attr(play, family, "man_beater")
        w *= 1.0 + (mb - 0.5) * 0.35
    elif cov in ("cover_2", "cover_3", "cover_4", "quarters"):
        zb = _attr(play, family, "zone_beater")
        w *= 1.0 + (zb - 0.5) * 0.3

    gm = ctx.game_mode or "normal"
    if gm == "drain_clock":
        cs = _attr(play, family, "clock_safe")
        w *= 1.0 + (cs - 0.5) * 0.4
    elif gm in ("must_score", "two_minute"):
        ex = _attr(play, family, "explosive_potential")
        w *= 1.0 + (ex - 0.5) * 0.28
        if gm == "two_minute":
            cs = _attr(play, family, "clock_safe")
            w *= 1.0 + (cs - 0.5) * 0.22
    elif gm == "normal" and ctx.quarter == 4 and ctx.seconds_remaining <= 120 and ctx.score_diff >= 1:
        cs = _attr(play, family, "clock_safe")
        w *= 1.0 + (cs - 0.5) * 0.2

    if ctx.down == 4:
        fd = _attr(play, family, "fourth_down_fit")
        w *= 1.0 + (fd - 0.5) * 0.45

    if ctx.qb_limited:
        cs = _attr(play, family, "clock_safe")
        ba = _attr(play, family, "blitz_answer")
        w *= 1.0 + (cs - 0.5) * 0.18
        w *= 1.0 + (ba - 0.5) * 0.15

    if model_input is not None:
        feat = model_input.features
        gcf = model_input.meta.get("game_context_features")
        if isinstance(gcf, dict):
            expl = float(feat.get("gcf_recent_explosive_rate", 0) or 0)
            stalled = float(feat.get("gcf_stalled_drive_share", 0) or 0)
            succ = float(feat.get("gcf_recent_success_rate", 0) or 0)
            if expl >= 0.18:
                ex = _attr(play, family, "explosive_potential")
                w *= 1.0 + (ex - 0.5) * 0.32
            if stalled >= 0.45 and succ < 0.42:
                cs = _attr(play, family, "clock_safe")
                rk = _attr(play, family, "risk_level")
                w *= 1.0 + (cs - 0.5) * 0.22
                w *= 1.0 + (0.5 - rk) * 0.18

            top = gcf.get("target_role_top") or []
            if top and float(top[0][1]) >= 0.34:
                heavy = str(top[0][0]).upper()
                featured = play.get("featured_roles")
                if isinstance(featured, list):
                    norm = {str(x).upper() for x in featured}
                    if heavy in norm:
                        w *= 0.76 # Slight bias away from over-called families in history (play-level dampening).
            over = gcf.get("overall") or {}
            orun = float(over.get("run_share") or 0)
            opass = float(over.get("pass_share") or 0)
            is_run = family in RUN_FAMILIES
            if orun >= 0.68 and is_run:
                w *= 0.88
            if opass >= 0.68 and not is_run and family not in RUN_FAMILIES:
                w *= 0.88

    return max(0.04, float(w))
