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


def week_line(rows, banked, kickoffs, week):
    """(report line, {team: error}) for one week. Never guesses: with no kickoff time, no quote,
    or no team in common with the banked result, the line says why and the errors are empty."""
    kick = (kickoffs or {}).get(str(week))
    if not kick:
        return f"week {week}: no kickoff on record; not quoted", {}
    rec = pre_kickoff_record(rows, week, min(kick))
    if rec is None:
        return f"week {week}: no canonical quote before kickoff", {}
    block = (banked or {}).get(f"week_{week}")
    if not block:
        return (f"week {week}: quoted {rec['logged_at']} (commit {str(rec.get('commit'))[:7]}); "
                "result pending"), {}
    errs = team_errors(rec, {t: v["points"] for t, v in block.items()})
    if not errs:
        return f"week {week}: no team in common between the quote and the banked result", {}
    s = summarise(errs)
    line = (f"week {week}: quoted {rec['logged_at']} (commit {str(rec.get('commit'))[:7]})  "
            f"n={s['n']} mean error {s['mean_error']:+.1f}  MAE {s['mae']:.1f}  "
            f"rms z {s['rms_z']:.2f}  80% band {s['coverage80']:.0%}  50% band {s['coverage50']:.0%}")
    return line, errs


def main():
    rows = _load_rows(PREDICTIONS)
    kickoffs = _load_json(SCHEDULE).get("_meta", {}).get("kickoffs", {})
    banked = _load_json(BANKED)
    weeks = sorted({int(r["week"]) for r in rows if r.get("record_type") == "week_predictions"})
    pooled = {}
    for w in weeks:
        line, errs = week_line(rows, banked, kickoffs, w)
        print(line)
        for t, e in errs.items():
            pooled.setdefault(t, {})[w] = e
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
