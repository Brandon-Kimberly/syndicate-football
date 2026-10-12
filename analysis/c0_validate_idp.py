"""C0: do AGS (nflverse play-by-play) IDP stat lines reproduce Sleeper's own IDP stats for 2026 weeks 1-4?"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import RAW, SITE, DATA, LOGS  # noqa: E402
import json, urllib.request, statistics as st
W = SITE
exec(open("build_pg.py", encoding="utf-8").read().split("con = duckdb.connect")[0])   # SCORING / WEIGHTS only
W = SITE
UA = {"User-Agent": "Mozilla/5.0"}
def get(u):
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60))
ids = json.load(open(W + "fantasy_ids.json", encoding="utf-8"))["sleeper"]
d = json.load(open(W + "fantasy/2026.json", encoding="utf-8"))
games, players = d["games"], d["players"]
ags = {}
for gid, pid, team, s in d["lines"]:
    g = games.get(gid)
    if not g or g[1] != "REG": continue
    ags[(pid, int(g[0]))] = s
KEYS = {"idp_tkl_solo": "tkl_solo", "idp_tkl_ast": "tkl_ast", "idp_tkl_loss": "tkl_loss", "idp_sack": "sack", "idp_qb_hit": "qb_hit",
        "idp_int": "def_int", "idp_pass_def": "def_pd", "idp_ff": "def_ff", "idp_fum_rec": "def_fum_rec"}
rows = []
for wk in (1, 2, 3, 4):
    for pos in ("DL", "LB", "DB"):
        data = get(f"https://api.sleeper.com/stats/nfl/2026/{wk}?season_type=regular&position[]={pos}")
        for x in data:
            sid = str(x.get("player_id")); gsis = ids.get(sid)
            if not gsis: continue
            s = x.get("stats") or {}
            if not any(s.get(k) for k in KEYS): continue
            sl = ags.get((gsis, wk), {})
            row = {"pos": pos, "wk": wk}
            for sk, ak in KEYS.items():
                row[sk] = (float(s.get(sk) or 0), float(sl.get(ak) or 0))
            rows.append(row)
print("player-weeks compared:", len(rows))
print(f"{'stat':14s} {'n_sleeper>0':>11s} {'sum sleeper':>12s} {'sum AGS':>9s} {'ratio':>6s} {'exact match %':>14s}")
for sk in KEYS:
    a = [r[sk][0] for r in rows]; b = [r[sk][1] for r in rows]
    n = sum(1 for x in a if x > 0); sa, sb = sum(a), sum(b)
    exact = sum(1 for x, y in zip(a, b) if abs(x - y) < 1e-9) / len(a)
    print(f"{sk:14s} {n:11d} {sa:12.1f} {sb:9.1f} {sb/sa if sa else float('nan'):6.3f} {100*exact:13.1f}%")
# points under the league scale
def pts(r, i): return sum(r[sk][i] * w for sk, w in {"idp_tkl_solo": 1.5, "idp_tkl_ast": 0.75, "idp_tkl_loss": 2.0, "idp_sack": 2.0, "idp_qb_hit": 0.5,
                                                    "idp_int": 5.0, "idp_pass_def": 1.5, "idp_ff": 3.0, "idp_fum_rec": 3.0}.items())
a = [pts(r, 0) for r in rows]; b = [pts(r, 1) for r in rows]
n = len(a); ma, mb = sum(a) / n, sum(b) / n
cov = sum((x - ma) * (y - mb) for x, y in zip(a, b)); va = sum((x - ma) ** 2 for x in a); vb = sum((y - mb) ** 2 for y in b)
print(f"points: mean Sleeper {ma:.2f}  mean AGS {mb:.2f}  ratio {mb/ma:.3f}  corr {cov/(va*vb)**.5:.3f}  MAE {sum(abs(x-y) for x,y in zip(a,b))/n:.2f}  exact {100*sum(1 for x,y in zip(a,b) if abs(x-y)<1e-9)/n:.1f}%")
for pos in ("DL", "LB", "DB"):
    aa = [pts(r, 0) for r in rows if r["pos"] == pos]; bb = [pts(r, 1) for r in rows if r["pos"] == pos]
    print(f"  {pos}: n={len(aa)} Sleeper {sum(aa)/len(aa):.2f} AGS {sum(bb)/len(bb):.2f} MAE {sum(abs(x-y) for x,y in zip(aa,bb))/len(aa):.2f}")
