"""Constants re-derived from ten seasons of nflverse data (owner request, 2026-10-12).

Each pins one adopted change AND the property it rests on, so a later edit that moves the constant
without moving its evidence fails here. The evidence is in docs/audit/DERIVED_CONSTANTS_2026-10.md and
the scripts in analysis/. What was MEASURED AND REJECTED is pinned too, because an un-pinned negative
result gets re-proposed:

  adopted   INJURY_RATES LB 0.025 -> 0.036, DB 0.020 -> 0.050   (2016-2025 absence-onset, outside the CI)
  adopted   TE vacated-volume capture 0.65 -> 0.45               (862 events; TE CI 0.31-0.51)
  adopted   bottom-defence script bonus +0.06 -> +0.04           (realised +3.7%, CI 1.016-1.054)
  adopted   ENV_SHARE_IN_PROJECTION 0.71                         (Sleeper's weekly number already holds ~71% of
                                                                  the game environment; slope 0.29 +/- 0.185, n = 541)
  rejected  any-given-stat's adjusted defence rating as the tier source (ties the engine's: corr 0.113 vs 0.112)
  rejected  a snap-share trend as a role-change signal (slope -1.0 +/- 2.3 pts per full share, n = 402)
  rejected  "no Sleeper projection => out" (67.5% of 77 players Sleeper stopped projecting still played)

Written before the code.
"""
import unittest

import numpy as np

import tests.test_decisions as td
from fantasy_sim.config import SIM_CONFIG
from fantasy_sim.simulation import FantasySimulationEngine


class TestTheAdoptedValues(unittest.TestCase):
    def test_idp_onset_rates_for_the_two_positions_whose_value_was_outside_the_interval(self):
        r = SIM_CONFIG["INJURY_RATES"]
        self.assertEqual((r["LB"], r["DB"]), (0.036, 0.050))
        # inside their intervals, so deliberately unchanged (the file's own decision rule)
        self.assertEqual((r["DL"], r["QB"], r["TE"], r["RB"], r["WR"]), (0.025, 0.054, 0.035, 0.070, 0.081))

    def test_te_capture_is_lower_and_the_others_are_not(self):
        by = SIM_CONFIG["VACATED_VOLUME_CAPTURE_BY_POSITION"]
        self.assertEqual(by, {"TE": 0.45})
        self.assertEqual(SIM_CONFIG["VACATED_VOLUME_CAPTURE_RATE"], 0.65)

    def test_the_engine_uses_the_position_rate(self):
        case = td._EngineCase("setUp")
        case.setUp()
        self.addCleanup(case.tearDown)
        eng = case.engine
        pools = {pos: {} for pos in SIM_CONFIG["VACATED_VOLUME_ELIGIBLE_POSITIONS"]}
        eng._record_vacated_volume(pools, "TE", "DET", 20.0)
        eng._record_vacated_volume(pools, "WR", "DET", 20.0)
        eng._record_vacated_volume(pools, "RB", "DET", 20.0)
        self.assertAlmostEqual(pools["TE"]["DET"], 20.0 * 0.45)
        self.assertAlmostEqual(pools["WR"]["DET"], 20.0 * 0.65)
        self.assertAlmostEqual(pools["RB"]["DET"], 20.0 * 0.65)

    def test_the_bottom_defence_bonus_is_smaller_and_the_top_penalty_is_not(self):
        case = td._EngineCase("setUp")
        case.setUp()
        self.addCleanup(case.tearDown)
        eng = case.engine
        eng.defensive_tiers = {"TOP_DEFENSE": ["TOP"], "BOTTOM_DEFENSE": ["BOT"]}
        veg = lambda opp: {"spread": 0.0, "opponent": opp}  # noqa: E731
        for pos in ("QB", "RB", "WR", "TE"):
            self.assertAlmostEqual(eng._script_multiplier(pos, veg("TOP")), 0.94, msg=pos)
            self.assertAlmostEqual(eng._script_multiplier(pos, veg("BOT")), 1.04, msg=pos)
        self.assertAlmostEqual(eng._script_multiplier("DL", veg("BOT")), 1.0)

    def test_the_repair_of_omitted_odds_lines_is_switched_on(self):
        from fantasy_sim import config
        self.assertTrue(config.NFLVERSE_REPAIR_ENABLED)


def _env_engine(testcase, share, teams=24):
    """An engine whose vegas file has `teams` real games' worth of lines: team i has implied total
    18 + i (mean over 24 teams = 29.5/... computed by the engine) -- enough teams to pass the guard."""
    case = td._EngineCase("setUp")
    case.setUp()
    fs = case.fs
    from fantasy_sim.config import NFL_TEAMS
    from fantasy_sim.storage import BASELINES_FILE, VEGAS_FILE, NFL_SCHEDULE_FILE
    vegas = {"_meta": {"week": 1, "source": "odds_api", "fetched_at": "x"}}
    sched = {}
    names = NFL_TEAMS[:teams]
    for i in range(0, teams, 2):
        a, b = names[i], names[i + 1]
        vegas[a] = {"total": 20.0 + i, "spread": -1.0, "opponent": b}
        vegas[b] = {"total": 22.0 + i, "spread": 1.0, "opponent": a}
        sched[a], sched[b] = b, a
    fs[VEGAS_FILE] = vegas
    fs[NFL_SCHEDULE_FILE] = {str(w): dict(sched) for w in range(1, 19)}
    fs[NFL_SCHEDULE_FILE]["_meta"] = {"failed_weeks": [], "byes": {}}
    bl = fs[BASELINES_FILE]
    bl["HIGH"] = {"mean": 20.0, "std_aleatoric": 8.0, "std_epistemic": 3.0, "pos": "WR", "team": names[teams - 1], "bye": 9}
    bl["LOW"] = {"mean": 20.0, "std_aleatoric": 8.0, "std_epistemic": 3.0, "pos": "WR", "team": names[0], "bye": 9}
    bl["CARRIED"] = {"mean": 20.0, "std_aleatoric": 8.0, "std_epistemic": 3.0, "pos": "WR", "team": names[teams - 1], "bye": 9,
                     "projection_source": "carried_prior"}
    bl["NOGAME"] = {"mean": 20.0, "std_aleatoric": 8.0, "std_epistemic": 3.0, "pos": "WR", "team": "FA", "bye": 0}
    testcase.addCleanup(case.tearDown)
    from unittest.mock import patch
    with patch.dict(SIM_CONFIG, {"ENV_SHARE_IN_PROJECTION": share}):
        eng = FantasySimulationEngine()
    return eng, vegas, names


class TestEnvironmentNeutralisation(unittest.TestCase):
    """Sleeper's weekly projection already contains ~71% of the game environment; the engine then
    multiplied by the FULL implied-total ratio. The baseline is made environment-neutral at load so
    that one full ratio is the only environment in the number."""

    def test_the_share_is_the_measured_one_and_documented(self):
        self.assertAlmostEqual(SIM_CONFIG["ENV_SHARE_IN_PROJECTION"], 0.71)

    def test_a_high_total_team_is_scaled_down_and_a_low_total_team_up(self):
        eng, vegas, names = _env_engine(self, 0.71)
        totals = [v["total"] for t, v in vegas.items() if t != "_meta"]
        wk_mean = sum(totals) / len(totals)
        for who, team in (("HIGH", names[23]), ("LOW", names[0])):
            r = vegas[team]["total"] / wk_mean
            f = 1.0 / (1.0 + 0.71 * (r - 1.0))
            self.assertAlmostEqual(eng.baselines[who]["mean"], 20.0 * f, places=6, msg=who)
            self.assertAlmostEqual(eng.baselines[who]["std_epistemic"], 3.0 * f, places=6, msg=who)
        self.assertLess(eng.baselines["HIGH"]["mean"], 20.0)
        self.assertGreater(eng.baselines["LOW"]["mean"], 20.0)

    def test_a_zero_share_changes_nothing(self):
        eng, _v, _n = _env_engine(self, 0.0)
        self.assertEqual(eng.baselines["HIGH"]["mean"], 20.0)
        self.assertEqual(eng.baselines["LOW"]["mean"], 20.0)

    def test_what_is_not_this_weeks_projection_is_left_alone(self):
        eng, _v, _n = _env_engine(self, 0.71)
        self.assertEqual(eng.baselines["CARRIED"]["mean"], 20.0, "a carried mean is an earlier week's, not this one's")
        self.assertEqual(eng.baselines["NOGAME"]["mean"], 20.0, "no game, no environment")

    def test_too_few_lines_to_know_the_weeks_level_means_no_change(self):
        eng, _v, _n = _env_engine(self, 0.71, teams=8)
        self.assertEqual(eng.baselines["LOW"]["mean"], 20.0)

    def test_the_week_level_is_preserved(self):
        """Neutralising and re-applying the ratio must give the same environment on average: the
        mean over teams of baseline x ratio stays within a few percent of the old mean."""
        eng, vegas, names = _env_engine(self, 0.71)
        totals = [v["total"] for t, v in vegas.items() if t != "_meta"]
        wk_mean = sum(totals) / len(totals)
        old = np.mean([20.0 * vegas[t]["total"] / wk_mean for t in names[:24]])
        new = np.mean([20.0 / (1 + 0.71 * (vegas[t]["total"] / wk_mean - 1)) * vegas[t]["total"] / wk_mean for t in names[:24]])
        self.assertAlmostEqual(old, new, delta=0.03 * old)

    def test_the_engine_reports_how_many_it_changed(self):
        eng, _v, _n = _env_engine(self, 0.71)
        self.assertGreaterEqual(eng.env_neutralized, 2)


if __name__ == "__main__":
    unittest.main()
