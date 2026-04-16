"""
Near-real-time game data ingestion (provider-agnostic).

UI and predictors consume normalized snapshots via ``sync.apply_snapshot``; providers
translate vendor JSON into :class:`NormalizedGameSnapshot`.
"""

from .espn_football import EspnFootballProvider, list_espn_scoreboard_games
from .sync import SyncOptions, SyncResult, apply_snapshot, session_mark_manual
from .types import FetchResult, NormalizedGameSnapshot

__all__ = [
    "EspnFootballProvider",
    "FetchResult",
    "NormalizedGameSnapshot",
    "SyncOptions",
    "SyncResult",
    "apply_snapshot",
    "list_espn_scoreboard_games",
    "session_mark_manual",
]
