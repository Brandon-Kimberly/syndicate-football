#!/usr/bin/env python3
"""Re-measure SIM_CONFIG['ENV_SHARE_IN_PROJECTION']: how much of the game environment Sleeper's
week-specific projection already contains.

  py -3.10 -m scripts.env_check            # fetch the public sources, print the slope and the share

Method (analysis/g_envcheck.py is the original, DuckDB-based): for every offensive player-week of the
season so far with a Sleeper projection >= 6 who played, the relative residual (actual - projection) /
projection is regressed on the team's relative implied total (its total over that week's league mean,
from nflverse's published lines). A slope of 0 means Sleeper's number already holds the whole
environment; 1 means none. share = 1 - slope. Actual points are the any-given-stat site's published
stat lines scored under THIS league's settings (data/logs/scoring_settings.jsonl); projections are the
last row of data/logs/projection_log.jsonl before each week's first Sunday kickoff.

Read-only: it prints and writes nothing. It says plainly when the estimate's interval contains both the
configured share and 1.0 (no information yet), and refuses with fewer than MIN_N player-weeks.
Pure functions below are tested; the one network step is `fetch_inputs`."""
import csv
import datetime as dt
import io
import json
import sys
import urllib.request
from collections import defaultdict

from fantasy_sim.config import SIM_CONFIG, normalize_position
from fantasy_sim.storage import _log

SITE = "https://brandon-kimberly.github.io/any-given-stat/data/"
GAMES_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
MIN_PROJECTION = 6.0
MIN_N = 150
ALIAS = {"LA": "LAR", "JAC": "JAX", "OAK": "LV", "SD": "LAC", "STL": "LAR", "WSH": "WAS"}
# Sleeper scoring key -> the site's stat-line key, offense only (the pass/rush/rec/fumble keys)
OFFENSE_KEYS = {"pass_yd": "pass_yd", "pass_td": "pass_td", "pass_int": "pass_int", "pass_2pt": "pass_2pt",
                "rush_yd": "rush_yd", "rush_td": "rush_td", "rush_2pt": "rush_2pt", "rec": "rec", "rec_yd": "rec_yd",
                "rec_td": "rec_td", "rec_2pt": "rec_2pt", "fum_lost": "fum_lost", "fum_rec_td": "fum_rec_td"}


def ols(xs, ys):
    """(slope, standard error) of y on x."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    resid = [y - my - b * (x - mx) for x, y in zip(xs, ys)]
    return b, (sum(r * r for r in resid) / (n - 2) / sxx) ** 0.5


def week_cutoffs(game_rows):
    """{week: ISO cutoff} -- 17:00Z on the week's first SUNDAY game day (fallback: its first day)."""
    days = defaultdict(set)
    for r in game_rows:
        if r.get("gameday"):
            days[int(r["week"])].add(r["gameday"])
    out = {}
    for w, ds in days.items():
        sundays = sorted(d for d in ds if dt.date.fromisoformat(d).weekday() == 6)
        out[w] = (sundays[0] if sundays else min(ds)) + "T17:00:00Z"
    return out


def implied_totals(game_rows):
    """{(week, team): implied total} from nflverse's total and (home-favoured-positive) spread."""
    out = {}
    for r in game_rows:
        try:
            w, tot, sp = int(r["week"]), float(r["total_line"]), float(r["spread_line"])
        except (KeyError, TypeError, ValueError):
            continue
        h, a = ALIAS.get(r["home_team"], r["home_team"]), ALIAS.get(r["away_team"], r["away_team"])
        out[(w, h)] = tot / 2 + sp / 2
        out[(w, a)] = tot / 2 - sp / 2
    return out


def last_projections(log_lines, cutoffs):
    """{(sleeper_id, week): (mean, pos)} -- each player's last projection logged before the week's cutoff."""
    best = {}
    for line in log_lines:
        r = json.loads(line)
        w = r.get("week")
        if w not in cutoffs or r.get("sleeper_mean") is None or r["synced_at"] > cutoffs[w]:
            continue
        if normalize_position(r.get("pos")) not in ("QB", "RB", "WR", "TE") or (r["sleeper_mean"] or 0) < MIN_PROJECTION:
            continue
        k = (r["player_id"], w)
        if k not in best or r["synced_at"] >= best[k][0]:
            best[k] = (r["synced_at"], r["sleeper_mean"], r["pos"])
    return {k: (v[1], v[2]) for k, v in best.items()}


def score_lines(fantasy_season, weights):
    """({(gsis, week): points}, {(gsis, week): team}) for regular-season lines."""
    pts, team = defaultdict(float), {}
    games = fantasy_season["games"]
    for gid, pid, tm, stats in fantasy_season["lines"]:
        g = games.get(gid)
        if not g or g[1] != "REG":
            continue
        pts[(pid, int(g[0]))] += sum(float(stats.get(k, 0) or 0) * w for k, w in weights.items())
        team[(pid, int(g[0]))] = ALIAS.get(tm, tm)
    return pts, team


def measure(projections, sleeper_to_gsis, pts, team, implied):
    """The regression rows and (slope, se, n)."""
    week_level = defaultdict(list)
    for (w, _t), v in implied.items():
        week_level[w].append(v)
    level = {w: sum(v) / len(v) for w, v in week_level.items()}
    xs, ys = [], []
    for (sid, w), (m, _pos) in projections.items():
        gsis = sleeper_to_gsis.get(str(sid))
        if not gsis or (gsis, w) not in team or (w, team[(gsis, w)]) not in implied:
            continue
        xs.append(implied[(w, team[(gsis, w)])] / level[w] - 1.0)
        ys.append((pts[(gsis, w)] - m) / m)
    if len(xs) < 3:
        return None, None, len(xs)
    b, se = ols(xs, ys)
    return b, se, len(xs)


def verdict(slope, se, n, configured):
    share = 1.0 - slope
    lo, hi = share - 1.96 * se, share + 1.96 * se
    lines = [f"player-weeks n = {n}",
             f"slope of the relative residual on the relative implied total: {slope:+.3f} (se {se:.3f})",
             f"share of the environment already in Sleeper's projection = 1 - slope = {share:.2f}  "
             f"(95%: {lo:.2f} to {hi:.2f})   configured: {configured:.2f}"]
    if lo <= configured <= hi:
        lines.append("the configured share is inside the interval: nothing to change.")
    else:
        lines.append(f"the configured share {configured:.2f} is OUTSIDE the interval: re-derive "
                     f"(a constant change is MAJOR-class).")
    if hi >= 1.0 and lo <= 0.0:
        lines.append("the interval spans 0 to 1: this season's data cannot yet tell the two stories apart.")
    return lines


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8")


def fetch_inputs(season):
    games = list(csv.DictReader(io.StringIO(_get(GAMES_URL))))
    games = [r for r in games if str(r["season"]) == str(season) and r.get("game_type") == "REG"]
    fantasy = json.loads(_get(f"{SITE}fantasy/{season}.json"))
    ids = json.loads(_get(f"{SITE}fantasy_ids.json"))["sleeper"]
    return games, fantasy, ids


def league_weights():
    path = _log("scoring_settings.jsonl")
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    settings = rows[-1]["settings"]
    return {OFFENSE_KEYS[k]: float(settings[k]) for k in OFFENSE_KEYS if settings.get(k)}


def main(argv=None):
    season = 2026
    games, fantasy, ids = fetch_inputs(season)
    cut = week_cutoffs(games)
    with open(_log("projection_log.jsonl"), encoding="utf-8") as f:
        proj = last_projections(f, cut)
    pts, team = score_lines(fantasy, league_weights())
    slope, se, n = measure(proj, ids, pts, team, implied_totals(games))
    if slope is None or n < MIN_N:
        print(f"only {n} player-weeks (need {MIN_N}): too early to say anything.")
        return 0
    print("\n".join(verdict(slope, se, n, SIM_CONFIG["ENV_SHARE_IN_PROJECTION"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
