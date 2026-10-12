"""The season movie's data preparation (fantasy_sim.season_movie): cumulative wins/points from the
banked results, bar-race frames that end exactly on the data, and odds series from canonical rows
only. Rendering needs matplotlib and is exercised by running the script, not here."""
import unittest

from fantasy_sim import season_movie as sm

BANKED = {
    "_meta": {"season": "2026"},
    "week_1": {"A": {"points": 100.0, "h2h_win": 1.0, "median_win": 1},
               "B": {"points": 90.0, "h2h_win": 0.0, "median_win": 0}},
    "week_2": {"A": {"points": 80.0, "h2h_win": 0.0, "median_win": 1},
               "B": {"points": 120.0, "h2h_win": 1.0, "median_win": 1}},
}


class TestBankedSeries(unittest.TestCase):
    def test_cumulative_wins_count_h2h_and_median_and_points_add_up(self):
        s = sm.banked_series(BANKED)
        self.assertEqual(s["weeks"], [1, 2])
        self.assertEqual(s["teams"], ["A", "B"])
        self.assertEqual(s["wins"], {"A": [2.0, 3.0], "B": [0.0, 2.0]})
        self.assertEqual(s["points"], {"A": [100.0, 180.0], "B": [90.0, 210.0]})
        self.assertEqual(s["weekly_points"]["B"], [90.0, 120.0])

    def test_a_week_added_later_is_just_another_stage(self):
        more = dict(BANKED, week_3={"A": {"points": 50.0, "h2h_win": 1.0, "median_win": 0},
                                    "B": {"points": 60.0, "h2h_win": 0.0, "median_win": 1}})
        self.assertEqual(sm.banked_series(more)["wins"]["A"], [2.0, 3.0, 4.0])


class TestRaceFrames(unittest.TestCase):
    def test_last_frame_is_the_data_and_positions_are_a_permutation(self):
        vals = sm.banked_series(BANKED)["points"]
        frames = sm.race_frames(vals, steps=5, hold=3)
        stage, state = frames[-1]
        self.assertEqual(stage, 1)
        self.assertEqual({t: v for t, (v, _) in state.items()}, {"A": 180.0, "B": 210.0})
        self.assertEqual(sorted(p for _, p in state.values()), [0.0, 1.0])
        self.assertEqual(state["B"][1], 0.0, "the leader is on top")

    def test_bars_glide_through_an_overtake(self):
        vals = {"A": [10.0, 10.0], "B": [5.0, 20.0]}
        mid = [p for _, st in sm.race_frames(vals, steps=10, hold=1)
               for p in [st["B"][1]] if 0.0 < st["B"][1] < 1.0]
        self.assertTrue(mid, "B's position passes through fractions, not a jump")


class TestPacing(unittest.TestCase):
    def test_default_pacing_is_readable_at_24_fps(self):
        """Owner, 2026-10-11: the first cut was too fast to read. A glide of at least 1.5 s, a rest
        of at least 1 s on each week, and a final hold of at least 3 s, at the renderer's 24 fps."""
        vals = {"A": [10.0, 20.0, 30.0], "B": [5.0, 25.0, 28.0]}
        frames = sm.race_frames(vals)
        stage_len = {}
        for stage, _ in frames:
            stage_len[stage] = stage_len.get(stage, 0) + 1
        self.assertGreaterEqual(stage_len[0] / 24.0, 1.0)
        self.assertGreaterEqual(stage_len[1] / 24.0, 1.5 + 1.0)
        self.assertGreaterEqual(stage_len[2] / 24.0, 1.5 + 1.0 + 3.0)


class TestOddsSeries(unittest.TestCase):
    def _row(self, at, week, canonical, champ):
        return {"record_type": "week_predictions", "logged_at": at, "week": week, "canonical": canonical,
                "season_outcomes": [{"Team": "A", "Champ_Pct": champ}, {"Team": "B", "Champ_Pct": 100 - champ}]}

    def test_only_canonical_rows_in_time_order(self):
        rows = [self._row("2026-09-20T15:00:00Z", 2, True, 30),
                self._row("2026-09-16T15:00:00Z", 2, False, 99),
                self._row("2026-09-13T15:00:00Z", 1, True, 20)]
        out = sm.odds_series(rows, "Champ_Pct")
        self.assertEqual([(w, v["A"]) for _, w, v in out], [(1, 20.0), (2, 30.0)])

    def test_a_row_missing_the_field_is_skipped(self):
        r = self._row("2026-09-13T15:00:00Z", 1, True, 20)
        self.assertEqual(sm.odds_series([r], "Nope_Pct"), [])


class TestColours(unittest.TestCase):
    def test_a_team_keeps_its_colour_whatever_the_field(self):
        full = sm.team_colors(["C", "A", "B"])
        self.assertEqual(full["A"], sm.PALETTE[0])
        self.assertEqual(sm.team_colors(["B", "A", "C"]), full)

    def test_renamed_passes_unmapped_names_through(self):
        self.assertEqual(sm.renamed({"A": 1, "B": 2}, {"A": "Real"}), {"Real": 1, "B": 2})


if __name__ == "__main__":
    unittest.main()
