"""I: does Sleeper's projection already discount a Questionable/Doubtful player?  (B4's premise.)
For rostered players flagged Questionable/Doubtful in the designation log: projection that week vs the same
player's projection the previous week (when not flagged), and projection vs what he actually scored."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import RAW, SITE, DATA, LOGS  # noqa: E402
import json, statistics as st
from collections import defaultdict
LOG = LOGS
cut = {1: "2026-09-13T17:00:00Z", 2: "2026-09-20T17:00:00Z", 3: "2026-09-27T17:00:00Z", 4: "2026-10-04T17:00:00Z", 5: "2026-10-11T17:00:00Z"}
proj = {}
for l in open(LOG + "projection_log.jsonl"):
    r = json.loads(l); w = r["week"]
    if w in cut and r["synced_at"] <= cut[w] and r.get("sleeper_mean") is not None:
        k = (r["player_id"], w)
        if k not in proj or r["synced_at"] >= proj[k][0]: proj[k] = (r["synced_at"], r["sleeper_mean"])
# status at the time of each week's LAST projection sync, from designations (rostered players only)
status = {}
for l in open(LOG + "designations.jsonl"):
    r = json.loads(l)
    k = (r["player_id"], r["week"])
    if k not in status or r["recorded_at"] >= status[k][0]: status[k] = (r["recorded_at"], r["injury_status"])
rows = []
for (pid, w), (_t, st_) in status.items():
    if st_ not in ("Questionable", "Doubtful"): continue
    cur, prev = proj.get((pid, w)), proj.get((pid, w - 1))
    if cur and prev and prev[1] > 3 and (pid, w - 1) not in status or (cur and prev and prev[1] > 3 and status.get((pid, w - 1), (0, None))[1] in (None,)):
        rows.append((st_, cur[1] / prev[1], cur[1], prev[1]))
for s in ("Questionable", "Doubtful"):
    xs = [r[1] for r in rows if r[0] == s]
    if xs: print(f"{s:12s} n={len(xs):3d}  projection this week / projection last week (healthy): mean {st.mean(xs):.2f}  median {st.median(xs):.2f}")
# control: how much does a typical healthy player's projection move week to week?
ctl = []
for (pid, w), (_t, m) in proj.items():
    if w >= 2 and (pid, w - 1) in proj and proj[(pid, w - 1)][1] > 3 and status.get((pid, w), (0, None))[1] is None and (pid, w) not in status:
        ctl.append(m / proj[(pid, w - 1)][1])
print(f"control (all players with no flag on record) n={len(ctl)}: mean ratio {st.mean(ctl):.2f}  median {st.median(ctl):.2f}")
