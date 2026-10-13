"""Forecast accuracy: the league-wide read of the canonical predictions log (read-only).

Fixtures use invented team names and invented numbers only -- never real identities (F73)."""
import unittest

from fantasy_sim import forecast_accuracy as fa


KICK = "2026-09-10T00:20Z"


def _row(week, logged_at, canonical, teams):
    return {"record_type": "week_predictions", "season": "2026", "week": week,
            "logged_at": logged_at, "canonical": canonical, "backfilled": False,
            "commit": "abc1234",
            "median": {t: {"expected_total": q, "sd_total": sd} for t, (q, sd) in teams.items()}}


class PreKickoffSelection(unittest.TestCase):
    def test_picks_latest_canonical_row_before_kickoff(self):
        rows = [
            _row(1, "2026-09-08T10:00Z", True, {"Alpha": (100.0, 20.0)}),   # older canonical
            _row(1, "2026-09-09T10:00Z", True, {"Alpha": (110.0, 20.0)}),   # the one
            _row(1, "2026-09-09T11:00Z", False, {"Alpha": (999.0, 20.0)}),  # not canonical
            _row(1, "2026-09-13T10:00Z", True, {"Alpha": (888.0, 20.0)}),   # after kickoff
        ]
        rec = fa.pre_kickoff_record(rows, week=1, kickoff=KICK)
        self.assertEqual(rec["logged_at"], "2026-09-09T10:00Z")
        self.assertEqual(rec["median"]["Alpha"]["expected_total"], 110.0)

    def test_none_when_no_canonical_row_before_kickoff(self):
        rows = [_row(1, "2026-09-13T10:00Z", True, {"Alpha": (1.0, 1.0)})]
        self.assertIsNone(fa.pre_kickoff_record(rows, week=1, kickoff=KICK))

    def test_other_weeks_ignored(self):
        rows = [_row(2, "2026-09-09T10:00Z", True, {"Alpha": (1.0, 1.0)})]
        self.assertIsNone(fa.pre_kickoff_record(rows, week=1, kickoff=KICK))


class TeamErrors(unittest.TestCase):
    def test_error_is_actual_minus_quote_and_z_uses_sd(self):
        rec = _row(1, "2026-09-09T10:00Z", True, {"Alpha": (100.0, 20.0)})
        errs = fa.team_errors(rec, {"Alpha": 110.0})
        self.assertEqual(errs["Alpha"]["error"], 10.0)
        self.assertEqual(errs["Alpha"]["z"], 0.5)

    def test_team_missing_actual_is_skipped_not_zeroed(self):
        rec = _row(1, "2026-09-09T10:00Z", True, {"Alpha": (100.0, 20.0), "Beta": (90.0, 20.0)})
        errs = fa.team_errors(rec, {"Alpha": 110.0})
        self.assertNotIn("Beta", errs)


class Summary(unittest.TestCase):
    def test_coverage_counts_inside_80_and_50_bands(self):
        # z values chosen either side of the 80% (|z| <= 1.2816) and 50% (|z| <= 0.6745) cut-offs
        zs = [0.0, 0.5, 0.9, 1.5, -1.0, -2.0, 0.3, 1.1, -0.2, 3.0]
        errs = {f"T{i}": {"error": z * 10.0, "z": z, "quote": 100.0, "actual": 100.0 + z * 10.0}
                for i, z in enumerate(zs)}
        s = fa.summarise(errs)
        self.assertEqual(s["n"], 10)
        # inside 80% (|z| <= 1.2816): 0.0, 0.5, 0.9, -1.0, 0.3, 1.1, -0.2 -> 7 of 10
        self.assertAlmostEqual(s["coverage80"], 7 / 10)
        # inside 50% (|z| <= 0.6745): 0.0, 0.5, 0.3, -0.2 -> 4 of 10
        self.assertAlmostEqual(s["coverage50"], 4 / 10)

    def test_rms_z_and_mean_error(self):
        errs = {"A": {"error": 10.0, "z": 1.0, "quote": 0, "actual": 0},
                "B": {"error": -10.0, "z": -1.0, "quote": 0, "actual": 0}}
        s = fa.summarise(errs)
        self.assertAlmostEqual(s["mean_error"], 0.0)
        self.assertAlmostEqual(s["mae"], 10.0)
        self.assertAlmostEqual(s["rms_z"], 1.0)

    def test_empty_input_gives_none_not_a_division_error(self):
        self.assertIsNone(fa.summarise({})["mean_error"])



import scripts.forecast_accuracy as fas  # noqa: E402


class WeekLine(unittest.TestCase):
    def setUp(self):
        self.rows = [_row(1, "2026-09-09T10:00Z", True, {"Alpha": (100.0, 20.0)})]

    def test_week_without_a_kickoff_is_not_quoted(self):
        # A missing kickoff must NOT make every canonical row count as pre-kickoff.
        line, errs = fas.week_line(self.rows, {"week_1": {"Alpha": {"points": 110.0}}}, {}, 1)
        self.assertEqual(errs, {})
        self.assertIn("no kickoff", line)

    def test_week_with_no_shared_team_names_does_not_crash(self):
        line, errs = fas.week_line(self.rows, {"week_1": {"Beta": {"points": 110.0}}},
                                   {"1": ["2026-09-10T00:20Z"]}, 1)
        self.assertEqual(errs, {})
        self.assertIn("no team", line)

    def test_normal_week_reports_the_numbers(self):
        line, errs = fas.week_line(self.rows, {"week_1": {"Alpha": {"points": 110.0}}},
                                   {"1": ["2026-09-10T00:20Z"]}, 1)
        self.assertIn("mean error +10.0", line)
        self.assertEqual(set(errs), {"Alpha"})


if __name__ == "__main__":
    unittest.main()
