from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from .domain import GameContext
from .features import ModelInput, extract_model_input
from .game import Game
from .evaluation.calibration import CalibrationProfile
from .heuristic_predictor import FourthDownAdvisor, HeuristicPredictor
from .model_types import ModelOutput
from .predicted_outcome import enrich_recommendation_dict
from .predictors.base import Predictor
from .state import DriveLogger


class FootballPlayPredictor:
    """
    Backwards-compatible façade.

    Internally this delegates to a `Predictor` implementation so you can later
    swap in ML/LLM backends without rewriting the UI/CLI.
    """

    def __init__(
        self,
        predictor: Optional[Predictor] = None,
        calibration: Optional[CalibrationProfile] = None,
    ) -> None:
        self._impl: HeuristicPredictor
        if predictor is None:
            self._impl = HeuristicPredictor(calibration=calibration)
        elif isinstance(predictor, HeuristicPredictor):
            self._impl = predictor
            if calibration is not None:
                self._impl.calibration = calibration
        else:
            # Future: allow arbitrary `Predictor` implementations.
            # Parsing helpers still live on `HeuristicPredictor`, so we keep a lightweight
            # heuristic instance for those methods only.
            self._impl = HeuristicPredictor(calibration=calibration)

        self._predictor: Predictor = predictor if predictor is not None else self._impl

        # Expose common attributes for older code paths / debugging.
        if isinstance(self._predictor, HeuristicPredictor):
            self.baselines = self._predictor.baselines
            self.play_library = self._predictor.play_library
            self.fourth_down_advisor = self._predictor.fourth_down_advisor
        else:
            self.baselines = None
            self.play_library = None
            self.fourth_down_advisor = None

    @property
    def predictor(self) -> Predictor:
        return self._predictor

    # --- Parsing / helpers (delegated) ---------------------------------------

    def parse_situation(self, text: str) -> Tuple[int, int, int, str]:
        return self._impl.parse_situation(text)

    def parse_defense(self, text: str, ctx: GameContext) -> None:
        return self._impl.parse_defense(text, ctx)

    def parse_game_script(self, text: str, ctx: GameContext) -> None:
        return self._impl.parse_game_script(text, ctx)

    def get_bucket(self, ctx: GameContext) -> str:
        return self._impl.get_bucket(ctx)

    def derive_game_mode(self, ctx: GameContext) -> str:
        return self._impl.derive_game_mode(ctx)

    def score_families(self, ctx: GameContext, bucket: str) -> Dict[str, float]:
        return self._impl.score_families(ctx, bucket)

    # --- Model-ready API ------------------------------------------------------

    def build_model_input(
        self, ctx: GameContext, drive_log: Optional[DriveLogger] = None, game: Optional[Game] = None
    ) -> ModelInput:
        ctx_n = self._impl.normalize_context(ctx, drive_log)
        ctx_n.game_mode = self._impl.derive_game_mode(ctx_n)
        return extract_model_input(ctx_n, drive_log, game)

    def predict_model_output(self, model_input: ModelInput, ctx: GameContext, drive_log: Optional[DriveLogger] = None) -> ModelOutput:
        ctx_n = self._impl.normalize_context(ctx, drive_log)
        ctx_n.game_mode = self._impl.derive_game_mode(ctx_n)
        if isinstance(self._predictor, HeuristicPredictor):
            return self._predictor._predict_core(model_input, ctx_n, drive_log)
        return self.predictor.predict(model_input, ctx_n, drive_log)

    # --- Legacy recommend dict ------------------------------------------------

    def recommend(
        self, ctx: GameContext, drive_log: Optional[DriveLogger] = None, game: Optional[Game] = None
    ) -> Dict[str, Any]:
        if isinstance(self._predictor, HeuristicPredictor):
            result = self._predictor.recommend(ctx, drive_log, game)
        else:
            ctx_n = self._impl.normalize_context(ctx, drive_log)
            ctx_n.game_mode = self._impl.derive_game_mode(ctx_n)
            model_in = extract_model_input(ctx_n, drive_log, game)
            out = self._predictor.predict(model_in, ctx_n, drive_log)
            result = {
                "ctx": ctx_n,
                "bucket": out.bucket,
                "play_family": out.play_family,
                "play": out.play,
                "fourth_down": out.fourth_down,
                "pa_warning": out.pa_warning,
                "coverage_note": out.coverage_note,
                "overuse_warning": out.overuse_warning,
                "scores": out.scores,
                "model": {
                    "name": out.model_name,
                    "version": out.model_version,
                    "confidence": out.confidence,
                },
                "model_input": model_in,
                "model_output": out,
            }
        enrich_recommendation_dict(result, drive_log)
        return result

