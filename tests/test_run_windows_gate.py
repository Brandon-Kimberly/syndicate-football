"""The canonical run must act on ANY open, uncovered window, not only one within 24 hours of its deadline.

On 2026-10-14 (Wednesday 10:42 PT) week 6's run1 window was open and uncovered with 30.6 hours left.
The 24-hour notify horizon marked it not actionable, so the Wednesday fire skipped quietly and the
window was covered only by Thursday's fire, 6.5 hours before its deadline. The horizon is a notify
rule; the run gate must not inherit it. Fixtures use fixed times; nothing here touches data/."""
import os
import unittest
from datetime import datetime, timezone

from fantasy_sim.run_windows import compute_windows, watch_verdict

WORKFLOW = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "canonical-run.yml")


def u(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


# Week 5's last game (Mon 17:15 PT) and week 6's first (Thu 17:15 PT), as UTC.
KICKS = {5: [u("2026-10-13T00:15:00")], 6: [u("2026-10-16T00:15:00")]}
WEDNESDAY_0742_PT = u("2026-10-14T17:42:00")  # 10:42 PT, 30.6 h before the week-6 deadline


class OpenUncoveredIsTheRunGate(unittest.TestCase):
    def setUp(self):
        self.result = compute_windows(WEDNESDAY_0742_PT, KICKS, [], state_week=6)
        self.verdict = watch_verdict(self.result, WEDNESDAY_0742_PT, horizon_hours=24.0)

    def test_an_open_uncovered_window_30_hours_out_is_still_a_run_trigger(self):
        names = [w["name"] for w in self.verdict["open_uncovered"]]
        self.assertIn("run1_pre_kickoff", names)

    def test_the_notify_horizon_still_keeps_the_far_window_out_of_actionable(self):
        self.assertEqual(self.verdict["actionable"], [])

    def test_the_canonical_run_gates_on_open_uncovered_not_on_the_horizon(self):
        with open(WORKFLOW, encoding="utf-8") as f:
            text = f.read()
        self.assertIn(".open_uncovered | length", text)
        self.assertNotIn(".actionable | length", text)


if __name__ == "__main__":
    unittest.main()
