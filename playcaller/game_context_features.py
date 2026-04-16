"""
Aggregated game-history features for the recommendation layer.

Uses only ``Game``, ``Drive``, and ``ActualPlayResult`` — does not touch the logging pipeline.

**Synthetic down:** ``ActualPlayResult`` does not store pre-snap down. We replay a nominal
chain (1st→2nd→…→4th) within each drive segment, resetting to 1st after first downs /
touchdowns. Late-down run/pass shares are therefore *approximate* but stable and useful for tendencies.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .domain import PASS_FAMILIES, RUN_FAMILIES, ActualPlayResult
from .game import DRIVE_END_TOUCHDOWN, DRIVE_END_FIELD_GOAL, Game
from .state import DriveLogger

_GCF_VERSION = 1

# Heavier-weight concepts often called near the goal line (weak field-position proxy).
_CONDENSED_FIELD_FAMILIES = frozenset({"fade_iso", "power", "inside_zone", "quick_game"})


def _net_yards(p: ActualPlayResult) -> int:
    return int(p.yards_gained) + (int(p.penalty_yards) if p.penalty else 0)


def _is_run_play(p: ActualPlayResult) -> bool:
    pt = (p.play_type or "").lower()
    if pt == "run":
        return True
    fam = str(p.family or "")
    return fam in RUN_FAMILIES or pt in ("qb_scramble",)


def _is_pass_play(p: ActualPlayResult) -> bool:
    pt = (p.play_type or "").lower()
    if pt == "pass":
        return True
    fam = str(p.family or "")
    return fam in PASS_FAMILIES


def _play_success(p: ActualPlayResult) -> bool:
    if bool(p.first_down) or bool(p.touchdown):
        return True
    if _net_yards(p) >= 5:
        return True
    return False


def _explosive_play(p: ActualPlayResult) -> bool:
    if bool(p.touchdown):
        return True
    return _net_yards(p) >= 15


def _turnover_play(p: ActualPlayResult) -> bool:
    if bool(p.turnover):
        return True
    rt = (p.result_type or "").lower()
    tk = (p.turnover_kind or "").lower()
    pr = (p.pass_result or "").lower()
    if "interception" in rt or tk == "interception" or pr == "intercepted":
        return True
    if tk == "fumble" or rt == "fumble":
        return True
    return False


def _normalize_target_role(p: ActualPlayResult) -> str:
    """
    Bucket targets for tendency / diversification (X, Z, H, Y, RB, TE, unknown).
    """
    lbl = (p.target_role_label or "").strip().upper()
    if lbl:
        if lbl in ("X", "Z", "H", "Y"):
            return lbl
        if "SLOT" in lbl or lbl == "SLOT":
            return "H"
        if "TE" in lbl or lbl in ("Y", "T"):
            return "Y"
        if "RB" in lbl or "BACK" in lbl:
            return "RB"
    pos = (p.target_position or "").strip().upper()
    if pos in ("X", "Z", "H", "Y"):
        return pos
    if pos == "RB":
        return "RB"
    if pos == "TE":
        return "Y"
    pt = (p.play_type or "").lower()
    fam = str(p.family or "")
    if pt == "run" or fam in RUN_FAMILIES:
        return "RB"
    if p.ball_carrier_or_target:
        b = p.ball_carrier_or_target.strip().upper()
        if b in ("X", "Z", "H", "Y"):
            return b
    return "unknown"


def _drive_segments_for_team(game: Optional[Game], drive_log: Optional[DriveLogger]) -> List[List[ActualPlayResult]]:
    segments: List[List[ActualPlayResult]] = []
    if game is not None:
        team = game.possession
        for dr in game.drives:
            if dr.possessing_team == team and dr.plays:
                segments.append(list(dr.plays))
    if drive_log and drive_log.results:
        segments.append(list(drive_log.results))
    return segments


def _flatten_plays_with_synthetic_down(
    segments: List[List[ActualPlayResult]],
) -> List[Tuple[ActualPlayResult, int]]:
    """Pair each play with synthetic down (1–4) within its drive segment."""
    out: List[Tuple[ActualPlayResult, int]] = []
    for plays in segments:
        d = 1
        for p in plays:
            out.append((p, max(1, min(4, d))))
            if bool(p.first_down) or bool(p.touchdown):
                d = 1
            else:
                d = min(4, d + 1)
    return out


def _share_run_pass(plays: List[ActualPlayResult]) -> Tuple[float, float, int]:
    runs = 0
    passes = 0
    for p in plays:
        if _is_run_play(p):
            runs += 1
        elif _is_pass_play(p):
            passes += 1
    t = runs + passes
    if t <= 0:
        return 0.0, 0.0, 0
    return runs / t, passes / t, t


def build_game_context_features(
    game: Optional[Game],
    drive_log: Optional[DriveLogger],
    *,
    last_n: int = 5,
) -> Dict[str, Any]:
    """
    Structured history bundle for ``ModelInput.meta["game_context_features"]``.

    All rates are over the possessing team's plays (archived drives + current log).
    """
    segments = _drive_segments_for_team(game, drive_log)
    flat_sd = _flatten_plays_with_synthetic_down(segments)
    all_plays = [t[0] for t in flat_sd]

    n_plays = len(all_plays)
    if n_plays == 0:
        return {
            "version": _GCF_VERSION,
            "sample_size_plays": 0,
            "overall": {
                "run_share": 0.0,
                "pass_share": 0.0,
                "success_rate": 0.0,
                "explosive_rate": 0.0,
                "turnover_play_rate": 0.0,
            },
            "by_synthetic_down": {
                "early_1_2": {"run_share": 0.0, "pass_share": 0.0, "n": 0},
                "late_3_4": {"run_share": 0.0, "pass_share": 0.0, "n": 0},
            },
            "target_role_share": {},
            "target_role_top": [],
            "last_n_plays": [],
            "last_archived_drive_result_kind": "",
            "drive_end_shares": {},
            "scoring_drive_share": 0.0,
            "stalled_drive_share": 0.0,
            "condensed_field_play_share": 0.0,
            "recent_success_rate": 0.0,
            "recent_explosive_rate": 0.0,
            "archived_team_drive_count": 0,
        }

    early_plays: List[ActualPlayResult] = []
    late_plays: List[ActualPlayResult] = []
    for p, sd in flat_sd:
        if sd <= 2:
            early_plays.append(p)
        else:
            late_plays.append(p)

    erun, epass, en = _share_run_pass(early_plays)
    lrun, lpass, ln = _share_run_pass(late_plays)
    orun, opass, on = _share_run_pass(all_plays)

    successes = sum(1 for p in all_plays if _play_success(p))
    explosives = sum(1 for p in all_plays if _explosive_play(p))
    turnovers = sum(1 for p in all_plays if _turnover_play(p))

    role_counts: Dict[str, int] = {}
    for p in all_plays:
        if not (_is_pass_play(p) or _is_run_play(p)):
            continue
        role = _normalize_target_role(p)
        if role == "unknown" and not p.ball_carrier_or_target and not p.target_role_label:
            continue
        role_counts[role] = role_counts.get(role, 0) + 1

    role_total = sum(role_counts.values())
    role_share = {k: round(v / role_total, 4) for k, v in role_counts.items()} if role_total else {}
    role_top = sorted(role_share.items(), key=lambda x: -x[1])[:5]

    last_n_summary: List[Dict[str, Any]] = []
    for p in all_plays[-last_n:]:
        fam = str(p.family or "")
        last_n_summary.append(
            {
                "family": fam,
                "play_type": str(p.play_type or ""),
                "yards": _net_yards(p),
                "success": _play_success(p),
                "explosive": _explosive_play(p),
                "target_role": _normalize_target_role(p),
            }
        )

    last_archived = ""
    drive_end_counts: Dict[str, int] = {}
    scoring_ends = 0
    stalled_ends = 0
    n_team_drives = 0
    if game is not None:
        team = game.possession
        team_drives = [dr for dr in game.drives if dr.possessing_team == team]
        n_team_drives = len(team_drives)
        if team_drives:
            res = team_drives[-1].result
            last_archived = str(res.kind) if res else ""
        for dr in team_drives:
            k = dr.result.kind if dr.result else "unknown"
            drive_end_counts[k] = drive_end_counts.get(k, 0) + 1
            if k in (DRIVE_END_TOUCHDOWN, DRIVE_END_FIELD_GOAL):
                scoring_ends += 1
            if k in (
                "punt",
                "turnover_interception",
                "turnover_fumble",
                "turnover_on_downs",
                "field_goal_miss",
            ):
                stalled_ends += 1

    denom_drives = max(1, n_team_drives)
    scoring_drive_share = scoring_ends / denom_drives
    stalled_drive_share = stalled_ends / denom_drives
    drive_end_shares = {k: round(v / denom_drives, 4) for k, v in drive_end_counts.items()}

    condensed_hits = sum(1 for p in all_plays if str(p.family or "") in _CONDENSED_FIELD_FAMILIES)
    condensed_share = condensed_hits / n_plays

    recent_slice = all_plays[-min(12, n_plays) :]
    recent_succ = sum(1 for p in recent_slice if _play_success(p)) / max(1, len(recent_slice))
    recent_expl = sum(1 for p in recent_slice if _explosive_play(p)) / max(1, len(recent_slice))

    return {
        "version": _GCF_VERSION,
        "sample_size_plays": n_plays,
        "overall": {
            "run_share": round(orun, 4),
            "pass_share": round(opass, 4),
            "success_rate": round(successes / n_plays, 4),
            "explosive_rate": round(explosives / n_plays, 4),
            "turnover_play_rate": round(turnovers / n_plays, 4),
        },
        "by_synthetic_down": {
            "early_1_2": {"run_share": round(erun, 4), "pass_share": round(epass, 4), "n": en},
            "late_3_4": {"run_share": round(lrun, 4), "pass_share": round(lpass, 4), "n": ln},
        },
        "target_role_share": role_share,
        "target_role_top": role_top,
        "last_n_plays": last_n_summary,
        "last_archived_drive_result_kind": last_archived,
        "drive_end_shares": drive_end_shares,
        "scoring_drive_share": round(scoring_drive_share, 4),
        "stalled_drive_share": round(stalled_drive_share, 4),
        "condensed_field_play_share": round(condensed_share, 4),
        "recent_success_rate": round(recent_succ, 4),
        "recent_explosive_rate": round(recent_expl, 4),
        "archived_team_drive_count": n_team_drives,
    }


def flatten_game_context_features_for_model(gcf: Dict[str, Any]) -> Dict[str, float]:
    """Numeric scalars merged into ``ModelInput.features`` (prefix ``gcf_``)."""
    out: Dict[str, float] = {}
    ov = gcf.get("overall") or {}
    out["gcf_sample_size_plays"] = float(gcf.get("sample_size_plays") or 0)
    out["gcf_overall_run_share"] = float(ov.get("run_share") or 0)
    out["gcf_overall_pass_share"] = float(ov.get("pass_share") or 0)
    out["gcf_success_rate"] = float(ov.get("success_rate") or 0)
    out["gcf_explosive_rate"] = float(ov.get("explosive_rate") or 0)
    out["gcf_turnover_play_rate"] = float(ov.get("turnover_play_rate") or 0)

    early = (gcf.get("by_synthetic_down") or {}).get("early_1_2") or {}
    late = (gcf.get("by_synthetic_down") or {}).get("late_3_4") or {}
    out["gcf_early_run_share"] = float(early.get("run_share") or 0)
    out["gcf_early_pass_share"] = float(early.get("pass_share") or 0)
    out["gcf_late_run_share"] = float(late.get("run_share") or 0)
    out["gcf_late_pass_share"] = float(late.get("pass_share") or 0)
    out["gcf_late_down_n"] = float(late.get("n") or 0)

    out["gcf_scoring_drive_share"] = float(gcf.get("scoring_drive_share") or 0)
    out["gcf_stalled_drive_share"] = float(gcf.get("stalled_drive_share") or 0)
    out["gcf_condensed_field_play_share"] = float(gcf.get("condensed_field_play_share") or 0)
    out["gcf_recent_success_rate"] = float(gcf.get("recent_success_rate") or 0)
    out["gcf_recent_explosive_rate"] = float(gcf.get("recent_explosive_rate") or 0)

    # Dominant target role concentration (0–1).
    top = gcf.get("target_role_top") or []
    out["gcf_top_target_role_share"] = float(top[0][1]) if top else 0.0
    out["gcf_archived_team_drives"] = float(gcf.get("archived_team_drive_count") or 0)

    return out
