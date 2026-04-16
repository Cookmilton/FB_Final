from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .domain import PASS_FAMILIES, RUN_FAMILIES, ActualPlayResult, GameContext
from .game import Game
from .game_context_features import build_game_context_features, flatten_game_context_features_for_model
from .state import DriveLogger


@dataclass(frozen=True)
class ModelInput:
    """
    Stable, serializable-ish bundle for future ML/LLM backends.

    Keep:
    - `features`: numeric + categorical fields (JSON-friendly)
    - `meta`: non-model debug context (optional)
    """

    features: Dict[str, Any]
    meta: Dict[str, Any] = field(default_factory=dict)


def weighted_family_from_plays(
    plays: List[ActualPlayResult],
    *,
    half_life_plays: float = 4.0,
    max_plays: int = 24,
) -> Dict[str, float]:
    """
    Recency-weighted play-call families over an arbitrary play list (e.g. full game for one team).

    Same weight scheme as ``DriveLogger.weighted_family_counts`` (half-life in plays).
    """
    if not plays or max_plays <= 0:
        return {}
    if half_life_plays <= 0:
        half_life_plays = 4.0
    decay = math.log(0.5) / half_life_plays
    out: Dict[str, float] = {}
    recent = plays[-max_plays:]
    for i, r in enumerate(reversed(recent)):
        fam = str(r.family or "")
        if not fam:
            continue
        w = math.exp(decay * i)
        out[fam] = out.get(fam, 0.0) + w
    return out


def plays_for_possessing_team(game: Optional[Game], drive_log: Optional[DriveLogger]) -> List[ActualPlayResult]:
    """
    All logged plays for whoever has the ball now: completed drives with matching
    ``possessing_team`` plus the in-progress ``drive_log``.
    """
    if game is None:
        return list(drive_log.results) if drive_log else []
    team = game.possession
    out: List[ActualPlayResult] = []
    for dr in game.drives:
        if dr.possessing_team == team:
            out.extend(dr.plays)
    if drive_log:
        out.extend(drive_log.results)
    return out


def prior_possessing_team_drive_stats(game: Optional[Game]) -> Tuple[int, int]:
    """(completed_drive_count, play_count) for the current possessing team, archived drives only."""
    if game is None:
        return 0, 0
    team = game.possession
    n_dr = 0
    n_pl = 0
    for dr in game.drives:
        if dr.possessing_team != team:
            continue
        n_dr += 1
        n_pl += len(dr.plays)
    return n_dr, n_pl


def extract_model_input(
    ctx: GameContext,
    drive_log: Optional[DriveLogger],
    game: Optional[Game] = None,
) -> ModelInput:
    """
    Feature extraction should be deterministic and side-effect free.

    Downstream models should not need Streamlit objects or UI state.

    When ``game`` is provided, adds **game-flow** features: tendencies across all of this
    team's logged plays in the session (prior drives + current series).
    """
    weighted: Dict[str, float] = {}
    recent_fams: List[str] = []
    if drive_log is not None:
        weighted = drive_log.weighted_family_counts(half_life_plays=3.0, max_plays=12)
        recent_fams = drive_log.recent_families(6)

    run_w = sum(w for fam, w in weighted.items() if fam in RUN_FAMILIES)
    pass_w = sum(w for fam, w in weighted.items() if fam in PASS_FAMILIES)
    total_w = run_w + pass_w
    run_share_w = (run_w / total_w) if total_w > 0 else 0.0
    pass_share_w = (pass_w / total_w) if total_w > 0 else 0.0

    streak_len = 0
    if recent_fams:
        last = recent_fams[-1]
        for fam in reversed(recent_fams):
            if fam == last:
                streak_len += 1
            else:
                break

    flow_plays = plays_for_possessing_team(game, drive_log)
    pr_dr, pr_pl = prior_possessing_team_drive_stats(game)
    gf_weighted = weighted_family_from_plays(flow_plays, half_life_plays=4.0, max_plays=24)
    gf_run_w = sum(w for fam, w in gf_weighted.items() if fam in RUN_FAMILIES)
    gf_pass_w = sum(w for fam, w in gf_weighted.items() if fam in PASS_FAMILIES)
    gf_tot = gf_run_w + gf_pass_w
    gf_run_share = (gf_run_w / gf_tot) if gf_tot > 0 else 0.0
    gf_pass_share = (gf_pass_w / gf_tot) if gf_tot > 0 else 0.0

    gf_recent = [str(p.family) for p in flow_plays[-6:] if p.family]
    gf_streak = 0
    if gf_recent:
        last_g = gf_recent[-1]
        for fam in reversed(gf_recent):
            if fam == last_g:
                gf_streak += 1
            else:
                break

    features: Dict[str, Any] = {
        # Core situation
        "down": int(ctx.down),
        "distance": int(ctx.distance),
        "yardline": int(ctx.yardline),
        "territory": ctx.territory,
        # Script
        "quarter": int(ctx.quarter),
        "seconds_remaining": int(ctx.seconds_remaining),
        "score_diff": int(ctx.score_diff),
        "own_timeouts": int(ctx.own_timeouts),
        "opp_timeouts": int(ctx.opp_timeouts),
        "game_mode": ctx.game_mode,
        # Defense
        "def_personnel": ctx.def_personnel,
        "box_count": int(ctx.box_count),
        "coverage_shell": ctx.coverage_shell,
        "safeties": ctx.safeties,
        "blitz_likely": bool(ctx.blitz_likely),
        # Environment / personnel
        "weather": ctx.weather,
        "wind_mph": int(ctx.wind_mph),
        "turf": ctx.turf,
        "qb_limited": bool(ctx.qb_limited),
        "personnel_group": ctx.personnel_group,
        "mismatch": ctx.mismatch or "",
        # Drive counters (explicit + derived) — **this series only** (``drive_log``)
        "plays_this_drive": int(ctx.plays_this_drive),
        "run_plays_this_drive": int(ctx.run_plays_this_drive),
        "weighted_run_share": float(run_share_w),
        "weighted_pass_share": float(pass_share_w),
        "recent_streak_len": int(streak_len),
        "recent_last_family": recent_fams[-1] if recent_fams else "",
        # Game-flow — this possessing team, prior drives + current log
        "game_flow_prior_drives": int(pr_dr),
        "game_flow_prior_plays": int(pr_pl),
        "game_flow_seq_len": int(len(flow_plays)),
        "game_flow_weighted_run_share": float(gf_run_share),
        "game_flow_weighted_pass_share": float(gf_pass_share),
        "game_flow_recent_streak_len": int(gf_streak),
        "game_flow_recent_last_family": gf_recent[-1] if gf_recent else "",
    }

    # Flatten weighted family counts for simple tabular models / LLM tool schemas.
    for fam, w in weighted.items():
        features[f"w_family__{fam}"] = float(w)
    for fam, w in gf_weighted.items():
        features[f"gf_w_family__{fam}"] = float(w)

    game_context_features = build_game_context_features(game, drive_log, last_n=5)
    for k, v in flatten_game_context_features_for_model(game_context_features).items():
        features[k] = float(v)

    meta = {
        "recent_families": recent_fams,
        "weighted_family_counts": weighted,
        "game_flow_weighted_family_counts": gf_weighted,
        "game_flow_recent_families": gf_recent,
        "game_context_features": game_context_features,
    }

    return ModelInput(features=features, meta=meta)
