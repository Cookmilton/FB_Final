from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from .domain import ActualPlayResult, RUN_FAMILIES


class DriveLogger:
    """Tracks play history within a drive for tendency analysis."""

    def __init__(self) -> None:
        self.results: List[ActualPlayResult] = []
        self.family_counts: Dict[str, int] = {}
        # Cache for the default (half_life=3, max_plays=12) + recent-6 slice — hot path per prediction.
        self._metrics_len: int = -1
        self._metrics_weighted: Dict[str, float] = {}
        self._metrics_recent6: List[str] = []

    def _invalidate_drive_metrics(self) -> None:
        self._metrics_len = -1

    def _ensure_standard_drive_metrics(self) -> None:
        """Recompute cached weighted counts + last-6 families when the drive length changes."""
        n = len(self.results)
        if n == self._metrics_len:
            return
        if n == 0:
            self._metrics_weighted = {}
            self._metrics_recent6 = []
            self._metrics_len = 0
            return

        half_life_plays = 3.0
        max_plays = 12
        decay = math.log(0.5) / half_life_plays
        out: Dict[str, float] = {}
        recent = self.results[-max_plays:]
        for i, r in enumerate(reversed(recent)):
            w = math.exp(decay * i)
            out[r.family] = out.get(r.family, 0.0) + w
        self._metrics_weighted = out
        tail = self.results[-6:]
        self._metrics_recent6 = [r.family for r in tail]
        self._metrics_len = n

    def log(self, result: ActualPlayResult) -> None:
        self.results.append(result)
        self.family_counts[result.family] = self.family_counts.get(result.family, 0) + 1
        self._invalidate_drive_metrics()

    def pop_last(self) -> Optional[ActualPlayResult]:
        """Remove and return the most recent play, or ``None`` if the log is empty."""
        if not self.results:
            return None
        r = self.results.pop()
        fam = r.family
        prev = self.family_counts.get(fam, 1) - 1
        if prev <= 0:
            self.family_counts.pop(fam, None)
        else:
            self.family_counts[fam] = prev
        self._invalidate_drive_metrics()
        return r

    def overuse_warning(self, family: str, threshold: int = 3) -> Optional[str]:
        count = self.family_counts.get(family, 0)
        if count >= threshold:
            label = family.replace("_", " ").title()
            return f"⚠  {label} called {count}x this drive — defense is keying on it."
        return None

    def run_pass_split(self) -> Tuple[int, int]:
        runs = sum(1 for r in self.results if r.family in RUN_FAMILIES)
        passes = len(self.results) - runs
        return runs, passes

    def run_count(self) -> int:
        return sum(1 for r in self.results if r.family in RUN_FAMILIES)

    def reset(self) -> None:
        self.results.clear()
        self.family_counts.clear()
        self._invalidate_drive_metrics()

    def summary(self) -> str:
        if not self.results:
            return "Drive log: 0 plays."
        runs, passes = self.run_pass_split()
        total = len(self.results)
        lines = [f"Drive log: {total} play{'s' if total != 1 else ''} | {runs} run / {passes} pass"]
        if self.family_counts:
            breakdown = "  |  ".join(
                f"{k.replace('_', ' ')}: {v}"
                for k, v in sorted(self.family_counts.items(), key=lambda x: -x[1])
            )
            lines.append(f"  Concepts: {breakdown}")
        return "\n".join(lines)

    def recent_results(self, n: int = 6) -> List[ActualPlayResult]:
        """Most recent play results (up to n)."""
        if n <= 0:
            return []
        return self.results[-n:]

    def recent_families(self, n: int = 6) -> List[str]:
        if n == 6:
            self._ensure_standard_drive_metrics()
            return list(self._metrics_recent6)
        return [r.family for r in self.recent_results(n)]

    def weighted_family_counts(self, *, half_life_plays: float = 3.0, max_plays: int = 12) -> Dict[str, float]:
        """
        Recency-weighted family counts for tendency detection.

        Each play i steps back gets weight: (0.5 ** (i / half_life_plays)).
        """
        if not self.results:
            return {}
        if half_life_plays <= 0:
            half_life_plays = 3.0
        if max_plays <= 0:
            return {}

        if half_life_plays == 3.0 and max_plays == 12:
            self._ensure_standard_drive_metrics()
            return self._metrics_weighted

        decay = math.log(0.5) / half_life_plays
        out: Dict[str, float] = {}
        recent = self.results[-max_plays:]
        # i=0 is most recent
        for i, r in enumerate(reversed(recent)):
            w = math.exp(decay * i)
            out[r.family] = out.get(r.family, 0.0) + w
        return out

