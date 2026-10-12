"""Game-time injury status is now priced (owner request, 2026-10-12; derived constants).

Until now the engine drew a `Questionable` or `Doubtful` player HEALTHY ("no game-time-probability
source", AUDIT_PLAN F4) and the tools called Sleeper's projection a discount that "would double-count"
(B4). Both premises are now measured (docs/audit/DERIVED_CONSTANTS_2026-10.md):

  * 2016-2025, fantasy-relevant starters (>= 50% snap share, >= 6 games): P(plays | Questionable) =
    0.739 and P(plays | Doubtful) = 0.016 (n = 6035 and 643); by position and by the practice
    report the Questionable figure runs 0.29 (QB, did not practice) to 0.95 (DL, full practice).
  * Sleeper does NOT discount: for 39 rostered Questionable players the projection was 1.03x the
    same player's healthy-week projection (control 1.01x, n = 159).
  * Persistence: after a missed game P(misses the next too) = 0.276 (Questionable), 0.397 (Doubtful).
  * Among 11 rostered Questionable players who did not play in 2026 weeks 3-4, 0 were in a started
    lineup (the manager knew), so a drawn absence is KNOWN, not a locked zero.

Written before the code.
"""
import unittest

import numpy as np

import tests.test_decisions as td
from fantasy_sim.config import SIM_CONFIG
from fantasy_sim.simulation import FantasySimulationEngine

POSITIONS = ("QB", "RB", "WR", "TE", "DL", "LB", "DB")
clock = FantasySimulationEngine._initial_absence_clock


class TestTheConstants(unittest.TestCase):
    def test_every_position_has_a_probability_and_a_default(self):
        play = SIM_CONFIG["GAME_STATUS_PLAY_PROBABILITY"]
        for status in ("Questionable", "Doubtful"):
            self.assertIn("DEFAULT", play[status])
            for pos in POSITIONS:
                self.assertTrue(0.0 <= play[status].get(pos, play[status]["DEFAULT"]) <= 1.0)

    def test_doubtful_is_far_below_questionable_and_questionable_below_certain(self):
        play = SIM_CONFIG["GAME_STATUS_PLAY_PROBABILITY"]
        for pos in POSITIONS:
            q, d = play["Questionable"].get(pos, play["Questionable"]["DEFAULT"]), play["Doubtful"].get(pos, play["Doubtful"]["DEFAULT"])
            self.assertLess(d, 0.1)
            self.assertLess(q, 0.95)
            self.assertGreater(q, 0.4)

    def test_practice_report_orders_the_questionable_probabilities(self):
        by = SIM_CONFIG["QUESTIONABLE_PLAY_PROBABILITY_BY_PRACTICE"]
        for pos in POSITIONS + ("DEFAULT",):
            self.assertGreater(by[pos]["full"], by[pos]["limited"])
            self.assertGreater(by[pos]["limited"], by[pos]["dnp"])

    def test_the_doc_that_derives_them_is_named_where_they_are_defined(self):
        import os
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src = open(os.path.join(root, "fantasy_sim", "config.py"), encoding="utf-8").read()
        self.assertIn("DERIVED_CONSTANTS_2026-10", src)
        self.assertTrue(os.path.exists(os.path.join(root, "docs", "audit", "DERIVED_CONSTANTS_2026-10.md")))


class TestTheClock(unittest.TestCase):
    def draws(self, status, pos, practice=None, n=20000, seed=5):
        np.random.seed(seed)
        return np.array([clock(status, False, pos, practice) for _ in range(n)])

    def test_without_a_position_the_old_contract_holds_and_no_rng_is_used(self):
        state = np.random.get_state()
        for status in ("Questionable", "Doubtful"):
            self.assertEqual(clock(status, False), 0)
        after = np.random.get_state()
        self.assertTrue(np.array_equal(state[1], after[1]) and state[2] == after[2])

    def test_a_questionable_player_misses_this_week_at_one_minus_the_play_probability(self):
        play = SIM_CONFIG["GAME_STATUS_PLAY_PROBABILITY"]["Questionable"]
        for pos in ("QB", "WR", "DB"):
            d = self.draws("Questionable", pos)
            self.assertAlmostEqual((d == 0).mean(), play.get(pos, play["DEFAULT"]), delta=0.012, msg=pos)

    def test_a_doubtful_player_almost_never_plays(self):
        d = self.draws("Doubtful", "WR")
        self.assertLess((d == 0).mean(), 0.05)

    def test_the_practice_report_moves_a_questionable_probability_not_a_doubtful_one(self):
        by = SIM_CONFIG["QUESTIONABLE_PLAY_PROBABILITY_BY_PRACTICE"]
        for pr in ("full", "limited", "dnp"):
            self.assertAlmostEqual((self.draws("Questionable", "TE", pr) == 0).mean(), by["TE"][pr], delta=0.012, msg=pr)
        a = (self.draws("Doubtful", "TE", "dnp") == 0).mean()
        b = (self.draws("Doubtful", "TE", "full") == 0).mean()
        self.assertAlmostEqual(a, b, delta=0.01)

    def test_an_unlisted_position_uses_the_default_not_a_crash(self):
        d = self.draws("Questionable", "K")
        self.assertAlmostEqual((d == 0).mean(), SIM_CONFIG["GAME_STATUS_PLAY_PROBABILITY"]["Questionable"]["DEFAULT"], delta=0.012)

    def test_a_miss_lasts_one_game_most_of_the_time_and_persistence_matches_the_measurement(self):
        for status in ("Questionable", "Doubtful"):
            d = self.draws(status, "WR", n=40000)
            missed = d[d > 0]
            self.assertTrue(((missed >= 1) & (missed <= 16)).all())
            h = SIM_CONFIG["GAME_STATUS_FIRST_WEEK_RETURN_HAZARD"][status]
            self.assertAlmostEqual((missed == 1).mean(), h, delta=0.03, msg=status)

    def test_the_league_ir_slot_still_dominates(self):
        np.random.seed(2)
        d = np.array([clock("Questionable", True, "WR", "full") for _ in range(5000)])
        self.assertTrue((d >= 1).all())
        self.assertAlmostEqual((d == 1).mean(), SIM_CONFIG["ABSENCE_RETURN_HAZARD_STEADY"], delta=0.02)

    def test_out_and_ir_are_unchanged(self):
        np.random.seed(4)
        d = np.array([clock("Out", False, "WR", None) for _ in range(20000)])
        self.assertAlmostEqual((d == 1).mean(), SIM_CONFIG["ABSENCE_RETURN_HAZARD_FIRST_WEEK"], delta=0.012)


class TestThePracticeToken(unittest.TestCase):
    def test_the_feed_wording_maps_to_the_three_tokens(self):
        from fantasy_sim.clients import ags
        self.assertEqual(ags.practice_token("BUF WR · Shoulder · Did not practice · Week 5 at LA"), "dnp")
        self.assertEqual(ags.practice_token("BUF WR · Shoulder · Limited in practice · Week 5 at LA"), "limited")
        self.assertEqual(ags.practice_token("BUF WR · Shoulder · Full practice · Week 5 at LA"), "full")
        self.assertIsNone(ags.practice_token("BUF WR · Shoulder"))
        self.assertIsNone(ags.practice_token(None))

    def test_the_fetched_report_carries_it(self):
        from tests.test_availability_watch import _get_factory, NEWS, NOW
        from fantasy_sim.clients import ags
        news = dict(NEWS)
        news["items"] = [dict(NEWS["items"][1], description="KC RB · Knee · Limited in practice · Week 6")]
        out = ags.fetch_injury_report(get=_get_factory(news=news), now=NOW)
        self.assertEqual(out["players"]["4881"]["practice"], "limited")

    def test_the_sync_annotates_a_matching_questionable_player_only(self):
        from fantasy_sim.availability_watch import annotate_practice
        baselines = {"A": {"injury_status": "Questionable", "player_id": "1"},
                     "B": {"injury_status": "Questionable", "player_id": "2"},
                     "C": {"injury_status": "Out", "player_id": "3"},
                     "D": {"injury_status": None, "player_id": "4"},
                     "E": {"injury_status": "Questionable", "player_id": "5"}}
        players = {"1": {"status": "Questionable", "week": 6, "practice": "dnp"},
                   "2": {"status": "Questionable", "week": 5, "practice": "full"},      # another week's report
                   "3": {"status": "Out", "week": 6, "practice": "dnp"},                # not Questionable
                   "4": {"status": "Questionable", "week": 6, "practice": "full"},      # Sleeper shows healthy
                   "5": {"status": "Doubtful", "week": 6, "practice": "dnp"}}           # statuses disagree
        n = annotate_practice(baselines, players, 6)
        self.assertEqual(n, 1)
        self.assertEqual(baselines["A"]["practice_status"], "dnp")
        for k in "BCDE":
            self.assertNotIn("practice_status", baselines[k])

    def test_a_stale_annotation_is_cleared_on_the_next_sync(self):
        from fantasy_sim.availability_watch import annotate_practice
        baselines = {"A": {"injury_status": "Questionable", "player_id": "1", "practice_status": "dnp"}}
        annotate_practice(baselines, {}, 6)
        self.assertNotIn("practice_status", baselines["A"])


class TestTheWeekTools(td._EngineCase):
    """The decision tools price the same availability the simulation does."""

    def _expect(self, name, **over):
        from fantasy_sim.decisions import week_expectation
        e = self.engine.baselines[name]
        saved = {k: e.get(k) for k in over}
        e.update(over)
        try:
            return week_expectation(self.engine, name, self.engine.current_week)
        finally:
            for k, v in saved.items():
                if v is None:
                    e.pop(k, None)
                else:
                    e[k] = v

    def _a_wr(self):
        return next(n for n, e in self.engine.baselines.items() if isinstance(e, dict) and e.get("pos") == "WR" and e.get("bye") != self.engine.current_week)

    def test_a_doubtful_player_is_worth_almost_nothing_this_week(self):
        n = self._a_wr()
        healthy = self._expect(n, injury_status=None)
        self.assertLess(self._expect(n, injury_status="Doubtful"), 0.05 * healthy)

    def test_a_questionable_player_is_worth_his_play_probability(self):
        n = self._a_wr()
        healthy = self._expect(n, injury_status=None)
        p = SIM_CONFIG["GAME_STATUS_PLAY_PROBABILITY"]["Questionable"]
        self.assertAlmostEqual(self._expect(n, injury_status="Questionable") / healthy, p.get("WR", p["DEFAULT"]), places=3)

    def test_the_practice_report_refines_it(self):
        n = self._a_wr()
        healthy = self._expect(n, injury_status=None)
        by = SIM_CONFIG["QUESTIONABLE_PLAY_PROBABILITY_BY_PRACTICE"]["WR"]
        self.assertAlmostEqual(self._expect(n, injury_status="Questionable", practice_status="dnp") / healthy, by["dnp"], places=3)

    def test_another_week_is_not_discounted(self):
        from fantasy_sim.decisions import week_expectation
        n = self._a_wr()
        e = self.engine.baselines[n]
        later = self.engine.current_week + 1
        base = week_expectation(self.engine, n, later)
        e["injury_status"] = "Doubtful"
        try:
            self.assertAlmostEqual(week_expectation(self.engine, n, later), base)
        finally:
            e.pop("injury_status", None)


if __name__ == "__main__":
    unittest.main()
