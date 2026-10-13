"""The recorded forecast-accuracy log: what gets written, and when (no duplicate lines).

Fixtures use invented team names and numbers only (F73). Nothing here touches data/."""
import json
import os
import tempfile
import unittest

from fantasy_sim.forecast_accuracy import build_record, append_if_changed


KICK = "2026-09-10T00:20Z"


def _row(week, logged_at, teams):
    return {"record_type": "week_predictions", "season": "2026", "week": week,
            "logged_at": logged_at, "canonical": True, "commit": "abc1234",
            "median": {t: {"expected_total": q, "sd_total": sd} for t, (q, sd) in teams.items()}}


class BuildRecord(unittest.TestCase):
    def setUp(self):
        self.rows = [_row(1, "2026-09-09T10:00Z", {"Alpha": (100.0, 20.0), "Beta": (90.0, 20.0)}),
                     _row(2, "2026-09-16T10:00Z", {"Alpha": (100.0, 20.0)})]
        self.kick = {"1": [KICK], "2": ["2026-09-17T00:15Z"], "3": ["2026-09-24T00:15Z"]}

    def test_scored_week_carries_its_numbers_and_team_errors(self):
        banked = {"week_1": {"Alpha": {"points": 110.0}, "Beta": {"points": 80.0}}}
        rec = build_record("2026", self.rows, banked, self.kick, generated_at="T")
        w1 = next(w for w in rec["weeks"] if w["week"] == 1)
        self.assertEqual(w1["status"], "scored")
        self.assertEqual(w1["teams"], {"Alpha": 10.0, "Beta": -10.0})
        self.assertEqual(w1["n"], 2)

    def test_unbanked_week_is_pending_and_not_scored(self):
        rec = build_record("2026", self.rows, {"week_1": {"Alpha": {"points": 110.0}, "Beta": {"points": 80.0}}},
                           self.kick, generated_at="T")
        w2 = next(w for w in rec["weeks"] if w["week"] == 2)
        self.assertEqual(w2["status"], "pending")
        self.assertIsNone(w2.get("mean_error"))

    def test_pooled_summary_covers_scored_weeks_only(self):
        banked = {"week_1": {"Alpha": {"points": 110.0}, "Beta": {"points": 80.0}}}
        rec = build_record("2026", self.rows, banked, self.kick, generated_at="T")
        self.assertEqual(rec["pooled"]["n"], 2)
        self.assertAlmostEqual(rec["pooled"]["mean_error"], 0.0)


class AppendIfChanged(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        os.remove(self.path)  # start with no file

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)

    def _rec(self, generated_at, mean_error):
        return {"record_type": "forecast_accuracy", "season": "2026", "generated_at": generated_at,
                "weeks": [{"week": 1, "status": "scored", "mean_error": mean_error, "teams": {"Alpha": 1.0}}],
                "pooled": {"n": 1}}

    def test_first_record_is_written(self):
        self.assertTrue(append_if_changed(self.path, self._rec("T1", 5.0)))
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(len(f.readlines()), 1)

    def test_same_content_on_a_later_run_is_not_written_again(self):
        append_if_changed(self.path, self._rec("T1", 5.0))
        self.assertFalse(append_if_changed(self.path, self._rec("T2", 5.0)))
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(len(f.readlines()), 1)

    def test_changed_numbers_are_written(self):
        append_if_changed(self.path, self._rec("T1", 5.0))
        self.assertTrue(append_if_changed(self.path, self._rec("T2", 6.0)))
        with open(self.path, encoding="utf-8") as f:
            last = json.loads(f.readlines()[-1])
        self.assertEqual(last["weeks"][0]["mean_error"], 6.0)


if __name__ == "__main__":
    unittest.main()
