from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union

from ..domain import GameContext


@dataclass
class CalibrationProfile:
    """
    Optional additive score nudges after heuristic family scoring.

    Loaded from JSON; all sections are optional. Values are added to family scores
    before family selection (same numeric scale as heuristic baselines).
    """

    version: int = 1
    family_offsets: Dict[str, float] = field(default_factory=dict)
    bucket_offsets: Dict[str, Dict[str, float]] = field(default_factory=dict)
    red_zone_family_offsets: Dict[str, float] = field(default_factory=dict)
    short_yardage_family_offsets: Dict[str, float] = field(default_factory=dict)
    fourth_down_family_offsets: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "CalibrationProfile":
        return cls(
            version=int(raw.get("version", 1)),
            family_offsets={str(k): float(v) for k, v in (raw.get("family_offsets") or {}).items()},
            bucket_offsets={
                str(bk): {str(k): float(v) for k, v in (bv or {}).items()}
                for bk, bv in (raw.get("bucket_offsets") or {}).items()
            },
            red_zone_family_offsets={
                str(k): float(v) for k, v in (raw.get("red_zone_family_offsets") or {}).items()
            },
            short_yardage_family_offsets={
                str(k): float(v) for k, v in (raw.get("short_yardage_family_offsets") or {}).items()
            },
            fourth_down_family_offsets={
                str(k): float(v) for k, v in (raw.get("fourth_down_family_offsets") or {}).items()
            },
        )

    def apply(self, scores: Dict[str, float], ctx: GameContext, bucket: str) -> Dict[str, float]:
        if not scores:
            return scores
        out = dict(scores)

        def add_offs(mapping: Mapping[str, float]) -> None:
            for fam, delta in mapping.items():
                if fam in out:
                    out[fam] = round(out[fam] + float(delta), 4)

        add_offs(self.family_offsets)
        bo = self.bucket_offsets.get(bucket)
        if isinstance(bo, dict):
            add_offs(bo)

        if ctx.territory == "opponents" and ctx.yardline <= 20:
            add_offs(self.red_zone_family_offsets)

        if ctx.down < 4 and ctx.distance <= 2:
            add_offs(self.short_yardage_family_offsets)

        if ctx.down == 4:
            add_offs(self.fourth_down_family_offsets)

        return out


def load_calibration_profile(path: Optional[Union[str, Path]] = None) -> Optional[CalibrationProfile]:
    """
    Load calibration from ``path``, or ``PLAYCALLER_CALIBRATION_JSON`` env, or ``calibration.json`` in cwd.

    Returns None if no file found or empty / invalid.
    """
    p: Optional[Path] = None
    if path is not None:
        p = Path(path)
    elif os.environ.get("PLAYCALLER_CALIBRATION_JSON"):
        p = Path(os.environ["PLAYCALLER_CALIBRATION_JSON"])
    else:
        cwd = Path.cwd() / "calibration.json"
        if cwd.is_file():
            p = cwd

    if p is None or not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return CalibrationProfile.from_dict(raw)
    except (TypeError, ValueError):
        return None
