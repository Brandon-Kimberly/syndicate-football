#!/usr/bin/env python3
"""Who the engine may be mis-pricing: rostered players whose availability looks wrong.

  py -3.10 -m scripts.availability_watch            # re-run now against data/current/ (and the live feed)
  py -3.10 -m scripts.availability_watch --saved    # print what the last sync wrote, fetch nothing

ADVISORY (fantasy_sim.availability_watch): it changes no number. Two classes -- a carried baseline
for a player Sleeper projects at nothing, and the any-given-stat injury report disagreeing with
Sleeper's status. Reads data/current/ only; writes data/current/availability_watch.json unless
--saved.
"""
import argparse
import sys

from fantasy_sim import availability_watch as aw
from fantasy_sim.clients import ags
from fantasy_sim.storage import AVAILABILITY_WATCH_FILE, BASELINES_FILE, LIVE_ROSTERS_FILE, NFL_SCHEDULE_FILE, load_json


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--saved", action="store_true", help="print the last saved findings only")
    args = ap.parse_args(argv)

    if args.saved:
        doc = load_json(AVAILABILITY_WATCH_FILE)
    else:
        rosters, baselines = load_json(LIVE_ROSTERS_FILE), load_json(BASELINES_FILE)
        manifest = load_json(NFL_SCHEDULE_FILE).get("_meta", {})
        from fantasy_sim.freshness import read_nfl_week
        week = read_nfl_week() or manifest.get("current_week")
        report = ags.try_fetch_injury_report()
        aw.write_availability_watch(AVAILABILITY_WATCH_FILE, rosters, baselines, week, ags_report=report)
        doc = load_json(AVAILABILITY_WATCH_FILE)

    meta, findings = doc.get("_meta", {}), doc.get("findings", [])
    ag = meta.get("ags") or {}
    print(f"week {meta.get('week')} -- injury feed: "
          + (f"used (generated {ag.get('generated_at')}, report week {ag.get('week')})" if meta.get("ags_used") else "not used"))
    if not findings:
        print("no findings: every rostered player's availability agrees with Sleeper's own picture.")
        return 0
    for f in findings:
        print(f"  [{f['kind']}] {f['name']} ({f['pos']}, {f['team']}) on {f['fantasy_team']}: {f['detail']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
