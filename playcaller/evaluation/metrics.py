from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..domain import PASS_FAMILIES, RUN_FAMILIES
from .audit import aggressiveness_label, situation_bucket

_EXPLOSIVE_YARDS = 15


def _is_turnover(actual: Mapping[str, Any]) -> bool:
    if actual.get("turnover"):
        return True
    rt = str(actual.get("result_type", "")).lower()
    if rt in ("interception", "fumble"):
        return True
    pr = str(actual.get("pass_result", "")).lower()
    if pr == "intercepted":
        return True
    return False


def _is_explosive(actual: Mapping[str, Any]) -> bool:
    try:
        y = int(actual.get("yards_gained", 0))
    except (TypeError, ValueError):
        return False
    return y >= _EXPLOSIVE_YARDS


def _family_match(rec: Mapping[str, Any]) -> Optional[bool]:
    act = rec.get("linked_actual")
    if not isinstance(act, dict):
        return None
    af = str(act.get("family", "") or "")
    sf = str(rec.get("selected_family", "") or "")
    if not af or not sf:
        return None
    return af == sf


def evaluate_audit_records(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """
    Core metrics over closed (and optionally open) audit rows.

    Open rows contribute to recommendation distribution only where noted.
    """
    closed = [r for r in records if r.get("status") == "closed" and r.get("linked_actual")]
    open_only = [r for r in records if r.get("status") == "open"]
    all_reco = [r for r in records if r.get("status") != "void_undone"]

    def fam_counts(rows: Sequence[Mapping[str, Any]]) -> Counter:
        c: Counter = Counter()
        for r in rows:
            f = str(r.get("selected_family", "") or "")
            if f:
                c[f] += 1
        return c

    reco_families = fam_counts(all_reco)
    n_closed = len(closed)
    matches = sum(1 for r in closed if _family_match(r) is True)
    mismatches = sum(1 for r in closed if _family_match(r) is False)

    # Diversity: Shannon entropy of selected families (all recommendations)
    total_r = sum(reco_families.values()) or 1
    probs = [c / total_r for c in reco_families.values() if c > 0]
    entropy = -sum(p * math.log(p + 1e-12, 2) for p in probs)

    expl_after: List[Tuple[str, bool]] = []
    tov_after: List[Tuple[str, bool]] = []
    agg_pairs: List[Tuple[str, str]] = []
    situation_strength: Dict[str, Dict[str, int]] = {}

    for r in closed:
        act = r.get("linked_actual") or {}
        sf = str(r.get("selected_family", ""))
        pre = r.get("pre_snap") or {}
        sb = situation_bucket(pre if isinstance(pre, dict) else {})
        bucket = str(r.get("bucket", ""))
        if sb not in situation_strength:
            situation_strength[sb] = {"match": 0, "mismatch": 0, "n": 0}
        situation_strength[sb]["n"] += 1
        m = _family_match(r)
        if m is True:
            situation_strength[sb]["match"] += 1
        elif m is False:
            situation_strength[sb]["mismatch"] += 1

        expl_after.append((sf, _is_explosive(act)))
        tov_after.append((sf, _is_turnover(act)))
        afam = str(act.get("family", "") or "")
        if sf and afam:
            agg_pairs.append((aggressiveness_label(sf), aggressiveness_label(afam)))

    expl_by_fam: Counter = Counter()
    expl_hits_by_fam: Counter = Counter()
    for fam, ex in expl_after:
        expl_by_fam[fam] += 1
        if ex:
            expl_hits_by_fam[fam] += 1

    expl_rates = {
        fam: round(expl_hits_by_fam[fam] / expl_by_fam[fam], 3) if expl_by_fam[fam] else 0.0
        for fam in expl_by_fam
    }

    tov_rate = (
        round(sum(1 for _, t in tov_after if t) / len(tov_after), 3) if tov_after else 0.0
    )

    agg_align = sum(1 for a, b in agg_pairs if a == b)
    agg_total = len(agg_pairs)

    # "Reasonable" heuristic: short yardage + pass_family reco + run actual => flag
    questionable: List[str] = []
    for r in closed:
        pre = r.get("pre_snap") or {}
        if not isinstance(pre, dict):
            continue
        down = int(pre.get("down", 1))
        dist = int(pre.get("distance", 10))
        sf = str(r.get("selected_family", ""))
        act = r.get("linked_actual") or {}
        af = str(act.get("family", "") or "")
        if down < 4 and dist <= 2 and sf in PASS_FAMILIES and af in RUN_FAMILIES:
            questionable.append(
                f"{r.get('snap_id')}: short yardage recommended pass family, actual run family"
            )
        if down == 4 and dist >= 6 and sf in RUN_FAMILIES and "GO FOR IT" not in str(
            r.get("fourth_down_recommendation", "")
        ):
            pass  # conservative — skip noisy flags

    worst_situations = sorted(
        (
            (k, v["mismatch"] / max(1, v["match"] + v["mismatch"]), v["n"])
            for k, v in situation_strength.items()
            if v["match"] + v["mismatch"] > 0
        ),
        key=lambda x: (-x[1], -x[2]),
    )[:8]

    best_situations = sorted(
        (
            (k, v["match"] / max(1, v["match"] + v["mismatch"]), v["n"])
            for k, v in situation_strength.items()
            if v["match"] + v["mismatch"] > 0
        ),
        key=lambda x: (-x[1], -x[2]),
    )[:8]

    return {
        "n_audit_total": len(records),
        "n_closed_vs_actual": n_closed,
        "n_open_unlogged": len(open_only),
        "family_match_count": matches,
        "family_mismatch_count": mismatches,
        "family_match_rate": round(matches / n_closed, 3) if n_closed else None,
        "reco_family_entropy_bits": round(entropy, 3),
        "reco_family_counts": dict(reco_families),
        "explosive_rate_by_recommended_family": expl_rates,
        "turnover_rate_after_logged_play": tov_rate,
        "aggressiveness_alignment_rate": round(agg_align / agg_total, 3) if agg_total else None,
        "situation_buckets_weak": [
            {"situation": k, "mismatch_rate": round(r, 3), "n": n} for k, r, n in worst_situations
        ],
        "situation_buckets_strong": [
            {"situation": k, "match_rate": round(r, 3), "n": n} for k, r, n in best_situations
        ],
        "heuristic_flags": questionable[:20],
    }


def summarize_audit_session(records: Sequence[Mapping[str, Any]]) -> str:
    ev = evaluate_audit_records(records)
    lines = [
        f"Audit rows: {ev['n_audit_total']} (closed vs actual: {ev['n_closed_vs_actual']}, "
        f"open: {ev['n_open_unlogged']})",
        f"Family match rate: {ev['family_match_rate']}",
        f"Recommendation diversity (entropy bits): {ev['reco_family_entropy_bits']}",
        f"Turnover rate (logged plays): {ev['turnover_rate_after_logged_play']}",
        f"Aggressiveness alignment (run/pass family): {ev['aggressiveness_alignment_rate']}",
    ]
    weak = ev.get("situation_buckets_weak") or []
    if weak:
        lines.append("Weakest situation buckets (by mismatch rate): " + ", ".join(
            f"{w['situation']} ({w['mismatch_rate']}, n={w['n']})" for w in weak[:4]
        ))
    flags = ev.get("heuristic_flags") or []
    if flags:
        lines.append("Flags: " + "; ".join(flags[:3]))
    return "\n".join(lines)
