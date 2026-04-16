"""
Pure geometry for play-art: formations, route waypoints, and run tracks.

Coordinate system (normalized, offense perspective):
  * x — lateral (negative = offense left / defense right)
  * y — downfield depth (0 = line of scrimmage, positive = toward opponent end zone)
  * QB sits slightly behind LOS; RB typically behind / beside QB in gun.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence, Tuple

# ── Receiver keys → display labels (gamecast / board style) ───────────────────

RECEIVER_BOARD_LABEL: Dict[str, str] = {
    "X": "X",
    "Z": "Z",
    "H": "Slot",
    "Y": "TE",
    "RB": "RB",
    "QB": "QB",
    "F": "F",
}


def board_label_for_position(code: str) -> str:
    return RECEIVER_BOARD_LABEL.get(code.upper(), code.upper())


# ── Route text → drawable shape id (extend ROUTE_WAYPOINT_DELTAS in lockstep) ─


def classify_route_shape(route_description: str) -> str:
    t = route_description.lower()
    if any(k in t for k in ("bubble", "now", "perimeter")):
        return "flat"
    if "wheel" in t:
        return "wheel"
    if "screen" in t:
        return "screen"
    if "slant" in t:
        return "slant"
    if any(k in t for k in ("hitch", "hook", "stick", "settle", "comeback")):
        return "hitch"
    if any(k in t for k in ("flat", "arrow", "swing", "outlet")):
        return "flat"
    if any(k in t for k in ("dig", "cross", "shallow", "drag")):
        return "in"
    if any(k in t for k in ("out", "speed out", "deep out")):
        return "out"
    if "corner" in t or "7 route" in t:
        return "corner"
    if "post" in t:
        return "post"
    # Avoid matching "over" alone (e.g. "sit over ball" is not a vertical).
    if any(k in t for k in ("go", "fade", "vertical", "clear", "seam")) or re.search(
        r"\bover\b", t
    ) and any(w in t for w in ("route", "deep", "clear", "cross")):
        return "go"
    return "stem"


# Cumulative deltas from alignment: each tuple adds to running (px, py).
ROUTE_WAYPOINT_DELTAS: Dict[str, List[Tuple[float, float]]] = {
    "go": [(0, 0), (0, 0.92)],
    "slant": [(0, 0), (0, 0.12), (0.32, 0.36)],
    "out": [(0, 0), (0, 0.30), (0.40, 0.30)],
    "in": [(0, 0), (0, 0.36), (-0.38, 0.46)],
    "post": [(0, 0), (0, 0.40), (-0.20, 0.88)],
    "corner": [(0, 0), (0, 0.46), (0.26, 0.84)],
    "hitch": [(0, 0), (0, 0.20), (0, -0.02)],
    "flat": [(0, 0), (0.32, 0.05), (0.48, 0.09)],
    "wheel": [(0, 0), (0.04, 0.07), (0.40, 0.62)],
    "screen": [(0, 0), (-0.10, -0.11), (-0.32, 0.06)],
    "stem": [(0, 0), (0, 0.32)],
}


def offset_from_deltas(
    base: Tuple[float, float],
    deltas: Sequence[Tuple[float, float]],
) -> List[Tuple[float, float]]:
    """Turn relative deltas into absolute vertices starting at ``base``."""
    bx, by = base
    out: List[Tuple[float, float]] = [(bx, by)]
    px, py = bx, by
    for dx, dy in list(deltas)[1:]:
        px += dx
        py += dy
        out.append((px, py))
    return out


def densify_polyline(
    vertices: Sequence[Tuple[float, float]],
    steps_per_segment: int = 18,
) -> List[Tuple[float, float]]:
    """
    Insert points along straight segments so matplotlib can draw smooth-looking
    paths with round caps (no scipy required).
    """
    if len(vertices) < 2:
        return list(vertices)
    pts: List[Tuple[float, float]] = []
    for i in range(len(vertices) - 1):
        x0, y0 = vertices[i]
        x1, y1 = vertices[i + 1]
        for s in range(steps_per_segment):
            t = s / steps_per_segment
            pts.append((x0 + t * (x1 - x0), y0 + t * (y1 - y0)))
    pts.append(vertices[-1])
    return pts


# ── Formation → starting xy for eligible skill players ────────────────────────


def formation_layout(formation: str) -> Dict[str, Tuple[float, float]]:
    f = (formation or "").lower()
    if "trips right" in f or ("trips" in f and "left" not in f):
        return {
            "X": (-0.88, 0.02),
            "H": (0.48, 0.02),
            "Y": (0.68, 0.0),
            "Z": (0.88, 0.02),
            "RB": (0.0, -0.14),
        }
    if "trips left" in f:
        return {
            "X": (0.88, 0.02),
            "H": (-0.48, 0.02),
            "Y": (-0.68, 0.0),
            "Z": (-0.88, 0.02),
            "RB": (0.0, -0.14),
        }
    if "bunch" in f:
        return {
            "X": (-0.82, 0.02),
            "H": (0.52, 0.03),
            "Y": (0.68, 0.0),
            "Z": (0.78, 0.04),
            "RB": (-0.05, -0.14),
        }
    if "i-" in f or "i formation" in f:
        return {
            "X": (-0.78, 0.02),
            "Z": (0.78, 0.02),
            "Y": (0.35, -0.05),
            "H": (-0.35, -0.05),
            "RB": (0.0, -0.18),
        }
    return {
        "X": (-0.86, 0.02),
        "Z": (0.86, 0.02),
        "H": (0.38, 0.02),
        "Y": (-0.38, 0.02),
        "RB": (0.0, -0.14),
    }


def ensure_layout_for_route_keys(
    layout: Dict[str, Tuple[float, float]],
    route_keys: Sequence[str],
) -> Dict[str, Tuple[float, float]]:
    """Fill missing WR tags so odd personnel still renders."""
    out = dict(layout)
    extras = [k for k in route_keys if k not in out and k != "QB"]
    if not extras:
        return out
    # Spread unknown tokens across the field behind LOS depth
    n = len(extras)
    for i, k in enumerate(sorted(extras)):
        x = -0.75 + (1.5 * (i + 1) / (n + 1))
        out[k] = (x, 0.02)
    return out


# ── Run concept → waypoint deltas from RB alignment ───────────────────────────


def classify_run_track(run_scheme: str, play_family: str) -> str:
    s = (run_scheme or "").lower()
    fam = play_family or ""
    if fam == "draw" or "draw" in s:
        return "draw"
    if "sneak" in s or ("qb" in s and "power" in s):
        return "qb_sneak"
    if "option" in s or "keep" in s:
        return "qb_keep"
    if "counter" in s:
        return "counter"
    if "sweep" in s:
        return "sweep"
    if "stretch" in s or ("outside" in s and "zone" in s):
        if "weak" in s:
            return "stretch_left"
        if "strong" in s:
            return "stretch_right"
        return "stretch_left"
    if "power" in s or fam == "power":
        return "power"
    if "duo" in s or fam == "duo":
        return "duo"
    if "dive" in s or "inside" in s or fam == "inside_zone":
        return "inside"
    return "inside"


# Deltas from RB start (same convention as routes)
RUN_TRACK_DELTAS: Dict[str, List[Tuple[float, float]]] = {
    "inside": [(0, 0), (0.02, 0.18), (-0.02, 0.52)],
    "duo": [(0, 0), (0.06, 0.28), (0.04, 0.58)],
    "power": [(0, 0), (0.14, 0.22), (0.10, 0.56)],
    "counter": [(0, 0), (-0.16, 0.10), (0.34, 0.46)],
    "sweep": [(0, 0), (-0.48, 0.10), (-0.62, 0.34)],
    "stretch_left": [(0, 0), (-0.28, 0.10), (-0.42, 0.54)],
    "stretch_right": [(0, 0), (0.28, 0.10), (0.42, 0.54)],
    "draw": [(0, 0), (0, -0.07), (0.02, 0.50)],
    "qb_keep": [(0, 0), (0.22, 0.12), (0.28, 0.38)],
    "qb_sneak": [(0, 0), (0, 0.22), (0, 0.35)],
}


def run_vertices(rb_base: Tuple[float, float], track: str) -> List[Tuple[float, float]]:
    deltas = RUN_TRACK_DELTAS.get(track, RUN_TRACK_DELTAS["inside"])
    return offset_from_deltas(rb_base, deltas)


def play_action_fake_vertices(rb_base: Tuple[float, float]) -> List[Tuple[float, float]]:
    """Short sell path for play-action (dashed)."""
    bx, by = rb_base
    return [(bx, by), (bx * 0.55 + 0.06, 0.12), (bx * 0.35 + 0.04, 0.22)]


def qb_scramble_vertices(qb_xy: Tuple[float, float]) -> List[Tuple[float, float]]:
    qx, qy = qb_xy
    return [(qx, qy), (qx * 0.4, 0.12), (0.0, 0.42)]


__all__ = [
    "RECEIVER_BOARD_LABEL",
    "ROUTE_WAYPOINT_DELTAS",
    "RUN_TRACK_DELTAS",
    "board_label_for_position",
    "classify_route_shape",
    "classify_run_track",
    "densify_polyline",
    "ensure_layout_for_route_keys",
    "formation_layout",
    "offset_from_deltas",
    "play_action_fake_vertices",
    "qb_scramble_vertices",
    "run_vertices",
]
