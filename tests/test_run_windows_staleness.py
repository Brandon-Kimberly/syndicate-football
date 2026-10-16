"""run_windows must say when its checkout is behind origin/main.

On 2026-10-16 the local report read week 6's run1_pre_kickoff as MISSED. The runner had covered
that window at 10:59 PT on Thursday (a canonical row committed to origin/main), but the local
checkout was 9 commits behind, so its predictions log did not have the row. Nothing in the
report said so. Fixtures are fixed strings; nothing here touches data/ or git."""
import unittest

from fantasy_sim.run_windows import checkout_behind_note


class CheckoutBehindNote(unittest.TestCase):
    def test_an_up_to_date_checkout_says_nothing(self):
        self.assertIsNone(checkout_behind_note(0))

    def test_a_behind_checkout_names_the_count_and_warns_that_a_missed_may_be_stale(self):
        note = checkout_behind_note(9)
        self.assertIn("9 commit", note)
        self.assertIn("origin/main", note)
        self.assertIn("MISSED", note)
        self.assertIn("git pull", note)

    def test_when_git_cannot_answer_the_note_says_so_rather_than_staying_silent(self):
        note = checkout_behind_note(None)
        self.assertIsNotNone(note)
        self.assertIn("could not compare", note)


if __name__ == "__main__":
    unittest.main()
