"""
streamlit_app.py — Football Play Predictor — Streamlit visual interface

Run with:
    streamlit run streamlit_app.py

Install deps:
    pip install -r requirements.txt

The `playcaller` package lives next to this file (directory `playcaller/`, not `playcaller.py`).
Streamlit Cloud and some local runs do not guarantee the repo root on ``sys.path`` before
importing the main script, so we add it explicitly below.
"""

from dataclasses import asdict
import html
import json
from pathlib import Path
import sys
import time
from typing import Optional


def _ensure_repo_root_on_sys_path() -> None:
    """Make `import playcaller` reliable on Streamlit Cloud and odd working directories."""
    root = Path(__file__).resolve().parent
    s = str(root)
    if s not in sys.path:
        sys.path.insert(0, s)


_ensure_repo_root_on_sys_path()

import streamlit as st

from playcaller.live_data import (
    EspnFootballProvider,
    SyncOptions,
    apply_snapshot,
    list_espn_scoreboard_games,
    session_mark_manual,
)
from playcaller import (
    ActualPlayResult,
    DRIVE_END_UI_AUTO,
    DRIVE_END_UI_LABELS,
    DRIVE_END_UI_OPTIONS,
    DriveLogger,
    FootballPlayPredictor,
    Game,
    GameContext,
    advance_game_state_after_actual,
    apply_scoring_after_drive,
    assemble_actual_semantics,
    build_play_art_figure,
    clock_seconds_after_drive_elapsed,
    complete_drive_from_plays,
    earned_first_down_for_actual_play,
    finalize_actual_after_snap,
    format_actual_play_result_description,
    flip_possession_after_drive,
    game_from_dict,
    game_to_json,
    invoke_post_play_hook,
)
from playcaller.game import (
    DRIVE_END_FIELD_GOAL,
    DRIVE_END_FIELD_GOAL_MISS,
    DRIVE_END_PUNT,
    DRIVE_END_TOUCHDOWN,
    DRIVE_END_TURNOVER_FUMBLE,
    DRIVE_END_TURNOVER_INT,
    DRIVE_END_TURNOVER_ON_DOWNS,
)
from playcaller.evaluation import (
    append_open_audit,
    audit_record_from_recommendation,
    evaluate_audit_records,
    link_open_audit_to_actual,
    summarize_audit_session,
    trim_stale_open_audits,
    void_last_closed_audit,
)
from playcaller.situation import yards_from_own_goal, yards_to_opponent_goal_from_abs
from playcaller.streamlit_app_support import (
    LAST_DRIVE_SNAP_CONTEXT,
    PENDING_END_DRIVE_UI,
    PENDING_LOG_SITUATION,
    PENDING_NEW_GAME_UI,
    UNDO_BUNDLE,
    apply_pending_end_drive_ui,
    apply_pending_log_situation,
    apply_pending_new_game_ui,
    clear_in_progress_log_state,
    clear_live_feed_session_keys,
    ensure_play_caller_session_defaults,
    new_game_ui_values,
    possession_side_radio_label,
)
from playcaller.ui_components import (
    FAM_COLOR,
    FAM_LABEL,
    drive_chart,
    drive_momentum_chart,
    fmt_clock,
    render_field,
    run_pass_donut,
    score_chart,
)

st.set_page_config(
    page_title="Play Caller — Sideline OC",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .block-container { padding-top: 1.5rem; }
  .stMetric label { font-size: 0.7rem !important; text-transform: uppercase; letter-spacing: 0.06em; }
  /* Make small secondary buttons feel like "chips" */
  div[data-testid="column"] button { padding-top: 0.35rem; padding-bottom: 0.35rem; }
</style>
""", unsafe_allow_html=True)

# ── Session state ────────────────────────────────────────────────────────────

ensure_play_caller_session_defaults(st.session_state)

LOG_OUTCOME_AUTO = "Auto (from call + yards)"
_LOG_COMPLETE = "Complete pass"
_LOG_RUN = "Run"
_LOG_FG_GOOD = "Field goal good"
_LOG_FG_MISS = "Field goal missed"
LOG_OUTCOME_OPTIONS = [
    LOG_OUTCOME_AUTO,
    "Complete pass",
    "Incomplete pass",
    "QB scramble",
    "Run",
    "Sack",
    "Interception",
    _LOG_FG_GOOD,
    _LOG_FG_MISS,
]
LOG_TARGET_AUTO = "Auto from play"
LOG_TARGET_OPTIONS = [
    LOG_TARGET_AUTO,
    "X",
    "Z",
    "H (slot)",
    "Y (TE)",
    "RB",
    "QB",
]


# Merge pending UI before any ``key="ui_*"`` widgets render (Streamlit forbids mutating widget keys mid-run).
# Order: quick-log advance → end-drive clock/possession → **New game** full reset (last wins on overlap).
apply_pending_log_situation(st.session_state)
apply_pending_end_drive_ui(st.session_state)
apply_pending_new_game_ui(st.session_state)

predictor = st.session_state.predictor
drive_log = st.session_state.drive_log
game = st.session_state.game
# Possession from the sidebar radio (prior run's value). Applied here so **New drive** / captions see it.
game.possession = (
    "offense" if str(st.session_state.get("ui_possession_side", "Our team")) == "Our team" else "defense"
)


def _net_yards_to_endzone(territory: str, yardline: int) -> int:
    """Yards needed for a touchdown from the current spot (offense perspective)."""
    a = yards_from_own_goal(territory, yardline)
    return int(yards_to_opponent_goal_from_abs(a))


def _fmt_local_epoch(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(ts)))


def _archive_current_drive_and_reset_session(*, end_kind_override: Optional[str] = None) -> None:
    """
    Archive the in-progress drive into ``game.drives`` when it has plays, then clear the live log.

    ``end_kind_override``: explicit ``DRIVE_END_*`` kind, or ``None`` / ``DRIVE_END_UI_AUTO`` to use the
    sidebar **How this drive ends** selector (or full auto-inference when that is Auto).
    """
    dl = st.session_state.drive_log
    if dl.results:
        snap_ctx = st.session_state.get(LAST_DRIVE_SNAP_CONTEXT) or {}
        if end_kind_override is not None and str(end_kind_override) != DRIVE_END_UI_AUTO:
            override_kw: dict = {"end_kind_override": str(end_kind_override)}
        else:
            end_mode = str(st.session_state.get("ui_drive_end_on_new", DRIVE_END_UI_AUTO))
            override_kw = (
                {}
                if end_mode == DRIVE_END_UI_AUTO
                else {"end_kind_override": end_mode}
            )
        g = st.session_state.game
        possessing = g.possession
        finished = complete_drive_from_plays(
            list(dl.results),
            last_snap_touchdown=bool(snap_ctx.get("touchdown")),
            last_snap_turnover_on_downs=bool(snap_ctx.get("turnover_on_downs")),
            possessing_team=possessing,
            **override_kw,
        )
        apply_scoring_after_drive(g, finished)
        flip_possession_after_drive(g, finished)
        g.drives.append(finished)
        g.quarter = int(st.session_state.get("ui_quarter", 1))
        clk = int(st.session_state.get("ui_clock_mins", 0)) * 60 + int(
            st.session_state.get("ui_clock_secs", 0)
        )
        new_clk = clock_seconds_after_drive_elapsed(clk, finished)
        g.clock_seconds_remaining = new_clk
        st.session_state[PENDING_END_DRIVE_UI] = {
            "ui_clock_mins": new_clk // 60,
            "ui_clock_secs": new_clk % 60,
            "ui_possession_side": possession_side_radio_label(
                possession=str(g.possession)
            ),
        }
    dl.reset()
    st.session_state.result = None
    st.session_state.last_play_summary = ""
    clear_in_progress_log_state(st.session_state)
    st.session_state.eval_drive_epoch = int(st.session_state.get("eval_drive_epoch", 0)) + 1


def _apply_and_rerun(**kwargs) -> None:
    for k, v in kwargs.items():
        st.session_state[k] = v
    st.rerun()


def _preset_snap_only(
    *,
    territory: str,
    yardline: int,
    down: int,
    distance: int,
    auto_generate: bool = True,
    rerun: bool = False,
) -> None:
    """
    Update **this snap** only (field + down & distance).

    Does not touch ``st.session_state.game``, ``game.drives``, or ``drive_log``.
    """
    st.session_state.ui_territory = territory
    st.session_state.ui_yardline = int(yardline)
    st.session_state.ui_down = int(down)
    st.session_state.ui_distance = int(distance)
    if auto_generate:
        st.session_state.ui_auto_generate = True
    if rerun:
        st.rerun()


def _preset_two_minute_drill(*, auto_generate: bool = True, rerun: bool = False) -> None:
    """
    Quarter / clock / timeouts / mode for a two-minute scenario.

    Does not change field position, score diff, or any ``Game`` / drive history.
    """
    st.session_state.ui_quarter = 4
    st.session_state.ui_clock_total = 70
    st.session_state.ui_clock_mins = 1
    st.session_state.ui_clock_secs = 10
    st.session_state.ui_own_tos = 1
    st.session_state.ui_opp_tos = 3
    st.session_state.ui_game_mode = "two_minute"
    if auto_generate:
        st.session_state.ui_auto_generate = True
    if rerun:
        st.rerun()


def _ordinal_down(n: int) -> str:
    return {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}.get(max(1, min(4, int(n))), f"{int(n)}th")


def _render_previous_drives(game: Game) -> None:
    if not game.drives:
        return
    st.markdown("### Previous drives")
    st.caption("Completed drives this session — summaries like a Gamecast drive list.")
    for dr in reversed(game.drives):
        res = dr.result
        title = res.headline if res else "Drive"
        detail = res.detail_line if res else ""
        with st.expander(f"{title} · {detail}", expanded=False):
            if not dr.plays:
                st.caption("No plays recorded.")
            else:
                for i, p in enumerate(dr.plays, start=1):
                    line = (p.description or "").strip() or format_actual_play_result_description(p)
                    st.markdown(f"{i}. {html.escape(line)}")


def _render_current_series_live(drive_log: DriveLogger) -> None:
    """Always-available view of the active drive (broadcast-style)."""
    n = len(drive_log.results)
    label = f"{n} play(s) on this drive" if n else "No plays logged on this drive yet"
    with st.expander(f"**This drive** — {label}", expanded=bool(n)):
        if not drive_log.results:
            st.caption("Use **Log result (quick)** below after a recommendation. Game history is never cleared except **New game**.")
            return
        tail = drive_log.results[-12:]
        start_i = len(drive_log.results) - len(tail) + 1
        for i, r in enumerate(tail, start=start_i):
            line = (r.description or "").strip() or format_actual_play_result_description(r)
            fc = FAM_COLOR.get(r.family, "#6b7280")
            st.markdown(
                f'<div style="border-left:3px solid {fc};padding:5px 0 5px 10px;margin:5px 0;'
                f'font-size:13px;line-height:1.4;color:#e2e8f0">'
                f'<span style="color:#64748b;font-weight:600;margin-right:6px">{i}.</span>'
                f"{html.escape(line)}</div>",
                unsafe_allow_html=True,
            )
        if len(drive_log.results) > 12:
            st.caption(f"Showing last 12 of {len(drive_log.results)} plays on this series.")


def _safe_summary_html(text: str) -> str:
    """Escape user-facing recap lines for ``unsafe_allow_html`` inserts."""
    return html.escape(str(text), quote=True).replace("\n", "<br/>")


def _undo_last_logged_play() -> None:
    """Restore the situation to the snap before the last logged play and drop that play from the drive log."""
    bundle = st.session_state.get(UNDO_BUNDLE)
    if not bundle:
        st.toast("Nothing to undo on this drive yet.")
        return
    dl = st.session_state.drive_log
    popped = dl.pop_last()
    if popped is None:
        st.session_state.pop(UNDO_BUNDLE, None)
        st.toast("Drive log was already empty.")
        return
    void_last_closed_audit(st.session_state.game.recommendation_audit)
    trim_stale_open_audits(st.session_state.game.recommendation_audit, len(dl.results))
    st.session_state[PENDING_LOG_SITUATION] = {
        "territory": str(bundle["territory"]),
        "yardline": int(bundle["yardline"]),
        "down": int(bundle["down"]),
        "distance": int(bundle["distance"]),
    }
    st.session_state.result = None
    st.session_state.ui_auto_generate = False
    st.session_state.last_play_summary = (
        "Undid last logged play — situation restored to that snap. Tap **Generate** when ready."
    )
    st.session_state.pop(UNDO_BUNDLE, None)
    st.session_state.pop(LAST_DRIVE_SNAP_CONTEXT, None)
    st.toast("Removed last play · restored previous snap")


def _post_log_summary_and_toast(actual: ActualPlayResult, snap) -> tuple[str, list[str]]:
    """
    Build (1) a multi-line recap for ``last_play_summary`` / UI and (2) short
    fragments joined for ``st.toast``. ``snap`` is the **next** snap after the play.
    """
    desc = (actual.description or "").strip() or format_actual_play_result_description(actual)
    pos = "Own" if snap.territory == "own" else "Opp."
    pos_toast = "Opp." if snap.territory == "opponents" else "Own"
    line1 = (
        f"Logged: {desc} — next: {_ordinal_down(snap.down)} & {int(snap.distance)} "
        f"at {pos} {int(snap.yardline)}"
    )
    toast = [
        desc[:72] + ("…" if len(desc) > 72 else ""),
        f"→ {snap.down}&{snap.distance} @ {pos_toast} {snap.yardline}",
    ]
    extras: list[str] = []
    if snap.touchdown:
        extras.append("TD — parked at GL (New drive when ready).")
        toast.append("TD")
    if snap.turnover_on_downs:
        extras.append("Turnover on downs — next 1st at this spot.")
        toast.append("TOD")
    tg = snap.tags
    if tg.first_down_exact:
        extras.append("First down — exact sticks.")
        toast.append("FD — exact sticks")
    if tg.crossed_midfield:
        extras.append("Crossed midfield.")
        toast.append("Crossed 50")
    if tg.explosive_midfield:
        extras.append("Explosive + midfield.")
        toast.append("Explosive + midfield")
    elif tg.explosive_play:
        extras.append("Explosive play.")
        toast.append("Explosive")
    if tg.no_gain:
        extras.append("No gain.")
        toast.append("No gain")
    if tg.negative_play:
        extras.append("Behind LOS.")
        toast.append("Behind LOS")
    summary = line1 if not extras else line1 + "\n" + " ".join(extras)
    return summary, toast


# ── Widget-backed session_state (Streamlit rules) ─────────────────────────────
# Keys used by `st.*(..., key="ui_*")` must not be assigned *after* that widget
# renders on the same run. Queue resets via ``PENDING_*`` (end drive, new game, undo snap)
# and apply at the top of the script. Chip buttons above the expander call `_set` then
# `st.rerun()`, so the expander often does not run on the same pass — OK.
# Wind is special: we also derived `wind_mph` after the sidebar and wrote
# `ui_wind_mph = 0`, which ran after the wind slider — invalid. Fix: sync here
# (before sidebar) + `on_change` on weather when leaving "wind".


def _sync_wind_slider_with_weather_pre_widgets() -> None:
    if str(st.session_state.get("ui_weather", "clear")) != "wind":
        st.session_state.ui_wind_mph = 0


def _on_ui_weather_changed() -> None:
    if str(st.session_state.get("ui_weather", "clear")) != "wind":
        st.session_state.ui_wind_mph = 0


_sync_wind_slider_with_weather_pre_widgets()

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 🏈 Play Caller")
    st.caption("Tap presets → Generate. Fine-tune only when needed.")
    st.caption(
        "**Presets** adjust the **current snap** only (field + down & distance; the 2-min chip also sets clock/mode). "
        "They do **not** clear **completed drives** or engine score — use **New game** for a full reset."
    )
    st.divider()

    st.markdown("#### ⚡ Presets")
    pcols = st.columns(2)
    with pcols[0]:
        if st.button("Own 25 · 1&10", use_container_width=True, key="sidebar_chip_preset_own25_1st10"):
            _preset_snap_only(territory="own", yardline=25, down=1, distance=10, rerun=True)
    with pcols[1]:
        if st.button("Opp 35 · 3&6", use_container_width=True, key="sidebar_chip_preset_opp35_3rd6"):
            _preset_snap_only(territory="opponents", yardline=35, down=3, distance=6, rerun=True)

    pcols2 = st.columns(2)
    with pcols2[0]:
        if st.button("RZ · 2&7", use_container_width=True, key="sidebar_chip_preset_rz_2nd7"):
            _preset_snap_only(territory="opponents", yardline=12, down=2, distance=7, rerun=True)
    with pcols2[1]:
        if st.button("2-min · Q4 1:10", use_container_width=True, key="sidebar_chip_preset_twomin_q4_1_10"):
            _preset_two_minute_drill(rerun=True)

    st.divider()
    st.markdown("#### ⚡ Quick adjust")
    st.caption("Most-used tweaks as one-tap chips.")

    st.markdown("**Down / distance**")
    dcols = st.columns(4)
    with dcols[0]:
        if st.button("1st", use_container_width=True, key="sidebar_chip_down_1"):
            _apply_and_rerun(ui_down=1, ui_auto_generate=True)
    with dcols[1]:
        if st.button("2nd", use_container_width=True, key="sidebar_chip_down_2"):
            _apply_and_rerun(ui_down=2, ui_auto_generate=True)
    with dcols[2]:
        if st.button("3rd", use_container_width=True, key="sidebar_chip_down_3"):
            _apply_and_rerun(ui_down=3, ui_auto_generate=True)
    with dcols[3]:
        if st.button("4th", use_container_width=True, key="sidebar_chip_down_4"):
            _apply_and_rerun(ui_down=4, ui_auto_generate=True)

    dist_cols = st.columns(5)
    for i, dist in enumerate([1, 3, 5, 7, 10]):
        with dist_cols[i]:
            if st.button(f"{dist}", use_container_width=True, key=f"sidebar_chip_to_go_{dist}"):
                _apply_and_rerun(ui_distance=dist, ui_auto_generate=True)

    st.markdown("**Territory / yardline**")
    tcols = st.columns(2)
    with tcols[0]:
        if st.button("Own", use_container_width=True, key="sidebar_chip_territory_own"):
            _apply_and_rerun(ui_territory="own", ui_auto_generate=True)
    with tcols[1]:
        if st.button("Opp", use_container_width=True, key="sidebar_chip_territory_opp"):
            _apply_and_rerun(ui_territory="opponents", ui_auto_generate=True)

    ycols = st.columns(5)
    yard_presets = [10, 25, 35, 40, 45]
    for i, y in enumerate(yard_presets):
        with ycols[i]:
            if st.button(f"{y}", use_container_width=True, key=f"sidebar_chip_yardline_{y}"):
                _apply_and_rerun(ui_yardline=y, ui_auto_generate=True)

    st.markdown("**Clock**")
    ccols = st.columns(4)
    with ccols[0]:
        if st.button("15:00", use_container_width=True, key="sidebar_chip_clock_15m00s"):
            _apply_and_rerun(
                ui_clock_total=15 * 60, ui_clock_mins=15, ui_clock_secs=0, ui_auto_generate=True
            )
    with ccols[1]:
        if st.button("10:00", use_container_width=True, key="sidebar_chip_clock_10m00s"):
            _apply_and_rerun(
                ui_clock_total=10 * 60, ui_clock_mins=10, ui_clock_secs=0, ui_auto_generate=True
            )
    with ccols[2]:
        if st.button("5:00", use_container_width=True, key="sidebar_chip_clock_5m00s"):
            _apply_and_rerun(
                ui_clock_total=5 * 60, ui_clock_mins=5, ui_clock_secs=0, ui_auto_generate=True
            )
    with ccols[3]:
        if st.button("1:10", use_container_width=True, key="sidebar_chip_clock_1m10s"):
            _apply_and_rerun(ui_clock_total=70, ui_clock_mins=1, ui_clock_secs=10, ui_auto_generate=True)

    st.markdown("**Possession**")
    st.caption("Who has the ball for **this** drive (updates when you end a drive or use **New game**).")
    st.radio(
        "Offense",
        ["Our team", "Opponent"],
        horizontal=True,
        key="ui_possession_side",
        label_visibility="collapsed",
    )
    st.caption(
        f"Logged scoreboard: **{game.offense_points}–{game.defense_points}** "
        "(TD +6 / FG good +3; missed FG adds no points)."
    )

    st.markdown("**Defense shell (fast)**")
    fcols = st.columns(2)
    with fcols[0]:
        if st.button("Nickel · 7 · C3", use_container_width=True, key="sidebar_chip_def_nickel_7_c3"):
            _apply_and_rerun(
                ui_def_personnel="nickel",
                ui_box_count=7,
                ui_coverage_shell="cover_3",
                ui_safeties="single_high",
                ui_blitz_likely=False,
                ui_auto_generate=True,
            )
    with fcols[1]:
        if st.button("Dime · 6 · Qtrs", use_container_width=True, key="sidebar_chip_def_dime_6_qtrs"):
            _apply_and_rerun(
                ui_def_personnel="dime",
                ui_box_count=6,
                ui_coverage_shell="quarters",
                ui_safeties="two_high",
                ui_blitz_likely=False,
                ui_auto_generate=True,
            )

    fcols2 = st.columns(2)
    with fcols2[0]:
        if st.button("GL · 9 · C0", use_container_width=True, key="sidebar_chip_def_gl_9_c0"):
            _apply_and_rerun(
                ui_def_personnel="goal_line",
                ui_box_count=9,
                ui_coverage_shell="cover_0",
                ui_safeties="single_high",
                ui_blitz_likely=True,
                ui_auto_generate=True,
            )
    with fcols2[1]:
        if st.button("Clear defense read", use_container_width=True, key="sidebar_chip_def_clear_read"):
            _apply_and_rerun(
                ui_def_personnel="unknown",
                ui_box_count=7,
                ui_coverage_shell="unknown",
                ui_safeties="unknown",
                ui_blitz_likely=False,
                ui_auto_generate=True,
            )

    st.divider()

    with st.expander("Fine tune (optional)", expanded=False):
        st.markdown("#### Down & Distance")
        c1, c2 = st.columns(2)
        c1.selectbox("Down", [1, 2, 3, 4], key="ui_down")
        c2.selectbox(
            "Distance",
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 20],
            key="ui_distance",
        )

        st.markdown("#### Field Position")
        st.radio(
            "Territory",
            ["own", "opponents"],
            horizontal=True,
            format_func=lambda x: "Own" if x == "own" else "Opp.",
            key="ui_territory",
        )
        st.slider("Yardline", 1, 50, key="ui_yardline")

        st.markdown("#### Defensive Read")
        st.selectbox(
            "Personnel",
            ["unknown", "nickel", "base", "dime", "goal_line"],
            format_func=lambda x: x.replace("_", " ").title(),
            key="ui_def_personnel",
        )
        st.slider("Box count", 4, 9, key="ui_box_count", format="%d in box")
        st.selectbox(
            "Coverage",
            ["unknown", "cover_0", "cover_1", "cover_2", "cover_3", "cover_4", "quarters"],
            format_func=lambda x: x.replace("_", " ").upper() if x != "unknown" else "Unknown",
            key="ui_coverage_shell",
        )
        st.selectbox(
            "Safeties",
            ["unknown", "single_high", "two_high"],
            format_func=lambda x: x.replace("_", " ").title(),
            key="ui_safeties",
        )
        st.toggle("Blitz expected", key="ui_blitz_likely")

        st.markdown("#### Game Script")
        c3, c4 = st.columns(2)
        c3.selectbox("Quarter", [1, 2, 3, 4], key="ui_quarter")
        c4.caption(
            f"Board **{game.offense_points}–{game.defense_points}** from completed drives "
            "(feeds play-calling context)."
        )

        st.slider("Minutes remaining", 0, 60, key="ui_clock_mins")
        st.slider("+ seconds", 0, 59, key="ui_clock_secs")

        c5, c6 = st.columns(2)
        c5.selectbox("Own TOs", [0, 1, 2, 3], key="ui_own_tos")
        c6.selectbox("Opp TOs", [0, 1, 2, 3], key="ui_opp_tos")

        st.markdown("#### Extras")
        st.selectbox(
            "Weather",
            ["clear", "wind", "rain", "snow"],
            key="ui_weather",
            on_change=_on_ui_weather_changed,
        )
        st.slider("Wind (mph)", 0, 40, key="ui_wind_mph")
        st.toggle("QB limited", key="ui_qb_limited")
        st.selectbox(
            "Override mode",
            ["normal", "must_score", "drain_clock", "two_minute", "two_point"],
            format_func=lambda x: x.replace("_", " ").title(),
            key="ui_game_mode",
        )
        st.text_input("Mismatch note", placeholder="Optional…", key="ui_mismatch")

    st.divider()

    st.markdown("#### Drive & session (live)")
    st.caption(
        "**End drive** archives plays to game history, flips possession when appropriate, burns clock, "
        "then starts a fresh series — same as broadcast “next possession.”"
    )
    if st.button(
        "End drive & next series",
        type="primary",
        use_container_width=True,
        key="sidebar_btn_end_drive_next",
    ):
        _archive_current_drive_and_reset_session()
        st.rerun()

    st.caption("**One-tap end** (overrides the dropdown for that archive only):")
    er1, er2, er3 = st.columns(3)
    with er1:
        if st.button("End · Auto", use_container_width=True, key="sidebar_quick_end_auto"):
            _archive_current_drive_and_reset_session(end_kind_override=DRIVE_END_UI_AUTO)
            st.rerun()
        if st.button("End · Punt", use_container_width=True, key="sidebar_quick_end_punt"):
            _archive_current_drive_and_reset_session(end_kind_override=DRIVE_END_PUNT)
            st.rerun()
        if st.button("End · TD", use_container_width=True, key="sidebar_quick_end_td"):
            _archive_current_drive_and_reset_session(end_kind_override=DRIVE_END_TOUCHDOWN)
            st.rerun()
    with er2:
        if st.button("End · FG", use_container_width=True, key="sidebar_quick_end_fg"):
            _archive_current_drive_and_reset_session(end_kind_override=DRIVE_END_FIELD_GOAL)
            st.rerun()
        if st.button("End · FG miss", use_container_width=True, key="sidebar_quick_end_fg_miss"):
            _archive_current_drive_and_reset_session(end_kind_override=DRIVE_END_FIELD_GOAL_MISS)
            st.rerun()
        if st.button("End · INT", use_container_width=True, key="sidebar_quick_end_int"):
            _archive_current_drive_and_reset_session(end_kind_override=DRIVE_END_TURNOVER_INT)
            st.rerun()
    with er3:
        if st.button("End · Fum", use_container_width=True, key="sidebar_quick_end_fum"):
            _archive_current_drive_and_reset_session(end_kind_override=DRIVE_END_TURNOVER_FUMBLE)
            st.rerun()
        if st.button("End · TOD", use_container_width=True, key="sidebar_quick_end_tod"):
            _archive_current_drive_and_reset_session(end_kind_override=DRIVE_END_TURNOVER_ON_DOWNS)
            st.rerun()

    st.selectbox(
        "When you use **End drive & next** (not the one-tap row):",
        options=list(DRIVE_END_UI_OPTIONS),
        format_func=lambda k: DRIVE_END_UI_LABELS.get(str(k), str(k)),
        key="ui_drive_end_on_new",
        help=(
            "**Auto** uses TDs, turnovers, turnover on downs (from last snap), and field goals when obvious; "
            "otherwise it labels the drive as a punt."
        ),
    )
    snap_hint = (
        f"**{len(drive_log.results)}** play(s) on this drive — end the drive when the series is over."
        if drive_log.results
        else "No plays on this drive yet — **End drive** only clears the call sheet."
    )
    st.caption(snap_hint)

    j_blob = game_to_json(game)
    st.download_button(
        label="Download game JSON",
        data=j_blob,
        file_name=f"playcaller_game_{game.game_id}.json",
        mime="application/json",
        use_container_width=True,
        key="sidebar_download_game_json",
    )
    st.toggle(
        "Show game-context debug",
        key="ui_debug_game_context",
        help="When on, surfaces tendencies and history fed into recommendations (model meta).",
    )
    st.toggle(
        "Record recommendation audit",
        key="ui_eval_audit_enabled",
        help="Store each **Generate** (+ link on **Log result**) for metrics, JSON export, and the Review session page.",
    )
    up = st.file_uploader(
        "Load game JSON",
        type=["json"],
        key="sidebar_game_json_upload",
        help="Replaces the scoreboard and completed drives. The in-progress drive log is cleared.",
    )
    if st.button(
        "Load uploaded game",
        use_container_width=True,
        key="sidebar_btn_load_game_json",
        disabled=up is None,
    ):
        if up is not None:
            try:
                raw = up.getvalue().decode("utf-8")
            except UnicodeDecodeError:
                st.error("That file is not valid UTF-8 text.")
            else:
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError as e:
                    st.error(f"Invalid JSON (parse error): {e}")
                else:
                    if not isinstance(payload, dict):
                        st.error("JSON root must be an object (e.g. { \"game_id\": ... }).")
                    else:
                        try:
                            st.session_state.game = game_from_dict(payload)
                        except (TypeError, ValueError, KeyError) as e:
                            st.error(f"JSON shape not compatible with a saved game: {e}")
                        except Exception as e:
                            st.error(f"Could not restore game: {e}")
                        else:
                            g0 = st.session_state.game
                            st.session_state[PENDING_END_DRIVE_UI] = {
                                "ui_possession_side": possession_side_radio_label(
                                    possession=str(g0.possession)
                                ),
                            }
                            drive_log.reset()
                            st.session_state.result = None
                            st.session_state.last_play_summary = ""
                            clear_in_progress_log_state(st.session_state)
                            clear_live_feed_session_keys(st.session_state)
                            aud = getattr(g0, "recommendation_audit", None) or []
                            mx = max((int(r.get("drive_epoch", 0)) for r in aud), default=-1)
                            st.session_state.eval_drive_epoch = mx + 1
                            st.toast("Loaded game from JSON.")
                            st.rerun()

    with st.expander("Live game data (ESPN)", expanded=False):
        st.caption(
            "Uses ESPN’s public **Site API** (not affiliated). Updates **clock, score, possession, field, down & distance** "
            "into the same widgets the OC already uses. **Completed drives** and **Log result** are unchanged unless you enable "
            "experimental feed play append. Use **locks** when the feed is late or wrong."
        )
        st.selectbox(
            "Sport",
            ["nfl", "college-football", "ufl"],
            format_func=lambda s: (
                "NFL"
                if s == "nfl"
                else "College football"
                if s == "college-football"
                else "UFL"
            ),
            key="ui_live_espn_sport",
        )
        if st.button("Refresh scoreboard", use_container_width=True, key="sidebar_live_refresh_board"):
            try:
                sport = str(st.session_state.ui_live_espn_sport)
                rows = list_espn_scoreboard_games(sport, limit=40)  # type: ignore[arg-type]
                st.session_state.live_feed_scoreboard_rows = rows
                st.toast(f"{len(rows)} games loaded.")
            except Exception as e:
                st.session_state.live_feed_last_error = str(e)
                st.error(str(e))
        rows = st.session_state.live_feed_scoreboard_rows or []
        event_id = ""
        our_tid = ""
        if rows:
            ids = [r["id"] for r in rows]
            labels = [
                f"{r.get('away_abbr', '?')} @ {r.get('home_abbr', '?')} — {str(r.get('detail', ''))[:36]}"
                for r in rows
            ]
            st.selectbox(
                "Game",
                ids,
                format_func=lambda x: labels[ids.index(x)],
                key="ui_live_pick_event_id",
            )
            pick_id = str(st.session_state.get("ui_live_pick_event_id") or ids[0])
            picked = next(r for r in rows if r["id"] == pick_id)
            event_id = pick_id
            st.radio(
                "Our sideline team",
                ["away", "home"],
                format_func=lambda x: (
                    f"{picked.get('away_abbr', 'Away')} (away)"
                    if x == "away"
                    else f"{picked.get('home_abbr', 'Home')} (home)"
                ),
                horizontal=True,
                key="ui_live_home_or_away",
            )
            ho = str(st.session_state.get("ui_live_home_or_away") or "away")
            our_tid = str(picked["away_id"] if ho == "away" else picked["home_id"])
        else:
            st.text_input(
                "Event ID (ESPN game URL)",
                key="ui_live_event_id_manual",
                help="Digits from the game URL, e.g. gameId/401772988",
            )
            st.text_input(
                "Our team ESPN ID",
                key="ui_live_our_team_manual",
                help="Numeric team id (same as in team URLs).",
            )
            event_id = str(st.session_state.get("ui_live_event_id_manual") or "").strip()
            our_tid = str(st.session_state.get("ui_live_our_team_manual") or "").strip()
        st.toggle("Lock situation vs feed", key="ui_live_lock_situation")
        st.toggle("Lock score & timeouts vs feed", key="ui_live_lock_score")
        st.toggle(
            "Append new feed plays to drive log (deduped)",
            key="ui_live_auto_plays",
            help="Off by default. Turn on only if you are not using **Log result** for the same plays.",
        )
        c_sync, c_man = st.columns(2)
        with c_sync:
            do_sync = st.button("Sync from ESPN", use_container_width=True, type="primary", key="sidebar_live_sync")
        with c_man:
            if st.button("Mark manual", use_container_width=True, key="sidebar_live_mark_manual"):
                session_mark_manual(st.session_state)
                st.rerun()
        if do_sync:
            if not event_id or not our_tid:
                st.session_state.live_feed_last_error = "Need Event ID and our team ID (pick a game or fill manual fields)."
                st.error(st.session_state.live_feed_last_error)
            else:
                sport = str(st.session_state.ui_live_espn_sport)
                prov = EspnFootballProvider(sport)  # type: ignore[arg-type]
                fr = prov.fetch_snapshot(event_id, our_team_id=our_tid)
                if not fr.ok or fr.snapshot is None:
                    st.session_state.live_feed_last_error = fr.error or "Fetch failed."
                    st.error(st.session_state.live_feed_last_error)
                else:
                    st.session_state.live_feed_last_error = None
                    opts = SyncOptions(
                        lock_situation=bool(st.session_state.ui_live_lock_situation),
                        lock_score=bool(st.session_state.ui_live_lock_score),
                        auto_append_feed_plays=bool(st.session_state.ui_live_auto_plays),
                    )
                    res = apply_snapshot(
                        game=game,
                        session=st.session_state,
                        drive_log=drive_log,
                        snapshot=fr.snapshot,
                        options=opts,
                    )
                    st.toast(res.message + (f" · +{res.plays_appended} feed plays" if res.plays_appended else ""))
                    st.rerun()
        err = st.session_state.get("live_feed_last_error")
        if err:
            st.warning(str(err))
        ts = st.session_state.get("live_feed_last_sync_epoch")
        if ts:
            st.caption(f"Last successful sync: **{_fmt_local_epoch(float(ts))}** · origin **{st.session_state.get('live_feed_last_origin', '—')}**")
        aud = st.session_state.get("live_feed_last_audit")
        if aud:
            with st.expander("Last sync detail", expanded=False):
                st.json(aud)

    # Avoid unnecessary full-app reruns while adjusting many inputs quickly.
    # The form batches widget changes and only triggers on submit.
    with st.form("generate_form", clear_on_submit=False):
        generate = st.form_submit_button(
            "Generate play call",
            type="primary",
            use_container_width=True,
            key="sidebar_form_submit_generate",
        )

    if st.button("New game", use_container_width=True, key="sidebar_btn_new_game"):
        st.session_state.pop(PENDING_END_DRIVE_UI, None)
        st.session_state.pop(PENDING_LOG_SITUATION, None)
        st.session_state.pop(PENDING_NEW_GAME_UI, None)
        st.session_state.game = Game.new_game()
        drive_log.reset()
        st.session_state[PENDING_NEW_GAME_UI] = new_game_ui_values()
        st.session_state.result = None
        st.session_state.last_play_summary = ""
        st.session_state.eval_drive_epoch = 0
        clear_in_progress_log_state(st.session_state)
        clear_live_feed_session_keys(st.session_state)
        st.rerun()

# Pull the latest UI state (fast path uses session_state; fine tune updates it too).
down = int(st.session_state.ui_down)
distance = int(st.session_state.ui_distance)
territory = str(st.session_state.ui_territory)
yardline = int(st.session_state.ui_yardline)
def_personnel = str(st.session_state.ui_def_personnel)
box_count = int(st.session_state.ui_box_count)
coverage_shell = str(st.session_state.ui_coverage_shell)
safeties = str(st.session_state.ui_safeties)
blitz_likely = bool(st.session_state.ui_blitz_likely)
quarter = int(st.session_state.ui_quarter)
_m = max(0, min(60, int(st.session_state.ui_clock_mins)))
_s = max(0, min(59, int(st.session_state.ui_clock_secs)))
seconds_remaining = max(0, min(24 * 3600, _m * 60 + _s))
st.session_state.ui_clock_total = int(seconds_remaining)
score_diff = int(game.offense_points) - int(game.defense_points)
game.quarter = quarter
game.clock_seconds_remaining = seconds_remaining
own_timeouts = int(st.session_state.ui_own_tos)
opp_timeouts = int(st.session_state.ui_opp_tos)
weather = str(st.session_state.ui_weather)
wind_mph = int(st.session_state.ui_wind_mph) if weather == "wind" else 0
qb_limited = bool(st.session_state.ui_qb_limited)
game_mode = str(st.session_state.ui_game_mode)
mismatch = str(st.session_state.ui_mismatch)

# ── Build context and generate ────────────────────────────────────────────────

ctx = GameContext(
    down=down, distance=distance, yardline=yardline, territory=territory,
    def_personnel=def_personnel, box_count=box_count, coverage_shell=coverage_shell,
    blitz_likely=blitz_likely, safeties=safeties,
    score_diff=score_diff, quarter=quarter, seconds_remaining=seconds_remaining,
    own_timeouts=own_timeouts, opp_timeouts=opp_timeouts,
    weather=weather, wind_mph=wind_mph, qb_limited=qb_limited,
    mismatch=mismatch or None, game_mode=game_mode,
    plays_this_drive=len(drive_log.results),
    shown_concepts=list(drive_log.family_counts.keys()),
    run_plays_this_drive=drive_log.run_count(),
)

# ── Main page ─────────────────────────────────────────────────────────────────
# Recommendations run after the live-ops bar so **Generate** here works on the same run as the sidebar form.

st.markdown("## Play Caller — Sideline OC")
st.caption("**Live entry mode** — quick log rows below; full forms stay in sidebars / expanders.")

st.markdown("##### Live console")
op1, op2, op3 = st.columns([2, 1, 1])
with op1:
    main_generate = st.button(
        "Generate play call",
        type="primary",
        use_container_width=True,
        help="Same as the sidebar — use whichever is closer on broadcast.",
        key="main_console_generate",
    )
with op2:
    can_undo = bool(drive_log.results) and st.session_state.get(UNDO_BUNDLE) is not None
    undo_clicked = st.button(
        "Undo last play",
        use_container_width=True,
        disabled=not can_undo,
        help="Restores down/distance/field to the snap before the last quick-log (one step).",
        key="main_console_undo",
    )
with op3:
    st.caption(f"**Drive:** {len(drive_log.results)} logged")

if undo_clicked:
    _undo_last_logged_play()
    st.rerun()

_should_recommend = (
    bool(generate) or bool(main_generate) or bool(st.session_state.ui_auto_generate)
)
if _should_recommend:
    try:
        st.session_state.result = predictor.recommend(ctx, drive_log, game)
    except Exception as e:
        st.session_state.result = None
        st.error(f"Could not generate a play call: {e}")
    st.session_state.ui_auto_generate = False
    if (
        st.session_state.result is not None
        and st.session_state.get("ui_eval_audit_enabled", True)
    ):
        append_open_audit(
            game.recommendation_audit,
            audit_record_from_recommendation(
                result=st.session_state.result,
                plays_at_recommend=len(drive_log.results),
                drive_epoch=int(st.session_state.get("eval_drive_epoch", 0)),
                game_id=game.game_id,
            ),
        )

result = st.session_state.result

MODE_BANNERS = {
    "two_minute":  ("\U0001f6a8 Two-Minute Drill",     "#ef4444"),
    "must_score":  ("\U0001f6a8 Must Score",            "#ef4444"),
    "drain_clock": ("\U000023f1 Drain the Clock",       "#22c55e"),
    "two_point":   ("\U0001f3af Two-Point Conversion",  "#f59e0b"),
}
eff_mode = result["ctx"].game_mode if result else predictor.derive_game_mode(ctx)
if eff_mode in MODE_BANNERS:
    bt, bc = MODE_BANNERS[eff_mode]
    st.markdown(f'<div style="background:{bc}18;border:1px solid {bc}44;border-radius:6px;padding:8px 14px;margin-bottom:12px;color:{bc};font-weight:600;font-size:16px">{bt}</div>', unsafe_allow_html=True)

if quarter >= 4 and seconds_remaining <= 120 and seconds_remaining > 0:
    st.markdown(
        '<div style="background:#f59e0b18;border:1px solid #f59e0b55;border-radius:6px;padding:8px 12px;'
        'margin-bottom:10px;color:#fbbf24;font-weight:600;font-size:14px">'
        "Late game: clock inside two minutes. Confirm time matches the broadcast.</div>",
        unsafe_allow_html=True,
    )

# Broadcast HUD (always-visible game state)
sc_lbl = f"{game.offense_points}–{game.defense_points}"
margin = int(game.offense_points) - int(game.defense_points)
margin_lbl = f"+{margin}" if margin > 0 else str(margin)
pos_lbl = "Our ball" if game.possession == "offense" else "Opponent ball"
terr_short = "Opp." if territory == "opponents" else "Own"
ytg_hud = _net_yards_to_endzone(territory, yardline)
def_lbl = def_personnel.replace("_", " ").title() if def_personnel != "unknown" else "Def ?"
cov_hud = coverage_shell.replace("_", " ").upper() if coverage_shell != "unknown" else "Cov ?"
saf_hud = safeties.replace("_", " ").title() if safeties != "unknown" else "S ?"
blitz_chip = " · BLITZ" if blitz_likely else ""
def_strip = html.escape(f"{def_lbl} · {box_count} box · {cov_hud} · {saf_hud}{blitz_chip}", quote=True)
st.markdown(
    f'<div style="background:linear-gradient(180deg,#0c1222 0%,#0f172a 100%);border:1px solid #334155;'
    f'border-radius:10px;padding:14px 18px;margin-bottom:6px">'
    f'<div style="font-size:1.5rem;font-weight:800;color:#f8fafc;letter-spacing:-0.02em">'
    f'{down}&{distance} <span style="color:#64748b;font-weight:500">·</span> {terr_short} {yardline}</div>'
    f'<div style="margin-top:6px;font-size:0.92rem;color:#cbd5e1">'
    f'<strong style="color:#94a3b8">To goal</strong> {ytg_hud} yds'
    f' &nbsp;·&nbsp; <strong style="color:#94a3b8">Defense</strong> {def_strip}</div>'
    f'<div style="margin-top:8px;font-size:0.95rem;color:#94a3b8;line-height:1.5">'
    f'<strong style="color:#e2e8f0">Score</strong> {sc_lbl} '
    f'<span style="color:#475569">(margin {margin_lbl})</span>'
    f' &nbsp;·&nbsp; <strong style="color:#e2e8f0">Clock</strong> Q{quarter} {fmt_clock(seconds_remaining)}'
    f' &nbsp;·&nbsp; <strong style="color:#e2e8f0">{html.escape(pos_lbl)}</strong>'
    f' &nbsp;·&nbsp; <strong style="color:#e2e8f0">TOs</strong> {own_timeouts}–{opp_timeouts}'
    f' &nbsp;·&nbsp; <strong style="color:#e2e8f0">This drive</strong> {len(drive_log.results)} play(s)'
    f'</div>'
    f'<div style="margin-top:6px;font-size:0.78rem;color:#64748b">Session {html.escape(str(game.game_id))}</div></div>',
    unsafe_allow_html=True,
)
if st.session_state.get("last_play_summary"):
    st.markdown(
        '<p style="font-size:0.88rem;color:#94a3b8;margin:0.35rem 0 0 0;line-height:1.35">'
        + _safe_summary_html(str(st.session_state.last_play_summary))
        + "</p>",
        unsafe_allow_html=True,
    )
lf_ts = st.session_state.get("live_feed_last_sync_epoch")
lf_org = str(st.session_state.get("live_feed_last_origin") or "")
if lf_ts and lf_org == "feed":
    st.caption(
        f"**Live data:** ESPN sync at {_fmt_local_epoch(float(lf_ts))} — situation locks in the sidebar are respected."
    )
elif lf_org == "manual":
    st.caption("**Live data:** Operating as **manual** (or after **Mark manual**). Use **Sync from ESPN** to pull the broadcast again.")
st.caption(
    "**Live ops:** End the possession from the sidebar **End drive & next series** (or one-tap **End ·** buttons) — "
    "scoreboard & prior drives stay intact."
)
st.divider()

with st.expander("Session evaluation (quick)", expanded=False):
    st.caption(
        "Turn on **Record recommendation audit** in the sidebar. Use the **Review session** page for snap-by-snap replay."
    )
    _aud = game.recommendation_audit
    if not _aud:
        st.info("No audit rows yet. Generate calls and log results to measure family match, diversity, and weak spots.")
    else:
        st.text(summarize_audit_session(_aud))
        with st.expander("Full metrics (JSON)", expanded=False):
            st.json(evaluate_audit_records(_aud))

_render_current_series_live(drive_log)
_render_previous_drives(game)

left, right = st.columns([1,1], gap="large")

with left:
    st.markdown("**Field position**")
    display_ctx = result["ctx"] if result else ctx
    st.markdown(render_field(display_ctx), unsafe_allow_html=True)
    if result:
        bkt = result["bucket"].replace("_"," ").title()
        cov = result["ctx"].coverage_shell.replace("_"," ").upper() if result["ctx"].coverage_shell!="unknown" else "Coverage unknown"
        blz = " · Blitz expected" if result["ctx"].blitz_likely else ""
        st.caption(f"Bucket: {bkt}  ·  {cov}{blz}")
        if result["bucket"] == "red_zone" and result["ctx"].territory == "opponents" and result["ctx"].yardline <= 20:
            rz = result["ctx"]
            if rz.distance <= 3:
                rz_note = "Short edges → quicker throws / condensed run answers."
            elif rz.distance >= 8:
                rz_note = "Long RZ → screens + outlets to stay ahead of sticks."
            elif rz.yardline <= 5:
                rz_note = "Goal-line-ish → heavier condensed run profile."
            else:
                rz_note = "RZ spacing → slight lean to PA + quick game."
            st.caption(f"Red-zone shift: {rz_note}")

    # 4th down
    if result and result.get("fourth_down"):
        fd = result["fourth_down"]
        fd_clrs = {"GO FOR IT":"#22c55e","FIELD GOAL":"#3b82f6","PUNT":"#9ca3af"}
        fc = fd_clrs.get(fd.get("recommendation","PUNT"),"#9ca3af")
        fgd = f"  <span style='font-size:12px;color:#9ca3af'>(~{fd['fg_distance']} yds)</span>" if fd.get("fg_distance") else ""
        st.markdown(
            f'<div style="margin-top:12px;padding:10px 14px;border-radius:6px;background:{fc}10;border:1px solid {fc}33">'
            f'<div style="color:{fc};font-size:16px;font-weight:600">4th down: {fd.get("recommendation","")}{fgd}</div>'
            f'<div style="color:#9ca3af;font-size:13px;margin-top:3px">{fd.get("reasoning","")}</div></div>',
            unsafe_allow_html=True)

    # Score chart
    if result and result.get("scores"):
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("**Family scores**")
        st.plotly_chart(score_chart(result["scores"]), use_container_width=True, config={"displayModeBar":False})

    if st.session_state.get("ui_debug_game_context") and result and result.get("model_input"):
        mi = result["model_input"]
        gcf = mi.meta.get("game_context_features") if hasattr(mi, "meta") else None
        if gcf:
            with st.expander("Game-context features (debug)", expanded=False):
                top = gcf.get("target_role_top") or []
                top_s = ", ".join(f"{r}: {p:.0%}" for r, p in top[:3]) if top else "—"
                st.caption(
                    f"Last archived drive: **{gcf.get('last_archived_drive_result_kind') or '—'}** · "
                    f"Plays in sample: **{gcf.get('sample_size_plays', 0)}** · "
                    f"Top roles: {top_s}"
                )
                st.json(gcf)

with right:
    if not result:
        if st.session_state.get("last_play_summary"):
            st.markdown(
                '<div style="border-left:3px solid #22c55e;background:rgba(34,197,94,0.08);'
                'padding:10px 14px;border-radius:0 6px 6px 0;margin-bottom:10px">'
                '<div style="color:#86efac;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px">'
                "Last logged play</div>"
                '<div style="color:#e2e8f0;font-size:14px;line-height:1.45">'
                + _safe_summary_html(str(st.session_state.last_play_summary))
                + "</div></div>",
                unsafe_allow_html=True,
            )
            st.caption(
                "**Situation** and **Position** in the row above match the next snap. "
                "Tap **Generate play call** when you want the next recommendation."
            )
        else:
            st.info("Use the sidebar **presets / quick adjust** chips, then tap **Generate play call**.")
    else:
        play   = result["play"]
        family = result["play_family"]
        fctx   = result["ctx"]
        fc     = FAM_COLOR.get(family,"#6b7280")

        # Header
        td_badge = f"  ·  TD {round(play['td_pct']*100)}%" if "td_pct" in play else ""
        conf = result.get("model", {}).get("confidence")
        if conf is None and result.get("model_output") is not None:
            conf = getattr(result["model_output"], "confidence", None)
        conf_badge = ""
        if isinstance(conf, (int, float)):
            pct = int(round(float(conf) * 100))
            conf_badge = f"  ·  Conf {pct}%"
        st.markdown(
            f'<div style="background:{fc}12;border:1px solid {fc}33;border-radius:6px;padding:12px 16px;margin-bottom:12px">'
            f'<div style="font-size:22px;font-weight:700;color:#f0f4f8">{play.get("name","")}</div>'
            f'<div style="font-size:11px;color:{fc};text-transform:uppercase;letter-spacing:0.1em;margin-top:2px">'
            f'{FAM_LABEL.get(family,family)}{td_badge}{conf_badge}</div></div>',
            unsafe_allow_html=True)

        # Situation strip (read at a glance)
        terr_lbl = "Opp." if fctx.territory == "opponents" else "Own"
        cov_lbl = fctx.coverage_shell.replace("_", " ").upper() if fctx.coverage_shell != "unknown" else "Cov ?"
        st.caption(
            f"{fctx.down}&{fctx.distance} · {terr_lbl} {fctx.yardline} · Q{fctx.quarter} {fmt_clock(fctx.seconds_remaining)} · "
            f"{cov_lbl} · {fctx.box_count} box"
            + (" · BLITZ" if fctx.blitz_likely else "")
        )

        # Pre-snap projection + diagram (collapsed by default for live entry — not logged).
        pred = result.get("predicted_play_result") or {}
        with st.expander("Model projection & play diagram (optional)", expanded=False):
            if pred.get("headline") or pred.get("description"):
                st.markdown("**Projected outcome (pre-snap)**")
                st.caption("Model guess only — **Log result (quick)** below records actual yards.")
                lead = pred.get("headline") or pred.get("description", "")
                st.markdown(
                    f'<div style="border:1px solid #334155;border-radius:8px;padding:12px 14px;'
                    f'background:linear-gradient(180deg,#1e293b 0%,#0f172a 100%);margin-bottom:10px">'
                    f'<div style="font-size:1.08rem;color:#f8fafc;line-height:1.45;font-weight:600">{lead}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                pm1, pm2, pm3, pm4, pm5 = st.columns(5)
                _py = pred.get("yards")
                pm1.metric("Proj. type", str(pred.get("play_type", "—")).replace("_", " ").title())
                pm2.metric("Proj. target", pred.get("target_player_or_role") or "—")
                _route_show = (pred.get("route") or "—")[:22]
                pm3.metric("Proj. route", _route_show + ("…" if pred.get("route") and len(pred["route"]) > 22 else ""))
                pm4.metric("Proj. yards", "—" if _py is None else str(int(_py)))
                _flags: list[str] = []
                if pred.get("success"):
                    _flags.append("Sticks")
                if pred.get("explosive"):
                    _flags.append("Explosive")
                pm5.metric("Proj. flags", " · ".join(_flags) if _flags else "—")
            else:
                st.caption("No projection headline for this call.")

            try:
                pri = pred.get("target_position") if pred else None
                _hint = pred.get("result_type") if pred else None
                fig = build_play_art_figure(
                    play,
                    family,
                    str(pri) if pri else None,
                    result_type_hint=str(_hint) if _hint else None,
                )
                if fig is not None:
                    st.markdown("**Play art**")
                    st.caption(
                        "Compact LOS · gold = primary · gray = secondary · dashed = PA sell (when applicable)."
                    )
                    st.pyplot(fig, clear_figure=True)
            except Exception:
                pass

        with st.expander("Install / mechanics (formation, protection, routes)", expanded=False):
            fi = st.columns(3)
            if play.get("formation"):
                fi[0].caption("Formation")
                fi[0].markdown(f"`{play['formation']}`")
            if play.get("protection") or play.get("blocking"):
                fi[1].caption("Protection / Blocking")
                fi[1].markdown(f"`{play.get('protection') or play.get('blocking')}`")
            if play.get("run_scheme"):
                fi[2].caption("Scheme")
                fi[2].markdown(f"`{play['run_scheme']}`")

            if play.get("routes"):
                st.markdown("**Routes**")
                ritems = list(play["routes"].items())
                rc1, rc2 = st.columns(2)
                for i, (pos, route) in enumerate(ritems):
                    (rc1 if i < (len(ritems) + 1) // 2 else rc2).markdown(f"**`{pos}`** {route}")

        # Why
        st.markdown(
            f'<div style="border-left:2px solid {fc};background:rgba(255,255,255,0.025);padding:6px 10px;'
            f'border-radius:0 4px 4px 0;margin:10px 0;font-size:13px;color:#d1d5db">'
            f'<strong style="color:#9ca3af;font-size:10px;text-transform:uppercase">Why:</strong> {play.get("why","")}</div>',
            unsafe_allow_html=True)

        # Coaching notes helper
        def note(icon, label, text, color="#9ca3af"):
            st.markdown(
                f'<div style="display:flex;gap:6px;padding:5px 8px;border-radius:4px;background:rgba(255,255,255,0.02);margin-bottom:4px;font-size:12px">'
                f'<span style="color:{color};min-width:70px;font-size:10px;text-transform:uppercase;letter-spacing:0.06em;padding-top:1px">{icon} {label}</span>'
                f'<span style="color:#d1d5db">{text}</span></div>',
                unsafe_allow_html=True)

        is_man   = fctx.coverage_shell in ("cover_0","cover_1")
        cov_note = (play.get("vs_man") if is_man else play.get("vs_zone")) if fctx.coverage_shell!="unknown" else None
        shell_l  = fctx.coverage_shell.replace("_"," ").upper() if fctx.coverage_shell!="unknown" else ""

        if cov_note:                                             note(">",f"vs. {shell_l}",cov_note,"#3b82f6")
        else:
            if play.get("vs_man"):                               note(">","vs. Man",play["vs_man"],"#3b82f6")
            if play.get("vs_zone"):                              note(">","vs. Zone",play["vs_zone"],"#60a5fa")
        if play.get("kill_look"):                                note("X","Kill look",play["kill_look"],"#ef4444")
        if play.get("post_snap_alert"):                          note("*","Post-snap",play["post_snap_alert"],"#8b5cf6")
        if family=="play_action" and fctx.run_plays_this_drive<3:
            note("!","PA warn",f"Run not established ({fctx.run_plays_this_drive} runs) — fake may not freeze LBs.","#f59e0b")
        if fctx.weather in ("wind","rain","snow") and family in ("dropback_pass","play_action"):
            wx = (f"Wind {fctx.wind_mph}mph — shorten the route tree." if fctx.weather=="wind"
                  else "Wet conditions — prioritize short throws." if fctx.weather=="rain"
                  else "Snow — consider running instead.")
            note("~","Weather",wx,"#60a5fa")
        if fctx.mismatch:                                        note("*","Mismatch",fctx.mismatch,"#f59e0b")
        if fctx.game_mode=="two_minute":                         note(">","Tempo",f"Hurry-up — {fctx.own_timeouts} TOs left. Spike or go OOB.","#f59e0b")
        if fctx.game_mode=="drain_clock":                        note(">","Tempo","Milk it — long cadence, stay in bounds.","#22c55e")
        if fctx.blitz_likely:                                    note(">","Snap count","Hard count — see if they jump before the snap.","#f59e0b")

        if result.get("overuse_warning"):
            st.warning(f"**Tendency:** {result['overuse_warning']}")

        # Log result (broadcast-style quick entry)
        st.divider()
        st.markdown("**Log result (quick)**")
        st.caption(
            "Each button logs **this call** with the shown yards/outcome and advances the chains. "
            "Use **Advanced** only when you need a non-default target or rare outcome label."
        )
        gen_distance = int(result["ctx"].distance)
        ytg = _net_yards_to_endzone(str(fctx.territory), int(fctx.yardline))

        with st.expander("Advanced: outcome dropdown & primary target", expanded=False):
            st.selectbox("What happened?", LOG_OUTCOME_OPTIONS, index=0, key="main_log_semantic_outcome")
            st.selectbox("Primary / target", LOG_TARGET_OPTIONS, index=0, key="main_log_semantic_target")

        def _log_play(
            yards: int,
            *,
            sack_from_chip: bool = False,
            forced_interception: bool = False,
            forced_incomplete: bool = False,
            outcome_ui_override: Optional[str] = None,
        ) -> None:
            st.session_state[UNDO_BUNDLE] = {
                "territory": str(fctx.territory),
                "yardline": int(fctx.yardline),
                "down": int(fctx.down),
                "distance": int(fctx.distance),
            }
            if forced_interception:
                outcome_ui = "Interception"
            elif forced_incomplete:
                outcome_ui = "Incomplete pass"
            elif outcome_ui_override is not None:
                outcome_ui = outcome_ui_override
            else:
                outcome_ui = str(st.session_state.get("main_log_semantic_outcome", LOG_OUTCOME_AUTO))
            target_choice = str(st.session_state.get("main_log_semantic_target", LOG_TARGET_AUTO))
            sem = assemble_actual_semantics(
                concept_name=play.get("name", ""),
                family=family,
                play=play,
                yards_gained=int(yards),
                target_choice=target_choice,
                outcome_ui=outcome_ui,
                sack_from_chip=sack_from_chip,
                forced_interception=forced_interception,
                forced_incomplete=forced_incomplete,
            )
            snap = advance_game_state_after_actual(
                territory=str(fctx.territory),
                yardline=int(fctx.yardline),
                down=int(fctx.down),
                distance=int(fctx.distance),
                actual=sem,
            )
            earned_fd = earned_first_down_for_actual_play(sem, sem.yards_gained, gen_distance) or bool(
                snap.touchdown
            )

            actual = finalize_actual_after_snap(
                sem,
                snap=snap,
                to_go=gen_distance,
                earned_first_down=earned_fd,
            )
            drive_log.log(actual)
            link_open_audit_to_actual(
                game.recommendation_audit,
                plays_after_log=len(drive_log.results),
                actual=actual,
            )
            st.session_state[LAST_DRIVE_SNAP_CONTEXT] = {
                "touchdown": bool(snap.touchdown),
                "turnover_on_downs": bool(snap.turnover_on_downs),
            }
            st.session_state[PENDING_LOG_SITUATION] = {
                "territory": str(snap.territory),
                "yardline": int(snap.yardline),
                "down": int(snap.down),
                "distance": int(snap.distance),
            }
            st.session_state.result = None
            st.session_state.ui_auto_generate = True
            invoke_post_play_hook(
                snap,
                {
                    "actual_play_result": asdict(actual),
                    "yards": int(actual.yards_gained),
                    "result_type": actual.result_type,
                    "family": family,
                    "concept": play.get("name", ""),
                    "description": actual.description,
                    "tags": snap.tags,
                },
            )
            summary, toast_parts = _post_log_summary_and_toast(actual, snap)
            st.session_state.last_play_summary = summary
            st.toast(" · ".join(toast_parts))
            st.rerun()

        st.markdown("**Auto / mixed (uses Advanced dropdown if not overridden)**")
        a1, a2, a3, a4, a5, a6, a7, a8 = st.columns(8)
        with a1:
            if st.button("0", use_container_width=True, key="main_log_yards_0"):
                _log_play(0)
        with a2:
            if st.button("+2", use_container_width=True, key="main_log_yards_plus2"):
                _log_play(2)
        with a3:
            if st.button("+3", use_container_width=True, key="main_log_yards_plus3"):
                _log_play(3)
        with a4:
            if st.button("+5", use_container_width=True, key="main_log_yards_plus5"):
                _log_play(5)
        with a5:
            if st.button("+8", use_container_width=True, key="main_log_yards_plus8"):
                _log_play(8)
        with a6:
            if st.button("+10", use_container_width=True, key="main_log_yards_plus10"):
                _log_play(10)
        with a7:
            if st.button("FD", use_container_width=True, help="First down at the sticks", key="main_log_yards_first_down"):
                _log_play(gen_distance)
        with a8:
            if st.button(
                "TD",
                use_container_width=True,
                help=f"Score — logs {ytg} yds (to goal)",
                key="main_log_td_score",
            ):
                _log_play(ytg)

        st.markdown("**Complete pass + yards (one tap each)**")
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            if st.button("C +3", use_container_width=True, key="main_log_c3"):
                _log_play(3, outcome_ui_override=_LOG_COMPLETE)
        with c2:
            if st.button("C +5", use_container_width=True, key="main_log_c5"):
                _log_play(5, outcome_ui_override=_LOG_COMPLETE)
        with c3:
            if st.button("C +8", use_container_width=True, key="main_log_c8"):
                _log_play(8, outcome_ui_override=_LOG_COMPLETE)
        with c4:
            if st.button("C +10", use_container_width=True, key="main_log_c10"):
                _log_play(10, outcome_ui_override=_LOG_COMPLETE)
        with c5:
            if st.button("C FD", use_container_width=True, key="main_log_c_fd"):
                _log_play(gen_distance, outcome_ui_override=_LOG_COMPLETE)

        st.markdown("**Run + yards (one tap each)**")
        r1, r2, r3, r4 = st.columns(4)
        with r1:
            if st.button("R +3", use_container_width=True, key="main_log_r3"):
                _log_play(3, outcome_ui_override=_LOG_RUN)
        with r2:
            if st.button("R +6", use_container_width=True, key="main_log_r6"):
                _log_play(6, outcome_ui_override=_LOG_RUN)
        with r3:
            if st.button("R FD", use_container_width=True, key="main_log_r_fd"):
                _log_play(gen_distance, outcome_ui_override=_LOG_RUN)
        with r4:
            if st.button("R −2", use_container_width=True, key="main_log_r_loss2"):
                _log_play(-2, outcome_ui_override=_LOG_RUN)

        st.markdown("**Defense / special**")
        d1, d2, d3, d4, d5, d6 = st.columns(6)
        with d1:
            if st.button("INC", use_container_width=True, help="Incomplete (0)", key="main_log_inc"):
                _log_play(0, forced_incomplete=True)
        with d2:
            if st.button("INT", use_container_width=True, help="Interception", key="main_log_int"):
                _log_play(0, forced_interception=True)
        with d3:
            if st.button("SACK", use_container_width=True, key="main_log_yards_sack"):
                _log_play(-8, sack_from_chip=True)
        with d4:
            if st.button("FG made", use_container_width=True, key="main_log_fg_good"):
                _log_play(0, outcome_ui_override=_LOG_FG_GOOD)
        with d5:
            if st.button("FG miss", use_container_width=True, key="main_log_fg_miss"):
                _log_play(0, outcome_ui_override=_LOG_FG_MISS)
        with d6:
            if st.button("TFL", use_container_width=True, help="Run loss −3", key="main_log_tfl"):
                _log_play(-3, outcome_ui_override=_LOG_RUN)

        lc1, lc2 = st.columns([3, 1])
        yards_input = lc1.number_input("Custom yards", value=0, step=1, key="main_log_custom_yards_value")
        if lc2.button("Log custom", use_container_width=True, key="main_log_yards_custom_submit"):
            yv = int(yards_input)
            _log_play(yv, sack_from_chip=yv <= -4)


# Drive charts for the active series (same data as **This drive** above)
with st.expander("Drive charts (this series)", expanded=False):
    if not drive_log.results:
        st.caption("No plays logged yet.")
    else:
        dm, rp, dc = drive_momentum_chart(drive_log), run_pass_donut(drive_log), drive_chart(drive_log)
        c1, c2 = st.columns(2, gap="small")
        with c1:
            if dm:
                st.plotly_chart(dm, use_container_width=True, config={"displayModeBar": False})
        with c2:
            if rp:
                st.plotly_chart(rp, use_container_width=True, config={"displayModeBar": False})
        if dc:
            st.plotly_chart(dc, use_container_width=True, config={"displayModeBar": False})
        chip_spans: list[str] = []
        for r in drive_log.results:
            d = r.description or format_actual_play_result_description(r)
            chip_spans.append(
                f'<span style="padding:2px 8px;border-radius:3px;background:{FAM_COLOR.get(r.family,"#6b7280")}22;'
                f'border:1px solid {FAM_COLOR.get(r.family,"#6b7280")}55;color:{FAM_COLOR.get(r.family,"#9ca3af")};font-size:11px">'
                f'{html.escape(d[:48])}{"…" if len(d) > 48 else ""}</span>'
            )
        chips = " ".join(chip_spans)
        st.markdown(f'<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:8px">{chips}</div>', unsafe_allow_html=True)
        runs_c, passes_c = drive_log.run_pass_split()
        st.caption(f"{len(drive_log.results)} plays · {runs_c} run / {passes_c} pass")
