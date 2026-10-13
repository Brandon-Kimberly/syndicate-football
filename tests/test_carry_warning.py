"""The carried-baseline warning must say WHY a player's projection is zero.

A bye-week player (no game this week) gets a zero Sleeper projection that is correct. The old
text told the reader he 'enters the engine through absence handling if his status warrants it',
which reads as an injury concern. Fixtures use invented names only (F73)."""
import unittest

from fantasy_sim.sync import carried_zero_warning


class CarriedZeroWarning(unittest.TestCase):
    def test_bye_week_player_is_described_as_a_bye(self):
        text = carried_zero_warning(name="Alpha Runner", pos="RB", team="AAA", status=None,
                                    on_ir=False, source="carried_prior", mean=12.0,
                                    week=6, bye_week=6)
        self.assertIn("; CARRIED ", text)            # the gate's benign marker must survive
        self.assertIn("BYE", text)
        self.assertIn("week 6", text)
        self.assertNotIn("if his status warrants it", text)

    def test_out_player_keeps_the_absence_wording(self):
        text = carried_zero_warning(name="Beta Receiver", pos="WR", team="BBB", status="Out",
                                    on_ir=False, source="carried_log", mean=8.0,
                                    week=6, bye_week=9)
        self.assertIn("; CARRIED ", text)
        self.assertIn("injury_status=Out", text)
        self.assertIn("if his status warrants it", text)
        self.assertNotIn("BYE", text)

    def test_missing_bye_week_is_treated_as_not_a_bye(self):
        text = carried_zero_warning(name="Gamma Tight", pos="TE", team="CCC", status=None,
                                    on_ir=False, source="carried_prior", mean=5.0,
                                    week=6, bye_week=None)
        self.assertNotIn("BYE", text)
        self.assertIn("if his status warrants it", text)


if __name__ == "__main__":
    unittest.main()
