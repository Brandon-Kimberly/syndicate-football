# Forecast watch (2026 season)

How the model's forecasts are checked as results come in. Written 2026-10-12, after week 5, so
the bar is set before the evidence that would test it.

## What is measured

- **Quote:** the last canonical `week_predictions` row before the week's first kickoff
  (`median[team].expected_total`, with `sd_total` for the band).
- **Result:** the banked points for that team (`data/current/banked_scores.json`).
- **Tool:** `py -3.10 -m scripts.forecast_accuracy`. Read-only; prints the league line, the
  per-week lines and the pooled team-week line. It writes nothing.

## Routine

1. After each week's banked scores land, run `scripts.forecast_accuracy`.
2. Record the pooled line and the per-team means in the weekly notes.
3. Milestone reviews at weeks 6, 11 and 15 (the points the release policy already uses).

## Proposed bar (for the owner to confirm)

These thresholds are proposals, not measured constants. They are chosen to be checkable, not
because a sample size has been shown to separate signal from noise.

- **Calibration.** Pooled 80% band coverage should sit between 75% and 85% once there are at
  least 40 team-weeks. Above 90% for two checks in a row means the intervals are too wide.
  Current (32 team-weeks): 94%. Current 50% band: 56%.
- **A team is a problem** only if its mean error through week 11 is more than two standard
  errors from zero (SE = sd of its weekly errors / sqrt(n)), *and* the per-player breakdown
  shows the environment/script multipliers drive the gap. A mean that is merely large is not
  enough: five weeks gave a standard error of about 13.5 points for the Quantum Ferrets.
- **The multiplier question** (`fantasy_sim/simulation.py`, `_script_multiplier`) is tested
  only by the per-player logs from v11 onward. If favoured-team running backs keep coming in
  well below their multiplied expectation over at least six weeks, the +0.15 RB bonus gets a
  measurement, not a tweak. Any change to it is MAJOR (CLAUDE.md release policy).

## Known gaps

- The week-5 Vegas lines were stale for 28 of 32 teams. Until the next sync uses real lines,
  the per-player multipliers for those teams cannot be trusted.
- Week 5 is not yet in `banked_scores.json`; the Sleeper matchup fetch used to check it was
  not written to the repo.
