"""
Snap-by-snap replay of recommendation_audit rows (saved game JSON or live session).

Run the app from the repo root:
    streamlit run streamlit_app.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from playcaller.evaluation import evaluate_audit_records, summarize_audit_session
from playcaller.game import game_from_dict

st.set_page_config(page_title="Review session", layout="wide")
st.title("Review session")
st.caption("Step through **Generate to actual** pairs from a saved game or the current browser session.")

source = st.radio(
    "Source",
    ["Current session", "Upload game JSON"],
    horizontal=True,
    key="review_page_source",
)

game = None
if source == "Current session":
    game = st.session_state.get("game")
    if game is None:
        st.warning("No session yet — open the main **Play Caller** page first, or upload JSON.")
        st.stop()
else:
    up = st.file_uploader("Game JSON", type=["json"], key="review_page_upload")
    if up is None:
        st.info(
            "Upload a file exported via **Download game JSON** (includes `recommendation_audit` when recorded)."
        )
        st.stop()
    try:
        payload = json.loads(up.getvalue().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        st.error(f"Could not read JSON: {e}")
        st.stop()
    if not isinstance(payload, dict):
        st.error("JSON root must be an object.")
        st.stop()
    try:
        game = game_from_dict(payload)
    except Exception as e:
        st.error(f"Could not load game: {e}")
        st.stop()

audit = list(game.recommendation_audit or [])
if not audit:
    st.warning(
        "This game has no **recommendation_audit** rows. On the main app, enable **Record recommendation audit** and generate calls."
    )
    st.stop()

st.subheader("Post-game summary")
st.text(summarize_audit_session(audit))
with st.expander("Metrics (JSON)", expanded=False):
    st.json(evaluate_audit_records(audit))

st.subheader("Snap replay")
idx = st.slider("Audit row", 0, len(audit) - 1, len(audit) - 1, key="review_snap_slider")
row = audit[idx]
pre = row.get("pre_snap") or {}
st.markdown(
    f"**#{idx + 1}/{len(audit)}** · drive epoch **{row.get('drive_epoch')}** · "
    f"snap **{row.get('snap_id')}** · status **{row.get('status')}**"
)
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Situation (pre-snap)**")
    st.json(
        {
            "down": pre.get("down"),
            "distance": pre.get("distance"),
            "territory": pre.get("territory"),
            "yardline": pre.get("yardline"),
            "quarter": pre.get("quarter"),
            "score_diff": pre.get("score_diff"),
            "game_mode": pre.get("game_mode"),
        }
    )
    st.markdown("**Top scored families**")
    st.json(row.get("top_families") or [])
with c2:
    st.markdown("**Recommendation**")
    st.json(
        {
            "bucket": row.get("bucket"),
            "selected_family": row.get("selected_family"),
            "play": row.get("selected_play_name"),
            "fourth_down": row.get("fourth_down_recommendation"),
            "model": row.get("model"),
        }
    )
    act = row.get("linked_actual")
    st.markdown("**Actual (logged)**")
    if act:
        st.json(
            {
                "concept": act.get("concept_name"),
                "family": act.get("family"),
                "yards": act.get("yards_gained"),
                "result_type": act.get("result_type"),
                "turnover": act.get("turnover"),
            }
        )
        match = str(act.get("family") or "") == str(row.get("selected_family") or "")
        st.caption(
            "Family match vs recommendation: **yes**" if match else "Family match vs recommendation: **no**"
        )
    else:
        st.caption("No linked actual yet (open row, or play not logged in app).")

with st.expander("Full audit row", expanded=False):
    st.json(row)
