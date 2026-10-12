"""D: which pre-week defensive-strength signal best predicts the fantasy points a defense allows to
QB/RB/WR/TE -- the engine's own PA-with-prior estimate, or any-given-stat's opponent-adjusted
points rating?  2017-2025, weeks 3-17 (every signal has >= 2 games of this season behind it)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import RAW, SITE, DATA, LOGS  # noqa: E402
import duckdb, json, os, random, statistics as st
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
con = duckdb.connect(os.path.join(HERE, "pg.duckdb"), read_only=True)
R = RAW
AGS = SITE
ALIAS = {"LA": "LAR", "STL": "LAR", "SD": "LAC", "OAK": "LV", "JAC": "JAX", "WSH": "WAS"}
a = lambda t: ALIAS.get(t, t)

# game results: points for/against per team-week (nfldata games.csv)
games = con.execute(f"select season, try_cast(week as integer) w, away_team, home_team, away_score, home_score from read_csv_auto('{R}games.csv') where game_type='REG' and away_score is not null and season between 2016 and 2025").fetchall()
pa = {}                      # (season, team, week) -> (points_for, points_allowed, opponent)
for s, w, at, ht, asc, hsc in games:
    pa[(s, a(at), w)] = (asc, hsc, a(ht)); pa[(s, a(ht), w)] = (hsc, asc, a(at))
# Y: fantasy points scored against each defense by QB/RB/WR/TE (all players with snaps)
rows = con.execute("select season, week, team, sum(points) from pg where pos in ('QB','RB','WR','TE') group by 1,2,3").fetchall()
off = {(s, a(t), w): p for s, w, t, p in rows}
Y = {}
for (s, t, w), p in off.items():
    key = (s, t, w)
    if key in pa:
        Y[(s, pa[key][2], w)] = p            # points the OPPONENT of t's defense ... i.e. scored against defense `opp`
# AGS ratings
ags = {}
for s in range(2017, 2026):
    for r in json.load(open(f"{AGS}ratings/{s}.json", encoding="utf-8")):
        ags[(s, r["team"], r["week"])] = r
# engine-like estimate: PA shrunk to a prior with n0=12; prior = the team's previous-season mean PA (proxy for the preseason table)
def season_pa(s):
    d = defaultdict(list)
    for (ss, t, w), (pf, pa_, opp) in pa.items():
        if ss == s: d[t].append(pa_)
    return {t: sum(v) / len(v) for t, v in d.items()}
prev = {s: season_pa(s - 1) for s in range(2017, 2026)}
N0 = 12.0
def engine_est(s, t, w):
    games_ = [pa[(s, t, ww)][1] for ww in range(1, w) if (s, t, ww) in pa]
    prior = prev[s].get(t, 22.0)
    n = len(games_)
    return (N0 * prior + sum(games_)) / (N0 + n) if n else prior
def ags_est(s, t, w):
    r = ags.get((s, t, w - 1))
    # AGS def_points is POSITIVE for a GOOD defense (net = off + def); negate so that, like the
    # engine's points-allowed estimate, a bigger number means a worse defense
    return -r["def_points"] if r else None
obs = []
for s in range(2017, 2026):
    for w in range(3, 18):
        for t in {k[1] for k in Y if k[0] == s and k[2] == w}:
            y = Y.get((s, t, w)); e = engine_est(s, t, w); g = ags_est(s, t, w)
            if y is not None and g is not None:
                obs.append({"s": s, "w": w, "t": t, "y": y, "eng": e, "ags": g})
print("observations:", len(obs))
# remove week means (a week's fantasy environment moves everyone together)
byw = defaultdict(list)
for o in obs: byw[(o["s"], o["w"])].append(o)
for k, v in byw.items():
    for key in ("y", "eng", "ags"):
        m = sum(o[key] for o in v) / len(v)
        for o in v: o[key + "_d"] = o[key] - m
def corr(xs, ys):
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** .5
def slope(xs, ys):
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
Yd = [o["y_d"] for o in obs]
res = {}
def boot(fn, reps=1000, seed=3):
    r = random.Random(seed); seasons = sorted({o["s"] for o in obs}); out = []
    for _ in range(reps):
        pick = [r.choice(seasons) for _ in seasons]
        sample = [o for s in pick for o in obs if o["s"] == s]
        out.append(fn(sample))
    out.sort(); return round(out[int(.025 * reps)], 3), round(out[int(.975 * reps)], 3)
print(f"{'signal':28s} {'corr with points allowed':>26s}   (95% CI over seasons)    slope (fantasy pts per +1 pt of rating)")
for name in ("eng", "ags"):
    xs = [o[name + "_d"] for o in obs]
    c = corr(xs, Yd); sl = slope(xs, Yd)
    lo, hi = boot(lambda smp, n=name: corr([o[n + "_d"] for o in smp], [o["y_d"] for o in smp]))
    print(f"{name:28s} {c:26.3f}   [{lo}, {hi}]   {sl:.3f}")
    res[name] = {"corr": round(c, 4), "ci": [lo, hi], "slope": round(sl, 4)}
# paired: which one wins by season?
wins = 0
for s in sorted({o["s"] for o in obs}):
    sm = [o for o in obs if o["s"] == s]
    ce, ca = corr([o["eng_d"] for o in sm], [o["y_d"] for o in sm]), corr([o["ags_d"] for o in sm], [o["y_d"] for o in sm])
    wins += ca > ce
    print(f"   {s}: engine-like {ce:+.3f}   AGS {ca:+.3f}")
print("AGS better in", wins, "of 9 seasons")
# blend
for wt in (0.25, 0.5, 0.75):
    xs = [wt * o["ags_d"] + (1 - wt) * o["eng_d"] for o in obs]
    print(f"   blend {wt:.2f} AGS: corr {corr(xs, Yd):.3f}")
# the engine's actual use: top-5 / bottom-5 tiers each week by the signal; realised relative difference vs league mean that week
print("tier test (engine multiplies skill players by 0.94 / 1.06):")
for name in ("eng", "ags"):
    top, bot, base = [], [], []
    for k, v in byw.items():
        ranked = sorted(v, key=lambda o: o[name])
        m = sum(o["y"] for o in v) / len(v)
        for o in ranked[:5]: top.append(o["y"] / m)
        for o in ranked[-5:]: bot.append(o["y"] / m)
    print(f"   {name}: top-5 defenses allow {st.mean(top):.3f}x the week's mean, bottom-5 allow {st.mean(bot):.3f}x   (n={len(top)} each)")
    res[name]["top5_ratio"] = round(st.mean(top), 4); res[name]["bottom5_ratio"] = round(st.mean(bot), 4)
json.dump(res, open("d_defense.json", "w"), indent=1)
