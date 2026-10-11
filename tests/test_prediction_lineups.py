"""The prediction record keeps the lineup behind each team's expected total (2026-10-11).

Why: the owner was favoured every week of 2026 and went 1-3 while the engine's quoted team
totals ran ~6 points/team above what teams scored (and ~20 above for the owner). The log kept
only the total, so the question "is the Vegas/script multiplier double-counting a projection
that is already week-specific?" could not be answered from the record -- the per-player
baseline, environment ratio and script multiplier behind each number were never saved. This
only ADDS saved output (MINOR): no draw, no existing key, no golden changes.
"""
import json
import os
import tempfile
import unittest

import tests.test_decisions as td
from fantasy_sim.decisions import league_week_outlook


class TestOutlookLineupDecomposition(td._EngineCase):
    def test_each_lineup_entry_carries_the_three_factors_of_its_expectation(self):
        r = league_week_outlook(self.engine, week=1, sims=300, seed=3)
        for team in r["teams"].values():
            self.assertTrue(team["lineup"])
            for row in team["lineup"]:
                for k in ("baseline_mean", "env_ratio", "script"):
                    self.assertIn(k, row, f"{row['name']} lacks {k}")
                self.assertAlmostEqual(row["baseline_mean"] * row["env_ratio"] * row["script"],
                                       row["expected"], places=6,
                                       msg="the logged factors must reproduce the logged expectation")


class TestPredictionRecordKeepsTheLineup(unittest.TestCase):
    OUTLOOK = {"week": 5, "n": 100, "cross": True,
               "matchups": [{"a": "A", "b": "B", "p_a": 0.6, "p_b": 0.4, "se": 0.01}],
               "teams": {"A": {"opponent": "B", "p_beat_median": 0.6, "expected_total": 150.0,
                               "sd_total": 30.0, "expected_pre_total": 160.0,
                               "lineup": [{"slot": "QB", "name": "P One", "expected": 20.0, "sd": 9.0,
                                           "flag": None, "nfl_team": "DET", "baseline_mean": 15.0,
                                           "env_ratio": 1.2, "script": 1.1111111111}]},
                         "B": {"opponent": "A", "p_beat_median": 0.4, "expected_total": 140.0,
                               "sd_total": 30.0, "expected_pre_total": 150.0, "lineup": []}}}

    def test_record_has_pre_total_and_a_compact_lineup(self):
        from fantasy_sim.weekly_report import append_predictions_log
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "predictions_2026.jsonl")
            append_predictions_log(5, [], self.OUTLOOK, path=path,
                                   manifest={"season": "2026"}, commit="c0ffee")
            row = json.loads(open(path, encoding="utf-8").read())
        a = row["median"]["A"]
        self.assertEqual(a["expected_pre_total"], 160.0)
        p = a["lineup"][0]
        self.assertEqual((p["slot"], p["name"], p["nfl_team"]), ("QB", "P One", "DET"))
        self.assertAlmostEqual(p["baseline_mean"] * p["env_ratio"] * p["script"], p["expected"], places=3)
        self.assertNotIn("flag", p, "display-only fields stay out of the permanent record")
        self.assertEqual(row["median"]["B"]["lineup"], [])

    def test_existing_keys_are_unchanged(self):
        from fantasy_sim.weekly_report import append_predictions_log
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "predictions_2026.jsonl")
            append_predictions_log(5, [], self.OUTLOOK, path=path, manifest={"season": "2026"})
            row = json.loads(open(path, encoding="utf-8").read())
        self.assertEqual(set(row["median"]["A"]) >= {"opponent", "p_beat_median", "expected_total", "sd_total"}, True)


if __name__ == "__main__":
    unittest.main()
