#!/usr/bin/env python3
"""The season as GIFs: wins banked, points banked, title/playoff odds over time.

  py -3.10 -m scripts.season_movie                 # real team names (your private copy)
  py -3.10 -m scripts.season_movie --fictional     # the league's fictional names (shareable)

Reads data/current/banked_scores.json and the tracked predictions log; writes three GIFs under
data/results/season_movie/ (gitignored -- real names must never sit anywhere publishable, so
anything outside data/ is refused, as localize_reports does). Re-run after each week: new banked
weeks and new canonical runs become new frames. No ffmpeg needed (GIF only).
"""
import argparse
import json
import os

from fantasy_sim import season_movie as sm
from fantasy_sim.config import MY_TEAM
from fantasy_sim.storage import load_json, predictions_log_file

OUT_DIR = os.path.join("data", "results", "season_movie")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fictional", action="store_true", help="keep the fictional names (shareable copy)")
    ap.add_argument("--out", default=OUT_DIR)
    args = ap.parse_args(argv)

    from scripts.localize_reports import refuse_unsafe_root, real_mapping
    refuse_unsafe_root(args.out)
    os.makedirs(args.out, exist_ok=True)

    rename = {}
    if not args.fictional:
        rename, how = real_mapping()
        print(f"names: real ({how})")
    mine = rename.get(MY_TEAM, MY_TEAM)

    banked = load_json(os.path.join("data", "current", "banked_scores.json"))
    s = sm.banked_series(banked)
    wins = sm.renamed(s["wins"], rename)
    pts = sm.renamed(s["points"], rename)
    suffix = "_fictional" if args.fictional else ""

    n = sm.render_race(wins, s["weeks"], "Wins banked", "wins (head-to-head + beat-the-median)",
                       os.path.join(args.out, f"wins_banked{suffix}.gif"), mine=mine)
    print(f"wins_banked: {n} frames, weeks {s['weeks'][0]}-{s['weeks'][-1]}")
    n = sm.render_race(pts, s["weeks"], "Points banked", "points scored",
                       os.path.join(args.out, f"points_banked{suffix}.gif"), mine=mine)
    print(f"points_banked: {n} frames")

    season = str(load_json(os.path.join("data", "current", "sync_manifest.json")).get("season") or "")
    with open(predictions_log_file(season), encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    title = [(a, w, sm.renamed(v, rename)) for a, w, v in sm.odds_series(rows, "Champ_Pct")]
    playoff = [(a, w, sm.renamed(v, rename)) for a, w, v in sm.odds_series(rows, "Playoff_Pct")]
    n = sm.render_odds(title, playoff, os.path.join(args.out, f"season_odds{suffix}.gif"), mine=mine)
    print(f"season_odds: {n} frames from {len(title)} canonical runs")
    print(f"written to {os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()
