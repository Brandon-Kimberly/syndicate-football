"""run_sync's command line. A flag it does not recognise must never start a sync: `--help` once
ran a full sync that rewrote data/current and appended to the logs (2026-10-12)."""
import unittest
from unittest import mock

from scripts import run_sync


class RunSyncArguments(unittest.TestCase):
    def _run(self, argv):
        """Run main() with the odds check passing and the sync mocked; return (exit code, sync mock)."""
        with mock.patch.object(run_sync, "verify_odds_key", return_value=("ok", "")), \
                mock.patch.object(run_sync, "sync_all") as sync:
            try:
                code = run_sync.main(argv)
            except SystemExit as ex:
                code = ex.code
        return code, sync

    def test_help_exits_zero_and_does_not_sync(self):
        code, sync = self._run(["--help"])
        self.assertEqual(code, 0)
        sync.assert_not_called()

    def test_unknown_flag_exits_nonzero_and_does_not_sync(self):
        code, sync = self._run(["--bogus"])
        self.assertNotEqual(code, 0)
        sync.assert_not_called()

    def test_known_flags_still_reach_the_sync(self):
        code, sync = self._run(["--official"])
        self.assertEqual(code, 0)
        sync.assert_called_once_with(sharp_polling=False, official=True)

    def test_no_flags_is_a_plain_sync(self):
        code, sync = self._run([])
        self.assertEqual(code, 0)
        sync.assert_called_once_with(sharp_polling=False, official=False)



class NoAbbreviations(unittest.TestCase):
    def test_prefix_of_a_flag_is_rejected_not_expanded(self):
        # argparse expands unique prefixes by default: --off would silently mean --official,
        # which spends the odds reserve. A prefix must be refused.
        code, sync = RunSyncArguments()._run(["--off"])
        self.assertNotEqual(code, 0)
        sync.assert_not_called()


if __name__ == "__main__":
    unittest.main()
