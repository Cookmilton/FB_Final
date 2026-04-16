from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, MutableMapping, Set

from ..domain import ActualPlayResult
from ..game import Game
from ..situation import territory_yardline_from_abs_yards
from ..state import DriveLogger
from .types import FeedPlayEvent, NormalizedGameSnapshot, SyncResult


def _family_from_feed_event(ev: FeedPlayEvent) -> str:
    if ev.type_hint == "rush":
        return "inside_zone"
    if ev.type_hint == "pass":
        return "dropback_pass"
    return "dropback_pass"


@dataclass
class SyncOptions:
    """Hybrid mode: locks skip applying feed fields so manual entry wins."""

    lock_situation: bool = False
    lock_score: bool = False
    auto_append_feed_plays: bool = False
    only_append_when_our_possession: bool = True
    reset_seen_play_ids_on_possession_change: bool = True


def apply_snapshot(
    *,
    game: Game,
    session: MutableMapping[str, Any],
    drive_log: DriveLogger,
    snapshot: NormalizedGameSnapshot,
    options: SyncOptions,
) -> SyncResult:
    """
    Merge ``snapshot`` into ``game``, Streamlit widget keys on ``session``, and optionally ``drive_log``.

    Mutates ``session`` keys ``ui_*``, ``live_feed_*`` audit keys, and ``live_feed_seen_play_ids``.
    """
    applied: List[str] = []
    skipped: List[str] = []

    if snapshot.quarter is not None:
        session["ui_quarter"] = int(snapshot.quarter)
        game.quarter = int(snapshot.quarter)
        applied.append("quarter")

    if snapshot.clock_seconds_in_period is not None:
        sec = int(snapshot.clock_seconds_in_period)
        session["ui_clock_mins"] = sec // 60
        session["ui_clock_secs"] = sec % 60
        game.clock_seconds_remaining = sec
        applied.append("clock")

    if not options.lock_score:
        if snapshot.our_score is not None:
            game.offense_points = int(snapshot.our_score)
            applied.append("our_score→game.offense_points")
        if snapshot.opponent_score is not None:
            game.defense_points = int(snapshot.opponent_score)
            applied.append("opponent_score→game.defense_points")
        if snapshot.our_timeouts is not None:
            session["ui_own_tos"] = max(0, min(3, int(snapshot.our_timeouts)))
            applied.append("own_timeouts")
        if snapshot.opponent_timeouts is not None:
            session["ui_opp_tos"] = max(0, min(3, int(snapshot.opponent_timeouts)))
            applied.append("opp_timeouts")
    else:
        skipped.append("score/timeouts locked")

    if snapshot.possession_is_our_team is not None:
        session["ui_possession_side"] = "Our team" if snapshot.possession_is_our_team else "Opponent"
        game.possession = "offense" if snapshot.possession_is_our_team else "defense"
        applied.append("possession")

    if not options.lock_situation:
        if snapshot.down is not None:
            session["ui_down"] = max(1, min(4, int(snapshot.down)))
            applied.append("down")
        if snapshot.distance is not None:
            session["ui_distance"] = max(1, min(25, int(snapshot.distance)))
            applied.append("distance")
        if snapshot.abs_yards_from_own_goal is not None:
            terr, yl = territory_yardline_from_abs_yards(int(snapshot.abs_yards_from_own_goal))
            session["ui_territory"] = terr
            session["ui_yardline"] = int(yl)
            applied.append("field_position")
    else:
        skipped.append("situation locked")

    plays_appended = 0
    if options.auto_append_feed_plays and snapshot.new_plays:
        seen_list = list(session.get("live_feed_seen_play_ids") or [])
        seen: Set[str] = set(str(x) for x in seen_list)
        last_p = session.get("live_feed_last_possession_team_id")
        cur_p = snapshot.possession_team_id
        if (
            options.reset_seen_play_ids_on_possession_change
            and cur_p
            and last_p
            and str(cur_p) != str(last_p)
        ):
            seen.clear()
        allow = True
        if options.only_append_when_our_possession and snapshot.possession_is_our_team is False:
            allow = False
            skipped.append("feed plays skipped (opponent possession)")
        if allow:
            for ev in snapshot.new_plays:
                eid = str(ev.event_id)
                if eid in seen:
                    continue
                fam = _family_from_feed_event(ev)
                pt = "run" if fam in ("inside_zone", "outside_zone", "power", "draw") else "pass"
                actual = ActualPlayResult(
                    family=fam,
                    concept_name="Feed",
                    play_type=pt,
                    result_type="feed",
                    yards_gained=int(ev.yards_gained or 0),
                    description=f"[Feed] {ev.summary_text[:220]}",
                )
                drive_log.log(actual)
                seen.add(eid)
                plays_appended += 1
        session["live_feed_seen_play_ids"] = list(seen)
    elif snapshot.new_plays:
        skipped.append("feed plays not auto-appended (toggle off)")

    if snapshot.possession_team_id:
        session["live_feed_last_possession_team_id"] = str(snapshot.possession_team_id)

    audit = {
        "provider": snapshot.provider,
        "game_id": snapshot.external_game_id,
        "status": snapshot.status_detail,
        "applied": applied,
        "skipped": skipped,
        "plays_appended": plays_appended,
        "debug_notes": list(snapshot.debug_notes),
    }
    session["live_feed_last_audit"] = audit
    session["live_feed_last_sync_epoch"] = snapshot.fetched_at_epoch
    session["live_feed_last_origin"] = "feed"

    msg = f"Synced {snapshot.provider} ({snapshot.status_detail})" if applied else "Sync: no fields updated"
    return SyncResult(
        ok=True,
        applied_fields=applied,
        skipped_reasons=skipped,
        plays_appended=plays_appended,
        message=msg,
    )


def session_mark_manual(session: MutableMapping[str, Any], *, note: str = "") -> None:
    """Call when the operator changes situation manually so the UI can show origin."""
    session["live_feed_last_origin"] = "manual"
    if note:
        session["live_feed_manual_note"] = note
