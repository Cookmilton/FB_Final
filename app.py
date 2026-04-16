import math
from typing import Dict, Any, List, Optional, Tuple

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import streamlit as st

from football_play_predictor_claude_final import FootballPlayPredictor


st.set_page_config(
    page_title="Football Play Predictor",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------- App styling ----------
st.markdown(
    """
    <style>
    .call-card {
        padding: 1rem 1rem 0.75rem 1rem;
        border: 1px solid #374151;
        border-radius: 14px;
        background: #0f172a;
        margin-bottom: 1rem;
    }
    .hero-card {
        padding: 1.15rem 1.15rem 0.95rem 1.15rem;
        border: 1px solid #4F8BF9;
        border-radius: 18px;
        background: linear-gradient(180deg, #111827 0%, #0b1220 100%);
        margin-bottom: 1rem;
    }
    .hero-kicker {
        color: #93c5fd;
        font-size: 0.88rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 0.35rem;
    }
    .call-title {
        font-size: 1.15rem;
        font-weight: 700;
        margin-bottom: 0.4rem;
    }
    .hero-title {
        font-size: 1.65rem;
        font-weight: 800;
        margin-bottom: 0.45rem;
    }
    .hero-note {
        color: #d1d5db;
        font-size: 0.96rem;
        margin-top: 0.45rem;
    }
    .small-label {
        color: #9ca3af;
        font-size: 0.9rem;
        margin-bottom: 0.2rem;
    }
    .compact-chip {
        display: inline-block;
        padding: 0.25rem 0.55rem;
        border: 1px solid #374151;
        border-radius: 999px;
        margin: 0.1rem 0.25rem 0.25rem 0;
        font-size: 0.83rem;
        color: #d1d5db;
        background: #111827;
    }
    .section-caption {
        color: #9ca3af;
        font-size: 0.92rem;
        margin-top: -0.25rem;
        margin-bottom: 0.75rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Predictor singleton ----------
if "predictor" not in st.session_state:
    st.session_state.predictor = FootballPlayPredictor()

predictor: FootballPlayPredictor = st.session_state.predictor

if "show_debug" not in st.session_state:
    st.session_state.show_debug = False

if "selected_example" not in st.session_state:
    st.session_state.selected_example = "2&7 opp43"

if "form_down" not in st.session_state:
    st.session_state.form_down = 2
if "form_distance" not in st.session_state:
    st.session_state.form_distance = 7
if "form_territory" not in st.session_state:
    st.session_state.form_territory = "opp"
if "form_yardline" not in st.session_state:
    st.session_state.form_yardline = 43
if "form_safe" not in st.session_state:
    st.session_state.form_safe = "Balanced"
if "form_explosive" not in st.session_state:
    st.session_state.form_explosive = "Normal"
if "form_runpass" not in st.session_state:
    st.session_state.form_runpass = "Balanced"
if "form_pressure" not in st.session_state:
    st.session_state.form_pressure = "Normal"
if "compact_mode" not in st.session_state:
    st.session_state.compact_mode = True


# ---------- Helpers ----------
EXAMPLE_LOOKUP: Dict[str, Dict[str, Any]] = {
    "2&7 opp43": dict(down=2, distance=7, territory="opp", yardline=43, safe="Balanced", explosive="Normal", runpass="Balanced", pressure="Normal"),
    "2&7 opp43 safe": dict(down=2, distance=7, territory="opp", yardline=43, safe="Safe", explosive="Normal", runpass="Balanced", pressure="Normal"),
    "3&6 own38 blitz": dict(down=3, distance=6, territory="own", yardline=38, safe="Balanced", explosive="Normal", runpass="Balanced", pressure="Blitz"),
    "1&10 opp24": dict(down=1, distance=10, territory="opp", yardline=24, safe="Balanced", explosive="Normal", runpass="Balanced", pressure="Normal"),
    "1&10 opp24 shot": dict(down=1, distance=10, territory="opp", yardline=24, safe="Balanced", explosive="Shot", runpass="Balanced", pressure="Normal"),
    "4&1 opp8 run": dict(down=4, distance=1, territory="opp", yardline=8, safe="Balanced", explosive="Normal", runpass="Run", pressure="Normal"),
}


def apply_example(example_key: str) -> None:
    cfg = EXAMPLE_LOOKUP[example_key]
    st.session_state.form_down = cfg["down"]
    st.session_state.form_distance = cfg["distance"]
    st.session_state.form_territory = cfg["territory"]
    st.session_state.form_yardline = cfg["yardline"]
    st.session_state.form_safe = cfg["safe"]
    st.session_state.form_explosive = cfg["explosive"]
    st.session_state.form_runpass = cfg["runpass"]
    st.session_state.form_pressure = cfg["pressure"]


def build_input_string() -> str:
    territory_text = st.session_state.form_territory
    core = f"{st.session_state.form_down}&{st.session_state.form_distance} {territory_text}{st.session_state.form_yardline}"

    tags: List[str] = []
    if st.session_state.form_safe == "Safe":
        tags.append("safe")
    if st.session_state.form_explosive == "Shot":
        tags.append("shot")
    if st.session_state.form_runpass == "Run":
        tags.append("run")
    elif st.session_state.form_runpass == "Pass":
        tags.append("pass")
    if st.session_state.form_pressure == "Blitz":
        tags.append("blitz")

    if tags:
        return f"{core} {' '.join(tags)}"
    return core


def format_score(score: float) -> str:
    return f"{score:.2f}"


def play_to_lines(call: Dict[str, Any]) -> List[str]:
    lines = [
        f"**Call:** {play.name}",
        f"**Family:** {call['family'].replace('_', ' ').title()}",
        f"**Score:** {format_score(call['score'])}",
        f"**Personnel:** {play.personnel}",
        f"**Formation:** {play.formation}",
    ]

    if play.run_scheme:
        lines.append(f"**Run scheme:** {play.run_scheme}")
        lines.append(f"**Blocking:** {play.blocking}")
    else:
        lines.append(f"**Protection:** {play.protection}")

    if play.routes:
        lines.append("**Routes:**")
        for player, route in play.routes.items():
            lines.append(f"- {player}: {route}")

    lines.append(f"**Why:** {call['why']}")
    lines.append(f"**Avoid if:** {call['avoid_if']}")
    return lines


def render_call_card(label: str, call: Optional[Dict[str, Any]]) -> None:
    st.markdown(f"### {label}")
    if call is None:
        st.info("No clearly distinct option available.")
        return

    lines = play_to_lines(call)
    with st.container():
        st.markdown('<div class="call-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="call-title">{call["play"].name}</div>', unsafe_allow_html=True)
        for line in lines[1:]:
            st.markdown(line)
        st.markdown("</div>", unsafe_allow_html=True)



def compact_profile_label(result: Dict[str, Any]) -> str:
    return f"{result['field_zone'].replace('_', ' ').title()} • {result['distance_profile'].replace('_', ' ').title()}"


def render_compact_chips(call: Dict[str, Any]) -> None:
    play = call["play"]
    chips = [
        call["family"].replace("_", " ").title(),
        play.personnel,
        play.formation,
    ]
    if play.run_scheme:
        chips.append(play.run_scheme)
    elif play.protection:
        chips.append(play.protection)

    st.markdown(
        "".join(f'<span class="compact-chip">{chip}</span>' for chip in chips),
        unsafe_allow_html=True,
    )


def render_best_call_hero(call: Dict[str, Any], result: Dict[str, Any], compact_mode: bool = False) -> None:
    if call is None:
        st.info("No best call available.")
        return

    play = call["play"]
    st.markdown('<div class="hero-card">', unsafe_allow_html=True)
    st.markdown('<div class="hero-kicker">Primary Recommendation</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="hero-title">{play.name}</div>', unsafe_allow_html=True)

    m1, m2, m3 = st.columns(3)
    m1.metric("Score", format_score(call["score"]))
    m2.metric("Family", call["family"].replace("_", " ").title())
    m3.metric("Profile", compact_profile_label(result))

    render_compact_chips(call)

    if compact_mode:
        st.markdown(f"**Why:** {call['why']}")
        st.markdown(f"**Avoid if:** {call['avoid_if']}")
    else:
        info1, info2 = st.columns(2)
        with info1:
            st.markdown("**Why it fits**")
            st.write(call["why"])
        with info2:
            st.markdown("**Watch-out**")
            st.write(call["avoid_if"])

        detail1, detail2 = st.columns(2)
        with detail1:
            st.markdown(f"**Personnel:** {play.personnel}")
            st.markdown(f"**Formation:** {play.formation}")
        with detail2:
            if play.run_scheme:
                st.markdown(f"**Run scheme:** {play.run_scheme}")
                st.markdown(f"**Blocking:** {play.blocking}")
            else:
                st.markdown(f"**Protection:** {play.protection}")

        if play.routes:
            with st.expander("Route detail", expanded=False):
                for player, route in play.routes.items():
                    st.markdown(f"- **{player}:** {route}")

    st.markdown("</div>", unsafe_allow_html=True)


def render_compact_call(label: str, call: Optional[Dict[str, Any]]) -> None:
    if call is None:
        return
    play = call["play"]
    with st.container(border=True):
        row1, row2 = st.columns([2.3, 1])
        with row1:
            st.markdown(f"**{label}: {play.name}**")
            st.caption(f"{call['family'].replace('_', ' ').title()} • {play.personnel} • {play.formation}")
        with row2:
            st.metric("Score", format_score(call["score"]))
        st.markdown(f"**Why:** {call['why']}")


def yardline_to_absolute(territory: str, yardline: int) -> int:
    if territory == "own":
        return yardline
    return 100 - yardline


def draw_field_position(result: Dict[str, Any]):
    s = result["situation"]
    abs_yard = yardline_to_absolute(s.territory, s.yardline)

    fig, ax = plt.subplots(figsize=(10, 1.8))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.add_patch(Rectangle((0, 0.1), 100, 0.8, fill=False, linewidth=2))

    zones = [
        (0, 10, "Backed Up"),
        (10, 20, "Coming Out"),
        (20, 50, "Open Field"),
        (50, 70, "Plus Territory"),
        (70, 80, "Fringe Red"),
        (80, 90, "High Red"),
        (90, 100, "Low Red"),
    ]

    for start, end, label in zones:
        ax.add_patch(Rectangle((start, 0.1), end - start, 0.8, fill=False, linewidth=1))
        ax.text((start + end) / 2, 0.88, label, ha="center", va="top", fontsize=8)

    for x in range(0, 101, 5):
        ax.plot([x, x], [0.1, 0.9], linewidth=0.5)
    for x in range(0, 101, 10):
        ax.text(x, 0.02, str(x), ha="center", va="bottom", fontsize=8)

    ax.scatter([abs_yard], [0.5], s=160, marker="o")
    ax.text(abs_yard, 0.58, "Ball", ha="center", fontsize=9)
    ax.set_title("Field Position", fontsize=12)
    return fig


def draw_family_rankings(result: Dict[str, Any]):
    rankings = result["family_rankings"]
    labels = [family.replace("_", " ").title() for family, _ in rankings]
    values = [score for _, score in rankings]

    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.barh(labels[::-1], values[::-1])
    ax.set_xlabel("Score")
    ax.set_title("Top Family Rankings")
    return fig


def _route_path(start_x, start_y, kind):
    if kind == "slant":
        return [start_x, start_x + 10], [start_y, start_y + 8]
    if kind == "flat":
        return [start_x, start_x + 8], [start_y, start_y]
    if kind == "hitch":
        return [start_x, start_x + 7], [start_y, start_y]
    if kind == "hook":
        return [start_x, start_x + 8, start_x + 8], [start_y, start_y, start_y + 4]
    if kind == "go":
        return [start_x, start_x + 20], [start_y, start_y]
    if kind == "fade":
        return [start_x, start_x + 18], [start_y, start_y + 6]
    if kind == "out":
        return [start_x, start_x + 12, start_x + 12], [start_y, start_y, start_y + 8]
    if kind == "dig":
        return [start_x, start_x + 14, start_x + 14], [start_y, start_y, start_y - 8]
    if kind == "cross":
        return [start_x, start_x + 6, start_x + 18], [start_y, start_y - 2, 26]
    if kind == "bubble":
        return [start_x, start_x - 2, start_x + 5], [start_y, start_y + 3, start_y + 6]
    if kind == "screen":
        return [start_x, start_x - 3, start_x + 2], [start_y, start_y, start_y]
    return [start_x, start_x + 8], [start_y, start_y]


def concept_diagram_data(play_name: str):
    concepts = {
        "Stick": [("X", 2, 8, "slant"), ("H", 2, 20, "hook"), ("Y", 2, 28, "flat"), ("Z", 2, 40, "fade"), ("RB", 0, 24, "flat")],
        "Spacing": [("X", 2, 8, "hitch"), ("H", 2, 18, "hook"), ("Y", 2, 30, "hook"), ("Z", 2, 42, "hitch"), ("RB", 0, 25, "hook")],
        "Slant-Flat": [("X", 2, 8, "slant"), ("H", 2, 20, "flat"), ("Y", 2, 30, "go"), ("Z", 2, 42, "dig"), ("RB", 0, 24, "flat")],
        "Drive": [("X", 2, 8, "dig"), ("H", 2, 20, "cross"), ("Y", 2, 28, "hook"), ("Z", 2, 42, "go"), ("RB", 0, 24, "flat")],
        "Dagger": [("X", 2, 8, "hitch"), ("H", 2, 20, "go"), ("Y", 2, 28, "dig"), ("Z", 2, 42, "go"), ("RB", 0, 24, "flat")],
        "Y-Cross": [("X", 2, 8, "hitch"), ("H", 2, 20, "cross"), ("Y", 2, 28, "cross"), ("Z", 2, 42, "go"), ("RB", 0, 24, "flat")],
        "RB Middle Screen": [("X", 2, 8, "go"), ("H", 2, 20, "go"), ("Y", 2, 30, "go"), ("Z", 2, 42, "go"), ("RB", 0, 24, "screen")],
        "Trips Bubble": [("X", 2, 8, "slant"), ("H", 2, 20, "bubble"), ("Y", 2, 30, "flat"), ("Z", 2, 40, "flat"), ("RB", 0, 24, "flat")],
        "Boot Flood": [("X", 2, 8, "go"), ("Y", 2, 28, "out"), ("H", 2, 20, "flat"), ("Z", 2, 40, "cross"), ("RB", 0, 24, "flat")],
        "Y-Leak": [("X", 2, 8, "go"), ("Y", 2, 28, "cross"), ("H", 2, 20, "cross"), ("Z", 2, 40, "out"), ("RB", 0, 24, "flat")],
    }
    return concepts.get(play_name)


    data = concept_diagram_data(play.name)
    if not data:
        return None

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.set_xlim(0, 30)
    ax.set_ylim(0, 50)
    ax.axis("off")

    ax.add_patch(Rectangle((0, 0), 30, 50, fill=False, linewidth=2))
    for y in range(0, 51, 5):
        ax.plot([0, 30], [y, y], linewidth=0.4)
    ax.plot([2, 2], [0, 50], linewidth=2)
    ax.text(1.5, 48, "LOS", fontsize=9, rotation=90)

    for label, sx, sy, route_kind in data:
        ax.scatter([sx], [sy], s=60)
        ax.text(sx - 1.2, sy + 1.5, label, fontsize=8)
        px, py = _route_path(sx, sy, route_kind)
        ax.plot(px, py, linewidth=2)

    ax.set_title(f"Concept Diagram: {play.name}", fontsize=12)
    return fig


# ---------- Sidebar ----------
st.sidebar.title("Tools")
example = st.sidebar.radio(
    "Quick examples",
    list(EXAMPLE_LOOKUP.keys()),
    index=list(EXAMPLE_LOOKUP.keys()).index(st.session_state.selected_example),
)

if st.sidebar.button("Load selected example", use_container_width=True):
    st.session_state.selected_example = example
    apply_example(example)
    st.rerun()

if st.sidebar.button("Clear recent memory", use_container_width=True):
    predictor.clear_recent_history()

st.session_state.compact_mode = st.sidebar.toggle("Compact one-screen mode", value=st.session_state.compact_mode)
st.session_state.show_debug = st.sidebar.toggle("Show debug rankings", value=st.session_state.show_debug)

with st.sidebar.expander("Input help", expanded=False):
    st.markdown(
        """
        Core format:
        - `2&7 opp43`
        - `1&10 own25`

        Intent tags generated by the buttons:
        - `safe`
        - `shot`
        - `run`
        - `pass`
        - `blitz`
        """
    )

# ---------- Main ----------
st.title("🏈 Football Play Predictor")
st.caption("Cleaner control panel version: grouped inputs on the left, recommendations and visuals on the right.")

top_left, top_right = st.columns([1.5, 1])
with top_left:
    st.markdown("### Current Situation")
    st.markdown('<div class="section-caption">Build the shorthand input without typing tags manually.</div>', unsafe_allow_html=True)
with top_right:
    input_preview = build_input_string()
    st.text_input("Generated input", value=input_preview, disabled=True)

controls_col, output_col = st.columns([1.08, 1], gap="large")

with controls_col:
    with st.container(border=True):
        st.markdown("#### Situation")
        row1 = st.columns(2)
        with row1[0]:
            st.selectbox("Down", [1, 2, 3, 4], key="form_down")
        with row1[1]:
            st.number_input("Distance", min_value=1, max_value=30, step=1, key="form_distance")

        row2 = st.columns(2)
        with row2[0]:
            st.segmented_control(
                "Field Side",
                ["opp", "own"],
                key="form_territory",
                help="opp = opponent territory, own = your own territory",
            )
        with row2[1]:
            st.slider("Yard Line", min_value=1, max_value=50, key="form_yardline")

    st.write("")

    with st.container(border=True):
        st.markdown("#### Game Context")
        st.markdown('<div class="section-caption">Use the buttons instead of typing tags like safe, shot, or blitz.</div>', unsafe_allow_html=True)

        st.segmented_control(
            "Risk Profile",
            ["Safe", "Balanced"],
            key="form_safe",
            selection_mode="single",
            default=st.session_state.form_safe,
        )
        st.segmented_control(
            "Explosive Intent",
            ["Normal", "Shot"],
            key="form_explosive",
            selection_mode="single",
            default=st.session_state.form_explosive,
        )
        st.segmented_control(
            "Run / Pass Lean",
            ["Run", "Balanced", "Pass"],
            key="form_runpass",
            selection_mode="single",
            default=st.session_state.form_runpass,
        )
        st.segmented_control(
            "Pressure Read",
            ["Normal", "Blitz"],
            key="form_pressure",
            selection_mode="single",
            default=st.session_state.form_pressure,
        )

    st.write("")

    with st.container(border=True):
        st.markdown("#### Quick Examples")
        st.selectbox("Example preset", list(EXAMPLE_LOOKUP.keys()), key="selected_example")
        ex1, ex2 = st.columns(2)
        with ex1:
            if st.button("Apply example", use_container_width=True):
                apply_example(st.session_state.selected_example)
                st.rerun()
        with ex2:
            predict_btn = st.button("Predict Call", type="primary", use_container_width=True)

with output_col:
    st.markdown("#### Live Summary")
    preview_situation = build_input_string()
    preview_result = None
    try:
        preview_result = predictor.recommend(preview_situation)
    except Exception:
        preview_result = None

    if preview_result:
        s = preview_result["situation"]
        indicator_cols = st.columns(4)
        indicator_cols[0].metric("Down", str(s.down))
        indicator_cols[1].metric("To Go", str(s.distance))
        indicator_cols[2].metric("Zone", preview_result["field_zone"].replace("_", " ").title())
        indicator_cols[3].metric("Profile", preview_result["distance_profile"].replace("_", " ").title())

        strip = []
        abs_yard = yardline_to_absolute(s.territory, s.yardline)
        if abs_yard >= 80:
            strip.append("Red Zone")
        if s.down == 4:
            strip.append("Four Down")
        if s.distance <= 2:
            strip.append("Short Yardage")
        if st.session_state.form_pressure == "Blitz":
            strip.append("Pressure Alert")
        if strip:
            st.markdown(
                "".join(f'<span class="compact-chip">{item}</span>' for item in strip),
                unsafe_allow_html=True,
            )
    else:
        st.info("Choose a valid situation to generate a recommendation.")

# Default behavior keeps the page populated without an extra click.
run_now = "predict_btn" not in locals() or predict_btn or True
user_input = build_input_string()

if run_now:
    try:
        result = predictor.recommend(user_input)

        left, right = st.columns([1.15, 1], gap="large")

        with left:
            st.subheader("Recommendations")
            render_best_call_hero(result["best_call"], result, compact_mode=st.session_state.compact_mode)

            if st.session_state.compact_mode:
                st.markdown("#### Secondary Options")
                render_compact_call("Safe Call", result["safe_call"])
                render_compact_call("Aggressive Call", result["aggressive_call"])
                render_compact_call("Run Alternative", result["run_alternative"])
            else:
                with st.expander("Secondary Options", expanded=True):
                    render_call_card("Safe Call", result["safe_call"])
                    render_call_card("Aggressive Call", result["aggressive_call"])
                    render_call_card("Run Alternative", result["run_alternative"])

            if result["other_calls"]:
                with st.expander("Other considerations", expanded=False):
                    for idx, call in enumerate(result["other_calls"], start=1):
                        st.markdown(
                            f"{idx}. **{call['play'].name}** "
                            f"({call['family'].replace('_', ' ').title()}, score {format_score(call['score'])})"
                        )

        with right:
            if st.session_state.compact_mode:
                st.subheader("Quick Visuals")
                st.pyplot(draw_field_position(result), clear_figure=True)
                best_play = result["best_call"]["play"]
                diagram = draw_play_diagram(best_play)
                if diagram is not None:
                    with st.expander("Best Call Diagram", expanded=False):
                        st.pyplot(diagram, clear_figure=True)
            else:
                st.subheader("Situation Visuals")
                st.pyplot(draw_field_position(result), clear_figure=True)
                st.pyplot(draw_family_rankings(result), clear_figure=True)

                st.subheader("Best Call Diagram")
                best_play = result["best_call"]["play"]
                diagram = draw_play_diagram(best_play)
                if diagram is None:
                    st.info("No custom concept diagram yet for this play.")
                else:
                    st.pyplot(diagram, clear_figure=True)

        with st.expander("Advanced details", expanded=False):
            if st.session_state.show_debug:
                st.markdown("**Debug rankings**")
                for family, score in result["family_rankings"]:
                    st.write(f"- {family.replace('_', ' ').title()}: {format_score(score)}")
            else:
                st.caption("Turn on 'Show debug rankings' in the sidebar to see internal family scores.")

    except Exception as e:
        st.error(str(e))
        st.info("Try a valid setup like 2&7 opp43 or 1&10 opp24.")
