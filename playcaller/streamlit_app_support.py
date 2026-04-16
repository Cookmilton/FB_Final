"""
Shared Streamlit session keys and defaults for the Play Caller app.

Keeps streamlit_app.py thinner without changing widget key strings or behavior.
"""

from __future__ import annotations

from typing import Any, MutableMapping

from playcaller import DriveLogger, FootballPlayPredictor, Game
from playcaller.evaluation.calibration import load_calibration_profile
from playcaller.game import DRIVE_END_UI_AUTO

PENDING_LOG_SITUATION = "pending_log_situation"
# After **End drive**: clock + possession must not be written while sidebar widgets exist — apply next run.
PENDING_END_DRIVE_UI = "pending_end_drive_ui"
# After **New game**: full sidebar/widget reset must apply before any ``key="ui_*"`` widgets render.
PENDING_NEW_GAME_UI = "pending_new_game_ui"
LAST_DRIVE_SNAP_CONTEXT = "last_drive_snap_context"
UNDO_BUNDLE = "undo_pre_snap_bundle"


def possession_side_radio_label(*, possession: str) -> str:
    """Sidebar radio label for who has the ball (``Game.possession`` is ``offense`` | ``defense``)."""
    return "Our team" if possession == "offense" else "Opponent"


def new_game_ui_values() -> dict[str, Any]:
    """Widget/session values after ``Game.new_game()`` + fresh drive log (single source of truth)."""
    return {
        "ui_down": 1,
        "ui_distance": 10,
        "ui_territory": "own",
        "ui_yardline": 25,
        "ui_def_personnel": "nickel",
        "ui_box_count": 7,
        "ui_coverage_shell": "cover_3",
        "ui_safeties": "single_high",
        "ui_blitz_likely": False,
        "ui_quarter": 2,
        "ui_clock_total": 30 * 60,
        "ui_clock_mins": 30,
        "ui_clock_secs": 0,
        "ui_own_tos": 3,
        "ui_opp_tos": 3,
        "ui_weather": "clear",
        "ui_wind_mph": 0,
        "ui_qb_limited": False,
        "ui_game_mode": "normal",
        "ui_mismatch": "",
        "ui_auto_generate": False,
        "ui_drive_end_on_new": DRIVE_END_UI_AUTO,
        "ui_possession_side": "Our team",
    }


def ensure_play_caller_session_defaults(ss: MutableMapping[str, Any]) -> None:
    """One-time defaults for predictor, game, drive log, and all ui_* widget keys."""
    if "predictor" not in ss:
        ss["predictor"] = FootballPlayPredictor(calibration=load_calibration_profile())
    if "drive_log" not in ss:
        ss["drive_log"] = DriveLogger()
    if "game" not in ss:
        ss["game"] = Game.new_game()
    if "result" not in ss:
        ss["result"] = None

    for k, v in new_game_ui_values().items():
        if k not in ss:
            ss[k] = v
    if "last_play_summary" not in ss:
        ss["last_play_summary"] = ""
    if "ui_debug_game_context" not in ss:
        ss["ui_debug_game_context"] = False
    if "ui_live_espn_sport" not in ss:
        ss["ui_live_espn_sport"] = "nfl"
    if "ui_live_lock_situation" not in ss:
        ss["ui_live_lock_situation"] = False
    if "ui_live_lock_score" not in ss:
        ss["ui_live_lock_score"] = False
    if "ui_live_auto_plays" not in ss:
        ss["ui_live_auto_plays"] = False
    if "live_feed_scoreboard_rows" not in ss:
        ss["live_feed_scoreboard_rows"] = []
    if "ui_live_event_id_manual" not in ss:
        ss["ui_live_event_id_manual"] = ""
    if "ui_live_our_team_manual" not in ss:
        ss["ui_live_our_team_manual"] = ""
    if "ui_live_home_or_away" not in ss:
        ss["ui_live_home_or_away"] = "away"
    if "live_feed_last_origin" not in ss:
        ss["live_feed_last_origin"] = "manual"
    if "eval_drive_epoch" not in ss:
        ss["eval_drive_epoch"] = 0
    if "ui_eval_audit_enabled" not in ss:
        ss["ui_eval_audit_enabled"] = True


def apply_pending_log_situation(ss: MutableMapping[str, Any]) -> None:
    """Apply auto-advance from the last logged play; run before any ui_* widgets."""
    pending = ss.pop(PENDING_LOG_SITUATION, None)
    if not pending:
        return
    ss["ui_territory"] = str(pending["territory"])
    ss["ui_yardline"] = int(pending["yardline"])
    ss["ui_down"] = int(pending["down"])
    ss["ui_distance"] = int(pending["distance"])


def apply_pending_end_drive_ui(ss: MutableMapping[str, Any]) -> None:
    """Apply clock + possession after archiving a drive; run before any ui_* widgets."""
    pending = ss.pop(PENDING_END_DRIVE_UI, None)
    if not pending:
        return
    if "ui_clock_mins" in pending:
        ss["ui_clock_mins"] = int(pending["ui_clock_mins"])
    if "ui_clock_secs" in pending:
        ss["ui_clock_secs"] = int(pending["ui_clock_secs"])
    if "ui_possession_side" in pending:
        ss["ui_possession_side"] = str(pending["ui_possession_side"])


def apply_pending_new_game_ui(ss: MutableMapping[str, Any]) -> None:
    """Apply full **New game** widget defaults; run before any ui_* widgets."""
    pending = ss.pop(PENDING_NEW_GAME_UI, None)
    if not pending:
        return
    for k, v in pending.items():
        ss[str(k)] = v


def clear_in_progress_log_state(ss: MutableMapping[str, Any]) -> None:
    """Drop pending snap merge, drive-end hints, and undo snapshot (not the drive log itself)."""
    ss.pop(PENDING_LOG_SITUATION, None)
    ss.pop(LAST_DRIVE_SNAP_CONTEXT, None)
    ss.pop(UNDO_BUNDLE, None)


def clear_live_feed_session_keys(ss: MutableMapping[str, Any]) -> None:
    ss.pop("live_feed_seen_play_ids", None)
    ss.pop("live_feed_last_possession_team_id", None)
    ss.pop("live_feed_last_audit", None)
    ss.pop("live_feed_last_error", None)
    ss.pop("live_feed_last_sync_epoch", None)
    ss["live_feed_last_origin"] = "manual"
