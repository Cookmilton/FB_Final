from __future__ import annotations

import dataclasses
import random
import re
from typing import Any, Dict, Optional, Tuple

from .domain import FG_RANGE_YARDLINE, PASS_FAMILIES, RUN_FAMILIES, GameContext
from .evaluation.calibration import CalibrationProfile
from .features import ModelInput, extract_model_input
from .game import Game
from .library import PLAY_LIBRARY
from .model_types import ModelOutput
from .play_metadata import play_selection_weight
from .predictors.base import Predictor
from .state import DriveLogger

# Compiled once — parse_situation is cold in CLI but free in tight loops if reused.
_SITUATION_RE = re.compile(
    r"(?P<down>\d+)(?:st|nd|rd|th)\s*(?:&|and)\s*(?P<distance>\d+)"
    r"\s*at\s*(?:the\s*)?(?P<territory>own|opponents?)\s*(?P<yardline>\d+)",
    re.IGNORECASE,
)

_FNV32_OFFSET = 2166136261
_FNV32_PRIME = 16777619


def _fnv32a_mix_bytes(h: int, data: bytes) -> int:
    for b in data:
        h ^= b
        h = (h * _FNV32_PRIME) & 0xFFFFFFFF
    return h


def _fnv32a_mix_int(h: int, x: int) -> int:
    """Mix a small signed int without allocating a str."""
    x &= 0xFFFFFFFF
    for _ in range(4):
        h ^= x & 0xFF
        h = (h * _FNV32_PRIME) & 0xFFFFFFFF
        x >>= 8
    return h


class FourthDownAdvisor:
    """
    Recommends go-for-it, field goal, or punt based on game context.
    Heuristic model — not a full EPA calculator.
    """

    def advise(self, ctx: GameContext) -> Dict[str, Any]:
        if ctx.down != 4:
            return {}

        in_fg_range = ctx.territory == "opponents" and ctx.yardline <= FG_RANGE_YARDLINE
        fg_distance = ctx.yardline + 17 if ctx.territory == "opponents" else None  # snap + EZ

        must_score = ctx.game_mode in ("must_score", "two_minute") or (
            ctx.score_diff < 0 and ctx.quarter == 4 and ctx.seconds_remaining < 300
        )

        if ctx.territory == "opponents" and ctx.yardline <= 2:
            return {
                "recommendation": "GO FOR IT",
                "reasoning": "Goal line — take the touchdown.",
                "fg_distance": None,
            }

        if in_fg_range and not must_score and ctx.distance > 3:
            return {
                "recommendation": "FIELD GOAL",
                "reasoning": f"~{fg_distance}-yard attempt. Take the points unless a TD is mandatory.",
                "fg_distance": fg_distance,
            }

        if ctx.distance <= 1:
            return {
                "recommendation": "GO FOR IT",
                "reasoning": "1 yard or less — the conversion rate far exceeds the field position risk.",
                "fg_distance": fg_distance,
            }

        if ctx.territory == "opponents" and ctx.yardline <= 40 and ctx.distance <= 3:
            return {
                "recommendation": "GO FOR IT",
                "reasoning": f"{ctx.distance} yards in opposing territory — field position favors the attempt.",
                "fg_distance": fg_distance if in_fg_range else None,
            }

        if must_score:
            return {
                "recommendation": "GO FOR IT",
                "reasoning": "Game script demands the conversion — can't afford to punt.",
                "fg_distance": fg_distance if in_fg_range else None,
            }

        return {
            "recommendation": "PUNT",
            "reasoning": "Outside FG range — flip field position.",
            "fg_distance": None,
        }


class HeuristicPredictor(Predictor):
    """
    Default predictor: rule-based scoring + deterministic tie breaks.

    This is the "model" you ship today; later you can swap in `SklearnPredictor`,
    `TorchPredictor`, `LLMToolPredictor`, etc. without changing feature extraction.
    """

    name = "heuristic_v1"

    def __init__(self, calibration: Optional[CalibrationProfile] = None) -> None:
        self.calibration: Optional[CalibrationProfile] = calibration
        self.baselines: Dict[str, Dict[str, float]] = {
            "short_yardage": {
                "inside_zone": 0.58,
                "duo": 0.57,
                "power": 0.55,
                "quick_game": 0.50,
                "play_action": 0.46,
            },
            "medium_yardage": {
                "inside_zone": 0.41,
                "outside_zone": 0.40,
                "quick_game": 0.52,
                "dropback_pass": 0.50,
                "screen": 0.45,
                "play_action": 0.48,
            },
            "long_yardage": {
                "draw": 0.26,
                "screen": 0.42,
                "quick_game": 0.39,
                "dropback_pass": 0.49,
                "play_action": 0.34,
            },
            "red_zone": {
                "inside_zone": 0.43,
                "power": 0.44,
                "quick_game": 0.53,
                "play_action": 0.51,
                "fade_iso": 0.31,
            },
            "backed_up": {
                "inside_zone": 0.44,
                "outside_zone": 0.42,
                "quick_game": 0.50,
                "screen": 0.46,
                "dropback_pass": 0.41,
            },
        }
        self.play_library = PLAY_LIBRARY
        self.fourth_down_advisor = FourthDownAdvisor()
        # O(1) play lookup by family + concept name (choose_play hot path).
        self._plays_by_name: Dict[str, Dict[str, Dict[str, Any]]] = {
            fam: {p["name"]: p for p in plays} for fam, plays in self.play_library.items()
        }

    # ── Guardrails / normalization ────────────────────────────────────────────

    def normalize_context(self, ctx: GameContext, drive_log: Optional[DriveLogger]) -> GameContext:
        """Public entrypoint for normalization (used by façades / future models)."""
        return self._normalized_ctx(ctx, drive_log)

    def _normalized_ctx(self, ctx: GameContext, drive_log: Optional[DriveLogger]) -> GameContext:
        c = dataclasses.replace(ctx)

        c.down = int(c.down) if c.down else 1
        c.down = max(1, min(4, c.down))

        c.distance = int(c.distance) if c.distance else 10
        c.distance = max(1, min(25, c.distance))

        c.yardline = int(c.yardline) if c.yardline else 25
        c.yardline = max(1, min(50, c.yardline))

        if c.territory not in ("own", "opponents"):
            c.territory = "own"

        c.quarter = int(c.quarter) if c.quarter else 2
        c.quarter = max(1, min(4, c.quarter))

        c.score_diff = int(c.score_diff or 0)
        c.score_diff = max(-99, min(99, c.score_diff))

        c.seconds_remaining = int(c.seconds_remaining or 0)
        c.seconds_remaining = max(0, min(60 * 60, c.seconds_remaining))

        c.own_timeouts = int(c.own_timeouts or 0)
        c.own_timeouts = max(0, min(3, c.own_timeouts))
        c.opp_timeouts = int(c.opp_timeouts or 0)
        c.opp_timeouts = max(0, min(3, c.opp_timeouts))

        if not c.def_personnel:
            c.def_personnel = "unknown"
        if not c.coverage_shell:
            c.coverage_shell = "unknown"
        if not c.safeties:
            c.safeties = "unknown"
        c.box_count = int(c.box_count or 7)
        c.box_count = max(4, min(9, c.box_count))
        c.blitz_likely = bool(c.blitz_likely)

        if c.weather not in ("clear", "wind", "rain", "snow"):
            c.weather = "clear"
        c.wind_mph = int(c.wind_mph or 0)
        c.wind_mph = max(0, min(60, c.wind_mph))
        if c.weather != "wind":
            c.wind_mph = 0

        if c.game_mode not in ("normal", "must_score", "drain_clock", "two_minute", "two_point", ""):
            c.game_mode = "normal"

        if drive_log is not None:
            c.plays_this_drive = len(drive_log.results)
            c.shown_concepts = list(drive_log.family_counts.keys())
            c.run_plays_this_drive = drive_log.run_count()
        else:
            c.plays_this_drive = int(c.plays_this_drive or 0)
            c.plays_this_drive = max(0, c.plays_this_drive)
            c.run_plays_this_drive = int(c.run_plays_this_drive or 0)
            c.run_plays_this_drive = max(0, c.run_plays_this_drive)

        return c

    def _stable_seed(
        self,
        ctx: GameContext,
        drive_log: Optional[DriveLogger],
        model_input: Optional[ModelInput] = None,
    ) -> int:
        """
        Deterministic 32-bit seed (same inputs → same RNG stream across processes).

        Uses FNV-1a instead of Python's salted str hash().
        """
        h = _FNV32_OFFSET
        h = _fnv32a_mix_int(h, int(ctx.down))
        h = _fnv32a_mix_int(h, int(ctx.distance))
        h = _fnv32a_mix_int(h, int(ctx.yardline))
        h = _fnv32a_mix_bytes(h, ctx.territory.encode("utf-8"))
        h = _fnv32a_mix_bytes(h, ctx.def_personnel.encode("utf-8"))
        h = _fnv32a_mix_int(h, int(ctx.box_count))
        h = _fnv32a_mix_bytes(h, ctx.coverage_shell.encode("utf-8"))
        h = _fnv32a_mix_bytes(h, ctx.safeties.encode("utf-8"))
        h = _fnv32a_mix_int(h, int(ctx.blitz_likely))
        h = _fnv32a_mix_int(h, int(ctx.score_diff))
        h = _fnv32a_mix_int(h, int(ctx.quarter))
        h = _fnv32a_mix_int(h, int(ctx.seconds_remaining))
        h = _fnv32a_mix_int(h, int(ctx.own_timeouts))
        h = _fnv32a_mix_int(h, int(ctx.opp_timeouts))
        h = _fnv32a_mix_bytes(h, ctx.weather.encode("utf-8"))
        h = _fnv32a_mix_int(h, int(ctx.wind_mph))
        h = _fnv32a_mix_int(h, int(ctx.qb_limited))
        h = _fnv32a_mix_bytes(h, ctx.game_mode.encode("utf-8"))
        if drive_log is None:
            h = _fnv32a_mix_int(h, 0)
        else:
            h = _fnv32a_mix_int(h, len(drive_log.results))
            for fam, cnt in sorted(drive_log.family_counts.items()):
                h = _fnv32a_mix_bytes(h, fam.encode("utf-8"))
                h = _fnv32a_mix_int(h, int(cnt))
        if model_input is not None:
            feat = model_input.features
            h = _fnv32a_mix_int(h, int(feat.get("game_flow_seq_len", 0) or 0))
            h = _fnv32a_mix_int(h, int(feat.get("game_flow_prior_plays", 0) or 0))
            tail = str(feat.get("game_flow_recent_last_family", "") or "")
            h = _fnv32a_mix_bytes(h, tail.encode("utf-8"))
            gf = model_input.meta.get("game_context_features")
            if isinstance(gf, dict):
                h = _fnv32a_mix_bytes(
                    h, str(gf.get("last_archived_drive_result_kind", "") or "").encode("utf-8")
                )
                h = _fnv32a_mix_int(h, int(gf.get("sample_size_plays", 0) or 0))
                h = _fnv32a_mix_int(h, int(1000 * float(feat.get("gcf_success_rate", 0) or 0)))
        return h & 0xFFFFFFFF

    # ── Drive tendencies / pattern detection ──────────────────────────────────

    def _apply_drive_awareness(
        self, scores: Dict[str, float], ctx: GameContext, drive_log: Optional[DriveLogger]
    ) -> Dict[str, float]:
        if not scores or not drive_log or not drive_log.results:
            return scores

        def nudge(family: str, amount: float) -> None:
            if family in scores:
                scores[family] = round(scores[family] + amount, 3)

        recent_fams = drive_log.recent_families(6)
        weighted = drive_log.weighted_family_counts(half_life_plays=3.0, max_plays=12)

        for fam, wc in weighted.items():
            if fam not in scores:
                continue
            if wc > 2.6:
                penalty = min(0.12, 0.03 * (wc - 2.6))
                nudge(fam, -penalty)

        if len(recent_fams) >= 2 and recent_fams[-1] == recent_fams[-2]:
            streak_fam = recent_fams[-1]
            nudge(streak_fam, -0.05)
            if streak_fam in RUN_FAMILIES:
                nudge("quick_game", +0.03)
                nudge("screen", +0.02)
                nudge("play_action", +0.01)
            else:
                nudge("inside_zone", +0.03)
                nudge("duo", +0.02)
                nudge("draw", +0.01)

        run_w = sum(w for fam, w in weighted.items() if fam in RUN_FAMILIES)
        pass_w = sum(w for fam, w in weighted.items() if fam in PASS_FAMILIES)
        total = run_w + pass_w
        if total > 0:
            run_share = run_w / total
            pass_share = pass_w / total
            if run_share >= 0.72:
                for fam in RUN_FAMILIES:
                    nudge(fam, -0.02)
                nudge("quick_game", +0.02)
                nudge("screen", +0.02)
                nudge("dropback_pass", +0.01)
            elif pass_share >= 0.72:
                for fam in PASS_FAMILIES:
                    nudge(fam, -0.02)
                nudge("inside_zone", +0.02)
                nudge("duo", +0.02)
                nudge("draw", +0.01)

        if len(recent_fams) >= 2:
            last2 = recent_fams[-2:]
            if all(f in RUN_FAMILIES for f in last2):
                nudge("play_action", +0.03)
                nudge("quick_game", +0.02)
            if all(f in PASS_FAMILIES for f in last2):
                nudge("inside_zone", +0.03)
                nudge("duo", +0.02)

        return scores

    def _apply_game_flow_awareness(self, scores: Dict[str, float], model_input: ModelInput) -> Dict[str, float]:
        """
        Session-level tendency adjustments from ``ModelInput`` game-flow features
        (archived drives for the possessing team + current ``drive_log``).
        """
        if not scores:
            return scores
        f = model_input.features
        prior_plays = int(f.get("game_flow_prior_plays", 0) or 0)
        seq_len = int(f.get("game_flow_seq_len", 0) or 0)
        if prior_plays < 3 and seq_len < 8:
            return scores

        def nudge(family: str, amount: float) -> None:
            if family in scores:
                scores[family] = round(scores[family] + amount, 3)

        gf_weighted = model_input.meta.get("game_flow_weighted_family_counts") or {}
        if isinstance(gf_weighted, dict):
            for fam, wc in gf_weighted.items():
                if fam not in scores:
                    continue
                try:
                    wcf = float(wc)
                except (TypeError, ValueError):
                    continue
                if wcf > 2.8:
                    penalty = min(0.07, 0.022 * (wcf - 2.8))
                    nudge(str(fam), -penalty)

        gf_recent = model_input.meta.get("game_flow_recent_families") or []
        if len(gf_recent) >= 2 and gf_recent[-1] == gf_recent[-2]:
            streak_fam = str(gf_recent[-1])
            nudge(streak_fam, -0.028)
            if streak_fam in RUN_FAMILIES:
                nudge("quick_game", +0.018)
                nudge("screen", +0.012)
                nudge("dropback_pass", +0.01)
            elif streak_fam in PASS_FAMILIES:
                nudge("inside_zone", +0.018)
                nudge("duo", +0.012)
                nudge("draw", +0.01)

        run_share = float(f.get("game_flow_weighted_run_share", 0) or 0)
        pass_share = float(f.get("game_flow_weighted_pass_share", 0) or 0)
        if run_share >= 0.68:
            for fam in RUN_FAMILIES:
                nudge(fam, -0.012)
            nudge("quick_game", +0.014)
            nudge("screen", +0.012)
            nudge("dropback_pass", +0.01)
        elif pass_share >= 0.68:
            for fam in PASS_FAMILIES:
                nudge(fam, -0.012)
            nudge("inside_zone", +0.014)
            nudge("duo", +0.012)
            nudge("draw", +0.01)

        if len(gf_recent) >= 2:
            last2 = gf_recent[-2:]
            if all(x in RUN_FAMILIES for x in last2):
                nudge("play_action", +0.02)
                nudge("quick_game", +0.014)
            if all(x in PASS_FAMILIES for x in last2):
                nudge("inside_zone", +0.02)
                nudge("duo", +0.014)

        return scores

    def _apply_game_context_nudges(self, scores: Dict[str, float], model_input: ModelInput) -> Dict[str, float]:
        """
        Lightweight adjustments from ``meta["game_context_features"]`` (success, drive
        outcomes, target concentration, explosives). Applied after drive + game-flow layers.
        """
        if not scores:
            return scores
        gcf = model_input.meta.get("game_context_features")
        if not isinstance(gcf, dict):
            return scores
        sample = int(gcf.get("sample_size_plays") or 0)
        if sample < 4:
            return scores

        feat = model_input.features
        archived = int(feat.get("gcf_archived_team_drives", 0) or 0)

        def nudge(family: str, amount: float) -> None:
            if family in scores:
                scores[family] = round(scores[family] + amount, 3)

        orun = float(feat.get("gcf_overall_run_share", 0) or 0)
        opass = float(feat.get("gcf_overall_pass_share", 0) or 0)
        if orun >= 0.64:
            nudge("quick_game", +0.01)
            nudge("screen", +0.009)
            nudge("dropback_pass", +0.008)
        elif opass >= 0.64:
            nudge("inside_zone", +0.01)
            nudge("duo", +0.009)
            nudge("draw", +0.008)

        late_n = int(feat.get("gcf_late_down_n", 0) or 0)
        if late_n >= 3:
            late_pass = float(feat.get("gcf_late_pass_share", 0) or 0)
            late_run = float(feat.get("gcf_late_run_share", 0) or 0)
            if late_pass >= 0.62:
                nudge("inside_zone", +0.009)
                nudge("draw", +0.007)
            elif late_run >= 0.62:
                nudge("quick_game", +0.009)
                nudge("screen", +0.007)

        top_share = float(feat.get("gcf_top_target_role_share", 0) or 0)
        top_list = gcf.get("target_role_top") or []
        if top_share >= 0.38 and top_list:
            role = str(top_list[0][0]).upper()
            if role == "X":
                nudge("inside_zone", +0.011)
                nudge("screen", +0.009)
                nudge("draw", +0.007)
            elif role == "Z":
                nudge("fade_iso", +0.011)
                nudge("outside_zone", +0.009)
            elif role in ("H", "SLOT"):
                nudge("fade_iso", +0.01)
                nudge("outside_zone", +0.008)
            elif role in ("Y", "TE"):
                nudge("draw", +0.01)
                nudge("quick_game", +0.008)
            elif role == "RB":
                nudge("quick_game", +0.01)
                nudge("dropback_pass", +0.009)

        succ = float(feat.get("gcf_recent_success_rate", 0) or 0)
        expl = float(feat.get("gcf_recent_explosive_rate", 0) or 0)
        stalled = float(feat.get("gcf_stalled_drive_share", 0) or 0)
        if archived >= 2 and stalled >= 0.5 and succ < 0.38:
            nudge("quick_game", +0.012)
            nudge("inside_zone", +0.011)
            nudge("screen", +0.009)
            nudge("fade_iso", -0.009)
            nudge("play_action", -0.008)
            nudge("dropback_pass", -0.007)
        if expl >= 0.2:
            nudge("dropback_pass", +0.01)
            nudge("play_action", +0.009)
            nudge("fade_iso", +0.008)

        tov = float(feat.get("gcf_turnover_play_rate", 0) or 0)
        if tov >= 0.1:
            nudge("quick_game", +0.009)
            nudge("inside_zone", +0.008)
            nudge("play_action", -0.007)
            nudge("fade_iso", -0.006)

        last_k = str(gcf.get("last_archived_drive_result_kind") or "")
        if last_k in ("punt", "turnover_interception", "turnover_fumble", "turnover_on_downs"):
            nudge("quick_game", +0.008)
            nudge("inside_zone", +0.008)

        condensed = float(feat.get("gcf_condensed_field_play_share", 0) or 0)
        if condensed >= 0.42:
            nudge("quick_game", +0.007)
            nudge("fade_iso", +0.006)

        return scores

    # ── Parsing (kept here for CLI convenience; not part of model I/O) ─────────

    def parse_situation(self, text: str) -> Tuple[int, int, int, str]:
        match = _SITUATION_RE.search(text.strip())
        if not match:
            raise ValueError("Use format: '2nd & 7 at the opponents 43'")
        down = int(match.group("down"))
        distance = int(match.group("distance"))
        yardline = int(match.group("yardline"))
        territory = "opponents" if match.group("territory").lower().startswith("opponent") else "own"
        return down, distance, yardline, territory

    def parse_defense(self, text: str, ctx: GameContext) -> None:
        t = text.lower().strip()
        if not t or t == "unknown":
            return

        for p in ("goal_line", "dime", "nickel", "base", "dollar"):
            if p.replace("_", " ") in t or p in t:
                ctx.def_personnel = p
                break

        m = re.search(r"\b([4-9])\b(?!\s*(?:yd|yard|man))", t)
        if m:
            ctx.box_count = int(m.group(1))

        cover_map = {
            "cover 0": "cover_0",
            "cover0": "cover_0",
            "zero": "cover_0",
            "cover 1": "cover_1",
            "cover1": "cover_1",
            "man": "cover_1",
            "cover 2": "cover_2",
            "cover2": "cover_2",
            "tampa": "cover_2",
            "cover 3": "cover_3",
            "cover3": "cover_3",
            "cover 4": "cover_4",
            "cover4": "cover_4",
            "quarters": "quarters",
        }
        for key, val in cover_map.items():
            if key in t:
                ctx.coverage_shell = val
                break

        if "single high" in t or "single" in t or "one high" in t:
            ctx.safeties = "single_high"
        elif "two high" in t or "2 high" in t:
            ctx.safeties = "two_high"

        if ctx.safeties == "unknown":
            if ctx.coverage_shell in ("cover_0", "cover_1", "cover_3"):
                ctx.safeties = "single_high"
            elif ctx.coverage_shell in ("cover_2", "cover_4", "quarters"):
                ctx.safeties = "two_high"

        if "blitz" in t or "pressure" in t or "fire zone" in t:
            ctx.blitz_likely = True

    def parse_game_script(self, text: str, ctx: GameContext) -> None:
        t = text.strip()
        if not t:
            return

        m = re.search(r"([+-]?\d+)", t)
        if m:
            ctx.score_diff = int(m.group(1))

        m = re.search(r"[Qq](\d)", t)
        if m:
            ctx.quarter = int(m.group(1))

        m = re.search(r"(\d{1,2}):(\d{2})", t)
        if m:
            ctx.seconds_remaining = int(m.group(1)) * 60 + int(m.group(2))

        m = re.search(r"\b([0-3])\s*/\s*([0-3])\b", t)
        if m:
            ctx.own_timeouts = int(m.group(1))
            ctx.opp_timeouts = int(m.group(2))

    # ── Situation bucket / game mode ───────────────────────────────────────────

    def get_bucket(self, ctx: GameContext) -> str:
        if ctx.territory == "opponents" and ctx.yardline <= 20:
            return "red_zone"
        if ctx.territory == "own" and ctx.yardline <= 10:
            return "backed_up"
        if ctx.distance <= 2:
            return "short_yardage"
        if 3 <= ctx.distance <= 6:
            return "medium_yardage"
        return "long_yardage"

    def derive_game_mode(self, ctx: GameContext) -> str:
        if ctx.game_mode not in ("normal", ""):
            return ctx.game_mode

        two_minute = ctx.quarter in (2, 4) and ctx.seconds_remaining <= 120
        if two_minute:
            return "two_minute"

        must_score = (ctx.score_diff <= -14 and ctx.quarter == 4) or (
            ctx.score_diff <= -8 and ctx.quarter == 4 and ctx.seconds_remaining <= 240
        )
        if must_score:
            return "must_score"

        drain = ctx.score_diff >= 10 and ctx.quarter == 4 and ctx.seconds_remaining > 120
        if drain:
            return "drain_clock"

        return "normal"

    # ── Family scoring / selection ─────────────────────────────────────────────

    def score_families(self, ctx: GameContext, bucket: str) -> Dict[str, float]:
        scores = self.baselines.get(bucket, {}).copy()
        if not scores:
            return {}

        def nudge(family: str, amount: float) -> None:
            if family in scores:
                scores[family] = round(scores[family] + amount, 3)

        # Red zone behavior shift (tighter spaces → different risk profile)
        # This is intentionally layered on top of the red_zone baselines.
        if bucket == "red_zone" and ctx.territory == "opponents" and ctx.yardline <= 20:
            # Short edges compress windows; lean on condensed-space answers.
            if ctx.distance <= 3:
                nudge("quick_game", +0.05)
                nudge("fade_iso", +0.03)
                nudge("power", +0.03)
                nudge("dropback_pass", -0.04)
                nudge("play_action", -0.03)
            elif ctx.distance >= 8:
                nudge("quick_game", +0.03)
                nudge("screen", +0.03)
                nudge("dropback_pass", +0.02)
                nudge("fade_iso", -0.02)
            else:
                nudge("play_action", +0.03)
                nudge("quick_game", +0.02)
                nudge("dropback_pass", +0.01)

            # Goal-line-ish: even more condensed
            if ctx.yardline <= 5:
                nudge("power", +0.04)
                nudge("quick_game", +0.03)
                nudge("dropback_pass", -0.03)

        if ctx.down == 1:
            nudge("inside_zone", +0.02)
            nudge("play_action", +0.02)

        if ctx.down == 2 and ctx.distance >= 7:
            nudge("dropback_pass", +0.03)
            nudge("quick_game", +0.02)

        if ctx.down == 3:
            nudge("dropback_pass", +0.04)
            if ctx.distance <= 4:
                nudge("quick_game", +0.03)
            if ctx.distance >= 8:
                nudge("screen", +0.02)

        if ctx.box_count <= 6:
            nudge("inside_zone", +0.04)
            nudge("outside_zone", +0.03)
            nudge("duo", +0.02)
            nudge("dropback_pass", -0.02)
        elif ctx.box_count >= 8:
            nudge("inside_zone", -0.04)
            nudge("duo", -0.03)
            nudge("dropback_pass", +0.04)
            nudge("quick_game", +0.03)

        if ctx.coverage_shell in ("cover_0", "cover_1"):
            nudge("play_action", +0.05)
            nudge("screen", +0.04)
            nudge("quick_game", +0.03)
            nudge("dropback_pass", -0.03)
        elif ctx.coverage_shell == "cover_2":
            nudge("outside_zone", +0.03)
            nudge("dropback_pass", +0.02)
            nudge("quick_game", -0.02)
        elif ctx.coverage_shell == "cover_3":
            nudge("dropback_pass", +0.04)
        elif ctx.coverage_shell in ("cover_4", "quarters"):
            nudge("quick_game", +0.05)
            nudge("draw", +0.03)
            nudge("play_action", -0.03)

        if ctx.safeties == "single_high":
            nudge("play_action", +0.04)
            nudge("dropback_pass", +0.03)
        elif ctx.safeties == "two_high":
            nudge("quick_game", +0.03)
            nudge("screen", +0.02)
            nudge("dropback_pass", -0.02)

        if ctx.blitz_likely:
            nudge("screen", +0.05)
            nudge("quick_game", +0.04)
            nudge("dropback_pass", -0.03)
            nudge("play_action", -0.02)

        if ctx.weather == "wind" and ctx.wind_mph >= 20:
            nudge("play_action", -0.05)
            nudge("dropback_pass", -0.04)
            nudge("inside_zone", +0.04)
            nudge("quick_game", +0.03)

        if ctx.weather in ("rain", "snow"):
            nudge("dropback_pass", -0.06)
            nudge("play_action", -0.04)
            nudge("screen", -0.03)
            nudge("inside_zone", +0.05)
            nudge("duo", +0.04)

        if ctx.game_mode == "drain_clock":
            nudge("inside_zone", +0.06)
            nudge("duo", +0.04)
            nudge("power", +0.03)
            nudge("dropback_pass", -0.05)
            nudge("screen", -0.04)
        elif ctx.game_mode == "must_score":
            nudge("dropback_pass", +0.05)
            nudge("play_action", +0.04)
            nudge("inside_zone", -0.03)
        elif ctx.game_mode == "two_minute":
            nudge("quick_game", +0.06)
            nudge("dropback_pass", +0.04)
            nudge("inside_zone", -0.05)
            nudge("play_action", -0.04)

        if ctx.qb_limited:
            nudge("dropback_pass", -0.04)
            nudge("play_action", -0.03)
            nudge("inside_zone", +0.04)
            nudge("quick_game", +0.03)

        if "play_action" in scores and ctx.run_plays_this_drive < 3:
            nudge("play_action", -0.04)

        if ctx.quarter == 4:
            if ctx.seconds_remaining <= 600 and ctx.score_diff >= 1:
                nudge("inside_zone", +0.03)
                nudge("duo", +0.02)
                nudge("dropback_pass", -0.02)
            if ctx.seconds_remaining <= 600 and ctx.score_diff <= -1:
                nudge("dropback_pass", +0.03)
                nudge("quick_game", +0.02)
                nudge("inside_zone", -0.02)

        return scores

    def choose_family(self, ctx: GameContext, bucket: str, scores: Optional[Dict[str, float]] = None) -> str:
        if scores is None:
            scores = self.score_families(ctx, bucket)
        if not scores:
            return "quick_game"

        if ctx.down == 4:
            if ctx.distance <= 2:
                preferred = ["duo", "power", "inside_zone", "quick_game"]
                filtered = {k: v for k, v in scores.items() if k in preferred}
                if filtered:
                    return max(filtered, key=filtered.get)
            else:
                preferred = ["quick_game", "dropback_pass", "screen"]
                filtered = {k: v for k, v in scores.items() if k in preferred}
                if filtered:
                    return max(filtered, key=filtered.get)

        return max(scores, key=scores.get)

    def choose_play(
        self,
        family: str,
        ctx: GameContext,
        rng: random.Random,
        model_input: Optional[ModelInput] = None,
    ) -> Dict[str, Any]:
        candidates = self.play_library.get(family, [])
        if not candidates:
            return {"name": f"[No plays defined for {family}]", "why": ""}
        if len(candidates) == 1:
            return candidates[0]

        bucket = self.get_bucket(ctx)

        def legacy_bonus(play: Dict[str, Any]) -> float:
            b = 0.0
            n = play.get("name")
            if family == "quick_game":
                if ctx.distance <= 3 and n == "Stick":
                    b += 0.18
                elif ctx.distance >= 6 and n == "Slant-Flat":
                    b += 0.14
            if family == "dropback_pass":
                if ctx.distance >= 8 and n == "Dagger":
                    b += 0.16
                elif 4 <= ctx.distance < 8 and n == "Drive":
                    b += 0.1
            if family == "play_action":
                if ctx.territory == "opponents" and ctx.yardline <= 20 and n == "Y-Leak":
                    b += 0.14
            return b

        weights = [
            play_selection_weight(
                p,
                family=family,
                ctx=ctx,
                bucket=bucket,
                model_input=model_input,
                legacy_bonus=legacy_bonus(p),
            )
            for p in candidates
        ]
        return rng.choices(candidates, weights=weights, k=1)[0]

    def coverage_note(self, play: Dict[str, Any], ctx: GameContext) -> Optional[str]:
        if ctx.coverage_shell in ("cover_0", "cover_1"):
            return play.get("vs_man")
        if ctx.coverage_shell != "unknown":
            return play.get("vs_zone")
        return None

    def pa_qualifier(self, family: str, ctx: GameContext) -> Optional[str]:
        if family != "play_action":
            return None
        if ctx.run_plays_this_drive < 3:
            return (
                f"⚠  Run not established ({ctx.run_plays_this_drive} run plays this drive) — "
                "play-action may not freeze linebackers. Consider running first."
            )
        return None

    def _confidence_from_scores(self, scores: Dict[str, float], family: str, ctx: GameContext) -> Optional[float]:
        if not scores or family not in scores:
            return None
        vals = sorted(scores.values(), reverse=True)
        if len(vals) < 2:
            return None
        top = vals[0]
        second = vals[1]
        gap = max(0.0, top - second)
        # Map gap to [0.5, 0.95] — heuristic "confidence"
        conf = min(0.95, max(0.5, 0.5 + gap * 2.0))

        # Uncertainty penalties (still heuristic, but directionally right)
        unk = 0
        if ctx.def_personnel == "unknown":
            unk += 1
        if ctx.coverage_shell == "unknown":
            unk += 1
        if ctx.safeties == "unknown":
            unk += 1
        conf -= 0.04 * unk

        # Red zone increases conflict/defensive density in real life → slightly wider uncertainty band
        if self.get_bucket(ctx) == "red_zone" and ctx.territory == "opponents" and ctx.yardline <= 20:
            conf -= 0.03

        return round(min(0.95, max(0.45, conf)), 3)

    def _two_point_confidence(self, ctx: GameContext) -> float:
        """
        2-pt shelf is a small discrete set; confidence is mostly about how complete the
        defensive read is (unknown reads widen uncertainty).
        """
        conf = 0.62
        unk = 0
        if ctx.def_personnel == "unknown":
            unk += 1
        if ctx.coverage_shell == "unknown":
            unk += 1
        if ctx.safeties == "unknown":
            unk += 1
        conf -= 0.05 * unk
        if ctx.blitz_likely:
            conf -= 0.02
        return round(min(0.9, max(0.45, conf)), 3)

    def predict(self, model_input: ModelInput, ctx: GameContext, drive_log: Optional[DriveLogger] = None) -> ModelOutput:
        ctx_n = self.normalize_context(ctx, drive_log)
        ctx_n.game_mode = self.derive_game_mode(ctx_n)
        return self._predict_core(model_input, ctx_n, drive_log)

    def _predict_core(
        self, model_input: ModelInput, ctx_n: GameContext, drive_log: Optional[DriveLogger] = None
    ) -> ModelOutput:
        """
        Run scoring + selection assuming `ctx_n` is already normalized and
        `ctx_n.game_mode` is finalized (avoids duplicate work in `recommend`).
        """
        rng = random.Random(self._stable_seed(ctx_n, drive_log, model_input))

        if ctx_n.game_mode == "two_point":
            play = self.choose_play("two_point", ctx_n, rng, model_input)
            return ModelOutput(
                play_family="two_point",
                play=play,
                bucket="two_point",
                scores={},
                fourth_down={},
                pa_warning=None,
                coverage_note=self.coverage_note(play, ctx_n) if play else None,
                overuse_warning=drive_log.overuse_warning("two_point") if drive_log else None,
                model_name=self.name,
                model_version="1.0.0",
                confidence=self._two_point_confidence(ctx_n),
                extras={"model_input": model_input},
            )

        bucket = self.get_bucket(ctx_n)
        base_scores = self.score_families(ctx_n, bucket)
        scores = self._apply_drive_awareness(base_scores, ctx_n, drive_log)
        scores = self._apply_game_flow_awareness(scores, model_input)
        scores = self._apply_game_context_nudges(scores, model_input)
        if self.calibration is not None:
            scores = self.calibration.apply(scores, ctx_n, bucket)
        family = self.choose_family(ctx_n, bucket, scores=scores)
        play = self.choose_play(family, ctx_n, rng, model_input)

        return ModelOutput(
            play_family=family,
            play=play,
            bucket=bucket,
            scores=scores,
            fourth_down=self.fourth_down_advisor.advise(ctx_n),
            pa_warning=self.pa_qualifier(family, ctx_n),
            coverage_note=self.coverage_note(play, ctx_n),
            overuse_warning=drive_log.overuse_warning(family) if drive_log else None,
            model_name=self.name,
            model_version="1.0.0",
            confidence=self._confidence_from_scores(scores, family, ctx_n),
            extras={"model_input": model_input, "base_scores": base_scores},
        )

    # Convenience wrapper used by the legacy façade API.
    def recommend(
        self, ctx: GameContext, drive_log: Optional[DriveLogger] = None, game: Optional[Game] = None
    ) -> Dict[str, Any]:
        ctx_n = self.normalize_context(ctx, drive_log)
        ctx_n.game_mode = self.derive_game_mode(ctx_n)
        model_in = extract_model_input(ctx_n, drive_log, game)
        out = self._predict_core(model_in, ctx_n, drive_log)
        return {
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
