"""A1: P(plays | injury-report game status, position), 2016-2025 regular seasons."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import RAW, SITE, DATA, LOGS  # noqa: E402
import duckdb, math, json
R = RAW
con = duckdb.connect()
inj = " union all ".join(f"select * from read_parquet('{R}injuries_{y}.parquet')" for y in range(2016, 2026))
snp = " union all ".join(f"select * from read_parquet('{R}snap_counts_{y}.parquet')" for y in range(2016, 2026))
con.execute(f"create view inj as select * from ({inj}) where game_type = 'REG'")
con.execute(f"create view snp as select * from ({snp}) where game_type = 'REG'")
con.execute(f"create view pl as select gsis_id, pfr_id from read_parquet('{R}players.parquet') where pfr_id is not null and gsis_id is not null")

POS = """case when position in ('QB') then 'QB' when position in ('RB','FB','HB') then 'RB' when position = 'WR' then 'WR'
 when position = 'TE' then 'TE' when position in ('DE','DT','NT','DL') then 'DL' when position in ('LB','ILB','OLB','MLB') then 'LB'
 when position in ('CB','S','SS','FS','DB') then 'DB' else null end"""

# player-season role: mean snap share of the unit he plays in (offense_pct for offense, defense_pct for defense), games played
con.execute(f"""create view role as
 select p.gsis_id, s.season, {POS.replace('position','s.position')} as pos,
        avg(case when {POS.replace('position','s.position')} in ('QB','RB','WR','TE') then s.offense_pct else s.defense_pct end) as share,
        count(*) as gp
 from snp s join pl p on p.pfr_id = s.pfr_player_id
 where {POS.replace('position','s.position')} is not null and (s.offense_snaps + s.defense_snaps) > 0
 group by 1,2,3""")
# every injury-report row, with whether he logged a snap in that game
con.execute(f"""create view obs as
 select i.season, i.week, i.gsis_id, {POS.replace('position','i.position')} as pos,
        coalesce(i.report_status, 'NoStatus') as status, i.practice_status,
        exists (select 1 from snp s join pl p on p.pfr_id = s.pfr_player_id
                where p.gsis_id = i.gsis_id and s.season = i.season and s.week = i.week
                  and (s.offense_snaps + s.defense_snaps + s.st_snaps) > 0) as played,
        r.share, r.gp
 from inj i left join role r on r.gsis_id = i.gsis_id and r.season = i.season
 where {POS.replace('position','i.position')} is not null""")

def wilson(k, n, z=1.96):
    if n == 0: return (0, 0)
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 3), round(c + h, 3))

out = {}
for label, cond in (("fantasy-relevant (share >= 0.5, gp >= 6)", "share >= 0.5 and gp >= 6"),
                    ("all listed players", "true")):
    print("==", label)
    rows = con.execute(f"""select pos, status, count(*) n, sum(case when played then 1 else 0 end) k
                           from obs where {cond} and status in ('Questionable','Doubtful','Out') group by 1,2 order by 1,2""").fetchall()
    for pos, status, n, k in rows:
        lo, hi = wilson(k, n)
        print(f"  {pos:3s} {status:13s} n={n:5d} P(play)={k/n:.3f} [{lo},{hi}]")
        if label.startswith("fantasy"):
            out.setdefault(status, {})[pos] = {"n": n, "k": int(k), "p": round(k / n, 4), "ci": [lo, hi]}
    tot = con.execute(f"""select status, count(*) n, sum(case when played then 1 else 0 end) k from obs
                          where {cond} and status in ('Questionable','Doubtful','Out') group by 1""").fetchall()
    for status, n, k in tot:
        print(f"  ALL {status:13s} n={n:5d} P(play)={k/n:.3f} {wilson(k,n)}")
# by season stability for relevant Questionable
print("== Questionable relevant, by season")
for r in con.execute("""select season, count(*) n, avg(case when played then 1.0 else 0 end) p from obs
                        where share >= 0.5 and gp >= 6 and status = 'Questionable' group by 1 order by 1""").fetchall():
    print("  ", r[0], r[1], round(r[2], 3))
# practice status refinement for Questionable (relevant)
print("== Questionable relevant by practice_status")
for r in con.execute("""select coalesce(practice_status,'none'), count(*) n, avg(case when played then 1.0 else 0 end) p from obs
                        where share >= 0.5 and gp >= 6 and status = 'Questionable' group by 1 order by 2 desc""").fetchall():
    print("  ", r[0], r[1], round(r[2], 3))
# weekly base rate: relevant players with NO status who did not play (surprise inactives)
r = con.execute("""select count(*), sum(case when played then 0 else 1 end) from obs where share >= 0.5 and gp >= 6 and status = 'NoStatus'""").fetchone()
print("NoStatus relevant:", r)
json.dump(out, open("a1_status_play.json", "w"), indent=1)
