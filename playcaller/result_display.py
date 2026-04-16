"""
Broadcast-style strings for projected play results (headlines + short route names).

Separated from ``predicted_outcome`` so formatting can evolve without touching RNG logic.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from .play_art_geometry import classify_run_track


def broadcast_target(position_code: Optional[str]) -> str:
    """Short on-screen label: X, Z, Slot, TE, RB, QB."""
    if not position_code:
        return "receiver"
    m = {
        "X": "X",
        "Z": "Z",
        "H": "Slot",
        "Y": "TE",
        "RB": "RB",
        "QB": "QB",
        "F": "F",
    }
    return m.get(position_code.upper(), position_code.upper())


def route_short_name(route_raw: str) -> str:
    """One- or two-word route label for headlines (best-effort from library text)."""
    if not route_raw:
        return "route"
    t = route_raw.lower()
    if "screen" in t:
        return "screen"
    if "bubble" in t:
        return "bubble"
    if "slant" in t:
        return "slant"
    if "hitch" in t:
        return "hitch"
    if "stick" in t:
        return "stick"
    if "flat" in t:
        return "flat"
    if "wheel" in t:
        return "wheel"
    if "dig" in t:
        return "dig"
    if "cross" in t:
        return "cross"
    if "post" in t:
        return "post"
    if "corner" in t:
        return "corner"
    if "comeback" in t:
        return "comeback"
    if "out" in t and "route" not in t[:5]:
        return "out"
    if "fade" in t:
        return "fade"
    if any(k in t for k in ("go", "vertical", "clear", "seam")):
        return "vertical"
    if "leak" in t:
        return "leak"
    if "shallow" in t:
        return "shallow"
    # Fallback: first few words
    frag = re.sub(r"\s+", " ", route_raw.strip())[:28]
    return frag if frag else "route"


def build_projected_headline(
    *,
    play_type: str,
    result_type: str,
    yards: int,
    target_position: Optional[str],
    route_raw: str,
    play: Dict[str, Any],
    play_family: str,
) -> str:
    """
    Single scan line, e.g. ``Result: Pass complete to X on a slant for 8 yards``.
    """
    tgt = broadcast_target(target_position)
    rn = route_short_name(route_raw)

    if result_type == "sack":
        return f"Result: Sack for {yards} yards"
    if result_type == "scramble":
        return f"Result: QB scramble up the middle for {yards} yards"
    if result_type == "incomplete":
        return f"Result: Incomplete pass intended for {tgt} on a {rn} route"

    if play_type == "qb_run" and result_type == "rush":
        tr = classify_run_track(str(play.get("run_scheme") or ""), play_family)
        if tr == "qb_keep":
            return f"Result: Read option keep by QB for {yards} yards"
        return f"Result: QB sneak for {yards} yards"

    if play_type == "run":
        scheme = str(play.get("run_scheme") or "")
        track = classify_run_track(scheme, play_family)
        if track == "stretch_left":
            return f"Result: RB stretch run left for {yards} yards"
        if track == "stretch_right":
            return f"Result: RB stretch run right for {yards} yards"
        if track == "sweep":
            return f"Result: RB sweep for {yards} yards"
        if track == "counter":
            return f"Result: RB counter for {yards} yards"
        if track == "power":
            return f"Result: RB power run for {yards} yards"
        if track == "duo":
            return f"Result: RB duo run for {yards} yards"
        if track == "draw":
            return f"Result: RB draw for {yards} yards"
        if track == "inside":
            return f"Result: RB inside run for {yards} yards"

    if "screen" in route_raw.lower() or rn == "screen":
        return f"Result: Screen pass to {tgt} for {yards} yards"
    if "check" in route_raw.lower():
        return f"Result: Checkdown to {tgt} for {yards} yards"

    if result_type == "complete":
        return f"Result: Pass complete to {tgt} on a {rn} for {yards} yards"

    return f"Result: Play for {yards} yards"


__all__ = ["broadcast_target", "build_projected_headline", "route_short_name"]
