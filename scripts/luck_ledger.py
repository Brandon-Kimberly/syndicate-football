#!/usr/bin/env python3
"""
Am I actually unlucky, or does it just feel that way? -- five pre-registered measurements.

Deliberately NOT part of the weekly report. This is a thing you pull when you want it,
not a number in your face every Sunday (owner's call, 2026-09-21).

  py -3.10 -m scripts.luck_ledger                      # current season
  py -3.10 -m scripts.luck_ledger --season 2025
  py -3.10 -m scripts.luck_ledger --all                # every season in the renewal chain
  py -3.10 -m scripts.luck_ledger --json

The definitions are FIXED in fantasy_sim/luck_ledger.py and documented in
docs/LUCK_LEDGER.md. They were pre-registered before the 2026 data existed; the git
history is the timestamp. Changing one after seeing what it says would make this a story
instead of a test, so don't.

Every metric is differenced against the LEAGUE, never against zero -- the engine carries
known bias (bias -2.12, cover80 0.654) and scoring a team against an absolute would
re-measure the model's error and call it luck.

Read the standard errors before the deltas. At two or three weeks nothing here is
significant and the tool will say so.

Since 2026-11-27 it leads with the WINS ACCOUNTING (fantasy_sim.luck_accounting; registered as
docs/LUCK_LEDGER.md Addendum 2): actual wins against what the projections of the lineups
actually started earned, split into players-vs-projection, schedule and median parts that add
up exactly, with "about 1 in N" from a simulated null and luck-neutral standings. It fetches
Sleeper's archived weekly projections (cached under data/local/luck/projections) and saves the
league-wide result to data/local/luck/accounting_<season>.json for the web UI's luck page.
Since Addendum 3 (registered 2026-11-27) it also reports LINEUP CALLS beside the luck, never in
it: what each roster's best lineup (the web UI's solver, each season's own starting slots,
eligibility from the sync's players cache) was projected to earn, against the lineups started.
With --all it also totals the team's luck across the seasons; an older season follows the
chosen team's OWNER (F96), and says so when that owner was not in the league.
"""
import argparse
import json
import os
import textwrap as _textwrap
from collections import defaultdict

import requests

from fantasy_sim.config import BASE_URL, LEAGUE_ID, MY_TEAM, TEAM_NAME_MAP, KNOWN_LEAGUE_IDS
from fantasy_sim.league_chain import resolve_chain
from fantasy_sim.luck_accounting import accounting, across_seasons
from fantasy_sim.luck_ledger import (MIN_WEEKS_FOR_INFERENCE, direction, ledger,
                                     two_sided_p)
from fantasy_sim.weekly_report import real_name_overlay


def _get(url):
    r = requests.get(url, timeout=45)
    r.raise_for_status()
    return r.json()


def _league_chain():
    """(season, league_id, info) for every season, newest first.

    B20: walks previous_league_id AND falls back to config.KNOWN_LEAGUE_IDS, because this
    league's chain is broken at 2025 -- without the map, --all silently stopped one season
    short. The shared walker lives in fantasy_sim.league_chain so this and
    scripts.season_retrospective cannot drift apart.
    """
    seen = {}

    def fetch(lid):
        seen[str(lid)] = info = _get(f"{BASE_URL}/league/{lid}") or {}
        return info

    pairs = resolve_chain(LEAGUE_ID, fetch=fetch, known=KNOWN_LEAGUE_IDS)
    # Seasons supplied by the map were never fetched by the walk; fetch them now.
    return [(season, lid, seen.get(str(lid)) or fetch(lid)) for season, lid in pairs]


def _team_names(lid, info):
    """roster_id -> display name. The current league uses the pseudonym map; older
    seasons fall back to that season's own team names."""
    rosters = _get(f"{BASE_URL}/league/{lid}/rosters")
    if str(lid) == str(LEAGUE_ID):
        return {r["roster_id"]: TEAM_NAME_MAP.get(str(r["roster_id"]), f"roster {r['roster_id']}")
                for r in rosters}
    users = {u["user_id"]: (u.get("metadata", {}).get("team_name") or u.get("display_name"))
             for u in _get(f"{BASE_URL}/league/{lid}/users")}
    return {r["roster_id"]: users.get(r.get("owner_id"), f"roster {r['roster_id']}")
            for r in rosters}


def closed_weeks(counted, per_week):
    """How many weeks the league has CLOSED: the fewest games any team has banked, in weeks.

    F95: a week used to count as played as soon as any team had a point, so on Thanksgiving
    Friday week 12 -- three games in, 5 to 12 of every team's 13 starters still to play --
    went in as a finished week, and every unplayed starter as a starter who did not play.
    The league's own record moves only when a week closes. None when there is no record."""
    games = [c.get("games") for c in (counted or {}).values() if c.get("games") is not None]
    if not games or not per_week:
        return None
    return min(games) // per_week


def _season_data(lid, info, names, through_week=None, ids=None, rosters=None, played=None):
    """weekly_scores, pairs, starter_points for a season -- completed weeks only. The caller
    passes `through_week` = the last CLOSED week (closed_weeks), never just a week that has
    started (F95). `ids`, when given, is filled with {week: {team: [starter player id, ...]}}
    in the same order as starter_points (the wins accounting prices those players), and
    `rosters` with {week: {team: [every player id on the roster that week]}} (Sleeper's matchup
    `players`, IR slots included: Addendum 3's roster), and `played` with {week: {player id:
    points}} for every player Sleeper scored that week (Addendum 4: did he play)."""
    last = int(info.get("settings", {}).get("playoff_week_start") or 15) - 1
    if through_week is not None:
        last = min(last, int(through_week))
    scores, pairs, starters = {}, {}, {}
    for wk in range(1, last + 1):
        try:
            ms = _get(f"{BASE_URL}/league/{lid}/matchups/{wk}") or []
        except Exception:
            continue
        row, by_mid, srow = {}, defaultdict(list), {}
        live = False
        for m in ms:
            rid = m["roster_id"]
            t = names.get(rid, f"roster {rid}")
            pts = float(m.get("points") or 0.0)
            row[t] = pts
            if pts > 0:
                live = True
            pp = m.get("players_points") or {}
            sids = [str(s) for s in (m.get("starters") or []) if s and str(s) != "0"]
            srow[t] = [float(pp.get(s) or 0.0) for s in sids]
            if ids is not None:
                ids.setdefault(wk, {})[t] = sids
            if rosters is not None:
                rosters.setdefault(wk, {})[t] = [str(p) for p in (m.get("players") or []) if p and str(p) != "0"]
            if played is not None:
                played.setdefault(wk, {}).update({str(p): float(v or 0.0) for p, v in pp.items()})
            if m.get("matchup_id") is not None:
                by_mid[m["matchup_id"]].append(t)
        if not live:
            if ids is not None:
                ids.pop(wk, None)
            if rosters is not None:
                rosters.pop(wk, None)
            if played is not None:
                played.pop(wk, None)
            continue                     # week hasn't been played
        scores[wk] = row
        starters[wk] = srow
        pairs[wk] = [tuple(v) for v in by_mid.values() if len(v) == 2]
    return scores, pairs, starters


def _banked_wins(lid, names):
    """{team: Sleeper's own settings.wins} -- the record the league BANKED (C4/F70).

    Every `points` value this tool reads is what Sleeper serves TODAY, re-scored under the
    league's CURRENT settings, so a mid-season scoring change rewrites finished weeks
    (F49's IDP cut flipped one on 2026-09-23). This number is not re-scored: it was
    written when the week closed. The two disagreeing is the only available signal that
    the scores are rewritten history.

    NOTE the field is TOTAL wins -- both legs of a median-scoring week -- which is why
    luck_ledger.banked_disagreement compares it against h2h wins PLUS median wins.
    """
    try:
        rosters = _get(f"{BASE_URL}/league/{lid}/rosters")
    except Exception:
        return {}
    out = {}
    for r in rosters or []:
        t = names.get(r.get("roster_id"))
        w = (r.get("settings") or {}).get("wins")
        if t is not None and w is not None:
            out[t] = int(w)
    return out


def _counted(lid, names):
    """{team: {wins, games, points_against}} -- the league's own record, as it was counted
    (settings.wins/losses/ties and fpts_against, none of them re-scored). {} on failure."""
    from fantasy_sim.sync import sleeper_points
    try:
        rosters = _get(f"{BASE_URL}/league/{lid}/rosters")
    except Exception:
        return {}
    out = {}
    for r in rosters or []:
        t, st = names.get(r.get("roster_id")), (r.get("settings") or {})
        if t is None or st.get("wins") is None:
            continue
        out[t] = {"wins": int(st["wins"]), "games": int(st.get("wins") or 0) + int(st.get("losses") or 0) + int(st.get("ties") or 0),
                  "points_against": sleeper_points(st, "fpts_against") if st.get("fpts_against") is not None else None}
    return out


def _as_played(season, logs_dir=os.path.join("data", "logs")):
    """{week: {team: (h2h_win, median_win)}} from the as-played record (scripts.as_played_record,
    F83): who won each re-scored week, as the league counted it. {} for a season without one."""
    try:
        with open(os.path.join(logs_dir, f"as_played_results_{season}.json"), encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return {}
    out = {}
    for key, teams in (doc or {}).items():
        if not str(key).startswith("week_") or not isinstance(teams, dict):
            continue
        try:
            wk = int(str(key)[5:])
        except ValueError:
            continue
        out[wk] = {t: (r.get("h2h_win"), r.get("median_win")) for t, r in teams.items() if isinstance(r, dict)}
    return out


def _banked(season, path=os.path.join("data", "current", "banked_scores.json")):
    """{week: {team: (points, h2h_win, median_win)}} from the sync's banked scores
    (fantasy_sim.banked_scores) for `season`: each past week as the league banked it. {} for
    another season, or unless the file says verified -- nothing unchecked replaces a score."""
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return {}
    meta = (doc or {}).get("_meta") or {}
    if not meta.get("verified") or str(meta.get("season")) != str(season):
        return {}
    out = {}
    for key, teams in doc.items():
        if not str(key).startswith("week_") or not isinstance(teams, dict):
            continue
        try:
            wk = int(str(key)[5:])
        except ValueError:
            continue
        out[wk] = {t: (r.get("points"), r.get("h2h_win"), r.get("median_win")) for t, r in teams.items()
                   if isinstance(r, dict) and r.get("points") is not None}
    return out


def _projections(season):
    """{week: {team: (expected_total, sd)}} from the committed predictions log.

    Only exists from 2026 -- the log started with this season, so earlier years get an
    honest None for scoring_luck rather than a fabricated one.
    """
    try:
        rows = [json.loads(l) for l in open("data/logs/predictions_2026.jsonl") if l.strip()]
    except OSError:
        return None
    if str(season) != "2026":
        return None
    out = {}
    for r in rows:
        med = r.get("median") or {}
        wk = r.get("week")
        if not med or wk is None:
            continue
        # last canonical row for a week wins; fall back to any row for that week
        if wk in out and not r.get("canonical"):
            continue
        out[wk] = {t: (float(v.get("expected_total") or 0.0), float(v.get("sd_total") or 0.0))
                   for t, v in med.items() if isinstance(v, dict)}
    return out or None


# ----------------------------------------------------------------- the wins accounting
# Registered in docs/LUCK_LEDGER.md (Addendum 2) before this code. Its inputs: Sleeper's
# weekly projection of every player a team STARTED, scored under the settings in force that
# week. Sleeper keeps past weeks' projections (checked 2026-11-27 against the sync's own
# pre-game log: 103 of 104 starters within 0.5 points, weeks 3 and 10).

LUCK_DIR = os.path.join("data", "local", "luck")     # gitignored, never served raw


def _settings_by_week(season, lid, info, weeks):
    """{week: scoring settings in force}. The current season reads the eras the banked scores
    were checked against (data/current/banked_scores.json + data/logs/scoring_settings.jsonl);
    any other week, or any season without them, gets the league's settings as served -- the
    settings its box scores are re-scored under."""
    default = (info or {}).get("scoring_settings") or {}
    out = {w: default for w in weeks}
    if str(lid) != str(LEAGUE_ID):
        return out
    try:
        from fantasy_sim.banked_scores import eras
        from fantasy_sim.storage import BANKED_SCORES_FILE, SCORING_SETTINGS_FILE
        with open(BANKED_SCORES_FILE, encoding="utf-8") as fh:
            meta = (json.load(fh) or {}).get("_meta") or {}
        if str(meta.get("season")) != str(season) or not meta.get("verified"):
            return out
        by_time = {e["observed_at"]: e["settings"] for e in eras(SCORING_SETTINGS_FILE, season)}
        for w in weeks:
            got = by_time.get((meta.get("eras") or {}).get(str(w)))
            if got:
                out[w] = got
    except (OSError, ValueError, KeyError, ImportError):
        pass
    return out


def _week_projection(season, week, settings):
    """{player_id: projected points} for one CLOSED week, scored under `settings`, cached
    under data/local/luck/projections (a past week's projection does not change). {} when
    Sleeper serves nothing; an empty answer is never cached."""
    import hashlib
    from fantasy_sim.banked_scores import player_points
    digest = hashlib.sha256(json.dumps(settings or {}, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    path = os.path.join(LUCK_DIR, "projections", f"{season}_w{int(week):02d}_{digest}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        pass
    try:
        raw = _get(f"{BASE_URL}/projections/nfl/regular/{season}/{week}") or {}
    except Exception:
        return {}
    out = {}
    for pid, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        pts = player_points(entry.get("stats", entry), settings)
        if pts:
            out[str(pid)] = pts
    if out:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(out, fh)
            os.replace(tmp, path)
        except OSError:
            pass
    return out


PLAYERS_CACHE = os.path.join("data", "current", "sleeper_players_cache.json")
PROJECTION_LOG = os.path.join("data", "logs", "projection_log.jsonl")
NFL_SCHEDULE = os.path.join("data", "current", "nfl_schedule.json")


def _prekickoff_log(season, log_path=None, schedule_path=None):
    """Addendum 4: {(week, player id): sleeper_mean} from the sync's projection log -- the newest
    row for that player and week logged before the week's FIRST kickoff (the row the team page's
    "Before the games" uses). {} for a season the log does not cover, or without kickoffs."""
    try:
        with open(schedule_path or NFL_SCHEDULE, encoding="utf-8") as fh:
            stamps = ((json.load(fh) or {}).get("_meta") or {}).get("kickoffs") or {}
    except (OSError, ValueError):
        return {}
    first = {}
    for wk, times in stamps.items():
        times = sorted(str(t).replace("+00:00", "Z") for t in (times or []) if t)
        if times:
            try:
                first[int(wk)] = times[0]
            except (TypeError, ValueError):
                continue
    out, at = {}, {}
    try:
        with open(log_path or PROJECTION_LOG, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return {}
    for line in lines:
        try:
            r = json.loads(line)
            wk, pid = int(r["week"]), str(r["player_id"])
        except (ValueError, KeyError, TypeError):
            continue
        stamp, ko = str(r.get("synced_at") or ""), first.get(wk)
        if str(r.get("season")) != str(season) or not stamp or ko is None or stamp >= ko:
            continue                             # another season, or logged after the first kickoff
        if (wk, pid) not in at or stamp >= at[(wk, pid)]:
            at[(wk, pid)] = stamp
            out[(wk, pid)] = r.get("sleeper_mean")
    return out


def _fill_gaps(week, proj, roster, played, log):
    """Addendum 4: `proj` with every player in `roster` the archive prices at 0 or omits, who
    scored (not 0.00) that week, priced from the pre-kickoff log when it holds more than 0.
    Returns (projection, the ids filled). An archived projection is never replaced. `log` may
    be a callable: it is read only when there is a gap to fill."""
    out, filled = proj, []
    for pid in roster:
        if proj.get(pid) or not (played or {}).get(pid):
            continue
        if callable(log):
            log = log()
        try:
            mean = float(log.get((week, pid)) or 0.0)
        except (TypeError, ValueError):
            mean = 0.0
        if mean > 0:
            if out is proj:
                out = dict(proj)
            out[pid] = mean
            filled.append(pid)
    return out, filled
NOT_STARTING = ("BN", "IR", "TAXI")


def starting_slots(info):
    """That season's own starting slots (Addendum 3): the league's roster_positions less the
    bench, IR and taxi spots. 2024 had fifteen, 2025 eleven, 2026 thirteen."""
    return [p for p in ((info or {}).get("roster_positions") or []) if p not in NOT_STARTING]


def _eligibility(path=None):
    """{player_id: {"pos", "slots"}} from the sync's players cache (Sleeper's fantasy_positions,
    as of the last sync). {} when there is no cache: then no best lineup is computed."""
    try:
        with open(path or PLAYERS_CACHE, encoding="utf-8") as fh:
            cache = json.load(fh) or {}
    except (OSError, ValueError):
        return {}
    return {str(pid): {"pos": c.get("position"), "slots": list(c.get("fantasy_positions") or [])}
            for pid, c in cache.items() if isinstance(c, dict)}


def _best_projection(roster, proj, slots, elig):
    """Addendum 3's P_best before the floor at what was started: the most a legal lineup from
    `roster` projects, solved by the web UI's own exact solver (webui.trade.best_lineup, the
    one behind the team page's "Before the games"). A player the cache does not know is
    eligible for no slot; a player with no projection counts 0."""
    from webui.trade import best_lineup
    pool = {pid: dict(elig[pid], mean=float(proj.get(pid, 0.0))) for pid in roster if pid in elig}
    total, _used, _empty = best_lineup(pool, None, slots)
    return total


def _projected_lineups(season, lid, info, ids, starters, rosters=None, elig=None, played=None, log=None):
    """(projected {week: {team: total}}, detail {week: {team: [(projected, scored), ...]}},
    best {week: {team: best lineup's projection}} or None) for every started player. A week
    Sleeper serves no projections for is left out. `best` needs the rosters, the eligibility
    and the season's starting slots (Addendum 3); without any of them it is None. `played` and
    `log` fill the archive's gaps (Addendum 4); the fourth value is how many player-weeks
    were filled."""
    weeks = sorted(ids)
    settings = _settings_by_week(season, lid, info, weeks)
    slots = starting_slots(info)
    can_solve = bool(rosters and elig and slots)
    projected, detail, best, filled = {}, {}, {}, set()
    memo = {}

    def lazy():
        if "log" not in memo:
            memo["log"] = (log() if callable(log) else log) or {}
        return memo["log"]

    for w in weeks:
        proj = _week_projection(season, w, settings[w])
        if not proj:
            continue
        if log is not None:                      # Addendum 4: every roster player of the week
            everyone = [p for t in ids[w] for p in (((rosters or {}).get(w) or {}).get(t) or ids[w][t])]
            proj, got = _fill_gaps(w, proj, everyone, (played or {}).get(w), lambda: lazy())
            filled.update((w, p) for p in got)
        for t, pids in ids[w].items():
            got = (starters.get(w) or {}).get(t) or []
            pairs = [(float(proj.get(p, 0.0)), float(got[i]) if i < len(got) else 0.0)
                     for i, p in enumerate(pids)]
            projected.setdefault(w, {})[t] = round(sum(p for p, _s in pairs), 2)
            detail.setdefault(w, {})[t] = pairs
            roster = ((rosters or {}).get(w) or {}).get(t)
            if can_solve and roster:
                best.setdefault(w, {})[t] = _best_projection(roster, proj, slots, elig)
    return projected, detail, (best if can_solve and best else None), len(filled)


def _save_accounting(season, acc):
    """The league-wide accounting for the web UI's luck page (data/local/luck/, gitignored)."""
    import datetime
    doc = dict(acc, season=str(season),
               computed_at=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    path = os.path.join(LUCK_DIR, f"accounting_{season}.json")
    try:
        os.makedirs(LUCK_DIR, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1)
        os.replace(tmp, path)
    except OSError:
        pass


def team_view(acc, team):
    """One team's slice of the league accounting, with the league-level fields it needs."""
    if not acc or team not in (acc.get("teams") or {}):
        return None
    return {k: acc[k] for k in ("weeks", "left_out", "median", "sigma", "simulations", "seed", "early", "standings")} \
        | {"filled_from_log": acc.get("filled_from_log") or 0, "team": team, **acc["teams"][team]}


def _wins(v):
    return f"{v:+.1f} win{'' if abs(round(v, 1)) == 1 else 's'}"


def _how_rare(part):
    if part.get("share") is None:
        return "too early to say"
    if part["way"] == "neutral":
        return "no luck either way"
    n = part.get("one_in")
    odds = f"about 1 in {n}" if n else f"rarer than 1 in {part['one_in_floor']}"
    return f"{part['word']}: {odds} seasons are this {part['way']} or more"


def render_accounting(view, team_label, ov=None):
    """The headline: wins, against what the lineups started were projected to earn."""
    ov = ov or {}
    a, e, p, x = view["actual"], view["expected"], view["parts"], view["explain"]
    total = p["total"]["wins"]
    print(f"\n  WINS AND LUCK ({len(view['weeks'])} weeks)")
    print(f"    {a['total']:g} wins; the lineups you started were projected to earn {e['total']:.1f}.")
    verb = "cost you" if total < 0 else "gave you"
    print(f"    Luck {verb} {abs(total):.1f} win{'s' if abs(round(total, 1)) != 1 else ''} "
          f"({_how_rare(p['total'])}).")
    rows = [("players vs projection", p["performance"]), ("schedule", p["schedule"])]
    if p.get("median"):
        rows.append(("median games", p["median"]))
    for label, part in rows:
        print(f"      {label:22s} {_wins(part['wins']):>11s}   {_how_rare(part)}")
    print(f"      {'total':22s} {_wins(total):>11s}   the three added; nothing else goes in")
    print(f"    Standings: {_ordinal(view['actual_rank'])} as played, {_ordinal(view['neutral_rank'])} "
          f"with every team's luck taken out.")
    bits = []
    if x.get("vs_projection_relative") is not None:
        bits.append(f"starters {abs(x['vs_projection_relative']):.1f} points a week "
                    f"{'above' if x['vs_projection_relative'] >= 0 else 'below'} projection, compared with the league")
    if x.get("dnp_points_relative") is not None:
        bits.append(f"{abs(x['dnp_points_relative']):.1f} points a week "
                    f"{'more' if x['dnp_points_relative'] >= 0 else 'less'} than the league lost to starters who scored nothing")
    if bits:
        print("    Where it came from (not added in): " + "; ".join(bits) + ".")
    render_lineup_calls(view)
    if view.get("left_out"):
        print(f"    Weeks with no projections, left out: {', '.join(str(w) for w in view['left_out'])}.")
    if view.get("filled_from_log"):
        n = view["filled_from_log"]
        print(f"    {n} player-week{'s' if n != 1 else ''} the projection archive missed, for players who then "
              f"played, priced from the sync's last pre-kickoff projection (Addendum 4).")


def render_lineup_calls(view):
    """Addendum 3: the roster's best lineups against the ones started. A decision, never luck."""
    calls, roster = view.get("lineup_calls"), view.get("roster_expected")
    if not calls or not roster:
        return
    n = len(view.get("weeks") or [])
    print("\n    LINEUP CALLS (a decision, not luck; never added to the luck above)")
    print(f"    Your roster's best lineups were projected to earn {roster['total']:.1f} wins; "
          f"the lineups you started, {view['expected']['total']:.1f}.")
    print(f"    Lineup calls: {_wins(calls['wins'])} ({calls['points_per_week']:+.1f} points a week; "
          f"a better lineup was on the roster in {calls['weeks_short']} of {n} weeks).")


def _ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _fmt(metric, keys, label, name, weeks,
         absent="-- not measurable for this season --"):
    if metric is None:
        return f"  {label:16s} {absent}"
    delta, se, z = metric.get("delta"), metric.get("se"), metric.get("z")
    detail = "  ".join(f"{k}={metric[k]}" for k in keys if k in metric)
    way = direction(name, delta)
    if z is None:
        return f"  {label:16s} {delta:+8.2f}  {way:8s} (no spread to test)  {detail}"
    # R2: below the pre-registered threshold the INFERENCE is unavailable, not merely
    # unnamed. This line used to suppress the verdict WORD and still print
    # `z -4.03  p 0.000` beside "too early" -- and the reader takes the number, because
    # "too early" is a word and 0.000 is four significant figures. The point estimate and
    # its standard error still print: they are honest at any n, and the SE is the thing
    # that actually says "too noisy to read".
    if weeks < MIN_WEEKS_FOR_INFERENCE:
        early = f"too early (n<{MIN_WEEKS_FOR_INFERENCE})"
        return (f"  {label:16s} {delta:+8.2f}  {way:8s} +-{se:6.2f}  "
                f"z {'--':>5s}  p {'--':>5s}  {early:11s} {detail}")
    p = two_sided_p(z)
    verdict = "SIGNIFICANT" if p < 0.05 else ("suggestive" if p < 0.20 else "noise")
    return (f"  {label:16s} {delta:+8.2f}  {way:8s} +-{se:6.2f}  z {z:+5.2f}  p {p:5.3f}  "
            f"{verdict:11s} {detail}")


def render(res, season, team_label, n_weeks):
    print(f"\n=== LUCK LEDGER -- {team_label}, {season} ({n_weeks} completed weeks) ===")
    if res.get("accounting"):
        render_accounting(res["accounting"], team_label)
    print("\n  THE FIVE REGISTERED MEASURES (each on its own; never added to the above)")
    print("  pre-registered definitions; every metric differenced against the league")
    d = res.get("banked_disagreement")
    absent = ("-- WITHHELD, the record was rewritten (see below) --" if d
              else "-- not measurable for this season --")
    print(_fmt(res["schedule_luck"], ["actual_wins", "expected_wins", "all_play_pct"],
               "schedule luck", "schedule_luck", n_weeks, absent))
    print(_fmt(res["opponent_luck"], ["my_pa_per_game", "league_avg_pa_per_game"],
               "opponent luck", "opponent_luck", n_weeks))
    print(_fmt(res["close_games"], ["wins", "losses", "n"], "close games",
               "close_games", n_weeks, absent))
    print(_fmt(res["dnp_luck"], ["my_dnps_per_game", "league_avg"], "DNP luck",
               "dnp_luck", n_weeks))
    print(_fmt(res["scoring_luck"], ["my_mean_z", "league_mean_z", "n_weeks"],
               "scoring luck", "scoring_luck", n_weeks))
    if d:
        print(f"\n  !! These {d['weeks']} weeks recompute to {d['recomputed']} wins "
              f"({d['h2h_wins']} head-to-head + {d['median_wins']} median), but the league "
              f"banked {d['banked']}.")
        print("     " + "\n     ".join(_textwrap.wrap(d["note"], 86)))
    if n_weeks < MIN_WEEKS_FOR_INFERENCE:
        print(f"\n  n = {n_weeks} weeks, below the pre-registered "
              f"{MIN_WEEKS_FOR_INFERENCE} (F53). z and p are WITHHELD rather than printed "
              f"beside 'too early': nothing here can be significant yet, and the standard "
              f"errors are the point.")


def _say(to_stderr, text):
    """A note between seasons: stdout for the text report, stderr under --json so the JSON on
    stdout stays parseable."""
    import sys
    print(text, file=sys.stderr if to_stderr else sys.stdout)


def _owner_of(team):
    """The owner_id of the CURRENT league's roster called `team` (the pseudonym map), or None."""
    try:
        rosters = _get(f"{BASE_URL}/league/{LEAGUE_ID}/rosters") or []
    except Exception:
        return None
    return next((r.get("owner_id") for r in rosters
                 if TEAM_NAME_MAP.get(str(r.get("roster_id"))) == team and r.get("owner_id")), None)


def _roster_of(lid, owner):
    """roster_id of `owner` in league `lid` -- as owner or co-owner -- or None when that owner
    had no team there. Never another roster in its place (F96)."""
    if not owner:
        return None
    try:
        rosters = _get(f"{BASE_URL}/league/{lid}/rosters") or []
    except Exception:
        return None
    for r in rosters:
        if r.get("owner_id") == owner or owner in (r.get("co_owners") or []):
            return r.get("roster_id")
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", default=None)
    ap.add_argument("--all", action="store_true", help="every season in the renewal chain")
    ap.add_argument("--league-id", default=None, dest="league_id",
                    help="score a league the renewal chain cannot reach. 2025 carries a "
                         "null previous_league_id, so 2024 is orphaned. Normally you do "
                         "not need this: set SLEEPER_LEAGUE_ID_2024 and --all picks it up "
                         "via config.KNOWN_LEAGUE_IDS (B20). The flag remains for a league "
                         "that is in no map at all.")
    ap.add_argument("--team", default=None)
    ap.add_argument("--week", type=int, default=None,
                    help="only count the current season through this week (finished seasons "
                         "always count every week, and a week still being played never counts)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if a.league_id:
        info = _get(f"{BASE_URL}/league/{a.league_id}") or {}
        chain = [(str(info.get("season")), a.league_id, info)]
    else:
        chain = _league_chain()
    if not a.all and not a.league_id:
        want = str(a.season) if a.season else chain[0][0]
        chain = [c for c in chain if c[0] == want] or chain[:1]

    ov = real_name_overlay()
    payload = []
    pool = []                                   # (season, total luck, simulated totals)
    want = a.team or MY_TEAM
    # F96: a CURRENT team is followed into older seasons by its OWNER (rosters' owner_id);
    # before, every older season fell back to the owner of MY_TEAM, so `--team X --all`
    # printed the owner's 2024/2025 under X's name. A name that is not a current team is
    # looked up in each season as it stands.
    current_team = want in set(TEAM_NAME_MAP.values())
    owner = _owner_of(want) if current_team else None
    # Addendum 3: today's fantasy_positions, read only when some season has slots to solve
    elig = _eligibility() if any(starting_slots(i) for _s, _l, i in chain) else {}
    for season, lid, info in chain:
        names = _team_names(lid, info)
        per_week = 2 if (info.get("settings") or {}).get("league_average_match") else 1
        counted = _counted(lid, names)
        # F95: only weeks the league has closed, and --week cuts the CURRENT season only --
        # it used to cut 2024 and 2025 in an --all run too.
        through = closed_weeks(counted, per_week)
        if a.week and (str(lid) == str(LEAGUE_ID) or a.league_id):
            through = a.week if through is None else min(through, a.week)
        ids, rosters, played = {}, {}, {}
        scores, pairs, starters = _season_data(lid, info, names, through, ids=ids, rosters=rosters, played=played)
        if not scores:
            _say(a.json, f"\n=== {season}: no completed weeks ===")
            continue
        if str(lid) == str(LEAGUE_ID) or not current_team:
            team = want if want in next(iter(scores.values())) else None
            why = f"no team called {ov.get(want, want)} in this league"
        else:
            rid = _roster_of(lid, owner)
            team = names.get(rid) if rid is not None else None
            why = (f"{ov.get(want, want)}'s owner was not in this league" if owner
                   else f"could not find {ov.get(want, want)}'s owner")
        if team is None:
            _say(a.json, f"\n=== {season}: {why} ===")
            continue
        # C4: only cross-check a season whose counted weeks are all CLOSED. A week still
        # in progress, or a --week cutoff, would differ from the banked total for an
        # innocent reason, and an alarm that cries wolf teaches the reader to ignore it.
        # Closed means the league's own record covers exactly the weeks counted here; the
        # older test (`leg` past the last week) stayed silent on the Tuesday after a week,
        # when Sleeper's `leg` still names it (audit 2026-09-29).
        closed = bool(counted.get(team)) and counted[team]["games"] == per_week * len(scores)
        banked = counted[team]["wins"] if closed else None
        pa = {t: c["points_against"] for t, c in counted.items()} if closed else None
        if pa and any(v is None for v in pa.values()):
            pa = None
        # who won a re-scored week comes from the as-played record, not today's box score --
        # and where the sync's banked scores cover a week, its points and results are the league's
        results = {w: r for w, r in _as_played(season).items() if w in scores}
        for w, teams in (_banked(season) if str(lid) == str(LEAGUE_ID) else {}).items():
            if w not in scores:
                continue
            for t, (pts, h, med) in teams.items():
                if t in scores[w]:
                    scores[w][t] = float(pts)
                    results.setdefault(w, {})[t] = (h, med)
        res = ledger(scores, pairs, team, starter_points=starters,
                     projections=_projections(season), banked_wins=banked,
                     results=results or None, points_against=pa, median=per_week == 2)
        res["season"] = season
        # the wins accounting (Addendum 2): computed for the whole league, saved for the web UI
        acc = None
        if ids:
            projected, detail, best, n_filled = _projected_lineups(season, lid, info, ids, starters, rosters, elig,
                                                                   played, lambda s=season: _prekickoff_log(s))
            if projected:
                acc = accounting(scores, projected, pairs, results=results or None,
                                 median=per_week == 2, starters=detail, keep_sims=True, best=best)
            if acc:
                acc["filled_from_log"] = n_filled      # Addendum 4, reported beside the weeks left out
        if acc:
            sims = acc["teams"].get(team, {}).get("_sims_total")
            for t in acc["teams"].values():
                t.pop("_sims_total", None)
            _save_accounting(season, acc)
            if sims:
                pool.append((season, acc["teams"][team]["parts"]["total"]["wins"], sims))
        res["accounting"] = team_view(acc, team)
        payload.append(res)
        if not a.json:
            render(res, season, ov.get(team, team), len(scores))

    # "year in and year out": the team's total luck summed over every season measured (F96:
    # any team's, now that older seasons follow that team's owner). Added
    # after the per-season numbers were seen, and labelled so (docs/LUCK_LEDGER.md).
    pooled = across_seasons([(w, s) for _season, w, s in pool]) if len(pool) > 1 else None
    if pooled:
        pooled["season_list"] = [s for s, _w, _s in pool]
        if payload:
            payload[0]["across_seasons"] = pooled
        if not a.json:
            render_across(pooled, pool)
    if a.json:
        print(json.dumps(payload, indent=1))
    return 0


def render_across(pooled, pool):
    print(f"\n=== ACROSS {pooled['seasons']} SEASONS ({', '.join(s for s, _w, _s in pool)}) ===")
    for season, w, _s in pool:
        print(f"    {season}: {_wins(w)}")
    n = pooled.get("one_in")
    odds = f"about 1 in {n}" if n else f"rarer than 1 in {pooled['one_in_floor']}"
    print(f"    Together: luck {'cost' if pooled['wins'] < 0 else 'gave'} you {abs(pooled['wins']):.1f} wins "
          f"({pooled['word']}: {odds} runs of {pooled['seasons']} seasons are this {pooled['way']} or more).")
    print("    (This total was added after the per-season numbers were seen: docs/LUCK_LEDGER.md.)")


if __name__ == "__main__":
    raise SystemExit(main())
