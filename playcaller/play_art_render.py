"""
Matplotlib renderer: compact horizontal “play art” card (broadcast / board style).

Kept separate from ``play_art_geometry`` so geometry can be tested without a display backend.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .domain import RUN_FAMILIES
from .play_art_geometry import (
    ROUTE_WAYPOINT_DELTAS,
    RUN_TRACK_DELTAS,
    board_label_for_position,
    classify_route_shape,
    classify_run_track,
    densify_polyline,
    ensure_layout_for_route_keys,
    formation_layout,
    offset_from_deltas,
    play_action_fake_vertices,
    qb_scramble_vertices,
    run_vertices,
)

# Visual theme (dark sideline console)
_FIELD_TOP = "#3d7a42"
_FIELD_MID = "#2f6b34"
_FIELD_EDGE = "#25632a"
_LOS = "#f8fafc"
_PRIMARY = "#fcd34d"
_SECONDARY = "#94a3b8"
_MUTED = "#64748b"
_QB_FILL = "#f1f5f9"


def _draw_field_strip(ax, xmin: float, xmax: float, ymin: float, ymax: float) -> None:
    from matplotlib import patches

    ax.add_patch(
        patches.Rectangle(
            (xmin, ymin),
            xmax - xmin,
            ymax - ymin,
            facecolor=_FIELD_MID,
            edgecolor=_FIELD_EDGE,
            lw=1.2,
            zorder=0,
        )
    )
    # Subtle horizontal bands (yard feel)
    for yi, alpha in [(0.22, 0.08), (0.48, 0.1), (0.72, 0.08)]:
        ax.axhspan(yi - 0.04, yi + 0.04, facecolor=_FIELD_TOP, alpha=alpha, zorder=0)
    # Hash marks on LOS
    for hx in (-0.82, -0.4, 0.0, 0.4, 0.82):
        ax.plot([hx, hx], [-0.02, 0.02], color=_LOS, lw=1.0, alpha=0.65, zorder=2)


def _plot_smooth_route(
    ax,
    xs: Sequence[float],
    ys: Sequence[float],
    *,
    color: str,
    lw: float,
    alpha: float,
    z: int,
    dashed: bool = False,
) -> None:
    ax.plot(
        xs,
        ys,
        color=color,
        lw=lw,
        alpha=alpha,
        zorder=z,
        solid_capstyle="round",
        solid_joinstyle="round",
        linestyle="--" if dashed else "-",
    )
    if len(xs) < 2:
        return
    # Arrowhead at end along final segment
    x0, y0 = xs[-2], ys[-2]
    x1, y1 = xs[-1], ys[-1]
    dx, dy = x1 - x0, y1 - y0
    mag = (dx * dx + dy * dy) ** 0.5
    if mag < 1e-6:
        return
    shrink = min(0.11, mag * 0.35)
    ux, uy = dx / mag, dy / mag
    ax.annotate(
        "",
        xy=(x1 - ux * shrink * 0.2, y1 - uy * shrink * 0.2),
        xytext=(x1 - ux * shrink, y1 - uy * shrink),
        arrowprops=dict(
            arrowstyle="-|>",
            color=color,
            lw=max(0.8, lw * 0.65),
            alpha=alpha,
            mutation_scale=10 + lw * 2,
        ),
        zorder=z + 1,
    )


def _draw_qb_rb(
    ax,
    qb_xy: Tuple[float, float],
    layout: Dict[str, Tuple[float, float]],
    *,
    show_rb_dot: bool,
) -> None:
    qx, qy = qb_xy
    ax.plot([qx], [qy], "o", color=_QB_FILL, ms=8, zorder=8, markeredgecolor="#334155", markeredgewidth=0.8)
    ax.text(qx, qy - 0.065, "QB", ha="center", va="top", fontsize=7, color="#0f172a", fontweight="600", zorder=9)
    if not show_rb_dot:
        return
    rb = layout.get("RB", (0.0, -0.14))
    ax.plot([rb[0]], [rb[1]], "s", color=_PRIMARY, ms=7, zorder=8, markeredgecolor="#b45309", markeredgewidth=0.6)
    ax.text(
        rb[0],
        rb[1] - 0.068,
        board_label_for_position("RB"),
        ha="center",
        va="top",
        fontsize=7,
        color="#1e293b",
        fontweight="600",
        zorder=9,
    )


def build_play_art_figure(
    play: Dict[str, Any],
    play_family: str,
    primary_position: Optional[str] = None,
    *,
    result_type_hint: Optional[str] = None,
    figsize: Tuple[float, float] = (6.8, 3.05),
    dpi: int = 110,
):
    """
    Build a compact wide “play art” figure.

    ``result_type_hint`` — when ``\"scramble\"``, draws a QB scramble stem in gold.
    """
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return None

    routes: Dict[str, str] = play.get("routes") or {}
    formation = str(play.get("formation") or "")
    base_layout = formation_layout(formation)
    layout = ensure_layout_for_route_keys(base_layout, list(routes.keys()))

    xmin, xmax = -1.02, 1.02
    ymin, ymax = -0.28, 0.98

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi, facecolor="#0f172a")
    ax.set_facecolor("#0f172a")

    _draw_field_strip(ax, xmin, xmax, ymin, ymax)

    # Line of scrimmage (thick)
    ax.axhline(0, color=_LOS, lw=2.4, zorder=3)
    ax.text(
        xmax - 0.06,
        0.02,
        "LOS",
        ha="right",
        va="bottom",
        fontsize=7,
        color=_LOS,
        alpha=0.85,
        fontweight="600",
        zorder=4,
    )

    qb_xy = (0.0, -0.065)
    pri = primary_position if primary_position and primary_position in routes else None

    run_only = (
        play_family in RUN_FAMILIES
        or (not routes and play.get("run_scheme"))
        or (play_family == "two_point" and play.get("run_scheme") and not routes)
    )

    if run_only:
        track = classify_run_track(str(play.get("run_scheme") or ""), play_family)
        rb_base = layout.get("RB", (0.0, -0.14))
        _draw_qb_rb(ax, qb_xy, layout, show_rb_dot=track != "qb_sneak")
        verts = run_vertices(rb_base, track)
        smooth = densify_polyline(verts, steps_per_segment=20)
        xs, ys = zip(*smooth)
        _plot_smooth_route(ax, xs, ys, color=_PRIMARY, lw=3.1, alpha=1.0, z=4)
        if track == "qb_sneak":
            qv = offset_from_deltas(qb_xy, RUN_TRACK_DELTAS["qb_sneak"])
            sx, sy = zip(*densify_polyline(qv, 16))
            _plot_smooth_route(ax, sx, sy, color=_PRIMARY, lw=3.0, alpha=1.0, z=4)
        title = re.sub(r"\s+", " ", (play.get("name") or "Run concept")[:44])
        ax.set_title(title, fontsize=11, color="#f1f5f9", fontweight="600", pad=8)
        sub = (play.get("run_scheme") or "").strip()
        if sub and sub.lower() != title.lower():
            ax.text(0, ymax - 0.06, sub[:56], ha="center", va="top", fontsize=8, color="#cbd5e1", zorder=4)
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.axis("off")
        fig.tight_layout(pad=0.25)
        return fig

    if not routes:
        plt.close(fig)
        return None

    _draw_qb_rb(ax, qb_xy, layout, show_rb_dot=True)

    # Play-action: dashed RB sell before routes
    if play_family == "play_action":
        fake = play_action_fake_vertices(layout.get("RB", (0.0, -0.14)))
        fx, fy = zip(*densify_polyline(fake, 14))
        _plot_smooth_route(ax, fx, fy, color=_MUTED, lw=1.4, alpha=0.75, z=3, dashed=True)

    if result_type_hint == "scramble":
        sv = qb_scramble_vertices(qb_xy)
        sx, sy = zip(*densify_polyline(sv, 18))
        _plot_smooth_route(ax, sx, sy, color=_PRIMARY, lw=2.9, alpha=0.95, z=5)

    # Sort so primary draws on top: draw non-primary first
    ordered = sorted(
        routes.items(),
        key=lambda kv: (pri is not None and kv[0] == pri, kv[0]),
    )

    for pos, txt in ordered:
        if pos not in layout:
            continue
        base = layout[pos]
        shape = classify_route_shape(txt)
        deltas = ROUTE_WAYPOINT_DELTAS.get(shape, ROUTE_WAYPOINT_DELTAS["stem"])
        verts = offset_from_deltas(base, deltas)
        smooth = densify_polyline(verts, steps_per_segment=22)
        xs, ys = zip(*smooth)
        is_pri = pri is not None and pos == pri
        col = _PRIMARY if is_pri else _SECONDARY
        lw = 3.15 if is_pri else 1.45
        al = 1.0 if is_pri else 0.58
        z = 5 if is_pri else 4
        _plot_smooth_route(ax, xs, ys, color=col, lw=lw, alpha=al, z=z)

        lbl = board_label_for_position(pos)
        ax.plot(
            [base[0]],
            [base[1]],
            "o",
            color=col,
            ms=8 if is_pri else 5.5,
            zorder=9,
            markeredgecolor="#0f172a",
            markeredgewidth=0.55,
        )
        ax.text(
            base[0],
            base[1] - 0.072,
            lbl + (" •" if is_pri else ""),
            ha="center",
            va="top",
            fontsize=7 if is_pri else 6.5,
            color=col if is_pri else "#e2e8f0",
            fontweight="700" if is_pri else "500",
            zorder=10,
        )

    title = re.sub(r"\s+", " ", (play.get("name") or "Pass concept")[:44])
    ax.set_title(title, fontsize=11, color="#f1f5f9", fontweight="600", pad=8)
    ax.text(
        0,
        ymin + 0.04,
        "Gold = primary read · Gray = secondary",
        ha="center",
        va="bottom",
        fontsize=7,
        color="#64748b",
        zorder=4,
    )

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.axis("off")
    fig.tight_layout(pad=0.25)
    return fig


__all__ = ["build_play_art_figure"]
