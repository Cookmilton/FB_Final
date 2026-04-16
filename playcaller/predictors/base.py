from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..domain import GameContext
from ..features import ModelInput
from ..model_types import ModelOutput
from ..state import DriveLogger


class Predictor(ABC):
    """
    Abstract prediction layer.

    Implementations can be:
    - Heuristic rules (current default)
    - Classical ML models
    - LLM-backed planners (tool-calling), etc.

    Contract:
    - Input is a structured `ModelInput` (features) + optional `GameContext` snapshot
      (for attaching provenance to outputs).
    - Output is a structured `ModelOutput` (normalized play decision + metadata).
    """

    name: str = "predictor"

    @abstractmethod
    def predict(self, model_input: ModelInput, ctx: GameContext, drive_log: Optional[DriveLogger] = None) -> ModelOutput:
        raise NotImplementedError
