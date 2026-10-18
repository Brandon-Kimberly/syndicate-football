"""The coverage read must fetch origin/main before it reads it.

On 2026-10-18 the scheduled popup read run2_sunday as MISSED at 10:00 PT. The runner had covered
it: a canonical row was committed to origin/main at 06:41 PT. But _origin_rows read the cached
origin/main ref, and that ref had last been fetched on 2026-10-17, before the row existed. A window
the runner covered read as missed. Fixtures only: subprocess is mocked, so nothing touches git."""
import unittest
from unittest import mock

from scripts import run_windows as rw


class OriginReadFetchesFirst(unittest.TestCase):
    def test_origin_rows_fetches_origin_before_it_reads_the_log(self):
        calls = []

        def fake_run(args, **_kw):
            calls.append(args)
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(rw.os.path, "join", return_value="data/logs/predictions_2026.jsonl"), \
                mock.patch("glob.glob", return_value=["data/logs/predictions_2026.jsonl"]), \
                mock.patch("subprocess.run", side_effect=fake_run):
            rw._origin_rows()
        fetch = [i for i, a in enumerate(calls) if a[:2] == ["git", "fetch"]]
        show = [i for i, a in enumerate(calls) if a[:2] == ["git", "show"]]
        self.assertTrue(fetch, f"no git fetch was run; calls were {calls}")
        self.assertLess(fetch[0], show[0], "the log was read before origin was fetched")


if __name__ == "__main__":
    unittest.main()
