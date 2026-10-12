"""nflverse's published game lines as the odds fallback and a cross-check (owner request, 2026-10-12).

Why. The Odds API is a paid, capped feed (500 credits a month; it ran out on 2026-09-30) and when
it is unavailable -- no key, rejected, out of credits, held below the reserve, request failed,
empty payload -- every team used to get a flat 21.5 total with no opponent: matchup and
defensive-tier effects OFF, and a canonical window blocked. On 2026-10-11 the same feed also left
two teams (DAL, TB) without a line, so the engine condemned them as stale. nflverse's
`nfldata/games.csv` carries the current week's total and spread for free (verified against the
Odds API's own week-5 file: 13 of 15 games within 0.75 points; the others were that stale pair and
one real line move).

Contract pinned here:
  * the parser maps nflverse's rows to our implied totals with our sign conventions;
  * it is a FALLBACK: it never replaces a successful Odds API fetch, and real Odds API lines
    already on disk for the week still win (C3);
  * it only runs when the caller passes a budget (the real sync always does), so older direct
    callers and the hermetic suite are unchanged;
  * teams the Odds payload left out are repaired from it, and the repair is named in `_meta`;
  * lines that disagree by more than LINES_CROSSCHECK_PTS are reported, never silently trusted;
  * the canonical gate accepts the fallback source and still blocks the flat one.

Written before the code.
"""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import fantasy_sim.sync as sync
from fantasy_sim.clients import nflverse
from tests.test_odds_budget import _Now, _reply, lines

CSV = """game_id,season,game_type,week,gameday,away_team,home_team,total_line,spread_line,result
2026_06_GB_DET,2026,REG,6,2026-10-18,GB,DET,50.0,3.5,
2026_06_BUF_LA,2026,REG,6,2026-10-18,BUF,LA,54.5,3.0,
2026_06_X_Y,2026,REG,6,2026-10-18,JAC,KC,,,
2026_07_GB_DET,2026,REG,7,2026-10-25,GB,DET,,,
2026_06_Z,2026,POST,6,2026-10-18,GB,DET,40.0,1.0,
2025_06_GB_DET,2025,REG,6,2025-10-12,GB,DET,44.0,6.0,
"""


class TestParse(unittest.TestCase):
    def test_only_this_seasons_regular_season_week_with_both_lines(self):
        rows = nflverse.parse_week_lines(CSV, 2026, 6)
        self.assertEqual(sorted((r["away"], r["home"]) for r in rows), [("BUF", "LAR"), ("GB", "DET")])

    def test_old_franchise_codes_map_to_ours(self):
        rows = nflverse.parse_week_lines(CSV.replace("LA\n", "LA\n"), 2026, 6)
        self.assertIn("LAR", {r["home"] for r in rows})
        self.assertEqual(nflverse.TEAM_ALIASES["JAC"], "JAX")

    def test_implied_totals_use_our_signs(self):
        rows = nflverse.parse_week_lines(CSV, 2026, 6)
        t = nflverse.implied_totals(rows)
        # total 50, home DET favoured by 3.5 -> DET 26.75, GB 23.25; our spread is negative for the favourite
        self.assertEqual((t["DET"]["total"], t["GB"]["total"]), (26.75, 23.25))
        self.assertEqual((t["DET"]["spread"], t["GB"]["spread"]), (-3.5, 3.5))
        self.assertEqual((t["DET"]["opponent"], t["GB"]["opponent"]), ("GB", "DET"))

    def test_a_game_not_on_the_weeks_schedule_is_dropped(self):
        rows = nflverse.parse_week_lines(CSV, 2026, 6)
        t = nflverse.implied_totals(rows, week_schedule={"DET": "GB", "GB": "DET"})
        self.assertEqual(sorted(t), ["DET", "GB"])

    def test_a_malformed_row_is_skipped_not_fatal(self):
        bad = CSV + "2026_06_Q,2026,REG,6,2026-10-18,GB,DET,abc,xyz,\n"
        self.assertEqual(len(nflverse.parse_week_lines(bad, 2026, 6)), 2)


def _rows():
    return nflverse.parse_week_lines(CSV, 2026, 6)


class _Drive(unittest.TestCase):
    ODDS_GAME = {"home_team": "Detroit Lions", "away_team": "Green Bay Packers",
                 "commence_time": "2026-10-18T17:00:00Z",
                 "bookmakers": [{"key": "draftkings", "markets": [
                     {"key": "totals", "outcomes": [{"name": "Over", "point": 51.0}]},
                     {"key": "spreads", "outcomes": [{"name": "Detroit Lions", "point": -3.0},
                                                     {"name": "Green Bay Packers", "point": 3.0}]}]}]}
    SCHEDULE = {"DET": "GB", "GB": "DET", "LAR": "BUF", "BUF": "LAR"}

    def go(self, *, key="k" * 32, remaining=400, on_disk=None, odds_status=200, payload=None,
           nfl_rows="rows", official=True, budget=True):
        saved = {}

        def get(url, params=None, timeout=None, **kw):
            if url.rstrip("/").endswith("/v4/sports"):
                return _reply(200, headers={"x-requests-remaining": str(remaining)})
            if "the-odds-api" in url:
                if odds_status != 200:
                    return _reply(odds_status)
                return _reply(200, [self.ODDS_GAME] if payload is None else payload,
                              {"x-requests-last": "2", "x-requests-remaining": str(remaining - 2)})
            raise OSError("weather is not under test")

        fetcher = (lambda *a, **k: _rows()) if nfl_rows == "rows" else (lambda *a, **k: (_ for _ in ()).throw(OSError("nflverse down")))
        with tempfile.TemporaryDirectory() as tmp:
            vf = os.path.join(tmp, "vegas_totals.json")
            if on_disk is not None:
                with open(vf, "w", encoding="utf-8") as fh:
                    json.dump(on_disk, fh)
            with patch.object(sync, "datetime", _Now), \
                    patch.object(sync, "ODDS_API_KEY", key), \
                    patch.object(sync, "VEGAS_FILE", vf), \
                    patch.object(sync, "fetch_nflverse_week_lines", side_effect=fetcher), \
                    patch.object(sync.requests, "get", side_effect=get), \
                    patch.object(sync, "save_json", side_effect=lambda p, d, *a, **k: saved.__setitem__(os.path.basename(p), d)):
                out = sync.fetch_vegas_implied_totals(
                    6, week_schedule=self.SCHEDULE, budget={"official": official} if budget else None)
        return out, saved


class TestFallback(_Drive):
    def test_no_key_uses_nflverse_not_the_flat_table(self):
        out, saved = self.go(key="")
        self.assertEqual(out["_meta"]["source"], "fallback_nflverse_lines")
        self.assertEqual(out["DET"]["total"], 26.75)
        self.assertEqual(out["DET"]["opponent"], "GB")
        self.assertEqual(out["BUF"]["opponent"], "LAR")

    def test_a_failed_odds_request_uses_nflverse(self):
        out, _s = self.go(odds_status=500)
        self.assertEqual(out["_meta"]["source"], "fallback_nflverse_lines")

    def test_an_empty_odds_payload_uses_nflverse(self):
        out, _s = self.go(payload=[])
        self.assertEqual(out["_meta"]["source"], "fallback_nflverse_lines")

    def test_held_below_the_reserve_uses_nflverse(self):
        from fantasy_sim.config import ODDS_CREDIT_RESERVE
        out, _s = self.go(remaining=ODDS_CREDIT_RESERVE, official=False)
        self.assertEqual(out["_meta"]["source"], "fallback_nflverse_lines")

    def test_nflverse_down_falls_back_to_the_flat_table_as_before(self):
        out, _s = self.go(key="", nfl_rows="down")
        self.assertEqual(out["_meta"]["source"], "fallback_no_api_key")
        self.assertEqual(out["DET"]["total"], 21.5)

    def test_it_never_replaces_a_successful_odds_fetch(self):
        out, _s = self.go()
        self.assertEqual(out["_meta"]["source"], "odds_api")
        self.assertEqual(out["DET"]["total"], 27.0, "the Odds API's (51 + 3) / 2, not nflverse's 26.75")

    def test_real_odds_lines_already_on_disk_still_win_over_it(self):
        out, saved = self.go(key="", on_disk=lines(week=6, hours_ago=20))
        self.assertEqual(out["DET"]["total"], 25.75)
        self.assertIn("stale_since", saved["vegas_totals.json"]["_meta"])

    def test_without_a_budget_nothing_changes(self):
        out, _s = self.go(key="", budget=False)
        self.assertEqual(out["_meta"]["source"], "fallback_no_api_key")


class TestRepairAndCrosscheck(_Drive):
    def test_a_team_the_odds_payload_left_out_is_repaired_and_named(self):
        # the Odds feed has DET/GB only; BUF@LAR is on the schedule and in nflverse
        out, _s = self.go()
        self.assertEqual(out["BUF"]["opponent"], "LAR")
        self.assertEqual(out["LAR"]["opponent"], "BUF")
        self.assertEqual(sorted(out["_meta"]["patched_from_nflverse"]), ["BUF", "LAR"])
        self.assertEqual(out["_meta"]["source"], "odds_api")

    def test_a_team_with_no_game_this_week_is_not_invented(self):
        out, _s = self.go()
        self.assertEqual(out["KC"]["opponent"], "FA")

    def test_a_large_disagreement_is_recorded_and_warned(self):
        game = json.loads(json.dumps(self.ODDS_GAME))
        game["bookmakers"][0]["markets"][0]["outcomes"][0]["point"] = 40.0   # nflverse says 50.0
        with self.assertLogs(level="WARNING") as cm:
            out, _s = self.go(payload=[game])
        self.assertTrue(any("LINES CROSSCHECK" in m for m in cm.output))
        self.assertIn("DET", out["_meta"]["crosscheck"]["differ"])

    def test_agreement_raises_no_crosscheck_warning(self):
        # the 4-club fixture still trips the (older) unfilled-clubs warning, so assert on OUR line only
        with self.assertLogs(level="WARNING") as cm:
            out, _s = self.go()
        self.assertFalse(any("LINES CROSSCHECK" in m for m in cm.output))
        self.assertEqual(out["_meta"]["crosscheck"]["differ"], {})


class TestGate(unittest.TestCase):
    def test_the_nflverse_source_is_accepted_and_the_flat_ones_still_block(self):
        from scripts.canonical_gate import canonical_gate
        ok = canonical_gate("OK", [], "fallback_nflverse_lines", baselines_count=1000)
        self.assertFalse([b for b in ok.get("blocking", []) if "vegas" in json.dumps(b)])
        for flat in ("fallback_no_api_key", "fallback_api_error", "fallback_empty_payload", "fallback_credit_reserve"):
            g = canonical_gate("OK", [], flat, baselines_count=1000)
            self.assertTrue([b for b in g.get("blocking", []) if "vegas" in json.dumps(b)], flat)

    def test_the_crosscheck_line_is_benign_not_blocking(self):
        from scripts.canonical_gate import BENIGN_MARKERS
        self.assertTrue(any("LINES CROSSCHECK" in m for m in BENIGN_MARKERS))


if __name__ == "__main__":
    unittest.main()
