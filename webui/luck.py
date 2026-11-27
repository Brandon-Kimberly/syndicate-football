"""webui.luck -- the luck ledger, pulled not pushed (docs/WEB_UI_ROADMAP.md UI-R6).

The owner's call: luck is looked up, never put on Sunday's front page. This page leads with the
WINS ACCOUNTING (docs/LUCK_LEDGER.md Addendum 2, owner ruling 2026-11-27: one total, because it
is an identity whose parts are always shown with it), then the ledger's five PRE-REGISTERED
measures (fantasy_sim.luck_ledger) for one team -- no sixth measure (Decision 2 governs new
ones) and none of the five added to anything. It is reached from team pages and the palette
and never from Home.

The inputs are the ones scripts.luck_ledger fetches, read from disk instead:
  weekly scores   current/weekly_actuals.json (Sleeper's box scores -- re-scored weeks
                  included, which is why the ledger compares against the banked record)
  pairs           current/league_schedule.json
  projections     logs/predictions_2026.jsonl, the median block (as the script reads it)
  banked wins     current/league_standings.json h2h_wins (the league's total, both legs)
  who won         webui.results.week_results: the as-played record where it covers a week, so a
                  re-scored week keeps the result the league counted (audit 2026-09-29)
  points against  current/league_standings.json points_against, the league's own totals, when
                  every team has one (the sync stores them from 2026-09-29); else the box scores
  starters        NOT on disk: weekly_actuals keeps each player's points, not who started,
                  so "starters who did not play" is not measurable here and says so.

fantasy_sim.luck_ledger is pure (it imports only math); the engine is not imported.
"""
import json
import math

from fantasy_sim.luck_ledger import MIN_WEEKS_FOR_INFERENCE, direction, ledger, two_sided_p

REGULAR_WEEKS = 14

# The five, in the ledger's order, with what each measures in plain words. Pre-registered:
# a sixth entry here is a new measure, which Decision 2 has not made (tests.test_webui_ninth_batch).
MEASURES = (
    ("schedule_luck", "Schedule luck", "head-to-head wins minus the wins your all-play record would give you", "wins"),
    ("opponent_luck", "Opponent luck", "points scored against you per game, compared with the league average", "points a game"),
    ("close_games", "Close games", "wins in head-to-head games decided by less than 10 points, minus half of those games", "wins"),
    ("dnp_luck", "Starters who did not play", "starters who scored zero, per game, compared with the league average", "a game"),
    ("scoring_luck", "Scoring luck", "how far your weekly scores beat the projection, in spreads, compared with the league", "spreads"),
)


def _inputs(root):
    from webui.results import week_results
    scores = {}
    for n, teams in week_results(root).items():             # the league's banked points where known
        row = {t: float(r["points_scored"]) for t, r in teams.items()
               if isinstance(r, dict) and r.get("points_scored") is not None}
        if n <= REGULAR_WEEKS and row:
            scores[n] = row
    sched = root.read_json("current/league_schedule.json", []) or []
    pairs = {n: [tuple(p) for p in sched[n - 1] if len(p) == 2] for n in scores if 0 < n <= len(sched)}
    proj = {}
    try:
        with open(root.resolve_file("logs/predictions_2026.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                med, wk = r.get("median") or {}, r.get("week")
                if not med or wk is None or (wk in proj and not r.get("canonical")):
                    continue
                proj[wk] = {t: (float(v.get("expected_total") or 0.0), float(v.get("sd_total") or 0.0))
                            for t, v in med.items() if isinstance(v, dict)}
    except (FileNotFoundError, ValueError):
        pass
    standings = root.read_json("current/league_standings.json", {}) or {}
    banked = {t: int(float(s["h2h_wins"])) for t, s in standings.items() if isinstance(s, dict) and s.get("h2h_wins") is not None}
    results = {w: {t: (r.get("h2h_win"), r.get("median_win")) for t, r in teams.items()}
               for w, teams in week_results(root).items() if w in scores}
    pa = {t: s.get("points_against") for t, s in standings.items() if isinstance(s, dict)}
    pa = {t: float(v) for t, v in pa.items() if v is not None} if pa and all(v is not None for v in pa.values()) else None
    return scores, pairs, (proj or None), banked, results, pa


def report(root, team):
    scores, pairs, proj, banked, results, pa = _inputs(root)
    n = len(scores)
    median = any(r[1] is not None for teams in results.values() for r in teams.values())   # F95
    res = ledger(scores, pairs, team, starter_points=None, projections=proj, banked_wins=banked.get(team),
                 results=results, points_against=pa, median=median) if n else {}
    early = n < MIN_WEEKS_FOR_INFERENCE
    withheld = bool(res.get("banked_disagreement"))
    rows = []
    for key, label, what, unit in MEASURES:
        m = res.get(key)
        row = {"key": key, "label": label, "what": what, "unit": unit, "metric": m, "why_none": None,
               "way": None, "z": None, "p": None, "word": None}
        if m is None:
            if key == "dnp_luck":
                row["why_none"] = "can't be measured here: the weekly results record each player's points but not who started"
            elif key in ("schedule_luck", "close_games") and withheld:
                row["why_none"] = "withheld: the league's record and today's box scores disagree on who won (see below)"
            elif key == "scoring_luck":
                row["why_none"] = "not measurable yet: no week has both a pre-game projection and a result"
            else:
                row["why_none"] = "not measurable yet"
        else:
            row["way"] = direction(key, m.get("delta"))
            if not early and m.get("z") is not None:
                row["z"] = m["z"]
                row["p"] = two_sided_p(m["z"])
                row["word"] = "significant" if row["p"] < 0.05 else ("suggestive" if row["p"] < 0.20 else "noise")
        rows.append(row)
    return {"team": team, "weeks": n, "early": early, "min_weeks": MIN_WEEKS_FOR_INFERENCE, "rows": rows,
            "disagreement": res.get("banked_disagreement")}


# ---- the wins accounting (docs/LUCK_LEDGER.md Addendum 2, owner ruling 2026-11-27) ----------
# Addendum 3 adds lineup calls (lineup_calls below): a decision measure shown beside the luck,
# never a bar and never in the total. A file saved before it has none, and the page says nothing.
# One total, in wins, from parts that add up exactly; the five above stay separate and are
# never added in. scripts.luck_ledger computes it (it needs Sleeper's archived projections,
# which the web UI never fetches) and saves the league-wide result under data/local/luck/;
# this page reads the newest. Shared with the job page (webui.render._luck).

PARTS = (
    ("performance", "Players vs projection", "head-to-head games: your all-play record against the one your started lineups were projected to earn"),
    ("median", "Players vs projection, median games", "median wins against the ones your projections earned (a median game has no schedule, so this is player luck too)"),
    ("schedule", "Schedule", "head-to-head wins against your all-play record: who you happened to play, and when"),
)


def ordinal(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "—"
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def odds_text(part, unit="seasons"):
    """'unusual · about 1 in 19 seasons this unlucky or more', in the registered words."""
    if not part or part.get("share") is None:
        return "too early to say: fewer than %d weeks" % MIN_WEEKS_FOR_INFERENCE
    if part.get("way") == "neutral":
        return "no luck either way"
    n = part.get("one_in")
    odds = f"about 1 in {n}" if n else f"rarer than 1 in {part.get('one_in_floor')}"
    return f"{part.get('word')} · {odds} {unit} this {part.get('way')} or more"


def bar_rows(view):
    """The parts and the total as centred bars, one scale for all of them (in wins)."""
    parts = (view or {}).get("parts") or {}
    rows = []
    for key, label, what in PARTS:
        p = parts.get(key)
        if p:
            rows.append({"label": label, "what": what, "wins": float(p["wins"]), "odds": odds_text(p), "total": False})
    t = parts.get("total")
    if t:
        rows.append({"label": "Total", "what": "the parts above, added; nothing else goes in",
                     "wins": float(t["wins"]), "odds": odds_text(t), "total": True})
    scale = max([1.0] + [abs(r["wins"]) for r in rows])
    for r in rows:
        w = r["wins"]
        r["tone"] = "pos" if w >= 0.05 else ("neg" if w <= -0.05 else "")
        r["left"] = round(50.0 + min(0.0, w) / scale * 50.0, 2)
        r["width"] = round(abs(w) / scale * 50.0, 2)
        r["text"] = f"{w:+.1f}"
    return rows


def explain_lines(view):
    """'Where it came from', in sentences. Never added to anything."""
    x = (view or {}).get("explain") or {}
    out = []
    v = x.get("vs_projection_relative")
    if v is not None:
        out.append(f"Your starters scored {abs(v):.1f} points a week {'more' if v >= 0 else 'less'} against their "
                   f"projections than the league's did ({x.get('scored_per_week', 0):.1f} scored, "
                   f"{x.get('projected_per_week', 0):.1f} projected, a week).")
    v = x.get("dnp_points_relative")
    if v is not None:
        out.append(f"Starters who scored nothing cost you {abs(v):.1f} points a week {'more' if v >= 0 else 'less'} "
                   f"than the league average.")
    return out


def lineup_calls(view):
    """Addendum 3, for the pages: the roster's best lineups against the ones started. A
    DECISION measure, shown beside the luck and never in its bars or its total. None for a
    file written before lineup calls existed."""
    calls, roster = (view or {}).get("lineup_calls"), (view or {}).get("roster_expected")
    if not calls or not roster:
        return None
    w = float(calls["wins"])
    return {"wins": w, "wins_text": f"{w:+.1f}", "tone": "neg" if w <= -0.05 else "",
            "points_per_week": float(calls.get("points_per_week") or 0.0),
            "points_text": f"{float(calls.get('points_per_week') or 0.0):+.1f}",
            "weeks_short": calls.get("weeks_short"), "weeks": len((view or {}).get("weeks") or []),
            "roster": float(roster["total"]), "started": float(view["expected"]["total"]),
            "sentence": (f"The roster's best lineups were projected to earn {float(roster['total']):.1f} wins; "
                         f"the lineups started, {float(view['expected']['total']):.1f}. Lineup calls: {w:+.1f} wins "
                         f"({float(calls.get('points_per_week') or 0.0):+.1f} points a week; a better lineup was on the "
                         f"roster in {calls.get('weeks_short')} of {len((view or {}).get('weeks') or [])} weeks). "
                         "This is a decision, not luck, so it is never added into the luck.")}


def standings_rows(acc):
    rows = []
    for r in (acc or {}).get("standings") or []:
        rows.append(dict(r, actual_rank_text=ordinal(r.get("actual_rank")), neutral_rank_text=ordinal(r.get("neutral_rank")),
                         move=(r.get("actual_rank") or 0) - (r.get("neutral_rank") or 0)))
    return rows


def headline(view):
    """The four facts a reader wants first: luck in wins, how unusual, wins vs earned, rank."""
    if not view:
        return None
    t = view["parts"]["total"]
    if t.get("share") is None:
        short, word_ = "too early", f"fewer than {MIN_WEEKS_FOR_INFERENCE} weeks"
    elif t.get("way") == "neutral":
        short, word_ = "even", "no luck either way"
    else:
        short = f"1 in {t['one_in']}" if t.get("one_in") else f"under 1 in {t.get('one_in_floor')}"
        word_ = f"{t.get('word')}: seasons this {t.get('way')} or more"
    return {"luck": float(t["wins"]), "luck_text": f"{t['wins']:+.1f}", "tone": "pos" if t["wins"] >= 0.05 else ("neg" if t["wins"] <= -0.05 else ""),
            "odds": odds_text(t), "odds_short": short, "odds_word": word_,
            "actual": view["actual"]["total"], "expected": view["expected"]["total"],
            "actual_rank": ordinal(view.get("actual_rank")), "neutral_rank": ordinal(view.get("neutral_rank"))}


def load_accounting(root):
    """The newest saved league accounting, or None. data/local is never served, so this opens
    the file directly rather than through root.read_json."""
    import glob
    import os
    files = sorted(glob.glob(os.path.join(root.local, "luck", "accounting_*.json")))
    if not files:
        return None
    try:
        with open(files[-1], encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def accounting_for(root, team, closed_weeks=None):
    """The page's view of the saved accounting for `team`: None without a saved file, or with
    one that does not cover the team. `stale` when weeks have closed since it was computed."""
    acc = load_accounting(root)
    if not acc or team not in (acc.get("teams") or {}):
        return {"missing": True, "season": (acc or {}).get("season")} if not acc else None
    view = dict(acc["teams"][team], team=team, weeks=acc.get("weeks") or [])
    last = max(view["weeks"] or [0])
    return {"missing": False, "season": acc.get("season"), "computed_at": acc.get("computed_at"),
            "weeks": len(view["weeks"]), "stale": bool(closed_weeks and max(closed_weeks) > last),
            "head": headline(view), "bars": bar_rows(view), "explain": explain_lines(view),
            "calls": lineup_calls(view),
            "standings": standings_rows(acc), "left_out": acc.get("left_out") or []}


# ---- Decision 2 (owner ruling 2026-09-29): the three measures pre-registered in
# docs/LUCK_LEDGER.md's addendum (aaf9807), implemented exactly as defined there.

def _late_rows(root):
    """{week: {team: (won, quoted_h2h, median_won, quoted_median)}} for the weeks with both a
    result as the league counted it (F83) and a canonical pre-kickoff quote."""
    from webui.accuracy import chances_in, quoted_week
    from webui.results import week_results
    out, left_out = {}, []
    for w, teams in sorted(week_results(root).items()):
        if w > REGULAR_WEEKS:
            continue
        q = quoted_week(root, w)
        if not q:
            left_out.append(w)
            continue
        row = {}
        for t, r in teams.items():
            ch = chances_in(q, t) or {}
            row[t] = (r.get("h2h_win"), ch.get("h2h"), r.get("median_win"), ch.get("median"))
        out[w] = row
    return out, left_out


def _stat(delta, var, n, key):
    se = math.sqrt(var) if var > 0 else 0.0
    early = n < MIN_WEEKS_FOR_INFERENCE
    z = (delta / se) if se > 0 else None
    p = two_sided_p(z) if (z is not None and not early) else None
    return {"delta": delta, "se": se, "n": n, "way": direction("schedule_luck", delta),
            "z": None if early else (round(z, 2) if z is not None else None), "p": p,
            "word": None if p is None else ("significant" if p < 0.05 else ("suggestive" if p < 0.20 else "noise"))}


def late_measures(root, team):
    """forecast_luck and median_luck for `team`, as pre-registered. Each None without a quote."""
    rows, left_out = _late_rows(root)
    out = {}
    wins = [(float(v[0]), float(v[1])) for wk in rows.values() for t, v in wk.items()
            if t == team and v[0] is not None and v[1] is not None]
    out["forecast_luck"] = None if not wins else dict(
        _stat(sum(a - p for a, p in wins), sum(p * (1 - p) for _a, p in wins), len(wins), "forecast"),
        left_out=len(left_out) + sum(1 for wk in rows.values() if team in wk and (wk[team][0] is None or wk[team][1] is None)))
    raw = {}
    for wk in rows.values():
        for t, v in wk.items():
            if v[2] is not None and v[3] is not None:
                a, p = float(v[2]), float(v[3])
                d = raw.setdefault(t, [0.0, 0.0, 0])
                d[0] += a - p
                d[1] += p * (1 - p)
                d[2] += 1
    if team in raw:
        league = sum(v[0] for v in raw.values()) / len(raw)
        out["median_luck"] = dict(_stat(raw[team][0] - league, raw[team][1], raw[team][2], "median"), league=league)
    else:
        out["median_luck"] = None
    return out


def swap_matrix(root):
    """Each team's head-to-head record on each other team's schedule (pre-registered as
    descriptive): A's score against B's opponent each played week; in the week B met A, A meets
    B. Box scores, like all-play; `rescored` when a counted week is one Sleeper re-scores."""
    from webui.results import rescaled_weeks, week_results
    sched = root.read_json("current/league_schedule.json", []) or []
    scaled = rescaled_weeks(root)
    pts = {}
    for w, teams in week_results(root).items():
        if w > REGULAR_WEEKS:
            continue
        row = {t: float(r["points_scored"]) for t, r in teams.items() if r.get("points_scored") is not None}
        if row and 0 < w <= len(sched):
            pts[w] = row
    teams = sorted({t for row in pts.values() for t in row})
    cells = {a: {} for a in teams}
    for a in teams:
        for b in teams:
            wlt = [0, 0, 0]
            for w, row in pts.items():
                opp = next((x for pair in sched[w - 1] if b in pair for x in pair if x != b), None)
                if opp is None or a not in row:
                    continue
                other = b if opp == a else opp
                if other not in row:
                    continue
                wlt[0 if row[a] > row[other] else (1 if row[a] < row[other] else 2)] += 1
            cells[a][b] = tuple(wlt)
    return {"teams": teams, "cells": cells, "weeks": sorted(pts), "rescored": any(w in scaled for w in pts)}
