"""F: when Sleeper has projected a player the previous week and projects NOTHING this week (team not on bye),
does he play? 2026 weeks 2-5 (the only weeks the projection log covers)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import RAW, SITE, DATA, LOGS  # noqa: E402
import json, duckdb
from collections import defaultdict
R = RAW
D = SITE
PROJ = LOGS + "projection_log.jsonl"
ids = json.load(open(D + "fantasy_ids.json", encoding="utf-8"))["sleeper"]
cut = {1: "2026-09-13T17:00:00Z", 2: "2026-09-20T17:00:00Z", 3: "2026-09-27T17:00:00Z", 4: "2026-10-04T17:00:00Z", 5: "2026-10-11T17:00:00Z"}
have = defaultdict(set); info = {}
for l in open(PROJ):
    r = json.loads(l); w = r["week"]
    if w in cut and r["synced_at"] <= cut[w] and (r.get("sleeper_mean") or 0) > 0:
        have[w].add(r["player_id"]); info[r["player_id"]] = (r["name"], r["pos"], r["team"], r.get("sleeper_mean"))
con = duckdb.connect()
con.execute(f"create view snp as select * replace (try_cast(week as integer) as week) from read_parquet('{R}snap_counts_2026.parquet') where game_type='REG'")
con.execute(f"create view pl as select gsis_id, pfr_id from read_parquet('{R}players.parquet') where pfr_id is not null and gsis_id is not null")
teamweeks = {(t, w) for t, w in con.execute("select distinct team, week from snp").fetchall()}
snaps = {(g, w): (o or 0) + (d or 0) + (s or 0) for g, w, o, d, s in con.execute(
    "select p.gsis_id, s.week, s.offense_snaps, s.defense_snaps, s.st_snaps from snp s join pl p on p.pfr_id=s.pfr_player_id").fetchall()}
n = played = 0; examples = []
for w in (2, 3, 4, 5):
    for sid in have[w - 1] - have[w]:
        name, pos, team, m = info[sid]
        if (team, w) not in teamweeks: continue            # bye or game not yet played
        gsis = ids.get(str(sid))
        if not gsis: continue
        n += 1; ok = snaps.get((gsis, w), 0) > 0; played += ok
        if len(examples) < 14: examples.append((w, name, pos, team, round(m, 1), "played" if ok else "DID NOT PLAY"))
print(f"projected last week, unprojected this week, team played: n={n}, played={played} ({played/max(n,1):.1%}), did not play={n-played}")
for e in examples: print("  ", e)
# by whether projection was a meaningful one last week
