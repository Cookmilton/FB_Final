"""
Backward-compatible entrypoints for play art.

The implementation lives in ``play_art_geometry`` (coordinates) and
``play_art_render`` (matplotlib). Import from here or from ``playcaller.play_art_render``.
"""

from __future__ import annotations

from .play_art_geometry import ROUTE_WAYPOINT_DELTAS as ROUTE_SHAPES
from .play_art_geometry import classify_route_shape
from .play_art_render import build_play_art_figure

# Legacy name used by earlier app versions
build_play_route_diagram_figure = build_play_art_figure

__all__ = [
    "ROUTE_SHAPES",
    "build_play_art_figure",
    "build_play_route_diagram_figure",
    "classify_route_shape",
]
