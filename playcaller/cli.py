from __future__ import annotations

import re
from typing import Any, Dict, List

from .actual_result import assemble_actual_semantics, finalize_actual_after_snap
from .domain import GameContext
from .engine import FootballPlayPredictor
from .situation import advance_game_state_after_actual, earned_first_down_for_actual_play
from .state import DriveLogger

_CLI_LOG_OUTCOME_AUTO = "Auto (from call + yards)"
_CLI_LOG_TARGET_AUTO = "Auto from play"


def ordinal_suffix(n: int) -> str:
    return {1: "st", 2: "nd", 3: "rd"}.get(n, "th")


def fmt_time(seconds: int) -> str:
    m, s = divmod(abs(seconds), 60)
    return f"{m}:{s:02d}"


def pretty_print(result: Dict[str, Any], drive_log: DriveLogger) -> None:
    ctx: GameContext = result["ctx"]
    play = result["play"]
    family = result["play_family"]
    bucket = result["bucket"]

    w = 62
    print(f"\n{'═' * w}")

    mode_banners = {
        "two_minute": "🚨  TWO-MINUTE DRILL",
        "must_score": "🚨  MUST SCORE",
        "drain_clock": "⏱   DRAIN THE CLOCK",
        "two_point": "🎯  TWO-POINT CONVERSION",
    }
    if ctx.game_mode in mode_banners:
        print(f"  {mode_banners[ctx.game_mode]}")
        print(f"{'─' * w}")

    fd = result.get("fourth_down", {})
    if fd:
        rec = fd["recommendation"]
        icon = {"GO FOR IT": "✅", "FIELD GOAL": "🏈", "PUNT": "👟"}.get(rec, "•")
        print(f"  {icon}  4TH DOWN: {rec}")
        print(f"     {fd['reasoning']}")
        if fd.get("fg_distance"):
            print(f"     Estimated FG distance: ~{fd['fg_distance']} yards")
        print(f"{'─' * w}")

    suf = ordinal_suffix(ctx.down)
    terr_label = "Opp." if ctx.territory == "opponents" else "Own"
    print(f"  {ctx.down}{suf} & {ctx.distance}  |  {terr_label} {ctx.yardline}  |  {bucket.replace('_', ' ').title()}")

    def_parts = []
    if ctx.def_personnel != "unknown":
        def_parts.append(ctx.def_personnel.replace("_", " ").title())
    def_parts.append(f"{ctx.box_count} in box")
    if ctx.coverage_shell != "unknown":
        def_parts.append(ctx.coverage_shell.replace("_", " ").upper())
    if ctx.safeties != "unknown":
        def_parts.append(ctx.safeties.replace("_", " ").title())
    if ctx.blitz_likely:
        def_parts.append("BLITZ")
    print(f"  Defense: {' | '.join(def_parts)}")

    score_label = f"+{ctx.score_diff}" if ctx.score_diff > 0 else str(ctx.score_diff)
    print(f"  Score: {score_label}  |  Q{ctx.quarter} {fmt_time(ctx.seconds_remaining)}  |  TOs {ctx.own_timeouts}–{ctx.opp_timeouts}")

    if ctx.mismatch:
        print(f"  🎯 Mismatch flagged: {ctx.mismatch}")

    print(f"{'═' * w}")

    if not play:
        print("  No play found.")
        return

    print(f"  PLAY: {play.get('name', 'Unknown')}   ({family.replace('_', ' ').title()})")
    print(f"  Personnel: {play.get('personnel', 'N/A')}  |  Formation: {play.get('formation', 'N/A')}")

    if "protection" in play:
        print(f"  Protection: {play['protection']}")
    elif "blocking" in play:
        print(f"  Blocking: {play['blocking']}")

    if "run_scheme" in play:
        print(f"  Run scheme: {play['run_scheme']}")

    if "routes" in play:
        print("\n  Routes:")
        for player, route in play["routes"].items():
            print(f"    {player}:  {route}")

    print(f"\n{'─' * w}")
    print(f"  📋 Why: {play.get('why', '')}")

    cov_note = result.get("coverage_note")
    if cov_note:
        shell_label = ctx.coverage_shell.replace("_", " ").upper()
        print(f"  📡 vs. {shell_label}: {cov_note}")
    else:
        if play.get("vs_man"):
            print(f"  📡 vs. MAN:  {play['vs_man']}")
        if play.get("vs_zone"):
            print(f"  📡 vs. ZONE: {play['vs_zone']}")

    if play.get("kill_look"):
        print(f"  ⛔ Kill look: {play['kill_look']}")
    if play.get("post_snap_alert"):
        print(f"  👁  Post-snap: {play['post_snap_alert']}")
    if result.get("pa_warning"):
        print(f"\n  {result['pa_warning']}")
    if result.get("overuse_warning"):
        print(f"\n  {result['overuse_warning']}")

    print(f"\n{'─' * w}")
    print(f"  {drive_log.summary()}")
    print(f"{'═' * w}")


TEST_CASES: List[Dict[str, Any]] = [
    {"situation": "1st & 10 at own 25", "defense": "nickel 7 cover3", "script": "0 Q2 10:00"},
    {"situation": "2nd & 7 at the opponents 43", "defense": "nickel 6 cover2", "script": "-3 Q3 6:30"},
    {"situation": "3rd & 8 at own 35", "defense": "dime 5 quarters two high", "script": "-7 Q4 4:00 2/3"},
    {"situation": "4th & 1 at the opponents 2", "defense": "goal_line 9 cover0", "script": "3 Q4 1:30"},
    {"situation": "4th & 12 at own 48", "defense": "nickel 6 cover3", "script": "-14 Q4 3:00"},
    {"situation": "1st & 10 at the opponents 15", "defense": "nickel 7 cover2", "script": "7 Q2 5:00"},
    {"situation": "3rd & 3 at own 8", "defense": "base 7 cover3", "script": "0 Q3 8:00"},
    {"situation": "2nd & 10 at own 40", "defense": "nickel 7 blitz", "script": "0 Q4 1:45 1/3", "extras": ""},
]


def run_tests(predictor: FootballPlayPredictor) -> None:
    for tc in TEST_CASES:
        try:
            down, distance, yardline, territory = predictor.parse_situation(tc["situation"])
            ctx = GameContext(down=down, distance=distance, yardline=yardline, territory=territory)
            predictor.parse_defense(tc.get("defense", ""), ctx)
            predictor.parse_game_script(tc.get("script", ""), ctx)
            log = DriveLogger()
            result = predictor.recommend(ctx, log)
            pretty_print(result, log)
        except Exception as e:
            print(f"Error on '{tc['situation']}': {e}")


def prompt(label: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    val = input(f"  {label}{hint}: ").strip()
    return val if val else default


def run_interactive(predictor: FootballPlayPredictor, drive_log: DriveLogger) -> None:
    w = 62
    print(f"\n{'═' * w}")
    print("  FOOTBALL PLAY PREDICTOR — SIDELINE OC")
    print(f"{'─' * w}")
    print("  Situation:  '3rd & 8 at the opponents 35'")
    print("  Defense:    'nickel 6 cover2 blitz'")
    print("  Script:     '-7 Q4 4:20 2/3'")
    print("  Extras:     'wind25'  'rain'  'grass'  'qblimited'  '2pt'")
    print("              'mismatch: slot cb is slow'")
    print(f"{'─' * w}")
    print("  Commands:   'new drive'  |  'log'  |  'test'  |  'quit'")
    print(f"{'═' * w}")

    while True:
        print()
        raw = input("  Situation: ").strip()

        if not raw:
            continue
        if raw.lower() in {"quit", "exit", "q"}:
            print("  Exiting.")
            break
        if raw.lower() in {"new drive", "new"}:
            drive_log.reset()
            print("  Drive log reset.\n")
            continue
        if raw.lower() == "log":
            print(f"\n  {drive_log.summary()}")
            continue
        if raw.lower() == "test":
            print("\n  --- Running test cases ---")
            run_tests(predictor)
            continue

        try:
            down, distance, yardline, territory = predictor.parse_situation(raw)
        except ValueError as e:
            print(f"  Error: {e}")
            continue

        ctx = GameContext(
            down=down,
            distance=distance,
            yardline=yardline,
            territory=territory,
            plays_this_drive=len(drive_log.results),
            shown_concepts=list(drive_log.family_counts.keys()),
            run_plays_this_drive=drive_log.run_count(),
        )

        def_raw = prompt("Defense [personnel/box/coverage/blitz]", "unknown")
        predictor.parse_defense(def_raw, ctx)

        script_raw = prompt("Script [score Q# mm:ss own/opp TOs]", "0 Q2")
        predictor.parse_game_script(script_raw, ctx)

        extras_raw = prompt("Extras [wind# / rain / snow / grass / qblimited / 2pt / mismatch:...]", "")
        if extras_raw:
            e = extras_raw.lower()
            if "2pt" in e or "two point" in e or "two-point" in e:
                ctx.game_mode = "two_point"
            if "qblimited" in e or "qb limited" in e or "qb_limited" in e:
                ctx.qb_limited = True
            if "grass" in e:
                ctx.turf = "grass"
            m = re.search(r"wind\s*(\d+)", e)
            if m:
                ctx.weather = "wind"
                ctx.wind_mph = int(m.group(1))
            elif "wind" in e:
                ctx.weather = "wind"
                ctx.wind_mph = 15
            if "rain" in e:
                ctx.weather = "rain"
            if "snow" in e:
                ctx.weather = "snow"
            mm = re.search(r"mismatch[:\s]+(.+)", extras_raw, re.IGNORECASE)
            if mm:
                ctx.mismatch = mm.group(1).strip()

        result = predictor.recommend(ctx, drive_log)
        pretty_print(result, drive_log)

        yards_raw = prompt("Result [yards gained, or skip]", "skip").strip().lower()
        if yards_raw not in ("skip", "s", ""):
            m = re.search(r"-?\d+", yards_raw)
            if m:
                yards = int(m.group())
                play = result["play"]
                family = str(result["play_family"])
                sack = yards <= -4
                sem = assemble_actual_semantics(
                    concept_name=play.get("name", ""),
                    family=family,
                    play=play,
                    yards_gained=yards,
                    target_choice=_CLI_LOG_TARGET_AUTO,
                    outcome_ui=_CLI_LOG_OUTCOME_AUTO,
                    sack_from_chip=sack,
                )
                snap = advance_game_state_after_actual(
                    territory=str(ctx.territory),
                    yardline=int(ctx.yardline),
                    down=int(ctx.down),
                    distance=int(ctx.distance),
                    actual=sem,
                )
                earned_fd = earned_first_down_for_actual_play(sem, sem.yards_gained, ctx.distance) or bool(
                    snap.touchdown
                )
                actual = finalize_actual_after_snap(
                    sem, snap=snap, to_go=int(ctx.distance), earned_first_down=earned_fd
                )
                drive_log.log(actual)
                print(f"  Logged: {actual.description}")

