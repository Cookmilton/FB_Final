from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Optional, Tuple


@dataclass(frozen=True)
class FeedPlayEvent:
    """One play row from a vendor feed (for optional auto-logging)."""

    event_id: str
    summary_text: str
    yards_gained: Optional[int]
    type_hint: str  # rush | pass | penalty | kick | unknown


@dataclass(frozen=True)
class NormalizedGameSnapshot:
    """Vendor-neutral game state aligned to this app's ``Game`` / sidebar widgets."""

    provider: str
    external_game_id: str
    sport: Literal["nfl", "college-football"]
    fetched_at_epoch: float
    status_detail: str
    quarter: Optional[int]
    clock_seconds_in_period: Optional[int]
    down: Optional[int]
    distance: Optional[int]
    abs_yards_from_own_goal: Optional[int]
    possession_team_id: Optional[str]
    possession_is_our_team: Optional[bool]
    our_score: Optional[int]
    opponent_score: Optional[int]
    our_timeouts: Optional[int]
    opponent_timeouts: Optional[int]
    is_final: bool
    new_plays: Tuple[FeedPlayEvent, ...] = ()
    debug_notes: Tuple[str, ...] = ()


@dataclass
class FetchResult:
    ok: bool
    snapshot: Optional[NormalizedGameSnapshot] = None
    error: Optional[str] = None
    raw_excerpt: Optional[str] = None


@dataclass
class SyncResult:
    """What the UI should show after ``apply_snapshot``."""

    ok: bool
    applied_fields: List[str] = field(default_factory=list)
    skipped_reasons: List[str] = field(default_factory=list)
    plays_appended: int = 0
    message: str = ""
    error: Optional[str] = None
