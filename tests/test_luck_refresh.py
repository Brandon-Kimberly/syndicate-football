"""The Luck page stays current: a LOCAL sync refreshes the saved luck accounting (2026-11-27).

The web UI's Luck page reads the newest data/local/luck/accounting_<season>.json, which only
moved when someone ran scripts.luck_ledger by hand, so it went stale every week and said so.
Now a successful local sync -- `scripts.run_sync` from the Sync page or a terminal, or
`scripts.weekly_report` with its sync -- reruns `scripts.luck_ledger --json` afterwards.

Pinned here:
  * best effort: a failed, timed-out or unlaunchable refresh never raises, and never changes
    the sync's or the report's exit code;
  * never on a runner: data/local is local only, so a GitHub run does not try;
  * only after a sync that succeeded (and in weekly_report, only when it synced at all);
  * pulled, not pushed (owner, 2026-09-21): it writes the file the Luck page reads and prints
    one line to the job's log -- nothing is added to the digest.
No network: every subprocess is a fake.
"""
import subprocess
import sys
import unittest
from unittest import mock


def refresh_after_sync(**kw):
    from fantasy_sim.luck_refresh import refresh_after_sync as f      # lazy: red before it exists
    return f(**kw)


class Recorder:
    def __init__(self, rc=0, raises=None):
        self.calls, self.rc, self.raises = [], rc, raises

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        if self.raises:
            raise self.raises
        return subprocess.CompletedProcess(argv, self.rc)


class TestTheRefresh(unittest.TestCase):
    def test_it_runs_the_luck_ledger_for_the_current_season(self):
        run = Recorder()
        out = refresh_after_sync(run=run, env={})
        self.assertEqual(out, "refreshed")
        argv, kw = run.calls[0]
        self.assertEqual(argv, [sys.executable, "-m", "scripts.luck_ledger", "--json"])
        self.assertEqual(kw.get("stdout"), subprocess.DEVNULL, "its JSON is not the sync's output")
        self.assertTrue(kw.get("timeout"), "a hung fetch must not hold the sync's job open")

    def test_never_on_a_runner(self):
        run = Recorder()
        self.assertTrue(refresh_after_sync(run=run, env={"GITHUB_ACTIONS": "true"}).startswith("skipped"))
        self.assertEqual(run.calls, [])

    def test_a_failure_is_reported_never_raised(self):
        for run in (Recorder(rc=1), Recorder(raises=subprocess.TimeoutExpired("x", 1)),
                    Recorder(raises=OSError("no interpreter"))):
            out = refresh_after_sync(run=run, env={})
            self.assertTrue(out.startswith("failed"), out)


class TestRunSyncRefreshesAfterASuccessfulSync(unittest.TestCase):
    def _cli(self, argv, verdict="ok", sync_raises=None):
        from scripts import run_sync
        hook = mock.Mock(return_value="refreshed")
        with mock.patch.object(run_sync, "verify_odds_key", return_value=(verdict, "")), \
                mock.patch.object(run_sync, "sync_all", side_effect=sync_raises):
            try:
                code = run_sync.cli(argv, after_sync=hook)
            except SystemExit as ex:
                code = ex.code
            except RuntimeError:
                code = "raised"
        return code, hook

    def test_a_good_sync_refreshes(self):
        code, hook = self._cli([])
        self.assertEqual(code, 0)
        hook.assert_called_once()

    def test_a_sync_stopped_by_the_key_check_does_not(self):
        code, hook = self._cli([], verdict="rejected")
        self.assertEqual(code, 2)
        hook.assert_not_called()

    def test_a_sync_that_raises_does_not(self):
        code, hook = self._cli([], sync_raises=RuntimeError("boom"))
        self.assertEqual(code, "raised")
        hook.assert_not_called()

    def test_a_failed_refresh_leaves_the_exit_code_alone(self):
        from scripts import run_sync
        with mock.patch.object(run_sync, "verify_odds_key", return_value=("ok", "")), \
                mock.patch.object(run_sync, "sync_all"):
            self.assertEqual(run_sync.cli([], after_sync=lambda: "failed: rc 1"), 0)

    def test_the_command_line_entry_is_the_refreshing_one(self):
        import inspect
        from scripts import run_sync
        src = inspect.getsource(run_sync)
        self.assertIn("sys.exit(cli())", src, "python -m scripts.run_sync must go through cli()")


class TestWeeklyReportRefreshesOnlyWhenItSynced(unittest.TestCase):
    def _main(self, argv, report):
        from scripts import weekly_report as wr
        hook = mock.Mock(return_value="refreshed")
        # _default_to_real_names would set SHOW_REAL_TEAM_NAMES for the rest of the suite (F48)
        with mock.patch.object(wr, "run_weekly_report", return_value=(report, "digest", "p.md", None)), \
                mock.patch.object(wr, "_default_to_real_names"), \
                mock.patch("builtins.print"):
            try:
                wr.main(argv, after_sync=hook)
                code = 0
            except SystemExit as ex:
                code = ex.code
        return code, hook

    def test_after_its_own_sync(self):
        code, hook = self._main([], {"status": "OK", "failed_step": None})
        self.assertEqual(code, 0)
        hook.assert_called_once()

    def test_not_with_skip_sync(self):
        _code, hook = self._main(["--skip-sync"], {"status": "OK", "failed_step": None})
        hook.assert_not_called()

    def test_not_when_the_sync_step_failed(self):
        code, hook = self._main([], {"status": "FAILED", "failed_step": "sync", "error": "x"})
        self.assertEqual(code, 1)
        hook.assert_not_called()

    def test_a_later_failure_still_refreshes_and_still_fails(self):
        """The sync wrote data/current; the simulation failing after it does not unwrite it."""
        code, hook = self._main([], {"status": "FAILED", "failed_step": "simulation", "error": "x"})
        self.assertEqual(code, 1)
        hook.assert_called_once()


if __name__ == "__main__":
    unittest.main()
