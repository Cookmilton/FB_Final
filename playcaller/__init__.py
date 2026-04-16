"""
playcaller

Small package that separates:
- domain models/constants
- state (drive logging)
- features (model-ready inputs)
- predictors (abstract prediction layer + implementations)
- engine façade (backwards compatible entrypoint)
- UI helpers (Streamlit rendering utilities)

The root exports keep imports ergonomic for the app.
"""

from .domain import (
    FG_RANGE_YARDLINE,
    PASS_FAMILIES,
    RUN_FAMILIES,
    ActualPlayResult,
    GameContext,
    PlayResult,
)
from .features import ModelInput, extract_model_input
from .game_context_features import build_game_context_features, flatten_game_context_features_for_model
from .heuristic_predictor import FourthDownAdvisor, HeuristicPredictor
from .model_types import ModelOutput
from .predictors import Predictor
from .state import DriveLogger
from .engine import FootballPlayPredictor
from .actual_result import (
    assemble_actual_semantics,
    classify_actual_result_type,
    finalize_actual_after_snap,
    format_actual_play_result_description,
)
from .predicted_outcome import PredictedPlayResult, enrich_recommendation_dict
from .play_art_render import build_play_art_figure
from .route_diagram import build_play_route_diagram_figure
from .game import (
    DRIVE_END_CHANGE_OF_POSSESSION_KINDS,
    DRIVE_END_FIELD_GOAL_MISS,
    DRIVE_END_OVERRIDE_KINDS,
    DRIVE_END_UI_AUTO,
    DRIVE_END_UI_LABELS,
    DRIVE_END_UI_OPTIONS,
    Drive,
    DriveResult,
    Game,
    apply_scoring_after_drive,
    classify_drive_end,
    clock_seconds_after_drive_elapsed,
    complete_drive_from_plays,
    drive_result_for_kind,
    flip_possession_after_drive,
    game_from_dict,
    game_from_json,
    game_to_dict,
    game_to_json,
)
from .situation import (
    ProgressionTags,
    SituationSnapshot,
    advance_game_state_after_actual,
    advance_game_state_after_play,
    classify_logged_outcome,
    earned_first_down_for_actual_play,
    invoke_post_play_hook,
    play_progression_tags,
    register_post_play_hook,
)

__all__ = [
    "Game",
    "Drive",
    "DriveResult",
    "DRIVE_END_CHANGE_OF_POSSESSION_KINDS",
    "DRIVE_END_FIELD_GOAL_MISS",
    "DRIVE_END_OVERRIDE_KINDS",
    "DRIVE_END_UI_AUTO",
    "DRIVE_END_UI_LABELS",
    "DRIVE_END_UI_OPTIONS",
    "complete_drive_from_plays",
    "classify_drive_end",
    "clock_seconds_after_drive_elapsed",
    "drive_result_for_kind",
    "flip_possession_after_drive",
    "game_from_dict",
    "game_from_json",
    "game_to_dict",
    "game_to_json",
    "apply_scoring_after_drive",
    "assemble_actual_semantics",
    "classify_actual_result_type",
    "finalize_actual_after_snap",
    "format_actual_play_result_description",
    "earned_first_down_for_actual_play",
    "PredictedPlayResult",
    "enrich_recommendation_dict",
    "build_play_art_figure",
    "build_play_route_diagram_figure",
    "GameContext",
    "ActualPlayResult",
    "PlayResult",
    "RUN_FAMILIES",
    "PASS_FAMILIES",
    "FG_RANGE_YARDLINE",
    "DriveLogger",
    "FootballPlayPredictor",
    "FourthDownAdvisor",
    "HeuristicPredictor",
    "Predictor",
    "ModelInput",
    "ModelOutput",
    "extract_model_input",
    "build_game_context_features",
    "flatten_game_context_features_for_model",
    "ProgressionTags",
    "SituationSnapshot",
    "advance_game_state_after_actual",
    "advance_game_state_after_play",
    "classify_logged_outcome",
    "invoke_post_play_hook",
    "play_progression_tags",
    "register_post_play_hook",
]

