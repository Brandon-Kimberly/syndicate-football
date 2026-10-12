"""B: the vacated-volume capture rate, measured on every RB/WR/TE absence 2016-2025.

Engine unit (simulation._record_vacated_volume): when a position-group member is out, the team's
position pool gains  capture * (his healthy mean)  fantasy points, shared among same-position
healthy teammates. Measured here: for each (team, week) where a player with a real role is
ABSENT (zero snaps) after playing, how many MORE fantasy points did his same-position teammates
score than their own trailing means predicted, as a multiple of the absent man's trailing mean.
The same quantity on team-weeks with NO such absence (placebo) is subtracted: trailing means are
a biased forecast (regression to the mean, game-script), and the placebo carries that bias."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import RAW, SITE, DATA, LOGS  # noqa: E402
import duckdb, os, random, statistics as st, json
from collections import defaultdict
con = duckdb.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), "pg.duckdb"), read_only=True)
rows = con.execute("select gsis, season, week, team, pos, points, share, offense_snaps from pg where pos in ('RB','WR','TE')").fetchall()
tg = con.execute("select distinct season, week, team from games_played").fetchall()
team_weeks = defaultdict(list)          # (season, team) -> sorted weeks
for s, w, t in tg: team_weeks[(s, t)].append(w)
for k in team_weeks: team_weeks[k].sort()
hist = defaultdict(list)                # (gsis) -> [(season, week, team, pos, points, share)] chronological
byteam = defaultdict(list)              # (season, team, week) -> [(gsis,pos,points,share)]
for g, s, w, t, p, pts, sh, sn in sorted(rows, key=lambda r: (r[1], r[2])):
    hist[g].append((s, w, t, p, pts, sh))
    byteam[(s, t, w)].append((g, p, pts, sh))

def trailing(gsis, season, week, n=4):
    """mean points / share over the player's previous n games (any season), games with snaps only."""
    h = [x for x in hist[gsis] if (x[0], x[1]) < (season, week)][-n:]
    if len(h) < 3: return None
    return sum(x[4] for x in h) / len(h), sum(x[5] for x in h) / len(h), h[-1][0], h[-1][1]

MIN_MEAN = {"RB": 8.0, "WR": 8.0, "TE": 6.0}
events, placebo = [], []
for (season, team), weeks in team_weeks.items():
    for w in weeks:
        if w == weeks[0]: continue
        prev_w = weeks[weeks.index(w) - 1]
        played = byteam[(season, team, w)]
        played_ids = {g for g, *_ in played}
        # who was a real contributor going in (played the team's previous game, trailing mean over the bar)
        absent = {}
        for pos in ("RB", "WR", "TE"):
            for g, p, pts, sh in byteam[(season, team, prev_w)]:
                if p != pos or g in played_ids: continue
                tr = trailing(g, season, w)
                if tr and tr[0] >= MIN_MEAN[pos] and tr[1] >= 0.4: absent.setdefault(pos, []).append((g, tr[0]))
        for pos in ("RB", "WR", "TE"):
            mates = [(g, pts) for g, p, pts, sh in played if p == pos]
            if not mates: continue
            base = []
            for g, pts in mates:
                tr = trailing(g, season, w)
                base.append(tr[0] if tr else 0.0)
            delta = sum(pts for _g, pts in mates) - sum(base)
            if pos in absent and len(absent[pos]) == 1:                # exactly one qualifying absentee in this group
                events.append({"pos": pos, "season": season, "team": team, "week": w, "delta": delta, "x": absent[pos][0][1],
                               "n_mates": len(mates)})
            elif pos not in absent:
                placebo.append({"pos": pos, "season": season, "delta": delta})

def boot(vals, fn, reps=2000, seed=1):
    r = random.Random(seed); n = len(vals); out = []
    for _ in range(reps):
        out.append(fn([vals[r.randrange(n)] for _ in range(n)]))
    out.sort(); return out[int(.025 * reps)], out[int(.975 * reps)]

res = {}
print(f"{'pos':3s} {'events':>6s} {'mean X':>7s} {'event dPts':>10s} {'placebo dPts':>12s} {'excess':>7s} {'capture':>8s} {'95% CI (bootstrap)':>22s}")
for pos in ("RB", "WR", "TE", "ALL"):
    ev = [e for e in events if pos == "ALL" or e["pos"] == pos]
    pl = [e for e in placebo if pos == "ALL" or e["pos"] == pos]
    mx = st.mean(e["x"] for e in ev); mp = st.mean(e["delta"] for e in pl)
    pairs = [(e["delta"], e["x"]) for e in ev]
    cap = lambda ps, mp=mp: (sum(d for d, _ in ps) / len(ps) - mp) / (sum(x for _, x in ps) / len(ps))
    lo, hi = boot(pairs, cap)
    me = st.mean(e["delta"] for e in ev)
    print(f"{pos:3s} {len(ev):6d} {mx:7.2f} {me:10.2f} {mp:12.2f} {me-mp:7.2f} {cap(pairs):8.3f} {'['+format(lo,'.3f')+', '+format(hi,'.3f')+']':>22s}")
    res[pos] = {"events": len(ev), "mean_absent_trailing_pts": round(mx, 3), "event_delta": round(me, 3), "placebo_delta": round(mp, 3),
                "capture": round(cap(pairs), 4), "ci95": [round(lo, 4), round(hi, 4)]}
print("by era (ALL):")
for lo_s, hi_s in ((2016, 2019), (2020, 2022), (2023, 2025)):
    ev = [(e["delta"], e["x"]) for e in events if lo_s <= e["season"] <= hi_s]
    pl = [e["delta"] for e in placebo if lo_s <= e["season"] <= hi_s]
    mp = st.mean(pl)
    print(f"   {lo_s}-{hi_s}: n={len(ev)}  capture {((sum(d for d,_ in ev)/len(ev)) - mp)/(sum(x for _,x in ev)/len(ev)):.3f}")
print("by position x era:")
for pos in ("RB", "WR", "TE"):
    for lo_s, hi_s in ((2016, 2019), (2020, 2022), (2023, 2025)):
        ev = [(e["delta"], e["x"]) for e in events if e["pos"] == pos and lo_s <= e["season"] <= hi_s]
        pl = [e["delta"] for e in placebo if e["pos"] == pos and lo_s <= e["season"] <= hi_s]
        print(f"   {pos} {lo_s}-{hi_s}: n={len(ev):3d}  capture {((sum(d for d,_ in ev)/len(ev)) - st.mean(pl))/(sum(x for _,x in ev)/len(ev)):.3f}")
# sensitivity: absentee trailing-mean bar, and only events with >= 2 teammates
for bar in (10.0, 12.0):
    ev = [(e["delta"], e["x"]) for e in events if e["x"] >= bar]
    mp = st.mean(e["delta"] for e in placebo)
    print(f"   absentee trailing mean >= {bar}: n={len(ev)} capture {((sum(d for d,_ in ev)/len(ev)) - mp)/(sum(x for _,x in ev)/len(ev)):.3f}")
json.dump(res, open("b_capture.json", "w"), indent=1)
