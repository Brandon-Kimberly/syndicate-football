"""E: does a snap-share trend predict how a player's week differs from Sleeper's own projection?

2026 weeks 1-5: residual = actual points (league scoring, AGS stat lines) - Sleeper's last pre-kickoff
projection. Signal = (mean snap share of his previous two games) - (mean snap share of all earlier games)
or, with only two games of history, last game - first game. Both are computable before kickoff.
If Sleeper's projection already prices role changes, the slope of residual on signal is ~0."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import RAW, SITE, DATA, LOGS  # noqa: E402
import json, duckdb, os, statistics as st, random
from collections import defaultdict
exec(open("build_pg.py", encoding="utf-8").read().split("con = duckdb.connect")[0])   # WEIGHTS
R = RAW
D = SITE
PROJ = LOGS + "projection_log.jsonl"
ids = json.load(open(D + "fantasy_ids.json", encoding="utf-8"))["sleeper"]
d = json.load(open(D + "fantasy/2026.json", encoding="utf-8"))
games, players = d["games"], d["players"]
POS = {"QB", "RB", "WR", "TE", "DL", "LB", "DB"}
pts = defaultdict(float)
for gid, pid, team, s in d["lines"]:
    g = games.get(gid)
    if not g or g[1] != "REG": continue
    pts[(pid, int(g[0]))] += sum(float(s.get(k, 0) or 0) * w for k, w in WEIGHTS.items())
con = duckdb.connect()
con.execute(f"create view snp as select * replace (try_cast(week as integer) as week) from read_parquet('{R}snap_counts_2026.parquet') where game_type='REG'")
con.execute(f"create view pl as select gsis_id, pfr_id from read_parquet('{R}players.parquet') where pfr_id is not null and gsis_id is not null")
share = defaultdict(dict)       # gsis -> week -> share (unit he plays in)
for g, w, pos, op, dp in con.execute("select p.gsis_id, s.week, s.position, s.offense_pct, s.defense_pct from snp s join pl p on p.pfr_id=s.pfr_player_id").fetchall():
    sh = op if pos in ("QB", "RB", "FB", "WR", "TE") else dp
    if sh is not None: share[g][w] = sh
# Sleeper's last projection before the week's first Sunday kickoff
cut = {1: "2026-09-13T17:00:00Z", 2: "2026-09-20T17:00:00Z", 3: "2026-09-27T17:00:00Z", 4: "2026-10-04T17:00:00Z", 5: "2026-10-11T17:00:00Z"}
proj = {}
for l in open(PROJ):
    r = json.loads(l); w = r["week"]
    if w in cut and r["synced_at"] <= cut[w] and r.get("sleeper_mean") is not None and r.get("pos") in POS:
        k = (r["player_id"], w)
        if k not in proj or r["synced_at"] >= proj[k][0]: proj[k] = (r["synced_at"], r["sleeper_mean"], r["pos"])
maxwk = max(w for (_p, w) in pts)
rows = []
for (sid, w), (_t, m, pos) in proj.items():
    if w < 3 or w > maxwk or m < 4.0: continue
    gsis = ids.get(str(sid))
    if not gsis or gsis not in share: continue
    hist = [share[gsis][x] for x in sorted(share[gsis]) if x < w]
    if len(hist) < 2 or w not in share[gsis]: continue          # must have played this week to have a defined outcome
    last2 = sum(hist[-2:]) / 2
    earlier = hist[:-2]
    sig = last2 - (sum(earlier) / len(earlier)) if earlier else hist[-1] - hist[0]
    rows.append({"w": w, "pos": pos, "m": m, "act": pts.get((gsis, w), 0.0), "sig": sig, "share": last2})
print("player-weeks (played, projected >= 4, >= 2 prior games):", len(rows), "weeks", sorted({r["w"] for r in rows}))
def ols(xs, ys):
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    res = [y - my - b * (x - mx) for x, y in zip(xs, ys)]
    se = (sum(r * r for r in res) / (len(xs) - 2) / sum((x - mx) ** 2 for x in xs)) ** .5
    return b, se
resid = [r["act"] - r["m"] for r in rows]
print(f"mean residual (actual - Sleeper) among players who played: {st.mean(resid):+.2f}  [conditioning on playing biases this upward]")
for label, sel in (("all", lambda r: True), ("offense", lambda r: r["pos"] in ("QB", "RB", "WR", "TE")), ("IDP", lambda r: r["pos"] in ("DL", "LB", "DB")),
                   ("RB/WR/TE", lambda r: r["pos"] in ("RB", "WR", "TE"))):
    sub = [r for r in rows if sel(r)]
    if len(sub) < 30: continue
    xs = [r["sig"] for r in sub]; ys = [r["act"] - r["m"] for r in sub]
    b, se = ols(xs, ys)
    rel = [(r["act"] - r["m"]) / r["m"] for r in sub]
    b2, se2 = ols(xs, rel)
    print(f"{label:9s} n={len(sub):4d}  residual pts per +1.0 share-trend: {b:+7.2f} (se {se:.2f})   relative: {b2:+.3f} (se {se2:.3f})   sd(signal)={st.pstdev(xs):.3f}")
# tercile view: big risers vs big fallers
srt = sorted(rows, key=lambda r: r["sig"]); n = len(srt) // 5
for name, grp in (("bottom quintile (role shrinking)", srt[:n]), ("top quintile (role growing)", srt[-n:])):
    print(f"  {name:34s} n={len(grp)} mean signal {st.mean(r['sig'] for r in grp):+.3f}  mean residual {st.mean(r['act']-r['m'] for r in grp):+.2f}  rel {st.mean((r['act']-r['m'])/r['m'] for r in grp):+.3f}")
