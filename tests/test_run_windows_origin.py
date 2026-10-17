"""Coverage must count the canonical rows the runner committed to origin/main, not only the local log.

On 2026-10-17 the daily popup said week 6 run1 was MISSED. The runner had covered it: a canonical
row was committed to origin/main at 2026-10-15 17:59:41Z, before the 00:15Z Friday deadline. The
local checkout was behind, so its predictions log did not have the row. Fixtures are invented
timestamps; nothing here reads git or data/."""
import unittest
from unittest import mock

from scripts import run_windows as rw

ROW = {"record_type": "week_predictions", "week": 6, "canonical": True,
       "logged_at": "2026-10-15T17:59:41Z"}


class CanonicalStampsSeeOriginRows(unittest.TestCase):
    def test_a_canonical_row_committed_to_origin_counts_for_coverage(self):
        with mock.patch.object(rw, "_local_digest_stamps", return_value=[]), \
                mock.patch.object(rw, "read_predictions_rows", return_value=[]), \
                mock.patch.object(rw, "_origin_rows", return_value=[ROW]):
            stamps = rw._canonical_stamps(6)
        self.assertEqual([dt.strftime("%Y-%m-%dT%H:%M:%SZ") for _n, dt in stamps],
                         ["2026-10-15T17:59:41Z"])


if __name__ == "__main__":
    unittest.main()
