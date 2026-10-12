"""A2/A3: persistence after a missed game, weekly all-cause onset hazard by position, and the
practice-status logistic for Questionable. 2016-2025 REG, fantasy-relevant players."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import RAW, SITE, DATA, LOGS  # noqa: E402
import duckdb, math, json
import numpy as np
R = RAW
con = duckdb.connect()
inj = " union all ".join(f"select * from read_parquet('{R}injuries_{y}.parquet')" for y in range(2016, 2026))
snp = " union all ".join(f"select * from read_parquet('{R}snap_counts_{y}.parquet')" for y in range(2016, 2026))
con.execute(f"create view inj as select * replace (try_cast(week as integer) as week) from ({inj}) where game_type = 'REG'")
con.execute(f"create view snp as select * replace (try_cast(week as integer) as week) from ({snp}) where game_type = 'REG'")
con.execute(f"create view pl as select gsis_id, pfr_id from read_parquet('{R}players.parquet') where pfr_id is not null and gsis_id is not null")
POS = """case when {c} in ('QB') then 'QB' when {c} in ('RB','FB','HB') then 'RB' when {c} = 'WR' then 'WR'
 when {c} = 'TE' then 'TE' when {c} in ('DE','DT','NT','DL') then 'DL' when {c} in ('LB','ILB','OLB','MLB') then 'LB'
 when {c} in ('CB','S','SS','FS','DB') then 'DB' else null end"""
P = lambda c: POS.format(c=c)

# every player-game with snaps, keyed by gsis; team schedule weeks (a team's games in a season) from snap rows
con.execute(f"""create view pg as
  select p.gsis_id, s.season, s.week, s.team, {P('s.position')} as pos,
         case when {P('s.position')} in ('QB','RB','WR','TE') then s.offense_pct else s.defense_pct end as share,
         (s.offense_snaps + s.defense_snaps + s.st_snaps) as snaps
  from snp s join pl p on p.pfr_id = s.pfr_player_id where {P('s.position')} is not null""")
con.execute("create view tg as select distinct season, week, team from snp")
# player-season role (fantasy-relevant = mean share >= .5 over games with snaps, >= 6 such games)
con.execute("""create view role as select gsis_id, season, avg(share) sh, count(*) gp from pg where snaps > 0 group by 1,2""")
# consecutive team games: for a player on team T in season S, game g and the team's NEXT game g'
con.execute("""create view nxt as
  select a.season, a.team, a.week, min(b.week) as next_week from tg a join tg b on a.season=b.season and a.team=b.team and b.week>a.week group by 1,2,3""")
# hazard: played game g (snaps>0, share>=...) -> did he log snaps in the team's next game?
con.execute("""create view haz as
  select g.season, g.pos, g.gsis_id, g.week, g.share,
         exists (select 1 from pg h where h.gsis_id=g.gsis_id and h.season=g.season and h.week=n.next_week and h.snaps>0) as played_next
  from pg g join nxt n on n.season=g.season and n.team=g.team and n.week=g.week
  join role r on r.gsis_id=g.gsis_id and r.season=g.season and r.sh>=0.5 and r.gp>=6
  where g.snaps>0 and g.share>=0.5""")
def wilson(k, n, z=1.96):
    p = k/n; d = 1+z*z/n; c=(p+z*z/(2*n))/d; h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d; return (round(c-h,3), round(c+h,3))
print("== A3: weekly all-cause absence-onset hazard | played last game (starters-by-share), REG 2016-2025")
cfg = {'RB': 0.070, 'WR': 0.081, 'TE': 0.035, 'QB': 0.054, 'DL': 0.025, 'LB': 0.025, 'DB': 0.020}
res = {}
for pos, n, k in con.execute("select pos, count(*), sum(case when played_next then 0 else 1 end) from haz group by 1 order by 1").fetchall():
    lo, hi = wilson(k, n); res[pos] = {"n": n, "k": int(k), "rate": round(k/n,4), "ci": [lo,hi]}
    print(f"  {pos}: {k}/{n} = {k/n:.4f} [{lo},{hi}]   config {cfg.get(pos)}  {'OUTSIDE' if not (lo<=cfg.get(pos,0)<=hi) else 'inside'}")
print("   by season (all positions):", [ (int(s), round(r,4)) for s,r in con.execute("select season, avg(case when played_next then 0.0 else 1.0 end) from haz group by 1 order by 1").fetchall()])

print("== A2: persistence. P(misses team's next game | listed Q/D at g and did NOT play g)  [fantasy-relevant]")
con.execute(f"""create view miss as
  select i.season, i.week, i.gsis_id, {P('i.position')} as pos, coalesce(i.report_status,'NoStatus') st,
         exists (select 1 from pg x where x.gsis_id=i.gsis_id and x.season=i.season and x.week=i.week and x.snaps>0) as played
  from inj i join role r on r.gsis_id=i.gsis_id and r.season=i.season and r.sh>=0.5 and r.gp>=6
  where {P('i.position')} is not null""")
con.execute("""create view miss2 as
  select m.*, (select min(n.next_week) from nxt n join (select distinct season, week, team from snp) t on 1=0) as dummy from miss m""")
con.execute("""create view pers as
  select m.st, m.pos, m.played,
         exists (select 1 from pg h, nxt n where n.season=m.season and n.week=m.week and h.gsis_id=m.gsis_id and h.season=m.season
                 and n.team=h.team and h.week=n.next_week and h.snaps>0) as played_next,
         exists (select 1 from pg g where g.gsis_id=m.gsis_id and g.season=m.season and g.week > m.week) as has_future
  from miss m""")
for st in ("Out", "Doubtful", "Questionable"):
    r = con.execute(f"select count(*), sum(case when played_next then 0 else 1 end) from pers where st='{st}' and not played and has_future").fetchone()
    if r[0]: print(f"  {st:12s} not played: n={r[0]} P(also misses next)={r[1]/r[0]:.3f} {wilson(int(r[1]), r[0])}")
r = con.execute("select count(*), sum(case when played_next then 0 else 1 end) from pers where st='Questionable' and played and has_future").fetchone()
print(f"  Questionable played: n={r[0]} P(misses next)={r[1]/r[0]:.3f}")

print("== practice-status logistic for Questionable (fantasy-relevant)")
rows = con.execute(f"""select {P('i.position')} pos, coalesce(i.practice_status,'none') pr,
   exists (select 1 from pg x where x.gsis_id=i.gsis_id and x.season=i.season and x.week=i.week and x.snaps>0) played
   from inj i join role r on r.gsis_id=i.gsis_id and r.season=i.season and r.sh>=0.5 and r.gp>=6
   where i.report_status='Questionable' and {P('i.position')} is not null""").fetchall()
pos_l = ['RB','WR','TE','DL','LB','DB']   # QB is the reference
pr_l = ['Limited Participation in Practice','Did Not Participate In Practice']  # Full is the reference
def design(pos, pr):
    x = [1.0] + [1.0 if pos == p else 0.0 for p in pos_l] + [1.0 if pr == q else 0.0 for q in pr_l]
    return x
rows = [r for r in rows if r[1] != 'none']
X = np.array([design(r[0], r[1]) for r in rows]); y = np.array([1.0 if r[2] else 0.0 for r in rows])
w = np.zeros(X.shape[1])
for _ in range(50):
    p = 1/(1+np.exp(-X@w)); W = p*(1-p)
    H = X.T@(X*W[:,None]) + 1e-6*np.eye(X.shape[1]); g = X.T@(y-p)
    step = np.linalg.solve(H, g); w += step
    if np.abs(step).max() < 1e-9: break
se = np.sqrt(np.diag(np.linalg.inv(X.T@(X*W[:,None]))))
names = ['intercept(QB,Full)'] + pos_l + ['Limited','DNP']
print("  n =", len(y))
for n_, c, s in zip(names, w, se): print(f"   {n_:20s} {c:+.3f}  (se {s:.3f})")
def pplay(pos, pr): return float(1/(1+np.exp(-np.array(design(pos, pr))@w)))
tab = {pos: {pr: round(pplay(pos, prl),3) for pr, prl in (('full','Full Participation in Practice'),('limited',pr_l[0]),('dnp',pr_l[1]))} for pos in ['QB']+pos_l}
for pos, d in tab.items(): print("  ", pos, d)
ll = lambda p_: -np.mean(y*np.log(p_)+(1-y)*np.log(1-p_))
pbar = y.mean()
print("  log-loss: constant pooled", round(ll(np.full_like(y,pbar)),4), "| position+practice logistic", round(ll(1/(1+np.exp(-X@w))),4), "| engine's implicit 1.0 (clipped .99):", round(ll(np.full_like(y,0.99)),4))
json.dump({"A3_onset": res, "practice_logistic": {"coef": dict(zip(names, [round(float(c),4) for c in w])), "n": int(len(y)), "table": tab}}, open("a2_a3.json","w"), indent=1)
