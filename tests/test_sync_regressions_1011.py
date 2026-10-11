"""Three defects behind "the sync is failing" (owner report 2026-10-11).

  1. A sync that REUSES fresh odds never rewrote vegas_totals.json (the odds-credit budget,
     2026-09-30), so the freshness check read the file as "older than the sync" and declared
     the sync STALE -- the sync "failed" though it had completed. The reuse rewrites the file
     in place, with `fetched_at` untouched (the 6-hour window must still run out) and a
     `reused_at` stamp.
  2. The engine aborted the whole run whenever any rostered player had no projection and no
     hand-typed KNOWN_MISSING_ASSETS entry. That cost the week-4 pre-kickoff window (#23, Tank
     Dell, whose entry then carried the wrong team) and put the week-5 Sunday window at risk
     (#37, Emmett Johnson). The abort exists to stop a WHOLESALE projection failure, not one
     stashed rookie, so: up to SIM_CONFIG['AUTO_ZERO_IMPUTE_MAX'] such players are valued at
     Sleeper's own number -- zero, no spread -- with team, position, bye and availability from
     Sleeper's roster record, loudly; more than that still aborts. A whitelist entry still wins,
     and a cap of 0 restores the old behaviour exactly.
  3. test_ingestion's two Vegas-fallback tests read the REAL data/current/vegas_totals.json, so
     they failed whenever the live synced week happened to equal their week 5 (C3 keeps real
     lines of the same week). Hermetic now.
Written before the fixes.
"""
import copy
import logging
import os
import unittest
from unittest.mock import patch

import fantasy_sim.sync as sync
from fantasy_sim.simulation import FantasySimulationEngine, SIM_CONFIG
from tests.test_imputed_availability import GHOST, TEAMS, _Case, _fs
from tests import test_odds_budget            # referenced, never imported by name: the loader would collect it twice

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------- 1. reuse rewrites
class TestReuseRewritesTheVegasFile(unittest.TestCase):
    def test_a_reuse_saves_the_file_so_the_sync_reads_as_having_written_it(self):
        h = test_odds_budget.TestTheFetchHonoursTheBudget("test_fresh_lines_are_reused_and_nothing_is_paid")
        lines = test_odds_budget.lines
        out, paid, saved = h.run_fetch(lines(hours_ago=1), official=False, remaining=400)
        self.assertEqual(paid, [], "nothing was bought")
        self.assertIn("vegas_totals.json", saved, "the reused lines must be written back in place")
        meta = saved["vegas_totals.json"]["_meta"]
        self.assertEqual(meta["fetched_at"], lines(hours_ago=1)["_meta"]["fetched_at"],
                         "fetched_at is when they were BOUGHT; touching it would extend the reuse window forever")
        self.assertIn("reused_at", meta)
        self.assertEqual(saved["vegas_totals.json"]["DET"], lines()["DET"], "the lines themselves are untouched")

    def test_the_freshness_check_accepts_a_sync_that_reused(self):
        from fantasy_sim import freshness
        verdict, reasons = freshness.assess(
            {"ok": True, "current_week": 5}, sync_start=1000.0,
            file_mtimes={"vegas_totals.json": 1001.0, "player_baselines.json": 1001.0},
            vegas_week=5, export_mtime=2000.0, nfl_week=5)
        self.assertFalse([r for r in reasons if "older than the sync" in r], reasons)


# ---------------------------------------------------------------------------- 2. auto-zero
class _Ghost(_Case):
    """The ghost is rostered, projected by nobody, and on NO whitelist."""
    WL = {}


class TestAutoZeroWithinTheCap(_Ghost):
    def test_the_engine_builds_and_values_him_at_sleepers_zero(self):
        b = self.engine.baselines[GHOST]
        self.assertEqual((b["mean"], b["std_aleatoric"], b["std_epistemic"]), (0.0, 0.0, 0.0))
        self.assertEqual(b["team"], "DET", "the team is Sleeper's roster record, so it can never mismatch")
        self.assertEqual(b["pos"], "WR")
        self.assertEqual(b["bye"], 0)

    def test_it_is_recorded_and_not_silent(self):
        self.assertEqual(self.engine.auto_imputed, [GHOST])
        self.assertEqual(self.engine.baselines[GHOST].get("auto_imputed"), "zero")

    def test_his_availability_comes_from_the_roster_like_a_whitelisted_player(self):
        self.assertIs(self.engine.baselines[GHOST].get("on_ir"), False)


class TestAutoZeroTakesTheRostersAvailability(_Ghost):
    GHOST_ENTRY = {"name": GHOST, "pos": "WR", "team": "DET", "on_ir": True, "injury_status": "IR"}

    def test_an_ir_player_is_on_ir(self):
        self.assertTrue(self.engine.baselines[GHOST]["on_ir"])
        self.assertEqual(self.engine.baselines[GHOST]["injury_status"], "IR")


class TestAWhitelistEntryStillWins(_Case):
    def test_the_hand_typed_number_is_used_and_nothing_is_auto_imputed(self):
        self.assertEqual(self.engine.baselines[GHOST]["mean"], 6.5)
        self.assertEqual(self.engine.auto_imputed, [])


class TestTheFailsafeStillStopsAWholesaleFailure(unittest.TestCase):
    def build(self, n_missing, cap):
        fs = _fs({"name": GHOST, "pos": "WR", "team": "DET"})
        extra = [{"name": f"Ghost {i}", "pos": "WR", "team": "CHI"} for i in range(n_missing - 1)]
        from fantasy_sim.storage import LIVE_ROSTERS_FILE
        fs[LIVE_ROSTERS_FILE] = copy.deepcopy(fs[LIVE_ROSTERS_FILE])
        fs[LIVE_ROSTERS_FILE][TEAMS[1]] += extra
        prev = logging.getLogger().getEffectiveLevel()
        logging.getLogger().setLevel(logging.ERROR)
        self.addCleanup(logging.getLogger().setLevel, prev)
        with patch("os.path.exists", side_effect=lambda p: p in fs), \
                patch("fantasy_sim.simulation.load_json", side_effect=lambda p: fs[p]), \
                patch.dict(SIM_CONFIG["KNOWN_MISSING_ASSETS"], {}, clear=True), \
                patch.dict(SIM_CONFIG, {"AUTO_ZERO_IMPUTE_MAX": cap}):
            return FantasySimulationEngine()

    def test_over_the_cap_it_aborts_as_before(self):
        cap = SIM_CONFIG["AUTO_ZERO_IMPUTE_MAX"]
        with self.assertRaises(ValueError) as ex:
            self.build(cap + 1, cap)
        self.assertIn("CRITICAL ABORT", str(ex.exception))

    def test_at_the_cap_it_builds(self):
        cap = SIM_CONFIG["AUTO_ZERO_IMPUTE_MAX"]
        self.assertEqual(len(self.build(cap, cap).auto_imputed), cap)

    def test_a_cap_of_zero_restores_the_old_abort_exactly(self):
        with self.assertRaises(ValueError) as ex:
            self.build(1, 0)
        self.assertIn("CRITICAL ABORT", str(ex.exception))


class TestTheCapIsSourced(unittest.TestCase):
    def test_it_exists_and_says_where_it_comes_from(self):
        self.assertGreaterEqual(SIM_CONFIG["AUTO_ZERO_IMPUTE_MAX"], 1)
        with open(os.path.join(REPO, "fantasy_sim", "config.py"), encoding="utf-8") as fh:
            src = fh.read()
        i = src.index('"AUTO_ZERO_IMPUTE_MAX"')
        self.assertIn("#", src[max(0, i - 1500):i], "rule 5: a new constant carries its source")


class TestTheSyncAndTheGateAgree(unittest.TestCase):
    SCORING = {"rush_yd": 0.1}

    def run_sync_baselines(self, n_uncovered):
        db, live, proj = {}, {"T": []}, {}
        for i in range(n_uncovered):
            db[str(i + 1)] = {"first_name": "Zed", "last_name": f"Rookie{i}", "position": "RB", "team": "KC"}
            live["T"].append({"name": f"Zed Rookie{i}", "pos": "RB", "team": "KC"})
            proj[str(i + 1)] = {"stats": {"rush_yd": 0.0}}
        from unittest.mock import MagicMock
        weekly = MagicMock()
        weekly.status_code = 200
        weekly.json.return_value = proj
        with patch.object(sync, "save_json"), patch.object(sync.os.path, "exists", return_value=False), \
                patch.object(sync.requests, "get", return_value=weekly), \
                patch.object(sync, "fetch_espn_projection_data", return_value=({}, {})), \
                self.assertLogs(level="WARNING") as logs:
            sync.generate_player_baselines(self.SCORING, db, live, "2026", 1,
                                           rostered_pids={str(i + 1) for i in range(n_uncovered)})
        return [m for m in logs.output if "BASELINES: rostered player" in m]

    def classify(self, logged):
        """The gate reads the manifest's entries: 'WARNING | <message>'."""
        from scripts.canonical_gate import classify_degraded_entry as classify
        return classify("WARNING | " + logged.split("WARNING:root:", 1)[1])

    def test_within_the_cap_the_sync_says_auto_zero_and_the_gate_calls_it_benign(self):
        msgs = self.run_sync_baselines(SIM_CONFIG["AUTO_ZERO_IMPUTE_MAX"])
        self.assertEqual(len(msgs), SIM_CONFIG["AUTO_ZERO_IMPUTE_MAX"])
        for m in msgs:
            self.assertIn("AUTO-ZERO", m)
            self.assertNotIn("NOT in baselines", m)
            self.assertEqual(self.classify(m), "benign", m)

    def test_over_the_cap_the_sync_keeps_the_blocking_wording(self):
        msgs = self.run_sync_baselines(SIM_CONFIG["AUTO_ZERO_IMPUTE_MAX"] + 1)
        for m in msgs:
            self.assertIn("NOT in baselines", m)
            self.assertTrue(self.classify(m).startswith("blocking"), m)


# ---------------------------------------------------------------------------- 3. hermetic tests
class TestIngestionFallbacksDoNotReadRealData(unittest.TestCase):
    def test_they_patch_the_vegas_file(self):
        with open(os.path.join(REPO, "tests", "test_ingestion.py"), encoding="utf-8") as fh:
            src = fh.read()
        for name in ("test_in_season_without_api_key_writes_the_fallback_it_returns",
                     "test_in_season_api_failure_writes_the_fallback_it_returns"):
            body = src[src.index(f"def {name}"):]
            body = body[:body.index("    def ", 10)]
            self.assertIn("_no_real_vegas()", body,
                          f"{name} reads the real vegas file unless it patches sync.VEGAS_FILE")


# ---------------------------------------------------------------------------- 4. the push race
class TestTheLogsPushSurvivesARace(unittest.TestCase):
    """2026-10-11, the week-5 Sunday window: the canonical report wrote its row at 16:46:42Z,
    git push was rejected (another job had pushed first -- the scheduled captures run all day),
    commit_and_push_logs gave up with 'committed locally', and the runner's copy was discarded:
    the window's only canonical row survived solely in the run's site-data artifact. The
    workflow's own early capture step already does pull --rebase and retries; this helper did not."""

    REJECTED = "! [rejected]        main -> main (fetch first)" + chr(10) + "hint: Updates were rejected"

    def run_logs_push(self, pushes, pull_rc=0):
        from fantasy_sim.weekly_report import commit_and_push_logs
        calls, left = [], list(pushes)

        def git(args):
            calls.append(list(args))
            if args[0] == "diff":
                return 1, ""
            if args[0] == "push":
                return (0, "") if (left.pop(0) if left else False) else (1, self.REJECTED)
            if args[0] == "pull":
                return pull_rc, "" if pull_rc == 0 else "CONFLICT"
            return 0, ""
        return commit_and_push_logs(5, git=git), calls

    def test_a_rejected_push_is_rebased_and_retried(self):
        out, calls = self.run_logs_push([False, True])
        self.assertTrue(out["pushed"], out)
        self.assertEqual([c[0] for c in calls if c[0] in ("push", "pull")], ["push", "pull", "push"])
        pull = next(c for c in calls if c[0] == "pull")
        self.assertIn("--rebase", pull)
        self.assertIn("--autostash", pull, "a user's unrelated dirty files must survive the rebase")

    def test_a_pull_that_fails_is_aborted_and_the_row_is_still_reported_as_unpushed(self):
        out, calls = self.run_logs_push([False], pull_rc=1)
        self.assertFalse(out["pushed"])
        self.assertIn(["rebase", "--abort"], calls, "never leave the checkout mid-rebase")
        self.assertIn("committed locally", out["warning"])

    def test_it_gives_up_after_a_few_attempts(self):
        out, calls = self.run_logs_push([False] * 20)
        self.assertFalse(out["pushed"])
        self.assertLessEqual(sum(1 for c in calls if c[0] == "push"), 4)

    def test_the_workflow_that_runs_it_keeps_the_rows_as_an_artifact(self):
        with open(os.path.join(REPO, ".github", "workflows", "canonical-run.yml"), encoding="utf-8") as fh:
            wf = fh.read()
        self.assertIn("data/logs/**", wf, "the artifact the lost row was recovered from")


if __name__ == "__main__":
    unittest.main()
