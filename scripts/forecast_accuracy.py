"""Forecast accuracy: how the canonical pre-kickoff quotes did against the banked results.

    py -3.10 -m scripts.forecast_accuracy            # print the report (read-only)
    py -3.10 -m scripts.forecast_accuracy --record   # also append to data/logs/forecast_accuracy_<season>.jsonl

Reads data/logs/predictions_2026.jsonl, data/current/nfl_schedule.json and
data/current/banked_scores.json. Without --record it writes nothing. With --record it appends one
line, and only when a scored number has changed since the last line, so the daily data-capture
workflow can run it without filling the log. A week with no banked result is reported as pending,
never guessed. See docs/audit/FORECAST_WATCH.md."""
import argparse
import datetime
import json
import os
import sys
from collections import Counter

from fantasy_sim.forecast_accuracy import append_if_changed, build_record, summarise, week_result

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PREDICTIONS = os.path.join(ROOT, "data", "logs", "predictions_2026.jsonl")
SCHEDULE = os.path.join(ROOT, "data", "current", "nfl_schedule.json")
BANKED = os.path.join(ROOT, "data", "current", "banked_scores.json")
RECORD_DIR = os.path.join(ROOT, "data", "logs")

_REASON = {
    "no_kickoff": "no kickoff on record; not quoted",
    "no_quote": "no canonical quote before kickoff",
    "no_overlap": "no team in common between the quote and the banked result",
}


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_rows(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def week_line(rows, banked, kickoffs, week):
    """(report line, {team: error}) for one week, formatted from week_result."""
    r = week_result(rows, banked, kickoffs, week)
    if r["status"] in _REASON:
        return f"week {week}: {_REASON[r['status']]}", {}
    if r["status"] == "pending":
        return (f"week {week}: quoted {r['quote_logged_at']} (commit {r['commit']}); result pending"), {}
    s = summarise(r["errors"])
    line = (f"week {week}: quoted {r['quote_logged_at']} (commit {r['commit']})  "
            f"n={s['n']} mean error {s['mean_error']:+.1f}  MAE {s['mae']:.1f}  "
            f"rms z {s['rms_z']:.2f}  80% band {s['coverage80']:.0%}  50% band {s['coverage50']:.0%}")
    return line, r["errors"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--record", action="store_true",
                    help="append to data/logs/forecast_accuracy_<season>.jsonl when a scored number changed")
    args = ap.parse_args(sys.argv[1:] if argv is None else list(argv))

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

    if args.record:
        season = Counter(str(r.get("season")) for r in rows if r.get("season")).most_common(1)[0][0]
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        record = build_record(season, rows, banked, kickoffs, generated_at=now)
        path = os.path.join(RECORD_DIR, f"forecast_accuracy_{season}.jsonl")
        wrote = append_if_changed(path, record)
        print(f"\nrecord: {'appended to' if wrote else 'unchanged, nothing written to'} "
              f"{os.path.relpath(path, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
