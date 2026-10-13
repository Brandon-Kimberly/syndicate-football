"""Forecast accuracy: how the canonical pre-kickoff quotes did against the banked results.

    py -3.10 -m scripts.forecast_accuracy

Read-only: it reads data/logs/predictions_2026.jsonl, data/current/nfl_schedule.json and
data/current/banked_scores.json, prints a report, and writes nothing. A week with no banked
result yet is listed as pending, not guessed. Run it after each week's banked scores land; the
pooled line is the number to watch across the season (see docs/audit/FORECAST_WATCH.md)."""
import json
import os
import sys

from fantasy_sim.forecast_accuracy import pre_kickoff_record, summarise, team_errors

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PREDICTIONS = os.path.join(ROOT, "data", "logs", "predictions_2026.jsonl")
SCHEDULE = os.path.join(ROOT, "data", "current", "nfl_schedule.json")
BANKED = os.path.join(ROOT, "data", "current", "banked_scores.json")


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_rows(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    rows = _load_rows(PREDICTIONS)
    kickoffs = _load_json(SCHEDULE).get("_meta", {}).get("kickoffs", {})
    banked = _load_json(BANKED)
    weeks = sorted({int(r["week"]) for r in rows if r.get("record_type") == "week_predictions"})
    pooled = {}
    for w in weeks:
        kick = min(kickoffs.get(str(w), ["9999"]))
        rec = pre_kickoff_record(rows, w, kick)
        actuals_block = banked.get(f"week_{w}")
        if rec is None:
            print(f"week {w}: no canonical quote before kickoff")
            continue
        if not actuals_block:
            print(f"week {w}: quoted at {rec['logged_at']} (commit {str(rec.get('commit'))[:7]}); result pending")
            continue
        actuals = {t: v["points"] for t, v in actuals_block.items()}
        errs = team_errors(rec, actuals)
        s = summarise(errs)
        print(f"week {w}: quoted {rec['logged_at']} (commit {str(rec.get('commit'))[:7]})  "
              f"n={s['n']} mean error {s['mean_error']:+.1f}  MAE {s['mae']:.1f}  "
              f"rms z {s['rms_z']:.2f}  80% band {s['coverage80']:.0%}  50% band {s['coverage50']:.0%}")
        for t in sorted(errs):
            pooled.setdefault(t, {}).update({w: errs[t]})
    all_errs = {f"{t}|{w}": e for t, per in pooled.items() for w, e in per.items()}
    if all_errs:
        p = summarise(all_errs)
        print(f"\npooled, {p['n']} team-weeks: mean error {p['mean_error']:+.1f}  MAE {p['mae']:.1f}  "
              f"rms z {p['rms_z']:.2f}  80% band {p['coverage80']:.0%}  50% band {p['coverage50']:.0%}")
        print("\nby team (mean error over the weeks banked):")
        for t in sorted(pooled, key=lambda t: sum(e["error"] for e in pooled[t].values())):
            per = pooled[t]
            mean = sum(e["error"] for e in per.values()) / len(per)
            print(f"  {t:18s} {mean:+7.1f}  over {len(per)} wk")
    return 0


if __name__ == "__main__":
    sys.exit(main())
