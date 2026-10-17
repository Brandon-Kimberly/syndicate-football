"""The daily canonical-window popup (hooks/windows_check.ps1) pops only for something a human must
act on now. On 2026-10-17 it popped every day on a RELEASE reminder and a FLAG that were already
known, and on a word that was not a window status at all. Fixture text is invented; the hook is
driven through its -TestOutput switch, which runs no report and writes no log and shows no box."""
import os
import subprocess
import unittest

HOOK = os.path.join(os.path.dirname(__file__), "..", "hooks", "windows_check.ps1")
HEAD = ("Canonical run windows -- week 7  (now Sat 2026-10-17 10:00 PDT; kickoffs from synced schedule)\n"
        "  freshness: OK\n")


def verdict(report):
    out = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                          "-File", HOOK, "-TestOutput", report],
                         capture_output=True, text=True, timeout=120)
    for line in out.stdout.splitlines():
        if line.startswith("attention:"):
            return line
    raise AssertionError(f"no verdict from the hook: {out.stdout!r} {out.stderr!r}")


class PopupTriggers(unittest.TestCase):
    def test_a_release_reminder_on_its_own_does_not_pop(self):
        text = HEAD + ("  UPCOMING run2_sunday        Sun 10-18 00:00 -> Sun 10-18 10:00 PDT\n"
                       "  RELEASE: milestone reached (week 5-6: calibration first measurable) -- cut a PATCH tag\n")
        self.assertTrue(verdict(text).startswith("attention: NO"), verdict(text))

    def test_an_early_kickoff_flag_on_its_own_does_not_pop(self):
        text = HEAD + ("  UPCOMING run2_sunday        Sun 10-18 00:00 -> Sun 10-18 10:00 PDT\n"
                       "  FLAG: early Sunday kickoff at 06:30 PT (London window?)\n")
        self.assertTrue(verdict(text).startswith("attention: NO"), verdict(text))

    def test_a_missed_window_pops(self):
        text = HEAD + "  MISSED   run1_pre_kickoff   Wed 10-14 00:00 -> Thu 10-15 17:15 PDT\n"
        self.assertTrue(verdict(text).startswith("attention: YES"), verdict(text))

    def test_an_open_window_within_26_hours_pops(self):
        text = HEAD + "  OPEN     run1_pre_kickoff   Wed 10-14 00:00 -> Thu 10-15 17:15 PDT  (5.0 h remaining)\n"
        self.assertTrue(verdict(text).startswith("attention: YES"), verdict(text))

    def test_the_word_missed_in_lowercase_prose_does_not_pop(self):
        text = HEAD + "  WARNING | BASELINES: a sync line that says the projection was missed for this player\n"
        self.assertTrue(verdict(text).startswith("attention: NO"), verdict(text))


if __name__ == "__main__":
    unittest.main()
