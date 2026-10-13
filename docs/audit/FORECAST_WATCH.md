# Forecast watch (2026 season)

How the model's forecasts are checked as results come in. Written 2026-10-12, after week 5, so
the bar is set before the evidence that would test it.

## What is measured

- **Quote:** the last canonical `week_predictions` row before the week's first kickoff
  (`median[team].expected_total`, with `sd_total` for the band).
- **Result:** the banked points for that team (`data/current/banked_scores.json`).
- **Tool:** `py -3.10 -m scripts.forecast_accuracy`. Read-only; prints the league line, the
  per-week lines and the pooled team-week line. It writes nothing unless `--record` is given.
- **Record:** `--record` appends one line to `data/logs/forecast_accuracy_<season>.jsonl`, and
  only when a scored number has changed. The daily `data-capture` workflow runs it after the
  sync and commits the log, so the season's accuracy history builds without anyone running it.

## Routine

1. Automated: the daily `data-capture` workflow runs `scripts.forecast_accuracy --record`.
   Nothing to run by hand. Check the log's last line after each week's results.
2. Review the pooled line and the per-team means at each milestone (below).
3. Milestone reviews at weeks 6, 11 and 15 (the points the release policy already uses).

## Proposed bar (for the owner to confirm)

These thresholds are proposals, not measured constants. They are chosen to be checkable, not
because a sample size has been shown to separate signal from noise.

- **Calibration.** Pooled 80% band coverage should sit between 75% and 85% once there are at
  least 40 team-weeks. Above 90% for two checks in a row means the intervals are too wide.
  As of week 5 (40 team-weeks, `scripts.forecast_accuracy`): 80% band 92%, 50% band 60%.
- **A team is a problem** only if its mean error through week 11 is more than two standard
  errors from zero (SE = sd of its weekly errors / sqrt(n)), *and* the per-player breakdown
  shows the environment/script multipliers drive the gap. A mean that is merely large is not
  enough. For the Quantum Ferrets over five weeks the weekly error sd is about 30 points, which
  puts the standard error of the 5-week mean near 13.5. That figure was a scratch calculation;
  the tool prints the mean but not the standard error yet.
- **The multiplier question** (`fantasy_sim/simulation.py`, `_script_multiplier`) is tested
  only by the per-player logs from v11 onward. If favoured-team running backs keep coming in
  well below their multiplied expectation over at least six weeks, the +0.15 RB bonus gets a
  measurement, not a tweak. Any change to it is MAJOR (CLAUDE.md release policy).

## Known gaps

- The week-5 Vegas lines were stale for 28 of 32 teams. The 2026-10-12 sync refreshed week 6
  (28 of 32 real lines; CIN, DET, MIA, MIN are on bye and have no game). Week 5's stale-line
  replay is not reproducible from the repo, because `data/current` is overwritten each sync.
