"""G: does Sleeper's weekly projection ALREADY contain the game environment?

The engine multiplies each player's baseline (Sleeper's week-specific projection, blended) by
(team implied total / league-average implied total). If Sleeper's number already reflects the game's
total, that second factor double-counts. Test on 2026 weeks 1-5: relative residual (actual - Sleeper)/Sleeper
regressed on the team's relative implied total. slope ~ 0  => Sleeper already has it (engine double-counts);
slope ~ +1 => Sleeper ignores environment (the engine's factor is right)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import RAW, SITE, DATA, LOGS  # noqa: E402
import json, duckdb, random, statistics as st
from collections import defaultdict
exec(open("build_pg.py", encoding="utf-8").read().split("con = duckdb.connect")[0])   # WEIGHTS
R = RAW
D = SITE
PROJ = LOGS + "projection_log.jsonl"
ALIAS = {"LA": "LAR", "JAC": "JAX", "OAK": "LV", "SD": "LAC", "STL": "LAR", "WSH": "WAS"}
a = lambda t: ALIAS.get(t, t)
ids = json.load(open(D + "fantasy_ids.json", encoding="utf-8"))["sleeper"]
d = json.load(open(D + "fantasy/2026.json", encoding="utf-8"))
games, players = d["games"], d["players"]
pts = defaultdict(float); tm = {}
for gid, pid, team, s in d["lines"]:
    g = games.get(gid)
    if not g or g[1] != "REG": continue
    pts[(pid, int(g[0]))] += sum(float(s.get(k, 0) or 0) * w for k, w in WEIGHTS.items()); tm[(pid, int(g[0]))] = a(team)
con = duckdb.connect()
imp = {}                                             # (week, team) -> implied total, from nfldata's lines
for w, at, ht, tot, sp in con.execute(f"select try_cast(week as integer), away_team, home_team, total_line, spread_line from read_csv_auto('{R}games.csv') where season=2026 and game_type='REG' and total_line is not null").fetchall():
    imp[(w, a(ht))] = tot / 2 + sp / 2; imp[(w, a(at))] = tot / 2 - sp / 2
lg = defaultdict(list)
for (w, t), v in imp.items(): lg[w].append(v)
lgmean = {w: sum(v) / len(v) for w, v in lg.items()}
cut = {1: "2026-09-13T17:00:00Z", 2: "2026-09-20T17:00:00Z", 3: "2026-09-27T17:00:00Z", 4: "2026-10-04T17:00:00Z", 5: "2026-10-11T17:00:00Z"}
proj = {}
for l in open(PROJ):
    r = json.loads(l); w = r["week"]
    if w in cut and r["synced_at"] <= cut[w] and (r.get("sleeper_mean") or 0) > 0 and r.get("pos") in ("QB", "RB", "WR", "TE"):
        k = (r["player_id"], w)
        if k not in proj or r["synced_at"] >= proj[k][0]: proj[k] = (r["synced_at"], r["sleeper_mean"], r["pos"])
rows = []
for (sid, w), (_t, m, pos) in proj.items():
    gsis = ids.get(str(sid))
    if not gsis or m < 6 or (gsis, w) not in tm: continue          # played (has a stat line) and a real projection
    t = tm[(gsis, w)]
    if (w, t) not in imp: continue
    rows.append({"w": w, "pos": pos, "m": m, "act": pts[(gsis, w)], "env": imp[(w, t)] / lgmean[w] - 1.0})
print("offensive player-weeks:", len(rows))
def ols(xs, ys):
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys); sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    res = [y - my - b * (x - mx) for x, y in zip(xs, ys)]
    return b, (sum(r * r for r in res) / (len(xs) - 2) / sxx) ** .5
def go(sel, label):
    sub = [r for r in rows if sel(r)]
    xs = [r["env"] for r in sub]; ys = [(r["act"] - r["m"]) / r["m"] for r in sub]
    b, se = ols(xs, ys)
    print(f"{label:9s} n={len(sub):4d}  slope of relative residual on relative implied total: {b:+.3f} (se {se:.3f})   [0 = already in Sleeper's number, +1 = absent]   sd(env)={st.pstdev(xs):.3f}")
    return b, se
go(lambda r: True, "all")
for p in ("QB", "RB", "WR", "TE"): go(lambda r, p=p: r["pos"] == p, p)
# same test on realised outcomes themselves: do points scale with the implied total at all? (sanity: is the signal there to be found)
xs = [r["env"] for r in rows]; ys = [r["act"] / r["m"] - 1 for r in rows]
b, se = ols(xs, ys); print(f"sanity: actual/projection - 1 on env  (same thing, shown as ratio): slope {b:+.3f} (se {se:.3f})")
ys2 = [r["act"] for r in rows]; b2, se2 = ols(xs, ys2); print(f"        raw actual points on env: {b2:+.1f} pts per +1.0 relative total (se {se2:.1f}); mean projection {st.mean(r['m'] for r in rows):.1f}")
