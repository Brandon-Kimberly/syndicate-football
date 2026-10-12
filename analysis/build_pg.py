"""Build one analysis table: every player-game 2016-2025 (REG) with fantasy points under the
league's CURRENT scoring, snaps and snap share. Writes pg.duckdb next to this file."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import RAW, SITE, DATA, LOGS  # noqa: E402
import json, duckdb, os, sys
R = RAW
W = SITE + "fantasy/"
SCORING = {  # league scoring (data/logs/scoring_settings.jsonl, 2026) -> AGS stat-line keys
    "pass_yd": ("pass_yd", 0.04), "pass_td": ("pass_td", 4.0), "pass_int": ("pass_int", -1.0), "pass_2pt": ("pass_2pt", 2.0),
    "rush_yd": ("rush_yd", 0.1), "rush_td": ("rush_td", 6.0), "rush_2pt": ("rush_2pt", 2.0),
    "rec": ("rec", 0.5), "rec_yd": ("rec_yd", 0.1), "rec_td": ("rec_td", 6.0), "rec_2pt": ("rec_2pt", 2.0),
    "fum_lost": ("fum_lost", -2.0), "fum_rec_td": ("fum_rec_td", 6.0),
    "idp_tkl_solo": ("tkl_solo", 1.5), "idp_tkl_ast": ("tkl_ast", 0.75), "idp_tkl_loss": ("tkl_loss", 2.0),
    "idp_sack": ("sack", 2.0), "idp_qb_hit": ("qb_hit", 0.5), "idp_int": ("def_int", 5.0), "idp_pass_def": ("def_pd", 1.5),
    "idp_ff": ("def_ff", 3.0), "idp_fum_rec": ("def_fum_rec", 3.0), "idp_def_td": ("def_td", 6.0),
    "idp_safe": ("def_safe", 2.0), "idp_blk_kick": ("blk_kick", 2.0),
}
WEIGHTS = {k: w for _n, (k, w) in SCORING.items()}
POSMAP = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE", "DL": "DL", "LB": "LB", "DB": "DB"}

con = duckdb.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), "pg.duckdb"))
con.execute("drop table if exists pts")
con.execute("create table pts (season int, week int, gsis varchar, team varchar, pos varchar, points double, stat_lines int)")
for season in range(2016, 2026):
    d = json.load(open(f"{W}{season}.json", encoding="utf-8"))
    games = d["games"]; players = d["players"]
    rows = []
    for gid, pid, team, st in d["lines"]:
        g = games.get(gid)
        if not g or g[1] != "REG":
            continue
        name_pos = players.get(pid)
        if not name_pos or name_pos[1] not in POSMAP:
            continue
        pts = sum(float(st.get(k, 0) or 0) * w for k, w in WEIGHTS.items())
        rows.append((season, int(g[0]), pid, team, POSMAP[name_pos[1]], round(pts, 4), 1))
    con.executemany("insert into pts values (?,?,?,?,?,?,?)", rows)
    print(season, len(rows))
snp = " union all ".join(f"select * from read_parquet('{R}snap_counts_{y}.parquet')" for y in range(2016, 2026))
con.execute(f"create or replace view snp as select * replace (try_cast(week as integer) as week) from ({snp}) where game_type='REG'")
con.execute(f"create or replace table pl as select gsis_id, pfr_id from read_parquet('{R}players.parquet') where pfr_id is not null and gsis_id is not null")
POS = """case when {c} in ('QB') then 'QB' when {c} in ('RB','FB','HB') then 'RB' when {c} = 'WR' then 'WR'
 when {c} = 'TE' then 'TE' when {c} in ('DE','DT','NT','DL') then 'DL' when {c} in ('LB','ILB','OLB','MLB') then 'LB'
 when {c} in ('CB','S','SS','FS','DB') then 'DB' else null end"""
con.execute("drop table if exists games_played")
con.execute(f"""create table games_played as
  select p.gsis_id as gsis, s.season, s.week, s.team, {POS.format(c='s.position')} as pos,
         s.offense_snaps, s.defense_snaps, s.st_snaps,
         case when {POS.format(c='s.position')} in ('QB','RB','WR','TE') then s.offense_pct else s.defense_pct end as share
  from snp s join pl p on p.pfr_id = s.pfr_player_id where {POS.format(c='s.position')} is not null""")
# the table every analysis reads: a row for every game a player took snaps in, points 0 when no scoring event
con.execute("drop table if exists pg")
con.execute("""create table pg as
  select g.gsis, g.season, g.week, g.team, g.pos, g.offense_snaps, g.defense_snaps, g.st_snaps, g.share,
         coalesce(p.points, 0.0) as points
  from games_played g left join pts p on p.gsis = g.gsis and p.season = g.season and p.week = g.week""")
print(con.execute("select pos, count(*), round(avg(points),2) from pg where share >= 0.5 group by 1 order by 1").fetchall())
print("unmatched stat lines (a scorer with no snap row):", con.execute(
    "select count(*) from pts p left join games_played g on g.gsis=p.gsis and g.season=p.season and g.week=p.week where g.gsis is null").fetchone())
