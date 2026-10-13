"""The Sunday canonical fire times must survive GitHub's real schedule lag.

The schedule was designed against "1h cron lag" (AUDIT_PLAN F36). Measured on 2026-10-13 over
every scheduled canonical-run since 2026-09-04 (n=42): median lag 3.1h, October median 3.5h,
maximum 6.1h, and rising. With the first fire at 11:30 UTC, week 5's run started 18 minutes
before the 17:00 UTC deadline and a manual dispatch produced the covering row; week 3's row is
stamped 8 minutes after it. These tests hold the fire times to the measured lag, not the assumed
one."""
import os
import re
import unittest

WORKFLOW = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "canonical-run.yml")

# Measured 2026-10-13 from `gh run list --workflow canonical-run` (schedule events only).
WORST_LAG_H = 6.1       # maximum observed start delay after the cron time
TYPICAL_LAG_H = 3.5     # October median
# Week 5's dispatched run: started 16:28 UTC, canonical row logged 16:46 UTC.
RUN_H = 20 / 60.0
# Run 2's deadline is Sunday 10:00 Pacific: 17:00 UTC in PDT (the tighter regime), 18:00 in PST.
DEADLINE_PDT_H = 17.0
# The window opens Sunday 00:00 Pacific: 07:00 UTC in PDT, 08:00 UTC in PST (the later one).
WINDOW_OPEN_PST_H = 8.0


def sunday_fire_hours():
    with open(WORKFLOW, encoding="utf-8") as f:
        crons = re.findall(r'cron: "(\d+) (\d+) \* \* 0"', f.read())
    return sorted(int(h) + int(m) / 60.0 for m, h in crons)


class SundayFireTimes(unittest.TestCase):
    def test_first_fire_lands_before_the_deadline_at_the_worst_measured_lag(self):
        first = sunday_fire_hours()[0]
        self.assertLessEqual(first + WORST_LAG_H + RUN_H, DEADLINE_PDT_H,
                             f"first Sunday fire {first:.2f}h UTC + {WORST_LAG_H}h lag + run time "
                             f"passes the {DEADLINE_PDT_H:.0f}:00 UTC deadline")

    def test_a_retry_also_lands_at_the_typical_lag(self):
        fires = sunday_fire_hours()
        in_time = [f for f in fires if f + TYPICAL_LAG_H + RUN_H <= DEADLINE_PDT_H]
        self.assertGreaterEqual(len(in_time), 2, f"fewer than two Sunday fires land in time: {fires}")

    def test_no_fire_precedes_the_window_opening_in_either_dst_regime(self):
        for f in sunday_fire_hours():
            self.assertGreaterEqual(f, WINDOW_OPEN_PST_H, f"Sunday fire at {f:.2f}h UTC is before the window opens in PST")


if __name__ == "__main__":
    unittest.main()
