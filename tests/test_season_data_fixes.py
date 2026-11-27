"""Fixes from the 2026 weeks 1-11 measurement pass (AUDIT_PLAN F91-F93, 2026-11-27).

Each class was written BEFORE its fix and failed against the code it describes. The
measurements themselves (pre-kickoff canonical quotes vs banked scores, weeks 6-11) are in the
F-entries; these tests pin the PROPERTY each measurement showed was violated, not the numbers.
"""
import unittest

import tests.test_decisions as td


class TestTheSpreadDoesNotMoveTheScriptMultiplier(unittest.TestCase):
    """F91. `_script_multiplier` added +0.15 to a favourite's RB, -0.10 to an underdog's, +0.10
    to an underdog's QB/WR/TE and +0.10 to a favourite's DL/DEF -- labelled UNVERIFIED in the
    code since 2026-10-12, with no source anywhere. Measured on 2026 weeks 6-11 (healthy quoted
    starters, pre-kickoff canonical rows): favoured RBs (mean multiplier 1.153, n=42) scored
    4.04 below their multiplied expectation (se 1.45), negative in 5 of 6 weeks, and only 1.44
    below it without the spread term; the same sign for every boosted group (QB -5.45, TE
    -3.68, WR -2.91), while the underdog penalties over-corrected (RB +1.00 multiplied vs -0.09
    without). The spread term is removed; the defensive-tier term, measured over 2017-2025
    (DEF_TIER_*), stays and is pinned by test_derived_constants."""

    def setUp(self):
        case = td._EngineCase("setUp")
        case.setUp()
        self.addCleanup(case.tearDown)
        self.eng = case.engine
        self.eng.defensive_tiers = {"TOP_DEFENSE": ["TOP"], "BOTTOM_DEFENSE": ["BOT"]}

    def test_no_position_moves_with_the_spread(self):
        for opp in ("MID", "TOP", "BOT"):
            for pos in ("QB", "RB", "WR", "TE", "K", "DL", "LB", "DB", "DEF"):
                neutral = self.eng._script_multiplier(pos, {"spread": 0.0, "opponent": opp})
                for spread in (-14.0, -5.5, 5.5, 14.0):
                    self.assertAlmostEqual(
                        self.eng._script_multiplier(pos, {"spread": spread, "opponent": opp}), neutral,
                        msg=f"{pos} v {opp} at spread {spread:+}")

    def test_the_defensive_tiers_still_apply(self):
        self.assertAlmostEqual(self.eng._script_multiplier("RB", {"spread": -7.0, "opponent": "TOP"}), 0.94)
        self.assertAlmostEqual(self.eng._script_multiplier("WR", {"spread": 7.0, "opponent": "BOT"}), 1.04)


def _blend_engine(testcase, weeks_observed, observed=20.0, share=0.71, teams=24):
    """test_derived_constants._env_engine's league (team i's implied total rises with i) plus
    `weeks_observed` completed weeks in which HIGH and LOW each scored `observed` -- so the
    Bayesian blend runs on them."""
    from unittest.mock import patch
    from fantasy_sim.config import NFL_TEAMS, SIM_CONFIG
    from fantasy_sim.simulation import FantasySimulationEngine
    from fantasy_sim.storage import (BASELINES_FILE, VEGAS_FILE, NFL_SCHEDULE_FILE, WEEKLY_ACTUALS_FILE,
                                    LEAGUE_STATE_FILE)
    case = td._EngineCase("setUp")
    case.setUp()
    testcase.addCleanup(case.tearDown)
    fs = case.fs
    fs[LEAGUE_STATE_FILE] = {"current_week": weeks_observed + 1}   # the lines are THIS week's, not stale
    vegas = {"_meta": {"week": weeks_observed + 1, "source": "odds_api", "fetched_at": "x"}}
    sched, names = {}, NFL_TEAMS[:teams]
    for i in range(0, teams, 2):
        a, b = names[i], names[i + 1]
        vegas[a] = {"total": 20.0 + i, "spread": -1.0, "opponent": b}
        vegas[b] = {"total": 22.0 + i, "spread": 1.0, "opponent": a}
        sched[a], sched[b] = b, a
    fs[VEGAS_FILE] = vegas
    fs[NFL_SCHEDULE_FILE] = {str(w): dict(sched) for w in range(1, 19)}
    fs[NFL_SCHEDULE_FILE]["_meta"] = {"failed_weeks": [], "byes": {}}
    bl = fs[BASELINES_FILE]
    bl["HIGH"] = {"mean": 20.0, "std_aleatoric": 8.0, "std_epistemic": 3.0, "pos": "WR", "team": names[teams - 1], "bye": 17}
    bl["LOW"] = {"mean": 20.0, "std_aleatoric": 8.0, "std_epistemic": 3.0, "pos": "WR", "team": names[0], "bye": 17}
    league = ['Quantum Ferrets', 'Neon Walruses', 'Rocket Pandas', 'Polar Yetis']
    fs[WEEKLY_ACTUALS_FILE] = {
        f"week_{w}": {"team_results": {t: {"points_scored": 100.0, "h2h_win": 0, "median_win": 0} for t in league},
                      "player_scores": {"HIGH": observed, "LOW": observed}}
        for w in range(1, weeks_observed + 1)}
    with patch.dict(SIM_CONFIG, {"ENV_SHARE_IN_PROJECTION": share}):
        eng = FantasySimulationEngine()
    totals = [v["total"] for t, v in vegas.items() if t != "_meta"]
    wk_mean = sum(totals) / len(totals)
    f = {who: 1.0 / (1.0 + share * (vegas[team]["total"] / wk_mean - 1.0))
         for who, team in (("HIGH", names[teams - 1]), ("LOW", names[0]))}
    return eng, f


class TestTheBlendDoesNotUndoTheNeutralisation(unittest.TestCase):
    """F92. ENV_SHARE_IN_PROJECTION neutralises each this-week projection BEFORE
    `_apply_bayesian_updates`, which then pulls the mean toward the player's realised average --
    and realised scores carry their games' full environment, so every observed week puts back
    environment the neutralisation took out. Measured on 2026 weeks 6-11: the slope of
    baseline/Sleeper on (env_ratio - 1) for healthy quoted starters was -0.50 where the
    neutralisation alone gives about -0.71 (about 70% surviving, the blend's prior weight), and
    starters in the highest-total games were lifted ~17% over Sleeper's projection where a 0.71
    share intends ~7%. scripts.env_check re-measured the share itself at 0.70 (0.48-0.91,
    n=1175): the constant is right, the ORDER was wrong.

    The property: observations equal to the raw projection carry no new information about the
    player, so they must leave the neutralised mean where it is."""

    def test_observations_equal_to_the_projection_leave_the_neutralised_mean_alone(self):
        eng, f = _blend_engine(self, weeks_observed=8)
        for who in ("HIGH", "LOW"):
            self.assertAlmostEqual(eng.baselines[who]["mean"], 20.0 * f[who], places=6, msg=who)

    def test_with_no_completed_weeks_the_neutralisation_is_unchanged(self):
        eng, f = _blend_engine(self, weeks_observed=0)
        for who in ("HIGH", "LOW"):
            self.assertAlmostEqual(eng.baselines[who]["mean"], 20.0 * f[who], places=6, msg=who)

    def test_a_player_who_outscores_his_projection_still_moves_up(self):
        eng, f = _blend_engine(self, weeks_observed=8, observed=30.0)
        self.assertGreater(eng.baselines["HIGH"]["mean"], 20.0 * f["HIGH"])


if __name__ == "__main__":
    unittest.main()
