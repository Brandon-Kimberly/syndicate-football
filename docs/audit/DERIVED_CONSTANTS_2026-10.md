# Constants derived from ten seasons of nflverse data (2026-10-12)

Owner request: use the any-given-stat site's data (nflverse play-by-play, injury reports, snap
counts, 2016-2025) to improve the model, "automatically and incorporated", and bundle it with the
held fixes in one MAJOR. This is the evidence for every number that moved, **and for every proposal
that was measured and rejected** -- an unrecorded negative result gets proposed again.

Every figure below is reproducible: `analysis/` holds the scripts (run them with the any-given-stat
environment, which has DuckDB: `cd analysis && uv run --project <any-given-stat>/pipeline python a1_status.py`),
and `analysis/results/*.txt` holds the output they printed when this was written.

## What was adopted, and what was not

| # | Question | Result | Decision |
|---|---|---|---|
| 1 | Does a Questionable / Doubtful player play? | 0.739 / 0.016 (n 6035 / 643); practice report moves Questionable 0.51 -> 0.91 | **ADOPTED** -- the engine drew both healthy |
| 2 | Does Sleeper already discount a Questionable player? (B4's premise) | No: 1.03x his healthy-week projection (n 39; control 1.01x) | B4's "would double-count" retired |
| 3 | Weekly absence-onset hazard for the "no data" IDP positions | LB 0.036 [0.033, 0.039], DB 0.050 [0.047, 0.053] vs 0.025 / 0.020 | **ADOPTED** LB and DB (outside the interval); DL, QB, TE inside, unchanged; RB/WR not comparable, unchanged |
| 4 | Vacated-volume capture (F30 revisit, 862 events, not 8) | RB 0.63 [0.54, 0.72], WR 0.52 [0.42, 0.62], TE 0.41 [0.31, 0.51] vs 0.65 | **ADOPTED** TE 0.45; RB, WR unchanged |
| 5 | Is the defensive-tier effect the right size? | top-5 0.945x (engine 0.94), bottom-5 1.035x [1.016, 1.054] (engine 1.06) | **ADOPTED** bottom bonus 0.06 -> 0.04 |
| 6 | Does Sleeper's weekly projection already contain the game environment? | Yes, ~71%: slope 0.290 (se 0.185), n 541; the engine multiplied by the full ratio again | **ADOPTED** `ENV_SHARE_IN_PROJECTION = 0.71`; re-measured by `scripts.env_check` |
| 7 | Omitted Odds lines filled from nflverse | moved a matchup's P(win) by up to 5.9 points (week-5 replay) | **ENABLED** (it is an input change; this is the MAJOR) |
| 8 | any-given-stat's opponent-adjusted defence rating as the tier source | corr with points allowed 0.113 vs the engine's 0.112 (5 of 9 seasons better) | **REJECTED** -- a tie is not a reason to add a dependency |
| 9 | A snap-share trend as a role-change signal | slope -1.0 +/- 2.3 points per full share, n 402 | **REJECTED** -- Sleeper's number already prices role |
| 10 | "Sleeper stopped projecting him, so he is out" (the Williams fix) | 52 of 77 (67.5%) such players played | **REJECTED** -- would have been wrong two times in three |
| 11 | Re-derive IDP volatility / epistemic constants | already done: F28 (volatility) and B1 (epistemic) on full-NFL 2025 stat lines | nothing to do; the ten-season data validates the pipeline (below) |

## The validation gate (run before any IDP number was used)

IDP play-by-play credit is known to be noisy, so before using it the same stat lines were compared
with **Sleeper's own** for 2026 weeks 1-4 (2,238 DL/LB/DB player-weeks, `analysis/c0_validate_idp.py`):
TFL, sacks, forced fumbles and interceptions match to the unit (100%); solo tackles match exactly on
89.7% of player-weeks and are 0.6% high in aggregate; assisted tackles are 6.3% high; **fantasy points
under the league's IDP scale correlate 0.994 with Sleeper's, mean 6.25 vs 6.16 (ratio 1.015), MAE 0.19.**
Good enough to measure absence and usage; it is not used to price a single player's tackles.

## 1-2. Game-time injury status (`analysis/a1_status.py`, `a2_onset.py`, `i_qproj.py`)

Population: injury-report rows joined to snap counts, regular seasons 2016-2025, **fantasy-relevant**
players (mean snap share >= 0.5 over >= 6 games), "played" = logged any snap.

| status | n | P(plays) | Wilson 95% |
|---|---|---|---|
| Questionable | 6,035 | 0.739 | 0.727-0.749 |
| Doubtful | 643 | 0.016 | 0.008-0.028 |
| Out | 3,296 | 0.001 | 0.000-0.002 |

By position (Questionable): QB 0.586, RB 0.717, WR 0.771, TE 0.779, DL 0.815, LB 0.773, DB 0.673.
By the practice report (Questionable, n 5,922): full 0.913, limited 0.748, did not participate 0.506;
fitted jointly with position as a logistic (log-loss 0.524 vs 0.573 pooled and 1.20 for "plays for
certain"). The Questionable rate by season runs 0.69-0.81 with no trend. Persistence after a missed
game: Questionable 0.276, Doubtful 0.397, Out 0.562 miss the next game too.

The old policy ("no game-time-probability source; drawn healthy", F4) is replaced: a Questionable or
Doubtful player misses the current week with the measured probability, and the miss is a **known**
absence (the player is not a lineup candidate and the bench fills). That choice rests on thin data:
of 11 rostered Questionable players who did not play in 2026 weeks 3-4, **0** were in a started
lineup (`h_locked.py`; upper 95% bound ~0.25). The week tools price the same probability into
`week_expectation`, so `optimize_lineup` no longer starts a Doubtful player at full value.

**B4's premise, tested:** B4 left Questionable out of every absence set because "the Sleeper
projection already reflects expected usage ... discounting again would double-count". For the 39
rostered Questionable players with a prior-week projection, this week's projection was **1.03x**
last week's (control, unflagged players: 1.01x, n 159). Sleeper does not discount. (Doubtful n = 3,
0.86x: not enough to say.)

## 3. Absence-onset hazards (`analysis/a2_onset.py`)

Hazard = P(no snap in the team's next game | played this one), fantasy-relevant, 2016-2025:

| pos | k / n | rate | Wilson 95% | config (was) | verdict |
|---|---|---|---|---|---|
| QB | 253 / 4,582 | 0.055 | 0.049-0.062 | 0.054 | inside, unchanged |
| TE | 169 / 4,706 | 0.036 | 0.031-0.042 | 0.035 | inside, unchanged |
| DL | 344 / 12,572 | 0.027 | 0.025-0.030 | 0.025 | inside, unchanged |
| **LB** | 445 / 12,459 | **0.036** | 0.033-0.039 | 0.025 | **outside -> 0.036** |
| **DB** | 1,064 / 21,349 | **0.050** | 0.047-0.053 | 0.020 | **outside -> 0.050** |
| RB | 112 / 3,111 | 0.036 | 0.030-0.043 | 0.070 | not comparable |
| WR | 485 / 11,418 | 0.043 | 0.039-0.046 | 0.081 | not comparable |

RB and WR stay because their 2025 values were measured as "scored exactly 0 given > 0 last week",
which counts a played-but-scoreless game as a zero; this counts only a missed game. Comparing them
would be a definition error, not evidence. (The DB number is 2.5x the old one; it applies to every
rostered DB every future week, so IDP-heavy rosters lose a little expected value.)

## 4. Vacated-volume capture (`analysis/b_capture.py`)

Event: a player with a trailing 4-game mean >= 8 (RB, WR) or >= 6 (TE) points and >= 40% snap share
who played the team's previous game and logged no snap; exactly one such player in his position group
that week. Measured: his same-position teammates' points above their own trailing means, **minus** the
same quantity on team-weeks with no such absence (the placebo, ~+0.4 points), as a multiple of his
trailing mean. 862 events:

| pos | events | capture | bootstrap 95% | 2016-19 / 2020-22 / 2023-25 |
|---|---|---|---|---|
| RB | 316 | 0.629 | 0.542-0.718 | 0.67 / 0.56 / 0.69 |
| WR | 368 | 0.522 | 0.419-0.622 | 0.41 / 0.56 / 0.63 |
| TE | 178 | 0.408 | 0.314-0.513 | 0.25 / 0.55 / 0.44 |

TE's 0.65 lies outside its interval, and its two recent eras average ~0.50 -> **0.45**. RB is inside.
WR is marginally outside the all-years interval but inside the recent-era one and rising -> unchanged.
Honest limits: the denominator (a trailing mean of a player selected for being high) overstates his
true mean, so the estimates are if anything low; the engine's invariant (total apportioned never
exceeds total vacated) caps any rate at 1.0. The old "+1.53" was 8 events with a different
denominator and is superseded.

## 5-6. Defence tiers and the environment (`analysis/d_defense.py`, `g_envcheck.py`)

**Tiers** (2017-2025, weeks 3-17, 3,906 team-weeks; outcome = fantasy points QB+RB+WR+TE scored
against a defence): top-5 defences allowed 0.945x the week's mean (the engine's -6% is right);
bottom-5 allowed 1.035x (the engine's +6% is high). The tier source: the engine-like estimate
(points allowed, shrunk to last season's) correlates 0.112 with points allowed; any-given-stat's
opponent-adjusted rating 0.113; a 50/50 blend 0.121. A tie -> keep the engine's, adopt the
measured bottom-tier size.

**Environment double-count.** Sleeper's projection is week-specific; the engine multiplies it by
(team implied total / schedule mean) again. 2026 weeks 1-5, 541 offensive player-weeks (projection
>= 6, played), nflverse's published lines for the total: relative residual (actual - projection) /
projection on the team's relative implied total has slope **0.290 (se 0.185)** -- 0 means Sleeper holds
the whole environment, 1 none. Raw points track the same total at ~1.04, so the environment is real;
Sleeper just holds ~71% of it. The engine's baseline is now made environment-neutral at load,
`mean / (1 + 0.71 x (r - 1))` with r = the team's implied total over the week's mean (standard
deviations scaled with their own formulas), and then takes the one full ratio it always applied.
The share is **unverified beyond four weeks of one season** (interval roughly 0.35-1.07; by position
QB 0.79, RB 0.44, WR -0.04, TE 0.59, all too noisy to split), so it is a config constant with a
monitor, `scripts.env_check`, and 0 restores the old behaviour exactly. It skips baselines that are
not this week's Sleeper projection (carried, hand-typed, auto-zero) and any week with fewer than 20
teams' lines.

## 7. The omitted Odds lines (`fetch_vegas_implied_totals`, `NFLVERSE_REPAIR_ENABLED`)

On a late-week sync the Odds payload drops every game already under way or finished (28 of 32 teams
on 2026-10-12 -- DAL and TB were just the first noticed), and those teams are condemned as stale.
Filling them from nflverse's published lines moved a matchup's P(win) by up to **5.9 points**
(week-5 replay with and without them: -1.7, +3.4, +5.9, -0.9). That is why it was built off; it is
on in this release and the number belongs in the release notes.

## 8-10. Rejected, with the reason

* **any-given-stat's adjusted defence rating.** No better at the one thing the engine uses defence for.
* **A role-change signal from snap-share trends** (`e_role.py`, 2026 weeks 3-5, n 402): residual per
  full share of trend -1.0 (se 2.3); IDP -3.3 (se 7.6); RB/WR/TE +1.7 (se 2.7). The quintile of players
  whose role is growing beat Sleeper's projection by +0.45 and the one shrinking by +0.87: no pattern.
  The power is real (a true effect of ~5 points per full share would have shown), so Sleeper prices role.
* **"Unprojected means out"** (`f_noproj.py`, 2026 weeks 2-5): of 77 players Sleeper projected one week
  and not the next (team playing), 52 played. Caleb Williams (hamstring, out since week 3) was a real
  miss; the cause was that Questionable was priced as healthy, which item 1 fixes -- for him
  P(plays | Questionable QB) is 0.59 and 0.29 if he does not practice.

## Gates run before merge (and what they cannot see)

| gate | result |
|---|---|
| full suite | 2428 tests, all passing once the goldens were regenerated (they were red by design in the code commit) |
| golden masters | regenerated in their own commit; week01 league scoring -3.67%, week06 -0.36%, week15 unchanged |
| behaviour check, both scenarios (M2) | every mechanic in the same plausibility band as before; drift on FAAB / lineup metrics is the F62 noise class; baselines regenerated, double-run identical |
| points backtest vs real 2025 (300 sims x 4 checkpoints) | bias -2.50 pts (was -2.79; change +0.29, limit 0.5), mean z +0.091 (was +0.110; change 0.018, limit 0.05), cover80 0.76 / cover50 0.46 (0.75 / 0.46), engine MAE 22.21 (22.38) |
| golden attribution (`analysis/golden_attribution.py`) | only the environment neutralisation is a material scoring effect (-3.6 points per team-week where lines apply); the rest are inside the +/-1 point run-to-run noise |

**What these gates cannot see.** The 2025 backtest league has no Vegas payload and rosters no IDP, so it barely
exercises the environment neutralisation, the game-status draw or the LB/DB hazards; it shows the
change did not damage the calibration it WAS measuring. The evidence for the big changes is the
measurements above and the live record: on 2026 weeks 1-4 the old engine's quoted team totals ran
+5.7 points per team-week above realised, and the neutralisation moves the week01 scenario by about
-5.5 points. That agreement in direction and size is consistent, not an out-of-sample validation:
the first real test is the next weeks' prediction records, which now carry each player's baseline,
ratio, script and availability.

## What would change these

* Item 6 is the soft one. Re-run `scripts.env_check` each week; if the interval stops containing 0.71,
  re-derive (a constant change is MAJOR-class).
* Item 1's "known absence" assumption: if a season of rostered Questionable players shows managers
  START the ones who then sit (the locked share), `GAME_STATUS_*` needs a locked-zero branch.
* A season of the new prediction record (`median[team].lineup` carries each player's baseline, ratio,
  script and availability) makes the whole quoted-vs-realised gap decomposable by stage.

## Files

`analysis/` (scripts, `results/`), `fantasy_sim/config.py` (constants, each citing this file),
`fantasy_sim/simulation.py` (`game_status_play_probability`, `_initial_absence_clock`,
`_neutralize_projection_environment`), `fantasy_sim/decisions.py` (`availability_factor`),
`fantasy_sim/availability_watch.py` / `clients/ags.py` (practice stamp), `scripts/env_check.py`,
tests `test_game_status_availability.py`, `test_derived_constants.py`, `test_env_check.py`.
