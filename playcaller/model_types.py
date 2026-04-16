from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .domain import GameContext
from .features import ModelInput


@dataclass(frozen=True)
class ModelOutput:
    """
    Normalized output contract for future ML/LLM backends.

    `extras` is intentionally open-ended for debugging / UI overlays.
    """

    play_family: str
    play: Dict[str, Any]
    bucket: str
    scores: Dict[str, float]
    fourth_down: Dict[str, Any] = field(default_factory=dict)
    pa_warning: Optional[str] = None
    coverage_note: Optional[str] = None
    overuse_warning: Optional[str] = None

    # Optional model metadata (confidence, rationale tokens, version, etc.)
    model_name: str = "heuristic_v1"
    model_version: str = "1.0.0"
    confidence: Optional[float] = None

    extras: Dict[str, Any] = field(default_factory=dict)
