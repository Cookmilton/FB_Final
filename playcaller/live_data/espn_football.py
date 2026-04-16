from __future__ import annotations

import time
from typing import Any, Dict, List, Literal, Optional, Tuple

from .http_util import fetch_json
from .types import FeedPlayEvent, FetchResult, NormalizedGameSnapshot

Sport = Literal["nfl", "college-football"]


def _sport_path(sport: Sport) -> str:
    return "football/nfl" if sport == "nfl" else "football/college-football"


def summary_url(sport: Sport, event_id: str) -> str:
    return f"https://site.api.espn.com/apis/site/v2/sports/{_sport_path(sport)}/summary?event={event_id}"


def scoreboard_url(sport: Sport) -> str:
    return f"https://site.api.espn.com/apis/site/v2/sports/{_sport_path(sport)}/scoreboard"


def _parse_clock_to_seconds(display_clock: Optional[str]) -> Optional[int]:
    if not display_clock:
        return None
    s = str(display_clock).strip()
    if not s or s.lower() in ("0:00", "00:00"):
        return 0
    parts = s.replace(" ", "").split(":")
    try:
        if len(parts) == 2:
            m, sec = int(parts[0]), int(parts[1])
            return max(0, min(15 * 60, m * 60 + sec))
        if len(parts) == 1:
            return max(0, int(parts[0]))
    except ValueError:
        return None
    return None


def _intish(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _competition(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    header = payload.get("header") or {}
    comps = header.get("competitions")
    if not comps:
        return None
    c0 = comps[0]
    return c0 if isinstance(c0, dict) else None


def list_espn_scoreboard_games(
    sport: Sport,
    *,
    limit: int = 30,
) -> List[Dict[str, Any]]:
    """
    Return recent games from the ESPN scoreboard (id, label, status, home, away).

    Each row: ``{"id", "label", "detail", "home_abbr", "away_abbr", "home_id", "away_id"}``.
    """
    data = fetch_json(scoreboard_url(sport))
    events = data.get("events") or []
    out: List[Dict[str, Any]] = []
    for ev in events[:limit]:
        if not isinstance(ev, dict):
            continue
        eid = str(ev.get("id") or "")
        if not eid:
            continue
        comps = ev.get("competitions") or []
        c0 = comps[0] if comps and isinstance(comps[0], dict) else {}
        st = (c0.get("status") or {}) if isinstance(c0, dict) else {}
        typ = (st.get("type") or {}) if isinstance(st, dict) else {}
        competitors = c0.get("competitors") or []
        home_abbr = away_abbr = home_id = away_id = ""
        for co in competitors:
            if not isinstance(co, dict):
                continue
            team = co.get("team") or {}
            tid = str(co.get("id") or team.get("id") or "")
            ab = str(team.get("abbreviation") or "")
            if co.get("homeAway") == "home":
                home_abbr, home_id = ab, tid
            elif co.get("homeAway") == "away":
                away_abbr, away_id = ab, tid
        name = str(ev.get("name") or ev.get("shortName") or f"{away_abbr} @ {home_abbr}")
        out.append(
            {
                "id": eid,
                "label": name,
                "detail": str(typ.get("detail") or typ.get("shortDetail") or ""),
                "home_abbr": home_abbr,
                "away_abbr": away_abbr,
                "home_id": home_id,
                "away_id": away_id,
            }
        )
    return out


def parse_espn_summary(
    payload: Dict[str, Any],
    *,
    sport: Sport,
    our_team_id: str,
) -> NormalizedGameSnapshot:
    """
    Map raw ESPN summary JSON into :class:`NormalizedGameSnapshot`.

    ``our_team_id`` is the ESPN numeric team id for the offense you coach (maps to ``Game`` "offense").
    """
    comp = _competition(payload)
    if not comp:
        raise ValueError("ESPN payload missing header.competitions[0]")

    eid = str(comp.get("id") or "")
    status = comp.get("status") or {}
    typ = status.get("type") or {}
    is_final = bool(typ.get("completed"))
    status_detail = str(typ.get("detail") or typ.get("shortDetail") or "")
    quarter = _intish(status.get("period"))
    clock_seconds_in_period = _parse_clock_to_seconds(status.get("displayClock"))

    situation = comp.get("situation")
    situation = situation if isinstance(situation, dict) else None

    down = distance = None
    abs_yards: Optional[int] = None
    possession_team_id: Optional[str] = None
    notes: List[str] = []

    if situation:
        down = _intish(situation.get("down"))
        distance = _intish(situation.get("distance"))
        yte = _intish(situation.get("yardsToEndzone"))
        if yte is not None:
            ytc = max(0, min(99, yte))
            abs_yards = 99 if ytc == 0 else max(1, min(99, 100 - ytc))
        possession_team_id = situation.get("teamPossessionId") or situation.get("possession")
        if possession_team_id is not None:
            possession_team_id = str(possession_team_id)
    else:
        notes.append("No in-game situation block (game may be final or between snaps).")

    our_score = opp_score = None
    our_tos = opp_tos = None
    competitors = comp.get("competitors") or []
    oid = str(our_team_id)
    for co in competitors:
        if not isinstance(co, dict):
            continue
        tid = str(co.get("id") or "")
        if not tid:
            continue
        sc = _intish(co.get("score"))
        if tid == oid:
            our_score = sc
        else:
            opp_score = sc
        # ESPN sometimes lists timeouts on competitor during live games
        to = _intish(co.get("timeouts"))
        if to is not None:
            if tid == oid:
                our_tos = to
            else:
                opp_tos = to

    poss_ours: Optional[bool] = None
    if possession_team_id:
        poss_ours = possession_team_id == oid

    new_plays, play_notes = _extract_recent_plays(payload, possession_team_id)
    notes.extend(play_notes)

    return NormalizedGameSnapshot(
        provider="espn",
        external_game_id=eid,
        sport=sport,
        fetched_at_epoch=time.time(),
        status_detail=status_detail,
        quarter=quarter,
        clock_seconds_in_period=clock_seconds_in_period,
        down=down,
        distance=distance,
        abs_yards_from_own_goal=abs_yards,
        possession_team_id=possession_team_id,
        possession_is_our_team=poss_ours,
        our_score=our_score,
        opponent_score=opp_score,
        our_timeouts=our_tos,
        opponent_timeouts=opp_tos,
        is_final=is_final,
        new_plays=tuple(new_plays),
        debug_notes=tuple(notes),
    )


def _extract_recent_plays(
    payload: Dict[str, Any],
    possession_team_id: Optional[str],
) -> Tuple[List[FeedPlayEvent], List[str]]:
    """Pull the last few plays from the current drive when ESPN exposes them."""
    notes: List[str] = []
    drives = payload.get("drives") or {}
    current = drives.get("current")
    plays_raw: List[Any] = []
    if isinstance(current, dict):
        plays_raw = list(current.get("plays") or [])
    if not plays_raw and isinstance(drives.get("previous"), list):
        prev = drives["previous"]
        if prev and isinstance(prev[-1], dict):
            plays_raw = list(prev[-1].get("plays") or [])
            notes.append("Using last archived drive for play tail (no current drive).")
    events: List[FeedPlayEvent] = []
    for p in plays_raw[-8:]:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id") or "")
        if not pid:
            continue
        tx = p.get("text") or p.get("statYardage")
        if isinstance(tx, dict):
            text = str(tx.get("text") or "")
        else:
            text = str(p.get("description") or "")
        if not text:
            text = "(no description)"
        yds = _intish(p.get("statYardage"))
        ty = p.get("type")
        if isinstance(ty, dict):
            ptype = str(ty.get("text") or "").lower()
        else:
            ptype = str(ty or "").lower()
        text_l = text.lower()
        if "rush" in ptype or "rushing" in ptype:
            th = "rush"
        elif "pass" in ptype or "sack" in text_l:
            th = "pass"
        elif "penalty" in text_l:
            th = "penalty"
        elif "kick" in text_l or "punt" in text_l or "field goal" in text_l:
            th = "kick"
        else:
            th = "unknown"
        events.append(FeedPlayEvent(event_id=pid, summary_text=text, yards_gained=yds, type_hint=th))
    _ = possession_team_id  # reserved for future filtering by team
    return events, notes


class EspnFootballProvider:
    """ESPN Site API provider for NFL or college football."""

    def __init__(self, sport: Sport) -> None:
        self.sport = sport

    def fetch_snapshot(self, event_id: str, *, our_team_id: str) -> FetchResult:
        try:
            url = summary_url(self.sport, event_id)
            data = fetch_json(url)
            snap = parse_espn_summary(data, sport=self.sport, our_team_id=str(our_team_id))
        except Exception as e:
            return FetchResult(ok=False, error=str(e))
        return FetchResult(ok=True, snapshot=snap)
