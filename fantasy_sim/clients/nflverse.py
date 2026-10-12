"""nflverse's published game lines -- a free second source for the week's totals and spreads.

`nflverse/nfldata`'s `games.csv` is the schedule file the any-given-stat site already reads. It
carries `total_line` and `spread_line` for the current week and the next, and nothing further
out (week 7 had none on 2026-10-12, week 6 had all 14). It is NOT a replacement for the Odds API
(one book per feed, refreshed on nflverse's own schedule, and it carries no weather); it is a
fallback and a cross-check. Pure parsing lives apart from the one network call so the suite can
test it without the network (F48).

nflverse convention: `spread_line` > 0 means the HOME team is favoured. Ours (`vegas_totals.json`)
is the team's own handicap, negative for the favourite, so the home spread is `-spread_line`.
"""
import csv
import io

import requests

from fantasy_sim.config import NFL_TEAM_ABBREVIATIONS

GAMES_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"

# nfldata still spells a few clubs the pre-relocation way; map them to the codes the rest of the
# repo uses. `LA` is the Rams (the any-given-stat game ids use it too).
TEAM_ALIASES = {"LA": "LAR", "JAC": "JAX", "OAK": "LV", "SD": "LAC", "STL": "LAR", "WSH": "WAS"}

_KNOWN = set(NFL_TEAM_ABBREVIATIONS.values())


def _code(raw):
    raw = (raw or "").strip().upper()
    return TEAM_ALIASES.get(raw, raw)


def parse_week_lines(text, season, week):
    """[{away, home, total, home_spread}] for one season's REGULAR-season week, only for games
    that carry BOTH a total and a spread and two clubs we know. `home_spread` is OUR sign
    (negative = the home team is favoured). A malformed row is skipped, never fatal."""
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            if str(row.get("season")) != str(season) or str(row.get("week")) != str(week):
                continue
            if (row.get("game_type") or "REG").upper() != "REG":
                continue
            total, spread = float(row["total_line"]), float(row["spread_line"])
            away, home = _code(row.get("away_team")), _code(row.get("home_team"))
        except (KeyError, TypeError, ValueError):
            continue
        if away not in _KNOWN or home not in _KNOWN:
            continue
        out.append({"away": away, "home": home, "total": total, "home_spread": -spread})
    return out


def implied_totals(rows, week_schedule=None):
    """{team: {"total", "spread", "opponent"}} -- the same shape and arithmetic the Odds API path
    writes (`total/2 -/+ home_spread/2`). With a `week_schedule` ({team: opponent}), a game the
    engine's own schedule does not have for this week is dropped: guessing is worse than the
    honest fallback, the rule the Odds path uses."""
    out = {}
    for r in rows:
        if week_schedule and week_schedule.get(r["home"]) != r["away"]:
            continue
        out[r["home"]] = {"total": round(r["total"] / 2.0 - r["home_spread"] / 2.0, 2),
                          "spread": r["home_spread"], "opponent": r["away"]}
        out[r["away"]] = {"total": round(r["total"] / 2.0 + r["home_spread"] / 2.0, 2),
                          "spread": -r["home_spread"], "opponent": r["home"]}
    return out


def fetch_week_lines(season, week, get=None, timeout=15):
    """Download games.csv and return `parse_week_lines`. Raises on any network or HTTP failure --
    the caller decides what a miss means."""
    resp = (get or requests.get)(GAMES_URL, timeout=timeout)
    resp.raise_for_status()
    return parse_week_lines(resp.text, season, week)
