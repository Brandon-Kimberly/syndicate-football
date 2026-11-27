# Luck ledger — pre-registration

**Registered 2026-09-21, before the rest of the 2026 season was played.** The git history
of this file and of `fantasy_sim/luck_ledger.py` is the timestamp.

## Why this exists

The owner's standing question is *"am I genuinely unlucky, or does it just feel that
way?"* — and the reason it is hard to answer honestly is that **any** specific sequence of
events is improbable after the fact. A 1.39-point loss in which a reversed fumble call
extends overtime is a one-in-something event; so is every other week, viewed narrowly
enough. Post-hoc probability is not evidence.

The only defence is to fix the measurements **before** the data arrives, then read
whatever they say. That is what this document is. Changing a definition after seeing an
answer converts this from a test into a story, and the whole thing becomes worthless.

## The five measurements

Each is reported separately, with its own standard error and two-sided p-value. **No
combined "luck score" is produced** — deliberately, matching `season_retrospective`'s
refusal of a combined verdict. A single blended number is exactly the thing that invites
narrative-fitting.

*Amended 2026-11-27 by the owner's ruling (see "Addendum 2" below):* these five are still
never blended. One total is now reported, but it comes from an exact accounting, not from
weights: total luck in wins = performance luck + schedule luck + median luck, where each
part is defined independently and the three add up exactly.

| metric | definition | null | lucky direction |
|---|---|---|---|
| `schedule_luck` | actual H2H wins − all-play expected wins | 0 | **+** |
| `opponent_luck` | my points-against per game − league average | 0 | **−** |
| `close_games` | W−L in H2H decided by < 10.0 points | .500 | **+** |
| `dnp_luck` | my starter-DNPs per game − league average | 0 | **−** |
| `scoring_luck` | my mean weekly z − league mean weekly z | 0 | **+** |

`CLOSE_MARGIN = 10.0`. A margin of *exactly* 10.0 is **not** close (strict inequality).
`DNP_EPSILON = 1e-9`: a starter scoring exactly 0.00 is the DNP proxy — the same proxy
`season_retrospective` uses, and it cannot distinguish "inactive" from "played and scored
nothing".

## The one methodological commitment

**Every metric is differenced against the league, never against an absolute.**

The engine has measured bias — points-backtest `bias −2.12`, `cover80 0.654` against a
nominal 0.80, optimal sd inflation ~1.27. Scoring a team's z against zero would therefore
re-measure *the model's error* and report it as *that team's luck*. Differencing against
the league cancels everything shared and leaves only what is specific to one roster.

This is why `scoring_luck` compares `my_mean_z` to `league_mean_z` rather than to 0.

## What it cannot do

- **It will not be significant soon.** Schedule luck over a 14-game season carries an SE
  near ±1.8 wins, so even a 2-win deficit is barely 1 SE. Below six completed weeks the
  tool prints `too early` instead of a significance word, on purpose.
- **`scoring_luck` only exists from 2026.** It needs contemporaneous projections, and
  `data/logs/predictions_2026.jsonl` began this season. 2024 and 2025 report `None`
  rather than a fabricated zero.
- **2024's `dnp_luck` is contaminated.** That season had an abandoned roster whose owner
  stopped setting lineups, so its starters score 0.00 in bulk and the league-average DNP
  rate is inflated (2.12/game against 0.43 for the owner). Read 2024's DNP row as
  unusable, not as good luck.
- **The renewal chain is broken at 2025.** `previous_league_id` is `None` there, so the
  chain alone reaches only 2026 and 2025. Set **`SLEEPER_LEAGUE_ID_2024`** and `--all`
  picks 2024 up through `config.KNOWN_LEAGUE_IDS` (B20). League ids are environment-only
  (F37) and are never written down here.
- **Refereeing, negated touchdowns and similar are not measured at all.** Sleeper does not
  log plays that were called back. That grievance is real and this tool is silent on it;
  it is not evidence either way.

## Standing result

Recorded at registration so later readings have a baseline:

| season | schedule | opponent | close | DNP |
|---|---|---|---|---|
| 2024 (14 wk) | **−1.14** unlucky | +1.28 unlucky | −0.50 unlucky | *contaminated* |
| 2025 (14 wk) | **−1.14** unlucky | +3.46 unlucky | −0.50 unlucky | −0.06 lucky |
| 2026 (2 wk) | −0.43 unlucky | +5.27 unlucky | 0.00 neutral | −0.69 lucky |

Schedule luck landed at **−1.14 in both completed seasons** — the same direction twice.
Pooled that is −2.28 wins against a pooled SE near ±2.6, **z ≈ −0.88, p ≈ 0.38**: a
consistent lean, and still indistinguishable from chance. Two seasons is not enough, which
is the point of writing it down and waiting.

## Correction, 2026-11-27 (F95): four defects, no definition changed

Found reading the 2026 week-12 output. Every **delta** above is unchanged; what changed is
which weeks count, which seasons are withheld, and the error bars.

1. **Standard errors.** Opponent, DNP and scoring luck divided the spread of the *other*
   teams' season values by sqrt(7): the standard error of the league average, not of one
   team's difference from it. Under a null of eight identical teams that called 44% / 42% /
   49% of seasons significant at 5%. Now each team's weekly difference from that week's
   league average is pooled across the league (the null is that the teams are alike, so
   they share one spread) and divided by sqrt(weeks): 2.0% / 5.3% / 4.3% on the same
   null (`tests/test_luck_ledger_fixes.py`). A per-team spread was tried first and rejected:
   eleven differences gave error bars from 4 to 13 points for the same measure, and 8-10%
   false alarms.
2. **Unfinished weeks.** A week counted once any team had a point. On Thanksgiving Friday
   week 12 had 5-12 of every team's 13 starters still to play, each one a "DNP". Only weeks
   the league has closed (its banked games) now count.
3. **2025 was withheld for nothing.** The banked-record check added median wins to a season
   that had no median game (7 against the banked 4), and withheld schedule luck and close
   games. It now adds them only when the season had one.
4. **`--week` cut every season** in an `--all` run (the web UI passes the current week). It
   now cuts the current season only.

What moved, 2026 through week 11: Quantum Ferrets' opponent luck z +2.55 → +0.79 and scoring
luck z −2.99 → −1.61; Cosmic Badgers' opponent luck z −6.14 → −1.45. 2025's schedule luck is
back at −1.14 (z −0.63), the value recorded at registration. 2024's DNP row is still
contaminated by the abandoned roster and still unusable.

**Known limit, unchanged in kind:** p-values use the normal curve. With 11-14 weeks and the
spread estimated from the data, that is close but not exact (the calibration above), and
eight teams times eight measures will turn up a "significant" one by chance now and then.

## Addendum: three more, registered 2026-09-29

**Registered 2026-09-29, after weeks 1-3 of 2026 had been played and were visible on the web
UI, and before any of the three below had been computed by anything in this project.** They
are registered late, not post hoc: the owner asked for them (docs/WEB_UI_ROADMAP.md, Decision
2) and nothing had computed them on this season's data before this commit. The git history of
this file is the timestamp, and the implementation lands in a later commit. Every rule above
holds for them: each is shown separately, never combined with anything, and z and p are
withheld below `MIN_WEEKS_FOR_INFERENCE` (6).

| metric | definition | null | lucky direction |
|---|---|---|---|
| `forecast_luck` | my actual H2H wins − the sum of my quoted pre-game H2H win probabilities | 0 | **+** |
| `median_luck` | (my actual median wins − the sum of my quoted pre-game median probabilities) − the league average of the same | 0 | **+** |

Definitions, fixed now:

- **The quote** is the model's canonical pre-kickoff forecast for that week, the row
  `webui.accuracy.quoted_week` returns, which the Accuracy page scores. A week with no such
  quote, or with no result, is left out, and the count of weeks left out is reported.
- **Wins** are the league's record as played (F83, `webui.results.week_results`). A tie is
  half a win, and a tie against the median is half a median win.
- **Standard error:** sqrt(sum of p × (1 − p)) over the counted weeks, treating each quoted
  game as an independent Bernoulli trial. The median measure's league average is itself
  estimated, which the SE ignores; that is stated beside the number, not corrected.
- **`forecast_luck` is not separately differenced against the league.** Across the league
  the sum of wins equals the sum of the quoted chances (each game's two chances sum to one),
  so the league average is zero by construction. The methodological commitment is met by
  that identity.
- **`median_luck` is differenced.** The quoted median chances need not sum to half the league
  each week, so the league average of the raw difference is subtracted.

**The schedule-swap matrix** is descriptive, not a test: no null, no z, no p. Row A, column
B is the head-to-head record team A would have had on team B's schedule. For each played
week, A's score is set against the score of B's opponent that week; in the week B played A,
A is set against B instead. Scores are Sleeper's box scores, the same basis and the same
re-scored-weeks caveat as all-play. The diagonal is A's own record on box scores, which can
differ from the league's record where a week was re-scored (F83), and the page says so.

## Addendum 2: the wins accounting, registered 2026-11-27

**Registered late, and after seeing the data.** The owner asked for it on 2026-11-27, after
reading this ledger's 2024-2026 numbers (2026 through week 11). It also reverses the "no
combined number" rule above for exactly one figure, by the owner's ruling. Both facts are
stated here so nobody has to dig them out of the git log. The defence is the one this file
always relied on: the definitions below are committed BEFORE any code computes them, and
every choice is fixed here, not tuned to the answer.

**Why it is not a blend.** The five measures overlap: points against is HOW schedule luck
happens, close games are part of it, and starters who did not play are part of how a team
misses its projection. Adding them would count the same luck twice. The accounting below
splits one quantity, *actual wins minus the wins the roster's projections earned*, into
parts that do not overlap and add up exactly. The five stay as they were, shown as "where it
came from", and are never added in.

### Inputs, per season, per team, per week

- **Projection `P`** = the sum, over the players the team actually STARTED (Sleeper's
  matchup `starters`), of Sleeper's weekly projection for that player, scored under the
  scoring settings in force that week. 2026: the eras in `data/current/banked_scores.json`
  and `data/logs/scoring_settings.jsonl`. 2024 and 2025: that season's league settings as
  Sleeper serves them now, the same settings its box scores are re-scored under. A started
  player with no projection counts 0. **Sleeper only, for every season:** the engine blends
  ESPN for offensive players, but there is no ESPN archive for 2024-25, and one basis for
  all three seasons beats a better basis for one. Checked 2026-11-27: Sleeper's archived
  week-3 and week-10 projections match the last pre-game value the sync logged for 103 of
  104 starters each week, within 0.5 points.
- **Score `S`** = the points the league counted: the banked score where the sync has a
  verified one (2026), else Sleeper's box score.
- **Results** = head-to-head and median wins as the league counted them (as for schedule
  luck above). A tie is half a win.

### Noise scale

`σ` (one per season): the residuals `S − P`, minus that week's league-average residual,
pooled over every team-week; sum of squares over (teams − 1) degrees of freedom per week. A
team-week projected at 0 (2024's abandoned roster) is left out of `σ`.

### The parts, in wins

| part | definition |
|---|---|
| **expected wins** `E` | `E_h + E_m`. `E_h` = games × the mean over weeks and opponents of Φ((P_me − P_opp) / (σ√2)): the all-play win rate the projections earned, on an average schedule. `E_m` (median seasons only) = Σ weeks of P(my score finishes in the top half), from the simulation below. |
| **performance luck** | all-play wins from the scores (the registered schedule luck's expected wins) − `E_h`. Did the starters beat their projections by more or less than everyone else's? |
| **schedule luck** | actual head-to-head wins − all-play wins from the scores. The registered measure, unchanged. |
| **median luck** | actual median wins − `E_m`. Median seasons only. (Not the forecast-based `median_luck` of the first addendum, which uses the model's quoted chances; that one is unchanged.) |
| **total luck** | performance + schedule + median = actual wins − `E`. An identity. |
| **luck-neutral wins** | `E`. |

Every part sums to zero across the league each week, so the methodological commitment holds
by construction: a bias every projection shares cancels.

**Luck-neutral standings:** every team ranked by `E` beside its actual rank (wins, then
points for). Every team's luck is taken out, not only mine, because the others' luck moves my
rank too.

**Where it came from** (explanations, never added): points a week against projection
relative to the league, (my mean of `S − P`) − (league mean); points a week lost to starters
who scored 0.00 with a projection above 0, relative to the league; and the five registered
measures as they stand.

### How unusual

4,000 simulated seasons, seed 20261127: every team-week `S = P + σ·ε`, `ε` standard normal and
independent, on the real schedule. For each part, the share of simulated seasons at least as
extreme in the same direction, reported as "about 1 in N" (N = 1/share, rounded), with these
words: share ≥ 0.25 **ordinary**; 0.10-0.25 **a bit unusual**; 0.025-0.10 **unusual**; below 0.025
**rare**. Two-sided p (twice the share, capped at 1) in the developer view. Below
`MIN_WEEKS_FOR_INFERENCE` (6) weeks the share is withheld, as for the five.

### What it cannot do

- **Picking on projections biases the projections picked.** A manager who adds or starts the
  player with the highest projection tends to pick projections that are too high, and then
  "underperforms" them. Everyone does it, so the league difference cancels most of it; a
  manager who churns more than the league carries more. Not measured.
- **Projections are not equally good everywhere.** A roster heavy in a position Sleeper
  projects worse (IDP, kickers) can look systematically lucky or unlucky. Not separated.
- **Lineup calls are inside `E`, not in the luck.** Starting a player projected lower than a
  bench player lowers `E`; it does not count as bad luck. The accounting does not split
  roster building from lineup setting.
- **Timing.** The archive keeps the final pre-game projection. A starter ruled out after his
  game locked keeps his projection, and his zero counts as luck. A starter left in after he
  was already ruled out projects 0, so starting him costs `E`, not luck.
- **The noise is modelled as normal and the same for every team.** Real weekly scores are a
  little skewed, and an IDP-heavy roster may swing more than a quarterback-heavy one.
- **A commissioner override counts as points scored** (2026 week 2).
- **Eight teams, three seasons, several parts.** Something will look unusual by chance.

### Noted at implementation (2026-11-27, after the numbers were seen)

- **Schedule luck reads rarer here than its registered z says, and this one is closer to
  right.** The registered standard error treats each game as a coin at the season-average
  all-play rate. But a week you outscore everyone, or score less than everyone, cannot be
  won or lost to the schedule, so the real spread is smaller. Quantum Ferrets 2026 (weeks
  1-11): registered ±1.65 wins, the actual weekly rates give ±1.37, and the simulated null
  about ±1.25. The same −1.86 reads z −1.12 (about 1 in 8 one-sided) in the five-measure
  table and about 1 in 19 in the accounting. The registered measure is left as registered.
- **Across seasons: added after the per-season numbers were seen.** The owner's question was
  "year in and year out", so the script also sums each season's total luck for the owner's
  roster and compares it with the sum of one simulated season from each, each season's
  draws shuffled first (seed 20261127) so no two seasons share a random stream. It is only
  computed for the owner's own roster: `--team` names a current team, and the older seasons
  fall back to the owner's. *(Changed by F96, 2026-11-27: that fallback was a defect -- another
  team's run showed the owner's history. Each older season now follows the chosen team's OWNER,
  a season that owner was not in is said and skipped, and the total applies to any team.)*
- **Median luck is player luck too.** The median game has no schedule, so its part is the
  players-against-projection effect in the median games. The page labels it that way.

### Readings at implementation (2026-11-27), for the record

Quantum Ferrets and its earlier names; 2026 through week 11:

| season | actual wins | projected to earn | players, head-to-head | schedule | players, median | total | rank as played → luck removed |
|---|---|---|---|---|---|---|---|
| 2024 | 14 | 16.3 | +0.1 | −1.1 | −1.2 | −2.3 | 6th → 4th |
| 2025 | 4 | 5.5 | −0.3 | −1.1 | — | −1.5 | 8th → 8th |
| 2026 | 10 | 13.8 | −0.9 | −1.9 | −1.1 | −3.8 | 4th → 1st |

Together −7.5 wins over three seasons (about 1 in 21 three-season runs).

## Addendum 3: roster versus lineup calls, registered 2026-11-27

**Registered after the owner saw the Addendum 2 numbers**, the same day, and in answer to the
limit Addendum 2 named itself: "Lineup calls are inside `E`, not in the luck." Committed
before any code computes it. It adds a DECISION measure beside the luck; it changes no luck
part, no luck definition and no "how unusual".

### Inputs, per season, per team, per week

- **Roster `R`** = Sleeper's matchup `players` for that team-week: everyone on the roster that
  week as Sleeper recorded it. That list includes players in IR slots, and Sleeper does not
  archive who was on IR in a past week, so they stay in (see below).
- **Slots** = that season's league `roster_positions` with `BN`, `IR` and `TAXI` removed, as
  Sleeper serves them: 2024 fifteen (two QB, three RB, three WR, two TE, three FLEX, K, DEF),
  2025 eleven (QB, two RB, two WR, TE, three FLEX, K, DEF), 2026 thirteen (QB, two RB, two WR,
  TE, three FLEX, K, DL, LB, DB).
- **Eligibility** = each player's Sleeper `fantasy_positions` from the sync's players cache
  (`data/current/sleeper_players_cache.json`), read through `config.eligible_slots`; FLEX takes
  RB, WR and TE (`webui.trade`). A player the cache does not know is eligible for no slot.
- **Projection** = exactly Addendum 2's: Sleeper's archived weekly projection, scored under the
  settings in force that week. **A player with no projection counts 0**, started or not.

### The definitions

- **`P_best`** = the highest total projection any legal assignment of `R` to the slots
  reaches, solved exactly by the web UI's existing solver (`webui.trade.best_lineup`, scipy's
  `linear_sum_assignment`; the team page's "Before the games" uses the same one), and never
  below `P`: the lineup actually started was legal in Sleeper, so `P_best = max(solved, P)`.
  **Ties** cannot matter: only the total is used, never which lineup reached it.
- **`σ`** = Addendum 2's, unchanged (from the started lineups).
- **Roster-earned expected wins `E_best`** = `E_h_best + E_m_best`.
  `E_h_best` = games × the mean over weeks and opponents of Φ((P_best_me − P_opp) / (σ√2)),
  **the opponents keeping the projections they started**: one team's calls are priced with
  everyone else's as they were. `E_m_best` (median seasons only) = Σ weeks of P(my
  `P_best + σε` finishes in the top half against the others' `P + σε`), from the SAME 4,000
  simulated seasons and the SAME draws: one `ε` per team-week serves both `E_m` and `E_m_best`,
  so the two differ only by the projections.
- **Lineup calls, in wins** = `E − E_best`. Zero or negative by construction: Φ increases,
  `P_best ≥ P`, and with shared draws a higher score never finishes lower. Also reported:
  **lineup calls in points a week** = the mean over weeks of `P − P_best`.
- **The identity:** actual wins − `E_best` = lineup calls + total luck. Every luck part is
  still measured against `E`, the lineups started, exactly as registered in Addendum 2.

**Lineup calls are not luck.** They are never added into the luck total, carry no "1 in N",
and are labelled as decisions wherever they appear. Unlike the luck parts they do not sum to
zero across the league (every team's is zero or below) and are not differenced against it:
the ceiling is the team's own best lineup, so the absolute number is the meaningful one.

### What it cannot do

- **Best by the projection everyone could see**, not by what the manager knew. Benching a
  player on later news the projection had not caught is charged as a lineup call; so is the
  reverse luck of a hunch.
- **IR players are in `R`.** One Sleeper projected above 0 could be "started" by `P_best`
  although moving him off IR needed a roster move. Sleeper projects most IR players at 0.
- **Eligibility is today's**, not that week's: a player redesignated mid-season is priced at
  his current positions; a player missing from the cache is eligible nowhere.
- **No roster moves**: the best lineup is drawn from that week's roster, never free agents.
- **Lineups lock per game**, and the projection used is the final pre-game one for the week,
  so a swap that was no longer possible once a game had started is still offered.

## Usage

```
py -3.10 -m scripts.luck_ledger                                  # current season
py -3.10 -m scripts.luck_ledger --season 2025
py -3.10 -m scripts.luck_ledger --all                            # renewal chain
py -3.10 -m scripts.luck_ledger --all                            # 2024 needs SLEEPER_LEAGUE_ID_2024
py -3.10 -m scripts.luck_ledger --json
```

**Deliberately not wired into `scripts.weekly_report`** (owner's decision, 2026-09-21):
a luck number in front of you every Sunday is an invitation to read noise as persecution.
This is a thing you pull when you want it.

**Kept current, still not pushed (2026-11-27).** A successful LOCAL sync -- `scripts.run_sync`
from the Sync page or a terminal, or `scripts.weekly_report` with its sync -- reruns
`scripts.luck_ledger --json` afterwards (`fantasy_sim.luck_refresh`), so the web UI's Luck page
reads this week's numbers. Best effort: a failure is one `[luck]` line in the log and never
fails the sync or the report; never on a GitHub runner, where `data/local` does not survive.
Nothing appears in the digest, the report or Home.
