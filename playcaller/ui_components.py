from __future__ import annotations

from typing import Dict, Optional, Tuple

import plotly.graph_objects as go

from .actual_result import format_actual_play_result_description
from .domain import RUN_FAMILIES, GameContext
from .state import DriveLogger


FAM_COLOR = {
    "inside_zone": "#16a34a",
    "outside_zone": "#22c55e",
    "duo": "#15803d",
    "power": "#166534",
    "draw": "#4ade80",
    "quick_game": "#3b82f6",
    "dropback_pass": "#2563eb",
    "screen": "#60a5fa",
    "play_action": "#8b5cf6",
    "fade_iso": "#a78bfa",
    "two_point": "#f59e0b",
}

FAM_LABEL = {
    "inside_zone": "Inside Zone",
    "outside_zone": "Outside Zone",
    "duo": "Duo",
    "power": "Power",
    "draw": "Draw",
    "quick_game": "Quick Game",
    "dropback_pass": "Dropback",
    "screen": "Screen",
    "play_action": "Play Action",
    "fade_iso": "Fade/Iso",
}


def fmt_clock(seconds_remaining: int) -> str:
    return f"{seconds_remaining // 60}:{seconds_remaining % 60:02d}"


def render_field(ctx: GameContext) -> str:
    """Returns an inline SVG for the current field position."""
    ypx, ez, w, h = 5.2, 44, 624, 86
    fl, fr = ez, w - ez
    bx = fl + ctx.yardline * ypx if ctx.territory == "own" else fr - ctx.yardline * ypx
    fd_raw = bx + ctx.distance * ypx if ctx.territory == "own" else bx - ctx.distance * ypx
    fdx = max(fl + 2, min(fr - 2, fd_raw))
    rz_l = fr - 20 * ypx

    stripes = "".join(
        f'<rect x="{fl + i * 10 * ypx}" y="0" width="{10 * ypx}" height="{h}" '
        f'fill="{"#0c1a0f" if i % 2 == 0 else "#0e1f12"}"/>'
        for i in range(10)
    )
    ylines = "".join(
        f'<line x1="{fl + i * 10 * ypx}" y1="0" x2="{fl + i * 10 * ypx}" y2="{h}" '
        f'stroke="rgba(255,255,255,0.18)" stroke-width="1"/>'
        for i in range(11)
    )
    hashes = "".join(
        f'<line x1="{fl + i * 5 * ypx}" y1="{h * .28}" x2="{fl + i * 5 * ypx}" y2="{h * .42}" '
        f'stroke="rgba(255,255,255,0.1)" stroke-width="0.5"/>'
        f'<line x1="{fl + i * 5 * ypx}" y1="{h * .58}" x2="{fl + i * 5 * ypx}" y2="{h * .72}" '
        f'stroke="rgba(255,255,255,0.1)" stroke-width="0.5"/>'
        for i in range(21)
    )
    ydlbls = "".join(
        f'<text x="{fl + y * ypx}" y="{h / 2 + 3.5}" fill="rgba(255,255,255,0.2)" font-size="8" '
        f'text-anchor="middle" font-family="monospace">{y}</text>'
        for y in [10, 20, 30, 40, 50]
    ) + "".join(
        f'<text x="{fl + y * ypx}" y="{h / 2 + 3.5}" fill="rgba(255,255,255,0.2)" font-size="8" '
        f'text-anchor="middle" font-family="monospace">{100 - y}</text>'
        for y in [60, 70, 80, 90]
    )
    rz = (
        f'<rect x="{rz_l + 3}" y="3" width="32" height="10" rx="2" fill="rgba(220,38,38,0.35)"/>'
        f'<text x="{rz_l + 19}" y="10.5" fill="#fca5a5" font-size="6.5" text-anchor="middle" '
        f'font-family="monospace">RED ZONE</text>'
        if ctx.territory == "opponents" and ctx.yardline <= 20
        else ""
    )

    return f"""<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg"
     style="width:100%;display:block;border-radius:6px;border:1px solid #1e2836">
  <rect width="{w}" height="{h}" fill="#090e0b"/>
  {stripes}
  <rect x="0" y="0" width="{ez}" height="{h}" fill="#0b1a0c"/>
  <rect x="{fr}" y="0" width="{ez}" height="{h}" fill="#1a0b0b"/>
  <rect x="{rz_l}" y="0" width="{20 * ypx}" height="{h}" fill="rgba(220,38,38,0.06)"/>
  <line x1="{rz_l}" y1="0" x2="{rz_l}" y2="{h}" stroke="rgba(220,38,38,0.3)" stroke-width="1" stroke-dasharray="3 2"/>
  {ylines}{hashes}{ydlbls}
  <text x="{ez / 2}" y="{h / 2 + 3}" fill="rgba(255,255,255,0.22)" font-size="7" text-anchor="middle" font-family="monospace">OWN</text>
  <text x="{w - ez / 2}" y="{h / 2 + 3}" fill="rgba(255,255,255,0.22)" font-size="7" text-anchor="middle" font-family="monospace">OPP</text>
  <line x1="{fdx}" y1="0" x2="{fdx}" y2="{h}" stroke="#f5c518" stroke-width="1.5" stroke-dasharray="4 3" opacity="0.65"/>
  <line x1="{bx}" y1="4" x2="{bx}" y2="{h - 4}" stroke="#f5c518" stroke-width="2.5"/>
  <ellipse cx="{bx}" cy="{h / 2}" rx="6" ry="3.8" fill="#c47e3a" stroke="#e09050" stroke-width="0.5" transform="rotate(-20 {bx} {h / 2})"/>
  <rect x="{bx - 14}" y="4" width="28" height="12" rx="2" fill="rgba(0,0,0,0.8)"/>
  <text x="{bx}" y="13" fill="#f5c518" font-size="8" text-anchor="middle" font-family="monospace">{ctx.down}&amp;{ctx.distance}</text>
  {rz}
</svg>"""


def score_chart(scores: Dict[str, float]) -> go.Figure:
    items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    labels = [FAM_LABEL.get(f, f) for f, _ in items]
    vals = [round(s * 100, 1) for _, s in items]
    colors = [FAM_COLOR.get(f, "#6b7280") for f, _ in items]

    fig = go.Figure(
        go.Bar(
            x=vals,
            y=labels,
            orientation="h",
            marker=dict(color=colors, cornerradius=3),
            text=[f"{v}%" for v in vals],
            textposition="outside",
            textfont=dict(size=10, color="#9ca3af", family="Courier New"),
            hovertemplate="%{y}: %{x}%<extra></extra>",
        )
    )
    fig.update_layout(
        margin=dict(l=0, r=50, t=10, b=10),
        height=max(160, len(items) * 30 + 20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(range=[20, 75], showgrid=False, showticklabels=False, zeroline=False),
        yaxis=dict(showgrid=False, tickfont=dict(size=11, color="#9ca3af", family="Courier New")),
        showlegend=False,
    )
    return fig


def drive_chart(log: DriveLogger) -> Optional[go.Figure]:
    counts = log.family_counts
    if not counts:
        return None
    runs = sum(v for f, v in counts.items() if f in RUN_FAMILIES)
    passes = sum(v for f, v in counts.items() if f not in RUN_FAMILIES)

    fig = go.Figure(
        go.Bar(
            x=list(counts.keys()),
            y=list(counts.values()),
            marker=dict(color=[FAM_COLOR.get(f, "#6b7280") for f in counts]),
            text=list(counts.values()),
            textposition="outside",
            textfont=dict(size=11, color="#9ca3af"),
            hovertemplate="%{x}: %{y} plays<extra></extra>",
        )
    )
    fig.update_layout(
        title=dict(text=f"Concept frequency — {runs}R / {passes}P", font=dict(size=12, color="#9ca3af")),
        margin=dict(l=0, r=0, t=30, b=0),
        height=180,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, tickfont=dict(size=10, color="#9ca3af"), tickangle=-20),
        yaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        showlegend=False,
    )
    return fig


def drive_momentum_chart(log: DriveLogger) -> Optional[go.Figure]:
    """
    Drive tracking visualization: cumulative yards gained across the drive,
    colored by run vs pass families.
    """
    if not log.results:
        return None

    xs = list(range(1, len(log.results) + 1))
    cum = 0
    ys = []
    colors = []
    hover = []
    for r in log.results:
        net = int(r.yards_gained) + (int(r.penalty_yards) if r.penalty else 0)
        cum += net
        ys.append(cum)
        is_run = r.family in RUN_FAMILIES
        colors.append("#22c55e" if is_run else "#60a5fa")
        desc = (r.description or "").strip() or format_actual_play_result_description(r)
        hover.append(
            f"{desc}<br>"
            f"{FAM_LABEL.get(r.family, r.family)} · {net:+d} yds net · "
            f"Play {len(ys)} · Drive total {cum:+d}"
        )

    fig = go.Figure(
        go.Scatter(
            x=xs,
            y=ys,
            mode="lines+markers",
            line=dict(color="rgba(148,163,184,0.55)", width=2),
            marker=dict(size=10, color=colors, line=dict(width=1, color="rgba(255,255,255,0.25)")),
            hovertext=hover,
            hoverinfo="text",
        )
    )
    fig.update_layout(
        title=dict(text="Drive momentum (cumulative yards)", font=dict(size=12, color="#9ca3af")),
        margin=dict(l=0, r=0, t=30, b=0),
        height=210,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(title="Play #", showgrid=False, tickfont=dict(size=10, color="#9ca3af")),
        yaxis=dict(title="Yards", showgrid=True, gridcolor="rgba(148,163,184,0.12)", tickfont=dict(size=10, color="#9ca3af")),
        showlegend=False,
    )
    return fig


def run_pass_share(log: DriveLogger) -> Tuple[int, int, float, float]:
    runs, passes = log.run_pass_split()
    total = runs + passes
    if total <= 0:
        return 0, 0, 0.0, 0.0
    return runs, passes, runs / total, passes / total


def run_pass_donut(log: DriveLogger) -> Optional[go.Figure]:
    runs, passes, r_pct, p_pct = run_pass_share(log)
    if runs + passes <= 0:
        return None

    fig = go.Figure(
        go.Pie(
            labels=["Run", "Pass"],
            values=[runs, passes],
            hole=0.72,
            marker=dict(colors=["#22c55e", "#60a5fa"], line=dict(color="rgba(0,0,0,0.35)", width=1)),
            textinfo="none",
            hovertemplate="%{label}: %{value} plays (%{percent})<extra></extra>",
        )
    )
    fig.update_layout(
        title=dict(text=f"Tendency · {round(r_pct*100)}% run / {round(p_pct*100)}% pass", font=dict(size=12, color="#9ca3af")),
        margin=dict(l=0, r=0, t=30, b=0),
        height=220,
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        annotations=[
            dict(
                text=(
                    f"<span style='font-size:16px;color:#e5e7eb'>{round(r_pct*100)}%</span>"
                    f"<span style='font-size:12px;color:#9ca3af'> run</span><br>"
                    f"<span style='font-size:14px;color:#cbd5e1'>{round(p_pct*100)}%</span>"
                    f"<span style='font-size:12px;color:#9ca3af'> pass</span>"
                ),
                x=0.5,
                y=0.5,
                font=dict(size=12, color="#e5e7eb"),
                showarrow=False,
            ),
        ],
    )
    return fig

