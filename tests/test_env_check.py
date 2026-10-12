"""scripts.env_check: the pure parts of the weekly re-measurement of ENV_SHARE_IN_PROJECTION. No
network: `fetch_inputs` is the one seam and is patched where main() is exercised."""
import json
import unittest
from unittest.mock import patch

from scripts import env_check as ec


class TestOls(unittest.TestCase):
    def test_recovers_an_exact_line(self):
        b, se = ec.ols([0.0, 1.0, 2.0, 3.0, 4.0], [1.0, 3.0, 5.0, 7.0, 9.0])
        self.assertAlmostEqual(b, 2.0)
        self.assertAlmostEqual(se, 0.0, places=9)

    def test_a_noisy_line_has_a_positive_standard_error(self):
        b, se = ec.ols([0, 1, 2, 3, 4, 5], [0.1, 0.9, 2.3, 2.8, 4.2, 4.9])
        self.assertAlmostEqual(b, 0.98, delta=0.1)
        self.assertGreater(se, 0.0)


class TestTheInputs(unittest.TestCase):
    ROWS = [{"week": "5", "gameday": "2026-10-11", "home_team": "DET", "away_team": "GB", "total_line": "50.0", "spread_line": "3.5"},
            {"week": "5", "gameday": "2026-10-08", "home_team": "LA", "away_team": "BUF", "total_line": "44.0", "spread_line": "-2.0"},
            {"week": "5", "gameday": "2026-10-11", "home_team": "KC", "away_team": "NE", "total_line": "", "spread_line": ""}]

    def test_the_cutoff_is_the_first_sundays_seventeen_hundred_utc(self):
        self.assertEqual(ec.week_cutoffs(self.ROWS), {5: "2026-10-11T17:00:00Z"})

    def test_implied_totals_follow_the_home_favoured_positive_spread_and_alias_old_codes(self):
        t = ec.implied_totals(self.ROWS)
        self.assertEqual((t[(5, "DET")], t[(5, "GB")]), (26.75, 23.25))
        self.assertEqual((t[(5, "LAR")], t[(5, "BUF")]), (21.0, 23.0))
        self.assertNotIn((5, "KC"), t, "a game with no line is not invented")

    def test_the_last_projection_before_the_cutoff_wins_and_small_ones_are_dropped(self):
        rows = [json.dumps({"week": 5, "player_id": "1", "pos": "WR", "sleeper_mean": 9.0, "synced_at": "2026-10-09T10:00:00Z"}),
                json.dumps({"week": 5, "player_id": "1", "pos": "WR", "sleeper_mean": 11.0, "synced_at": "2026-10-10T10:00:00Z"}),
                json.dumps({"week": 5, "player_id": "1", "pos": "WR", "sleeper_mean": 3.0, "synced_at": "2026-10-11T18:00:00Z"}),   # after the cutoff
                json.dumps({"week": 5, "player_id": "2", "pos": "WR", "sleeper_mean": 4.0, "synced_at": "2026-10-10T10:00:00Z"}),   # below 6
                json.dumps({"week": 5, "player_id": "3", "pos": "LB", "sleeper_mean": 9.0, "synced_at": "2026-10-10T10:00:00Z"})]   # not offense
        got = ec.last_projections(rows, {5: "2026-10-11T17:00:00Z"})
        self.assertEqual(got, {("1", 5): (11.0, "WR")})

    def test_lines_are_scored_under_the_given_weights_and_only_regular_season(self):
        season = {"games": {"g1": [5, "REG", "DET", "GB"], "g2": [19, "POST", "DET", "GB"]},
                  "lines": [["g1", "p1", "DET", {"rec": 5, "rec_yd": 60}], ["g2", "p1", "DET", {"rec": 9}]]}
        pts, team = ec.score_lines(season, {"rec": 0.5, "rec_yd": 0.1})
        self.assertEqual(pts, {("p1", 5): 8.5})
        self.assertEqual(team, {("p1", 5): "DET"})


class TestTheMeasurement(unittest.TestCase):
    def synthetic(self, slope, n_teams=12):
        """players whose relative residual is exactly `slope` x their team's relative implied total"""
        implied = {(5, f"T{i}"): 18.0 + 1.5 * i for i in range(n_teams)}
        level = sum(implied.values()) / len(implied)
        proj, pts, team, ids = {}, {}, {}, {}
        for i in range(n_teams):
            for j in range(3):
                pid = f"{i}-{j}"
                m = 10.0 + j
                r = implied[(5, f"T{i}")] / level - 1.0
                proj[(pid, 5)] = (m, "WR")
                pts[(f"g{pid}", 5)] = m * (1.0 + slope * r)
                team[(f"g{pid}", 5)] = f"T{i}"
                ids[pid] = f"g{pid}"
        return proj, ids, pts, team, implied

    def test_it_recovers_the_slope_it_was_built_with(self):
        for slope in (0.0, 0.29, 1.0):
            b, se, n = ec.measure(*self.synthetic(slope))
            self.assertAlmostEqual(b, slope, places=6, msg=slope)
            self.assertEqual(n, 36)

    def test_too_few_rows_is_not_a_number(self):
        proj, ids, pts, team, implied = self.synthetic(0.3, n_teams=1)
        self.assertEqual(ec.measure(dict(list(proj.items())[:2]), ids, pts, team, implied)[0], None)

    def test_the_verdict_says_inside_outside_and_cannot_tell(self):
        inside = ec.verdict(0.29, 0.10, 400, 0.71)
        self.assertTrue(any("inside the interval" in line for line in inside))
        outside = ec.verdict(0.75, 0.05, 400, 0.71)               # share 0.25, interval 0.15-0.35
        self.assertTrue(any("OUTSIDE" in line for line in outside))
        vague = ec.verdict(0.5, 0.4, 400, 0.71)                   # share 0.5, interval -0.28 to 1.28
        self.assertTrue(any("cannot yet tell" in line for line in vague))

    def test_main_refuses_below_the_minimum_without_printing_a_verdict(self):
        import io
        from contextlib import redirect_stdout
        with patch.object(ec, "fetch_inputs", return_value=([{"week": "5", "gameday": "2026-10-11", "home_team": "DET", "away_team": "GB",
                                                              "total_line": "50", "spread_line": "3"}], {"games": {}, "lines": []}, {})), \
                patch.object(ec, "league_weights", return_value={"rec": 0.5}), \
                patch("builtins.open", side_effect=lambda *a, **k: io.StringIO("")) as _o:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = ec.main()
        self.assertEqual(rc, 0)
        self.assertIn("too early", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
