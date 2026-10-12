"""The any-given-stat adapter and the availability watchdog (owner request, 2026-10-12).

Two jobs, both ADVISORY -- nothing here is read by the engine, a roster, a lineup or a quote, so
no draw moves (MINOR, additive):

  1. `clients/ags.py` reads the injury report the any-given-stat site publishes (a public Pages
     JSON feed, because the scheduled runner cannot see the owner's disk) and refuses it unless
     its schema version is one we know and it is fresh -- a stale or reshaped feed must say so,
     not quietly feed a comparison.
  2. `availability_watch.py` flags two classes the engine cannot see by itself:
       * CARRIED-UNPROJECTED -- Sleeper projects a non-bye, not-already-out player at nothing, the
         engine keeps the carried mean, and 'Questionable' is not an absence status. (2026-10-12:
         Caleb Williams, out since week 3, was valued at a healthy 19.4 and started at QB.)
       * AGS-DISAGREES -- the injury report says Out/Doubtful for a player Sleeper still shows
         healthy or merely Questionable.

Written before the code.
"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fantasy_sim import availability_watch as aw
from fantasy_sim.clients import ags

NOW = datetime(2026, 10, 12, 20, 0, 0, tzinfo=timezone.utc)
META = {"generated_at": "2026-10-12T19:50:00+00:00", "data_version": 5}
IDS = {"sleeper": {"11560": "00-0000001", "4881": "00-0000002", "999": "00-0000003"}}
NEWS = {"generated_at": "2026-10-12T19:49:56Z", "injury_report": {"season": 2026, "week": 6},
        "items": [
            {"kind": "news", "headline": "a story", "players": ["00-0000001"]},
            {"kind": "injury", "players": ["00-0000002"], "status": "Out", "change": "new", "week": 6,
             "headline": "B ruled out (knee)", "description": "KC RB . Knee . Did not practice",
             "published": "2026-10-10T20:00:00Z"},
            {"kind": "injury", "players": ["00-0000003"], "status": "Questionable", "change": "same", "week": 6,
             "headline": "C questionable", "description": "x", "published": "2026-10-10T20:00:00Z"},
        ]}


def _get_factory(meta=META, news=NEWS, ids=IDS, fail=None):
    def get(url, timeout=None, **kw):
        if fail and fail in url:
            raise OSError("down")
        body = {"meta.json": meta, "news.json": news, "fantasy_ids.json": ids}[url.rsplit("/", 1)[1]]
        r = MagicMock()
        r.json.return_value = body
        r.raise_for_status.return_value = None
        return r
    return get


class TestTheClient(unittest.TestCase):
    def test_it_indexes_injury_items_by_sleeper_id_and_ignores_news(self):
        out = ags.fetch_injury_report(get=_get_factory(), now=NOW)
        self.assertEqual(sorted(out["players"]), ["4881", "999"])
        self.assertEqual(out["players"]["4881"]["status"], "Out")
        self.assertEqual(out["players"]["4881"]["change"], "new")
        self.assertEqual(out["_meta"]["week"], 6)
        self.assertEqual(out["_meta"]["data_version"], 5)

    def test_an_unknown_schema_version_is_refused(self):
        with self.assertRaises(ags.FeedRejected) as cm:
            ags.fetch_injury_report(get=_get_factory(meta=dict(META, data_version=6)), now=NOW)
        self.assertIn("data_version", str(cm.exception))

    def test_a_stale_feed_is_refused(self):
        old = (NOW - timedelta(hours=ags.MAX_AGE_HOURS + 1)).isoformat()
        with self.assertRaises(ags.FeedRejected) as cm:
            ags.fetch_injury_report(get=_get_factory(meta=dict(META, generated_at=old)), now=NOW)
        self.assertIn("old", str(cm.exception))

    def test_a_network_failure_raises_not_returns_junk(self):
        with self.assertRaises(OSError):
            ags.fetch_injury_report(get=_get_factory(fail="news.json"), now=NOW)

    def test_the_safe_wrapper_returns_none_and_never_raises(self):
        self.assertIsNone(ags.try_fetch_injury_report(get=_get_factory(fail="meta.json"), now=NOW))
        self.assertIsNone(ags.try_fetch_injury_report(get=_get_factory(meta=dict(META, data_version=9)), now=NOW))


def _bl(name, pid, pos="QB", team="CHI", mean=19.4, bye=10, status=None, on_ir=False, source=None):
    d = {"pos": pos, "team": team, "mean": mean, "bye": bye, "player_id": pid,
         "injury_status": status, "on_ir": on_ir}
    if source:
        d["projection_source"] = source
    return name, d


ROSTERS = {"Team A": [{"name": "Carried Q", "pos": "QB"}, {"name": "Healthy R", "pos": "RB"},
                      {"name": "On Bye", "pos": "WR"}, {"name": "Already Out", "pos": "WR"},
                      {"name": "On IR", "pos": "WR"}]}


class TestCarriedUnprojected(unittest.TestCase):
    def watch(self, baselines, week=6, ags_players=None):
        return aw.availability_findings(ROSTERS, dict(baselines), week, ags_players or {})

    def test_a_carried_questionable_player_not_on_bye_is_flagged(self):
        f = self.watch([_bl("Carried Q", "11560", status="Questionable", source="carried_prior")])
        self.assertEqual([(x["kind"], x["name"], x["fantasy_team"]) for x in f],
                         [("carried_unprojected", "Carried Q", "Team A")])
        self.assertIn("19.4", f[0]["detail"])

    def test_a_carried_healthy_looking_player_is_flagged_too(self):
        f = self.watch([_bl("Carried Q", "11560", status=None, source="carried_log")])
        self.assertEqual(len(f), 1)

    def test_not_flagged_when_it_is_a_bye_week(self):
        self.assertEqual(self.watch([_bl("On Bye", "1", bye=6, source="carried_prior")]), [])

    def test_not_flagged_when_sleeper_already_says_out_or_ir(self):
        self.assertEqual(self.watch([_bl("Already Out", "2", status="Out", source="carried_prior")]), [])
        self.assertEqual(self.watch([_bl("On IR", "3", on_ir=True, source="carried_prior")]), [])

    def test_a_normally_projected_player_is_never_flagged(self):
        self.assertEqual(self.watch([_bl("Healthy R", "4", status="Questionable")]), [])

    def test_an_unrostered_player_is_ignored(self):
        self.assertEqual(self.watch([_bl("Free Agent", "5", status="Questionable", source="carried_prior")]), [])


class TestAgsDisagrees(unittest.TestCase):
    def test_ags_out_while_sleeper_shows_healthy_is_flagged(self):
        ags_players = {"4": {"status": "Out", "change": "new", "week": 6, "headline": "R ruled out (knee)"}}
        f = aw.availability_findings(ROSTERS, dict([_bl("Healthy R", "4", pos="RB")]), 6, ags_players)
        self.assertEqual([(x["kind"], x["name"]) for x in f], [("ags_disagrees", "Healthy R")])
        self.assertIn("Out", f[0]["detail"])

    def test_doubtful_while_sleeper_says_questionable_is_flagged(self):
        ags_players = {"4": {"status": "Doubtful", "change": "worse", "week": 6, "headline": "x"}}
        f = aw.availability_findings(ROSTERS, dict([_bl("Healthy R", "4", pos="RB", status="Questionable")]), 6, ags_players)
        self.assertEqual(len(f), 1)

    def test_agreement_is_silent(self):
        ags_players = {"4": {"status": "Out", "change": "same", "week": 6, "headline": "x"}}
        self.assertEqual(aw.availability_findings(ROSTERS, dict([_bl("Healthy R", "4", pos="RB", status="Out")]), 6, ags_players), [])

    def test_a_report_for_another_week_is_ignored(self):
        ags_players = {"4": {"status": "Out", "change": "new", "week": 5, "headline": "x"}}
        self.assertEqual(aw.availability_findings(ROSTERS, dict([_bl("Healthy R", "4", pos="RB")]), 6, ags_players), [])

    def test_a_player_with_a_bye_this_week_is_ignored(self):
        ags_players = {"1": {"status": "Out", "change": "new", "week": 6, "headline": "x"}}
        self.assertEqual(aw.availability_findings(ROSTERS, dict([_bl("On Bye", "1", bye=6)]), 6, ags_players), [])


class TestTheFileAndTheSyncHook(unittest.TestCase):
    def test_write_creates_a_stamped_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "availability_watch.json")
            aw.write_availability_watch(path, ROSTERS, dict([_bl("Carried Q", "11560", status="Questionable", source="carried_prior")]),
                                        6, ags_report=None, now=NOW)
            doc = json.load(open(path, encoding="utf-8"))
        self.assertEqual(doc["_meta"]["week"], 6)
        self.assertFalse(doc["_meta"]["ags_used"])
        self.assertEqual(len(doc["findings"]), 1)

    def test_the_sync_hook_never_raises_and_never_warns(self):
        import fantasy_sim.sync as sync
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(sync, "AVAILABILITY_WATCH_FILE", os.path.join(tmp, "aw.json")), \
                patch.object(sync._ags, "try_fetch_injury_report", return_value=None), \
                self.assertLogs(level="INFO") as cm:
            sync.run_availability_watch(ROSTERS, dict([_bl("Carried Q", "11560", status="Questionable", source="carried_prior")]), 6)
        # the gate counts WARNING/ERROR as degradation; this advisory must stay below that
        self.assertFalse([r for r in cm.output if r.startswith(("WARNING", "ERROR"))])

    def test_a_crash_inside_the_watch_is_swallowed(self):
        import fantasy_sim.sync as sync
        with patch.object(sync._availability_watch, "availability_findings", side_effect=RuntimeError("boom")), \
                patch.object(sync._ags, "try_fetch_injury_report", return_value=None):
            sync.run_availability_watch(ROSTERS, {}, 6)      # must not raise


if __name__ == "__main__":
    unittest.main()
