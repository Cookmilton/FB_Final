"""
Game session: multiple drives, Gamecast-style summaries.

Aggregates ``ActualPlayResult`` rows without changing the logging / advancement pipeline.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field, fields, replace
from typing import Any, Dict, List, Optional

from .domain import ActualPlayResult

# Drive ended how (stable keys for analytics / UI)
DRIVE_END_TOUCHDOWN = "touchdown"
DRIVE_END_FIELD_GOAL = "field_goal"
DRIVE_END_FIELD_GOAL_MISS = "field_goal_miss"
DRIVE_END_PUNT = "punt"
DRIVE_END_TURNOVER_INT = "turnover_interception"
DRIVE_END_TURNOVER_FUMBLE = "turnover_fumble"
DRIVE_END_TURNOVER_ON_DOWNS = "turnover_on_downs"
DRIVE_END_UNKNOWN = "unknown"

# Drive endings that change who has the ball (simplified: always flip offense ↔ defense).
DRIVE_END_CHANGE_OF_POSSESSION_KINDS = frozenset(
    {
        DRIVE_END_TOUCHDOWN,
        DRIVE_END_FIELD_GOAL,
        DRIVE_END_FIELD_GOAL_MISS,
        DRIVE_END_PUNT,
        DRIVE_END_TURNOVER_INT,
        DRIVE_END_TURNOVER_FUMBLE,
        DRIVE_END_TURNOVER_ON_DOWNS,
    }
)

# Kinds allowed for explicit user override when completing a drive (includes ``unknown``).
DRIVE_END_OVERRIDE_KINDS = frozenset(
    {
        DRIVE_END_TOUCHDOWN,
        DRIVE_END_FIELD_GOAL,
        DRIVE_END_FIELD_GOAL_MISS,
        DRIVE_END_PUNT,
        DRIVE_END_TURNOVER_INT,
        DRIVE_END_TURNOVER_FUMBLE,
        DRIVE_END_TURNOVER_ON_DOWNS,
        DRIVE_END_UNKNOWN,
    }
)

# Sidebar / form ordering for “how did this drive end?” (values match ``DRIVE_END_*`` or ``auto``).
DRIVE_END_UI_AUTO = "auto"
DRIVE_END_UI_OPTIONS = (
    DRIVE_END_UI_AUTO,
    DRIVE_END_TOUCHDOWN,
    DRIVE_END_FIELD_GOAL,
    DRIVE_END_FIELD_GOAL_MISS,
    DRIVE_END_PUNT,
    DRIVE_END_TURNOVER_INT,
    DRIVE_END_TURNOVER_FUMBLE,
    DRIVE_END_TURNOVER_ON_DOWNS,
    DRIVE_END_UNKNOWN,
)
DRIVE_END_UI_LABELS = {
    DRIVE_END_UI_AUTO: "Auto (infer from plays & last snap)",
    DRIVE_END_TOUCHDOWN: "Touchdown",
    DRIVE_END_FIELD_GOAL: "Field goal (good)",
    DRIVE_END_FIELD_GOAL_MISS: "Field goal (missed)",
    DRIVE_END_PUNT: "Punt",
    DRIVE_END_TURNOVER_INT: "Interception",
    DRIVE_END_TURNOVER_FUMBLE: "Fumble",
    DRIVE_END_TURNOVER_ON_DOWNS: "Turnover on downs",
    DRIVE_END_UNKNOWN: "Other / unclear",
}

_GAME_JSON_VERSION = 1

_DRIVE_END_HEADLINE: Dict[str, str] = {
    DRIVE_END_TOUCHDOWN: "Touchdown",
    DRIVE_END_FIELD_GOAL: "Field goal",
    DRIVE_END_FIELD_GOAL_MISS: "Missed field goal",
    DRIVE_END_PUNT: "Punt",
    DRIVE_END_TURNOVER_INT: "Interception",
    DRIVE_END_TURNOVER_FUMBLE: "Fumble",
    DRIVE_END_TURNOVER_ON_DOWNS: "Turnover on downs",
    DRIVE_END_UNKNOWN: "Drive ended",
}


@dataclass
class DriveResult:
    """How the drive ended + Gamecast-style lines."""

    kind: str
    headline: str
    detail_line: str

    @property
    def full_line(self) -> str:
        return f"{self.headline} — {self.detail_line}"


@dataclass
class Drive:
    plays: List[ActualPlayResult] = field(default_factory=list)
    total_yards: int = 0
    play_count: int = 0
    time_elapsed_seconds: int = 0
    result: Optional[DriveResult] = None
    # Team that had the ball for this drive: ``offense`` = OC / our team, ``defense`` = opponent on offense.
    possessing_team: str = "offense"

    def with_computed_stats(
        self,
        *,
        seconds_per_play: int = 38,
        result: Optional[DriveResult] = None,
    ) -> "Drive":
        net = sum(int(p.yards_gained) + (int(p.penalty_yards) if p.penalty else 0) for p in self.plays)
        n = len(self.plays)
        elapsed = max(0, int(seconds_per_play) * n)
        r = result if result is not None else self.result
        return replace(
            self,
            total_yards=net,
            play_count=n,
            time_elapsed_seconds=elapsed,
            result=r,
            possessing_team=self.possessing_team,
        )


@dataclass
class Game:
    """One session (e.g. one full game or one half)."""

    game_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    drives: List[Drive] = field(default_factory=list)
    offense_points: int = 0
    defense_points: int = 0
    possession: str = "offense"
    quarter: int = 1
    clock_seconds_remaining: Optional[int] = None
    # Parallel to drives: recommendation audit rows (dicts) for validation / replay; not used by engine.
    recommendation_audit: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def new_game(cls) -> "Game":
        return cls(game_id=str(uuid.uuid4())[:8])


def _fmt_drive_clock(seconds: int) -> str:
    s = max(0, int(seconds))
    m, sec = divmod(s, 60)
    return f"{m}:{sec:02d}"


def _drive_detail_line(
    plays: List[ActualPlayResult],
    *,
    seconds_per_play: int = 38,
) -> str:
    if not plays:
        return "0 plays, 0 yards, 0:00"
    n = len(plays)
    net = sum(int(p.yards_gained) + (int(p.penalty_yards) if p.penalty else 0) for p in plays)
    elapsed_sec = max(0, int(seconds_per_play) * n)
    return f"{n} play{'s' if n != 1 else ''}, {net} yards, {_fmt_drive_clock(elapsed_sec)}"


def drive_result_for_kind(
    kind: str,
    plays: List[ActualPlayResult],
    *,
    seconds_per_play: int = 38,
) -> DriveResult:
    """Build a ``DriveResult`` for a known ``kind`` with the usual stats line."""
    k = str(kind)
    if k not in DRIVE_END_OVERRIDE_KINDS:
        k = DRIVE_END_UNKNOWN
    detail = _drive_detail_line(plays, seconds_per_play=seconds_per_play)
    headline = _DRIVE_END_HEADLINE.get(k, _DRIVE_END_HEADLINE[DRIVE_END_UNKNOWN])
    return DriveResult(kind=k, headline=headline, detail_line=detail)


def classify_drive_end(
    plays: List[ActualPlayResult],
    *,
    last_snap_touchdown: bool = False,
    last_snap_turnover_on_downs: bool = False,
    seconds_per_play: int = 38,
    end_kind_override: Optional[str] = None,
) -> DriveResult:
    """
    Determine drive end headline from the last play + last advancement snapshot flags.

    ``last_snap_*`` should reflect the situation **after** the final logged play.

    If ``end_kind_override`` is a valid ``DRIVE_END_*`` key in ``DRIVE_END_OVERRIDE_KINDS``, that outcome wins (explicit user classification).
    """
    override = (end_kind_override or "").strip()
    if override in DRIVE_END_OVERRIDE_KINDS:
        if not plays and override == DRIVE_END_UNKNOWN:
            return DriveResult(
                kind=DRIVE_END_UNKNOWN,
                headline="Empty drive",
                detail_line="0 plays, 0 yards, 0:00",
            )
        return drive_result_for_kind(override, plays, seconds_per_play=seconds_per_play)

    if not plays:
        return DriveResult(
            kind=DRIVE_END_UNKNOWN,
            headline="Empty drive",
            detail_line="0 plays, 0 yards, 0:00",
        )

    last = plays[-1]
    rt = (last.result_type or "").lower()
    tk = (last.turnover_kind or "").lower()
    pr = (last.pass_result or "").lower()

    detail = _drive_detail_line(plays, seconds_per_play=seconds_per_play)

    td = bool(last.touchdown) or bool(last_snap_touchdown)
    if td:
        return DriveResult(kind=DRIVE_END_TOUCHDOWN, headline="Touchdown", detail_line=detail)

    if rt == "interception" or tk == "interception" or pr == "intercepted":
        return DriveResult(
            kind=DRIVE_END_TURNOVER_INT,
            headline="Interception",
            detail_line=detail,
        )

    if tk == "fumble" or rt == "fumble":
        return DriveResult(
            kind=DRIVE_END_TURNOVER_FUMBLE,
            headline="Fumble",
            detail_line=detail,
        )

    if last_snap_turnover_on_downs:
        return DriveResult(
            kind=DRIVE_END_TURNOVER_ON_DOWNS,
            headline="Turnover on downs",
            detail_line=detail,
        )

    if rt == "field_goal_miss":
        return DriveResult(
            kind=DRIVE_END_FIELD_GOAL_MISS,
            headline="Missed field goal",
            detail_line=detail,
        )

    if rt == "field_goal" or (
        "field goal" in (last.concept_name or "").lower() and "miss" not in (last.concept_name or "").lower()
    ):
        return DriveResult(kind=DRIVE_END_FIELD_GOAL, headline="Field goal", detail_line=detail)

    return DriveResult(kind=DRIVE_END_PUNT, headline="Punt", detail_line=detail)


def _norm_possessing_team(raw: str) -> str:
    t = (raw or "").strip().lower()
    return t if t in ("offense", "defense") else "offense"


def complete_drive_from_plays(
    plays: List[ActualPlayResult],
    *,
    last_snap_touchdown: bool = False,
    last_snap_turnover_on_downs: bool = False,
    seconds_per_play: int = 38,
    end_kind_override: Optional[str] = None,
    possessing_team: str = "offense",
) -> Drive:
    """Build a finished ``Drive`` with stats + ``DriveResult``."""
    base = Drive(plays=list(plays), possessing_team=_norm_possessing_team(possessing_team))
    res = classify_drive_end(
        base.plays,
        last_snap_touchdown=last_snap_touchdown,
        last_snap_turnover_on_downs=last_snap_turnover_on_downs,
        seconds_per_play=seconds_per_play,
        end_kind_override=end_kind_override,
    )
    return base.with_computed_stats(seconds_per_play=seconds_per_play, result=res)


def clock_seconds_after_drive_elapsed(current_clock_seconds: int, drive: Drive) -> int:
    """Subtract modeled drive duration from the game clock (non-negative)."""
    return max(0, int(current_clock_seconds) - int(drive.time_elapsed_seconds))


def flip_possession_after_drive(game: Game, drive: Drive) -> None:
    """Flip ``game.possession`` after a drive that changes who has the ball."""
    if drive.result is None or drive.result.kind == DRIVE_END_UNKNOWN:
        return
    if drive.result.kind not in DRIVE_END_CHANGE_OF_POSSESSION_KINDS:
        return
    game.possession = "defense" if game.possession == "offense" else "offense"


def _actual_play_from_dict(d: Dict[str, Any]) -> ActualPlayResult:
    names = {f.name for f in fields(ActualPlayResult)}
    return ActualPlayResult(**{k: v for k, v in d.items() if k in names})


def _drive_result_from_dict(d: Optional[Dict[str, Any]]) -> Optional[DriveResult]:
    if not d:
        return None
    return DriveResult(
        kind=str(d.get("kind", DRIVE_END_UNKNOWN)),
        headline=str(d.get("headline", "")),
        detail_line=str(d.get("detail_line", "")),
    )


def _drive_from_dict(d: Dict[str, Any]) -> Drive:
    plays = [_actual_play_from_dict(p) for p in (d.get("plays") or [])]
    dr = _drive_result_from_dict(d.get("result"))
    out = Drive(
        plays=plays,
        total_yards=int(d.get("total_yards", 0)),
        play_count=int(d.get("play_count", 0)),
        time_elapsed_seconds=int(d.get("time_elapsed_seconds", 0)),
        result=dr,
        possessing_team=_norm_possessing_team(str(d.get("possessing_team", "offense"))),
    )
    return out


def game_to_dict(game: Game) -> Dict[str, Any]:
    """Structured dict suitable for JSON (``game_to_json``)."""
    payload: Dict[str, Any] = {
        "schema_version": _GAME_JSON_VERSION,
        "game_id": game.game_id,
        "offense_points": game.offense_points,
        "defense_points": game.defense_points,
        "possession": game.possession,
        "quarter": game.quarter,
        "clock_seconds_remaining": game.clock_seconds_remaining,
        "recommendation_audit": list(game.recommendation_audit),
        "drives": [],
    }
    for dr in game.drives:
        res = dr.result
        payload["drives"].append(
            {
                "plays": [asdict(p) for p in dr.plays],
                "total_yards": dr.total_yards,
                "play_count": dr.play_count,
                "time_elapsed_seconds": dr.time_elapsed_seconds,
                "possessing_team": dr.possessing_team,
                "result": asdict(res) if res else None,
            }
        )
    return payload


def game_from_dict(data: Dict[str, Any]) -> Game:
    """Restore a ``Game`` from ``game_to_dict`` output."""
    drives_raw = data.get("drives") or []
    drives = [_drive_from_dict(x) for x in drives_raw]
    audit_raw = data.get("recommendation_audit")
    audit: List[Dict[str, Any]] = list(audit_raw) if isinstance(audit_raw, list) else []
    return Game(
        game_id=str(data.get("game_id") or str(uuid.uuid4())[:8]),
        drives=drives,
        offense_points=int(data.get("offense_points", 0)),
        defense_points=int(data.get("defense_points", 0)),
        possession=str(data.get("possession", "offense")),
        quarter=int(data.get("quarter", 1)),
        clock_seconds_remaining=data.get("clock_seconds_remaining"),
        recommendation_audit=audit,
    )


def game_to_json(game: Game, *, indent: int = 2) -> str:
    return json.dumps(game_to_dict(game), indent=indent)


def game_from_json(s: str) -> Game:
    return game_from_dict(json.loads(s))


def apply_scoring_after_drive(game: Game, drive: Drive) -> None:
    """Apply TD (+6) or made FG (+3) to the team that possessed the ball on this drive."""
    if drive.result is None:
        return
    team = _norm_possessing_team(getattr(drive, "possessing_team", "offense"))
    rk = drive.result.kind
    if rk == DRIVE_END_TOUCHDOWN:
        if team == "offense":
            game.offense_points += 6
        else:
            game.defense_points += 6
    elif rk == DRIVE_END_FIELD_GOAL:
        if team == "offense":
            game.offense_points += 3
        else:
            game.defense_points += 3


__all__ = [
    "DRIVE_END_CHANGE_OF_POSSESSION_KINDS",
    "DRIVE_END_FIELD_GOAL",
    "DRIVE_END_FIELD_GOAL_MISS",
    "DRIVE_END_OVERRIDE_KINDS",
    "DRIVE_END_UI_AUTO",
    "DRIVE_END_UI_LABELS",
    "DRIVE_END_UI_OPTIONS",
    "DRIVE_END_PUNT",
    "DRIVE_END_TOUCHDOWN",
    "DRIVE_END_TURNOVER_FUMBLE",
    "DRIVE_END_TURNOVER_INT",
    "DRIVE_END_TURNOVER_ON_DOWNS",
    "DRIVE_END_UNKNOWN",
    "Drive",
    "DriveResult",
    "Game",
    "apply_scoring_after_drive",
    "classify_drive_end",
    "clock_seconds_after_drive_elapsed",
    "complete_drive_from_plays",
    "flip_possession_after_drive",
    "drive_result_for_kind",
    "game_from_dict",
    "game_from_json",
    "game_to_dict",
    "game_to_json",
]
