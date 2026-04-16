from __future__ import annotations

import time
import uuid
from dataclasses import asdict
from typing import Any, Dict, List, Mapping, Optional

from ..domain import ActualPlayResult, GameContext, PASS_FAMILIES, RUN_FAMILIES
from ..features import ModelInput


def _top_family_scores(scores: Mapping[str, float], *, n: int = 5) -> List[Dict[str, Any]]:
    if not scores:
        return []
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"family": k, "score": round(float(v), 4)} for k, v in ranked[:n]]


def _compact_model_input(mi: Optional[ModelInput]) -> Dict[str, Any]:
    if mi is None:
        return {}
    gcf = mi.meta.get("game_context_features") if isinstance(mi.meta, dict) else None
    if not isinstance(gcf, dict):
        gcf = None
    # Trim features to high-signal keys for storage size
    feat = mi.features or {}
    keys = (
        "gcf_archived_team_drives",
        "gcf_overall_run_share",
        "gcf_overall_pass_share",
        "gcf_recent_success_rate",
        "gcf_recent_explosive_rate",
        "gcf_turnover_play_rate",
        "gcf_stalled_drive_share",
        "game_flow_weighted_run_share",
        "game_flow_weighted_pass_share",
        "game_flow_prior_plays",
        "game_flow_seq_len",
    )
    slim_features = {k: feat[k] for k in keys if k in feat}
    return {
        "features": slim_features,
        "game_context_features": gcf,
    }


def audit_record_from_recommendation(
    *,
    result: Dict[str, Any],
    plays_at_recommend: int,
    drive_epoch: int,
    game_id: str,
) -> Dict[str, Any]:
    """
    Build one open audit row from a ``recommend()`` return dict (post-enrichment).

    Stored as plain dict for JSON round-trip on ``Game.recommendation_audit``.
    """
    ctx: GameContext = result["ctx"]
    scores = result.get("scores") or {}
    play = result.get("play") or {}
    mi: Optional[ModelInput] = result.get("model_input")
    fd = result.get("fourth_down") or {}
    model = result.get("model") or {}

    rec: Dict[str, Any] = {
        "snap_id": str(uuid.uuid4())[:12],
        "ts": time.time(),
        "game_id": str(game_id),
        "drive_epoch": int(drive_epoch),
        "plays_at_recommend": int(plays_at_recommend),
        "status": "open",
        "pre_snap": {k: v for k, v in asdict(ctx).items()},
        "bucket": str(result.get("bucket", "")),
        "top_families": _top_family_scores(scores, n=6),
        "selected_family": str(result.get("play_family", "")),
        "selected_play_name": str(play.get("name", "") or ""),
        "model": {
            "name": model.get("name"),
            "version": model.get("version"),
            "confidence": model.get("confidence"),
        },
        "fourth_down_recommendation": fd.get("recommendation"),
        "model_input_compact": _compact_model_input(mi),
    }
    mo = result.get("model_output")
    if mo is not None and hasattr(mo, "extras") and isinstance(mo.extras, dict):
        bs = mo.extras.get("base_scores")
        if isinstance(bs, dict) and bs:
            rec["base_scores_top"] = _top_family_scores(bs, n=4)
    return rec


def append_open_audit(game_audit_list: List[Dict[str, Any]], record: Dict[str, Any]) -> None:
    game_audit_list.append(record)


def actual_to_audit_dict(actual: ActualPlayResult) -> Dict[str, Any]:
    d = asdict(actual)
    return d


def void_last_closed_audit(game_audit_list: List[Dict[str, Any]]) -> None:
    """Mark the most recent closed audit as undone (user reversed the logged play)."""
    for rec in reversed(game_audit_list):
        if rec.get("status") == "closed":
            rec["status"] = "void_undone"
            rec.pop("linked_actual", None)
            return


def trim_stale_open_audits(game_audit_list: List[Dict[str, Any]], plays_on_drive: int) -> None:
    """Drop trailing open audits that assumed more plays than currently on the drive (e.g. after undo)."""
    n = int(plays_on_drive)
    while game_audit_list and game_audit_list[-1].get("status") == "open":
        pat = int(game_audit_list[-1].get("plays_at_recommend", -1))
        if pat > n:
            game_audit_list.pop()
        else:
            break


def link_open_audit_to_actual(
    game_audit_list: List[Dict[str, Any]],
    *,
    plays_after_log: int,
    actual: ActualPlayResult,
) -> bool:
    """
    Close the most recent open audit that matches this snap (plays_at_recommend == plays_after_log - 1).

    Returns True if a row was updated.
    """
    target_prev = int(plays_after_log) - 1
    for rec in reversed(game_audit_list):
        if rec.get("status") != "open":
            continue
        if int(rec.get("plays_at_recommend", -999)) != target_prev:
            continue
        rec["linked_actual"] = actual_to_audit_dict(actual)
        rec["status"] = "closed"
        return True
    return False


def aggressiveness_label(family: str) -> str:
    """Coarse bucket for run vs pass tendency vs special."""
    if family in RUN_FAMILIES:
        return "run_family"
    if family in PASS_FAMILIES:
        return "pass_family"
    if family == "two_point":
        return "two_point"
    return "other"


def situation_bucket(ctx: Mapping[str, Any]) -> str:
    """Human-readable situation tag for grouping in metrics."""
    down = int(ctx.get("down", 1))
    dist = int(ctx.get("distance", 10))
    terr = str(ctx.get("territory", "own"))
    yl = int(ctx.get("yardline", 25))
    if terr == "opponents" and yl <= 20:
        zone = "red_zone"
    elif terr == "opponents" and yl <= 35:
        zone = "frontier"
    elif terr == "own" and yl <= 15:
        zone = "backed_up"
    else:
        zone = "field"
    short = dist <= 2 and down < 4
    long = dist >= 7
    if down == 4:
        return f"4th_{zone}"
    if short:
        return f"short_yardage_{zone}"
    if long:
        return f"long_distance_{zone}"
    return f"standard_{zone}"
