"""
football_play_predictor.py

Compatibility layer.

The implementation has been refactored into the `playcaller/` package to
separate UI, domain models, state, and engine logic. This module keeps the
original import surface working for existing code.

Import speed: symbols from `playcaller` load eagerly (small). CLI helpers are
lazy-loaded so `import football_play_predictor` does not pull `cli` until used.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any


def _ensure_repo_root_on_sys_path() -> None:
    root = Path(__file__).resolve().parent
    s = str(root)
    if s not in sys.path:
        sys.path.insert(0, s)


_ensure_repo_root_on_sys_path()

from playcaller import (  # noqa: F401
    ActualPlayResult,
    DriveLogger,
    FG_RANGE_YARDLINE,
    FootballPlayPredictor,
    FourthDownAdvisor,
    GameContext,
    HeuristicPredictor,
    ModelInput,
    ModelOutput,
    PASS_FAMILIES,
    PlayResult,
    Predictor,
    RUN_FAMILIES,
    extract_model_input,
)
from playcaller.library import PLAY_LIBRARY  # noqa: F401


def __getattr__(name: str) -> Any:
    if name in ("pretty_print", "run_interactive", "run_tests"):
        from playcaller import cli as _cli

        return getattr(_cli, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    predictor = FootballPlayPredictor()
    drive_log = DriveLogger()
    from playcaller.cli import run_interactive

    run_interactive(predictor, drive_log)
