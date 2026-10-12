"""H: among the owner-league's rostered Questionable players (2026 weeks 3-4), how many played, how many were
started, and -- of those who did NOT play -- how many were in a started lineup (a locked zero the manager
could not avoid) vs benched (known / avoidable)?"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import RAW, SITE, DATA, LOGS  # noqa: E402
import json, duckdb
R = RAW
D = SITE
LOG = DATA
ids = json.load(open(D + "fantasy_ids.json", encoding="utf-8"))["sleeper"]
banked = json.load(open(LOG + "current/banked_scores.json", encoding="utf-8"))
con = duckdb.connect()
con.execute(f"create view snp as select * replace (try_cast(week as integer) as week) from read_parquet('{R}snap_counts_2026.parquet') where game_type='REG'")
con.execute(f"create view pl as select gsis_id, pfr_id from read_parquet('{R}players.parquet') where pfr_id is not null and gsis_id is not null")
snaps = {(g, w): (o or 0) + (d or 0) + (s or 0) for g, w, o, d, s in con.execute(
    "select p.gsis_id, s.week, s.offense_snaps, s.defense_snaps, s.st_snaps from snp s join pl p on p.pfr_id=s.pfr_player_id").fetchall()}
# last designation recorded for each (team, player, week); Questionable only if that is the final status
last = {}
for l in open(LOG + "logs/designations.jsonl"):
    r = json.loads(l)
    k = (r["team"], r["player_id"], r["week"])
    if k not in last or r["recorded_at"] > last[k]["recorded_at"]: last[k] = r
n = played = started = 0; dnp_started = dnp_benched = 0; q_played_started = 0
rows = []
for (team, pid, wk), r in last.items():
    if r["injury_status"] != "Questionable" or wk not in (3, 4): continue
    wb = banked.get(f"week_{wk}", {}).get(team)
    if not wb: continue
    gsis = ids.get(str(pid))
    if not gsis: continue
    play = snaps.get((gsis, wk), 0) > 0
    st_ = str(pid) in wb["starters"]
    n += 1; played += play; started += st_
    if not play:
        if st_: dnp_started += 1
        else: dnp_benched += 1
    rows.append((wk, r["name"], team, play, st_, r.get("practice_participation")))
print(f"rostered Questionable (final designation), weeks 3-4: n={n}")
print(f"  played {played} ({played/n:.0%}); started {started} ({started/n:.0%})")
print(f"  did not play: {n-played}  -> of those, in a STARTED lineup (locked zero): {dnp_started}; benched: {dnp_benched}")
print(f"  P(started | Questionable & did not play) = {dnp_started/max(n-played,1):.2f}   P(started | Questionable & played) = {sum(1 for x in rows if x[3] and x[4])/max(played,1):.2f}")
print("  practice_participation populated for:", sum(1 for x in rows if x[5]), "of", len(rows))
