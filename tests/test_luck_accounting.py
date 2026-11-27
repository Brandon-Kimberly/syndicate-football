"""fantasy_sim.luck_accounting: the wins accounting registered in docs/LUCK_LEDGER.md
(Addendum 2, committed before the code).

What is pinned: a hand-computed two-team case; the identity (the parts add to the total
exactly); conservation (every part sums to zero across the league, which is what makes a
shared projection bias cancel); calibration (under the registered null the "1 in N" shares
are honest); the explanations; the early-season withholding; and the luck-neutral standings.
Fictional teams throughout.
"""
import random
import unittest

from fantasy_sim.luck_accounting import accounting, noise_scale, word


def _league(rng, teams=8, weeks=14, skill=None, noise=25.0, bias=0.0):
    """A season where scores are projection + noise (+ a shared bias). `skill` shifts a
    team's projections; the null holds by construction."""
    names = [f"T{i}" for i in range(teams)]
    skill = skill or {}
    scores, proj, pairs = {}, {}, {}
    for w in range(1, weeks + 1):
        proj[w] = {t: 150.0 + skill.get(t, 0.0) + rng.gauss(0, 8) for t in names}
        scores[w] = {t: proj[w][t] + bias + rng.gauss(0, noise) for t in names}
        order = names[:]
        rng.shuffle(order)
        pairs[w] = [(order[i], order[i + 1]) for i in range(0, teams, 2)]
    return scores, proj, pairs


class TestHandComputed(unittest.TestCase):
    def test_two_teams_one_week(self):
        """A projected 110, B 100; A scored 100, B 110.
        Residuals -10 and +10; week mean 0; sum of squares 200 over 1 df; sigma = 14.142.
        P(A beats B on projections) = Phi((110 - 100) / (14.142 * sqrt 2)) = Phi(0.5) = 0.6915.
        A lost, and all-play is the one game: performance = 0 - 0.6915, schedule = 0 - 0."""
        scores = {1: {"A": 100.0, "B": 110.0}}
        proj = {1: {"A": 110.0, "B": 100.0}}
        out = accounting(scores, proj, {1: [("A", "B")]}, sims=200)
        self.assertAlmostEqual(out["sigma"], 14.14, places=2)
        a = out["teams"]["A"]
        # reported to 3 dp
        self.assertAlmostEqual(a["expected"]["h2h"], 0.6915, delta=0.001)
        self.assertAlmostEqual(a["parts"]["performance"]["wins"], -0.6915, delta=0.001)
        self.assertAlmostEqual(a["parts"]["schedule"]["wins"], 0.0, places=6)
        self.assertEqual(a["actual"]["total"], 0.0)

    def test_noise_scale_leaves_out_a_roster_projected_at_zero(self):
        """2024's abandoned roster scored and projected 0 every week; its zero residuals
        would shrink sigma for everyone else."""
        scores = {1: {"A": 100.0, "B": 110.0, "Gone": 0.0}}
        proj = {1: {"A": 110.0, "B": 100.0, "Gone": 0.0}}
        self.assertAlmostEqual(noise_scale(scores, proj), 14.142, places=3)


class TestIdentityAndConservation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = random.Random(7)
        cls.scores, cls.proj, cls.pairs = _league(rng, skill={"T0": 12.0, "T1": -9.0})
        cls.out = accounting(cls.scores, cls.proj, cls.pairs, median=True, sims=400)

    def test_the_parts_add_up_to_the_total_exactly(self):
        for t, r in self.out["teams"].items():
            p = r["parts"]
            added = p["performance"]["wins"] + p["schedule"]["wins"] + p["median"]["wins"]
            self.assertAlmostEqual(added, p["total"]["wins"], places=2, msg=t)
            self.assertAlmostEqual(r["actual"]["total"] - r["expected"]["total"], p["total"]["wins"],
                                   places=2, msg=t)

    def test_every_part_sums_to_zero_across_the_league(self):
        """One team's luck is another's: wins are conserved every week. The median part is
        estimated by simulation, so it is zero to the simulation's precision."""
        for part, places in (("performance", 6), ("schedule", 6), ("total", 6), ("median", 6)):
            s = sum(r["parts"][part]["wins"] for r in self.out["teams"].values())
            self.assertAlmostEqual(s, 0.0, places=2, msg=part)

    def test_a_bias_every_projection_shares_changes_no_part(self):
        """The methodological commitment: the engine runs ~2 points low; a shared miss is
        the model's error, not anybody's luck."""
        rng = random.Random(11)
        scores, proj, pairs = _league(rng, bias=0.0)
        shifted = {w: {t: v + 15.0 for t, v in row.items()} for w, row in scores.items()}
        a = accounting(scores, proj, pairs, median=True, sims=50)
        b = accounting(shifted, proj, pairs, median=True, sims=50)
        for t in a["teams"]:
            for part in ("performance", "schedule", "median", "total"):
                self.assertAlmostEqual(a["teams"][t]["parts"][part]["wins"],
                                       b["teams"][t]["parts"][part]["wins"], places=6, msg=(t, part))

    def test_the_strong_team_is_expected_to_win_more(self):
        e = {t: r["expected"]["total"] for t, r in self.out["teams"].items()}
        self.assertEqual(max(e, key=e.get), "T0")
        self.assertEqual(min(e, key=e.get), "T1")


class TestLineupCalls(unittest.TestCase):
    """Addendum 3 (docs/LUCK_LEDGER.md, registered before this code): roster-earned expected
    wins from each team's BEST lineup projection, and lineup calls = E - E_best. A decision
    measure: never a luck part, never added to the luck total."""

    def test_two_teams_one_week_by_hand(self):
        """A started 110 but its roster's best lineup projected 120; B started its best (100).
        sigma is Addendum 2's, from the started lineups: 14.142. Opponents keep what they started:
        E_h_best(A) = Phi((120 - 100) / 20) = Phi(1) = 0.8413, so A's calls cost
        0.6915 - 0.8413 = -0.1498 wins and 10 points; B's cost nothing."""
        out = accounting({1: {"A": 100.0, "B": 110.0}}, {1: {"A": 110.0, "B": 100.0}}, {1: [("A", "B")]},
                         sims=200, best={1: {"A": 120.0, "B": 100.0}})
        a, b = out["teams"]["A"], out["teams"]["B"]
        self.assertAlmostEqual(out["sigma"], 14.14, places=2)
        self.assertAlmostEqual(a["roster_expected"]["h2h"], 0.8413, delta=0.001)
        self.assertAlmostEqual(a["lineup_calls"]["wins"], -0.1498, delta=0.001)
        self.assertAlmostEqual(a["lineup_calls"]["points_per_week"], -10.0, places=6)
        self.assertAlmostEqual(b["lineup_calls"]["wins"], 0.0, places=6)
        self.assertAlmostEqual(b["roster_expected"]["h2h"], 0.3085, delta=0.001)

    @classmethod
    def setUpClass(cls):
        rng = random.Random(5)
        cls.scores, cls.proj, cls.pairs = _league(rng)
        cls.best = {w: {t: p + (rng.choice((0.0, 0.0, rng.uniform(0, 14)))) for t, p in row.items()}
                    for w, row in cls.proj.items()}
        cls.plain = accounting(cls.scores, cls.proj, cls.pairs, median=True, sims=300)
        cls.out = accounting(cls.scores, cls.proj, cls.pairs, median=True, sims=300, best=cls.best)

    def test_the_luck_is_untouched(self):
        """Every luck part, expected win and standing is what Addendum 2 gives without it."""
        for t in self.plain["teams"]:
            a, b = self.plain["teams"][t], self.out["teams"][t]
            for key in ("actual", "expected", "parts", "all_play_wins", "explain", "actual_rank", "neutral_rank"):
                self.assertEqual(a[key], b[key], (t, key))
        self.assertEqual([dict((k, r[k]) for k in self.plain["standings"][0]) for r in self.out["standings"]],
                         self.plain["standings"])

    def test_calls_are_never_positive_and_zero_for_a_perfect_manager(self):
        for t, r in self.out["teams"].items():
            self.assertLessEqual(r["lineup_calls"]["wins"], 1e-9, t)
            self.assertLessEqual(r["lineup_calls"]["points_per_week"], 1e-9, t)
        same = accounting(self.scores, self.proj, self.pairs, median=True, sims=100, best=self.proj)
        for t, r in same["teams"].items():
            self.assertAlmostEqual(r["lineup_calls"]["wins"], 0.0, places=9, msg=t)

    def test_the_identity(self):
        """actual - E_best = lineup calls + total luck."""
        for t, r in self.out["teams"].items():
            self.assertAlmostEqual(r["actual"]["total"] - r["roster_expected"]["total"],
                                   r["lineup_calls"]["wins"] + r["parts"]["total"]["wins"], places=2, msg=t)

    def test_calls_are_never_a_luck_part(self):
        for t, r in self.out["teams"].items():
            self.assertNotIn("lineup_calls", r["parts"], t)
            self.assertNotIn("share", r["lineup_calls"], "no 1 in N for a decision")

    def test_one_teams_calls_are_priced_against_the_others_as_started(self):
        """Raising another team's best lineup changes nothing of mine."""
        bumped = {w: dict(row, T1=row["T1"] + 30.0) for w, row in self.best.items()}
        other = accounting(self.scores, self.proj, self.pairs, median=True, sims=300, best=bumped)
        self.assertEqual(other["teams"]["T0"]["lineup_calls"], self.out["teams"]["T0"]["lineup_calls"])
        self.assertLess(other["teams"]["T1"]["lineup_calls"]["wins"], self.out["teams"]["T1"]["lineup_calls"]["wins"])

    def test_a_best_below_what_was_started_is_raised_to_it(self):
        """The lineup started was legal, so P_best is never below P (e.g. eligibility data that
        disagrees with Sleeper)."""
        low = {w: {t: p - 5.0 for t, p in row.items()} for w, row in self.proj.items()}
        out = accounting(self.scores, self.proj, self.pairs, median=True, sims=100, best=low)
        for t, r in out["teams"].items():
            self.assertAlmostEqual(r["lineup_calls"]["wins"], 0.0, places=9, msg=t)

    def test_without_best_lineups_there_is_nothing_to_say(self):
        for r in self.plain["teams"].values():
            self.assertIsNone(r["lineup_calls"])
            self.assertIsNone(r["roster_expected"])


class TestUnderTheNullTheSharesAreHonest(unittest.TestCase):
    """When scores really are projection + normal noise, a season 'rarer than 1 in 20' must
    turn up about one time in twenty, in each direction."""

    def test_the_total_share_is_calibrated(self):
        rng = random.Random(2026)
        low = high = n = 0
        for _ in range(80):
            scores, proj, pairs = _league(rng)
            out = accounting(scores, proj, pairs, median=True, sims=300, seed=rng.randrange(10 ** 6))
            part = out["teams"]["T0"]["parts"]["total"]
            n += 1
            if part["share"] is not None and part["share"] < 0.05:
                low += part["way"] == "unlucky"
                high += part["way"] == "lucky"
        rate = (low + high) / n
        self.assertLess(rate, 0.20, f"{rate:.0%} of null seasons came out 'rarer than 1 in 20' one way or the other")
        self.assertGreater(rate, 0.0)


class TestExplanations(unittest.TestCase):
    def test_points_against_projection_are_relative_to_the_league(self):
        scores = {w: {"A": 90.0 + w, "B": 110.0 + w, "C": 100.0 + w, "D": 100.0 + w} for w in range(1, 4)}
        proj = {w: {"A": 100.0, "B": 100.0, "C": 100.0, "D": 100.0} for w in range(1, 4)}
        pairs = {w: [("A", "B"), ("C", "D")] for w in range(1, 4)}
        out = accounting(scores, proj, pairs, sims=20)
        a = out["teams"]["A"]["explain"]
        # A: -10 + w against projection; the league: 0 + w. Relative: -10 a week.
        self.assertAlmostEqual(a["vs_projection_per_week"], -8.0)
        self.assertAlmostEqual(a["vs_projection_relative"], -10.0)

    def test_points_lost_to_starters_who_scored_nothing(self):
        scores = {1: {"A": 100.0, "B": 120.0}, 2: {"A": 110.0, "B": 100.0}}
        proj = {1: {"A": 110.0, "B": 110.0}, 2: {"A": 110.0, "B": 110.0}}
        starters = {1: {"A": [(15.0, 0.0), (95.0, 100.0)], "B": [(110.0, 120.0)]},
                    2: {"A": [(110.0, 110.0)], "B": [(8.0, 0.0), (0.0, 0.0), (102.0, 100.0)]}}
        out = accounting(scores, proj, {1: [("A", "B")], 2: [("A", "B")]}, starters=starters, sims=20)
        # A lost 15 in week 1, 0 in week 2 (7.5 a week); B 0 then 8 (a projected-0 starter
        # who scored 0 was never expected to play): 4 a week. League 5.75; A +1.75.
        self.assertAlmostEqual(out["teams"]["A"]["explain"]["dnp_points_per_week"], 7.5)
        self.assertAlmostEqual(out["teams"]["A"]["explain"]["dnp_points_relative"], 1.75)


class TestWithheldEarly(unittest.TestCase):
    def test_below_six_weeks_there_is_no_share(self):
        rng = random.Random(3)
        scores, proj, pairs = _league(rng, weeks=5)
        out = accounting(scores, proj, pairs, sims=50)
        self.assertTrue(out["early"])
        part = out["teams"]["T0"]["parts"]["total"]
        self.assertIsNotNone(part["wins"])
        self.assertIsNone(part["share"])
        self.assertIsNone(part["word"])

    def test_a_week_without_projections_is_left_out_and_counted(self):
        rng = random.Random(4)
        scores, proj, pairs = _league(rng, weeks=8)
        del proj[3]
        out = accounting(scores, proj, pairs, sims=20)
        self.assertNotIn(3, out["weeks"])
        self.assertEqual(out["left_out"], [3])


class TestStandings(unittest.TestCase):
    def test_ranks_by_actual_and_by_luck_neutral_wins(self):
        rng = random.Random(9)
        scores, proj, pairs = _league(rng, skill={"T3": 25.0})
        out = accounting(scores, proj, pairs, median=True, sims=50)
        st = {r["team"]: r for r in out["standings"]}
        self.assertEqual(st["T3"]["neutral_rank"], 1)
        self.assertEqual(sorted(r["actual_rank"] for r in out["standings"]), list(range(1, 9)))
        self.assertEqual([r["actual_rank"] for r in out["standings"]], list(range(1, 9)), "listed in actual order")
        for t, r in out["teams"].items():
            self.assertEqual(st[t]["neutral_rank"], r["neutral_rank"])


class TestAcrossSeasons(unittest.TestCase):
    def test_the_seasons_add_and_the_null_is_their_independent_sum(self):
        from fantasy_sim.luck_accounting import across_seasons
        # two seasons whose simulated totals are +-1 with equal chance: the sum is -2, 0 or +2
        # with chances 1/4, 1/2, 1/4. Observed -2 in total: share 1/4.
        a = [-1.0, 1.0] * 500
        b = [1.0, -1.0] * 500           # same order as a, reversed: unshuffled they would cancel
        out = across_seasons([(-1.0, a), (-1.0, b)])
        self.assertAlmostEqual(out["wins"], -2.0)
        self.assertEqual(out["seasons"], 2)
        self.assertAlmostEqual(out["share"], 0.25, delta=0.04)

    def test_one_season_is_not_a_pool(self):
        from fantasy_sim.luck_accounting import across_seasons
        self.assertIsNone(across_seasons([(-1.0, [0.0, 1.0])]))

    def test_the_simulations_are_kept_only_on_request(self):
        rng = random.Random(5)
        scores, proj, pairs = _league(rng, weeks=6)
        self.assertNotIn("_sims_total", accounting(scores, proj, pairs, sims=10)["teams"]["T0"])
        kept = accounting(scores, proj, pairs, sims=10, keep_sims=True)["teams"]["T0"]["_sims_total"]
        self.assertEqual(len(kept), 10)


class TestWords(unittest.TestCase):
    def test_the_registered_cuts(self):
        self.assertEqual(word(0.01), "rare")
        self.assertEqual(word(0.05), "unusual")
        self.assertEqual(word(0.2), "a bit unusual")
        self.assertEqual(word(0.25), "ordinary")
        self.assertEqual(word(0.6), "ordinary")
        self.assertIsNone(word(None))


if __name__ == "__main__":
    unittest.main()


# --------------------------------------------------------------------------- the script
class TestTheScriptReportsAndSavesIt(unittest.TestCase):
    """scripts.luck_ledger end to end on a fake Sleeper that also serves projections. The
    saved file and the projection cache go to a temporary directory, never data/local."""

    def _run(self, *argv, owners=None, gaps=None, log_rows=None, kickoffs=None):
        import io
        import json
        import os
        import tempfile
        from contextlib import redirect_stdout
        from unittest import mock
        from scripts import luck_ledger as sl
        from tests.test_luck_ledger_fixes import CUR, OLD, TEAMS, FakeSleeper

        class WithProjections(FakeSleeper):
            def __init__(self):
                super().__init__(closed=11, in_progress=12)
                for lid in (CUR, OLD):
                    self.info[lid]["scoring_settings"] = {"pts": 1.0}
                    # Addendum 3: four starting slots, the rest bench
                    self.info[lid]["roster_positions"] = ["QB", "RB", "WR", "TE", "BN", "BN"]

            def rosters(self, lid):
                out = super().rosters(lid)
                if lid == OLD and owners:
                    for r in out:
                        r["owner_id"] = owners.get(r["roster_id"], r["owner_id"])
                return out

            def __call__(self, url):
                if "/projections/" in url:
                    # Alpha's bench WR p19 projects 50, above its started WR p12 (37): a lineup
                    # call worth 13 points a week. Every other bench player has no projection (0).
                    out = dict({f"p{rid}{i}": {"pts": 36.0 + rid} for rid in TEAMS for i in range(4)},
                               p19={"pts": 50.0})
                    wk = int(url.rstrip("/").rsplit("/", 1)[-1])
                    for pid in (gaps or {}).get(wk, ()):      # Addendum 4: the archive omits him
                        out.pop(pid, None)
                    return out
                got = super().__call__(url)
                if "/matchups/" in url:
                    for m in got:
                        if m.get("starters"):
                            m["players"] = list(m["starters"]) + [f"p{m['roster_id']}9"]
                return got

        fake = WithProjections()
        chain = [("2026", CUR, fake.info[CUR]), ("2025", OLD, fake.info[OLD])]
        tmp = tempfile.mkdtemp()
        cache = os.path.join(tmp, "players_cache.json")
        with open(cache, "w", encoding="utf-8") as fh:
            json.dump({f"p{rid}{i}": {"position": pos, "fantasy_positions": [pos]}
                       for rid in TEAMS for i, pos in ((0, "QB"), (1, "RB"), (2, "WR"), (3, "TE"), (9, "WR"))}, fh)
        plog = os.path.join(tmp, "projection_log.jsonl")
        with open(plog, "w", encoding="utf-8") as fh:
            for row in log_rows or []:
                fh.write(json.dumps(row) + "\n")
        sched = os.path.join(tmp, "nfl_schedule.json")
        with open(sched, "w", encoding="utf-8") as fh:
            json.dump({"_meta": {"kickoffs": kickoffs or {}}}, fh)
        buf = io.StringIO()
        with mock.patch.object(sl, "_get", fake), \
                mock.patch.object(sl, "_league_chain", lambda: chain), \
                mock.patch.object(sl, "LEAGUE_ID", CUR), \
                mock.patch.object(sl, "TEAM_NAME_MAP", {str(k): v for k, v in TEAMS.items()}), \
                mock.patch.object(sl, "MY_TEAM", "Alpha"), \
                mock.patch.object(sl, "real_name_overlay", lambda: {}), \
                mock.patch.object(sl, "_as_played", lambda season: {}), \
                mock.patch.object(sl, "_banked", lambda season: {}), \
                mock.patch.object(sl, "_projections", lambda season: None), \
                mock.patch.object(sl, "LUCK_DIR", tmp), \
                mock.patch.object(sl, "PLAYERS_CACHE", cache, create=True), \
                mock.patch.object(sl, "PROJECTION_LOG", plog, create=True), \
                mock.patch.object(sl, "NFL_SCHEDULE", sched, create=True), \
                mock.patch("fantasy_sim.storage.BANKED_SCORES_FILE", os.path.join(tmp, "absent.json")), \
                redirect_stdout(buf):
            sl.main(["--json", *argv])
        return json.loads(buf.getvalue()), tmp

    def test_lineup_calls_from_the_rosters_best_lineup(self):
        """Addendum 3 end to end: Alpha left a 50-point WR on the bench for a 37-point one every
        week; nobody else had a better bench option."""
        import json
        import os
        out, tmp = self._run("--all")
        by = {r["season"]: r for r in out}
        mine = by["2026"]["accounting"]
        self.assertAlmostEqual(mine["lineup_calls"]["points_per_week"], -13.0, places=6)
        self.assertLess(mine["lineup_calls"]["wins"], 0.0)
        self.assertGreater(mine["roster_expected"]["total"], mine["expected"]["total"])
        with open(os.path.join(tmp, "accounting_2026.json"), encoding="utf-8") as fh:
            saved = json.load(fh)
        for t in ("Bravo", "Charlie", "Delta"):
            self.assertAlmostEqual(saved["teams"][t]["lineup_calls"]["points_per_week"], 0.0, places=6, msg=t)
            self.assertAlmostEqual(saved["teams"][t]["lineup_calls"]["wins"], 0.0, places=6, msg=t)
        self.assertAlmostEqual(by["2025"]["accounting"]["lineup_calls"]["points_per_week"], -13.0, places=6,
                               msg="each season's own slots and roster")

    def _gap_run(self):
        """Addendum 4. The archive omits, in 2026 (and in the fake's 2025 too):
          week 4  p21  Bravo's started RB, who scored     -> filled from the pre-kickoff row (40)
          week 4  p29  Bravo's bench, who scored nothing  -> stays 0 although logged at 60
          week 5  p31  Charlie's starter, who scored      -> only a row AFTER kickoff: stays 0
          week 6  p41  Delta's starter, who scored        -> logged at 0: stays 0"""
        def row(wk, pid, mean, at):
            return {"season": "2026", "week": wk, "player_id": pid, "sleeper_mean": mean, "synced_at": at}
        kick = {"4": ["2026-09-25T00:15:00Z", "2026-09-28T17:00:00Z"], "5": ["2026-10-02T00:15:00Z"],
                "6": ["2026-10-09T00:15:00Z"]}
        rows = [row(4, "p21", 35.0, "2026-09-23T12:00:00Z"), row(4, "p21", 40.0, "2026-09-24T12:00:00Z"),
                row(4, "p21", 99.0, "2026-09-26T12:00:00Z"),           # after the first kickoff: not used
                row(4, "p29", 60.0, "2026-09-24T12:00:00Z"),
                row(5, "p31", 50.0, "2026-10-03T12:00:00Z"),
                row(6, "p41", 0.0, "2026-10-08T12:00:00Z")]
        return self._run("--all", gaps={4: ["p21", "p29"], 5: ["p31"], 6: ["p41"]}, log_rows=rows, kickoffs=kick)

    def test_a_player_the_archive_omits_who_played_is_priced_from_the_log(self):
        import json
        import os
        out, tmp = self._gap_run()
        with open(os.path.join(tmp, "accounting_2026.json"), encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertEqual(saved["filled_from_log"], 1, "p21 only")
        # Bravo's starters project 38 each: 152 a week, and 154 in week 4 with p21 at 40 (not 99, not 114)
        self.assertAlmostEqual(saved["teams"]["Bravo"]["explain"]["projected_per_week"],
                               round((152.0 * 10 + 154.0) / 11, 2), places=2)
        for t, base in (("Charlie", 156.0), ("Delta", 160.0)):         # p31 and p41 stay 0
            self.assertAlmostEqual(saved["teams"][t]["explain"]["projected_per_week"],
                                   round((base * 10 + base * 3 / 4) / 11, 2), places=2, msg=t)
        by = {r["season"]: r for r in out}
        self.assertEqual(by["2026"]["accounting"]["filled_from_log"], 1)

    def test_a_season_without_the_log_is_unchanged(self):
        import json
        import os
        _out, tmp = self._gap_run()
        with open(os.path.join(tmp, "accounting_2025.json"), encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertEqual(saved["filled_from_log"], 0)
        self.assertAlmostEqual(saved["teams"]["Old Bravo"]["explain"]["projected_per_week"],
                               round((152.0 * 13 + 114.0) / 14, 2), places=2)

    def test_the_text_report_says_how_many_were_filled(self):
        import io
        from contextlib import redirect_stdout
        from scripts.luck_ledger import render_accounting, team_view
        acc = accounting({w: {"A": 100.0 + w, "B": 110.0 - w} for w in range(1, 8)},
                         {w: {"A": 110.0, "B": 100.0} for w in range(1, 8)},
                         {w: [("A", "B")] for w in range(1, 8)}, sims=100)
        acc["filled_from_log"] = 3
        buf = io.StringIO()
        with redirect_stdout(buf):
            render_accounting(team_view(acc, "A"), "A")
        self.assertIn("3 player-weeks", buf.getvalue())
        self.assertIn("pre-kickoff", buf.getvalue())

    def test_the_text_report_names_lineup_calls_as_a_decision(self):
        import io
        from contextlib import redirect_stdout
        from scripts.luck_ledger import render_accounting, team_view
        acc = accounting({w: {"A": 100.0 + w, "B": 110.0 - w} for w in range(1, 8)},
                         {w: {"A": 110.0, "B": 100.0} for w in range(1, 8)},
                         {w: [("A", "B")] for w in range(1, 8)}, sims=100,
                         best={w: {"A": 118.0, "B": 100.0} for w in range(1, 8)})
        buf = io.StringIO()
        with redirect_stdout(buf):
            render_accounting(team_view(acc, "A"), "A")
        text = buf.getvalue()
        self.assertIn("LINEUP CALLS", text)
        self.assertIn("a decision, not luck", text)
        self.assertIn("-8.0 points a week", text)
        total_line = next(ln for ln in text.splitlines() if ln.strip().startswith("total"))
        self.assertNotIn("lineup", total_line.lower(), "never added into the luck total")

    def test_each_season_carries_my_accounting_and_the_league_is_saved(self):
        import json
        import os
        out, tmp = self._run("--all")
        by = {r["season"]: r for r in out}
        mine = by["2026"]["accounting"]
        self.assertEqual(mine["team"], "Alpha")
        self.assertEqual(mine["weeks"], list(range(1, 12)))
        p = mine["parts"]
        self.assertAlmostEqual(p["performance"]["wins"] + p["schedule"]["wins"] + p["median"]["wins"],
                               p["total"]["wins"], places=2)
        self.assertIsNone(by["2025"]["accounting"]["parts"]["median"], "2025 had no median game")
        self.assertEqual(by["2025"]["accounting"]["team"], "Old Alpha")
        with open(os.path.join(tmp, "accounting_2026.json"), encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertEqual(sorted(saved["teams"]), sorted(TEAMS_NAMES))
        self.assertNotIn("_sims_total", json.dumps(out) + json.dumps(saved))
        self.assertTrue(os.listdir(os.path.join(tmp, "projections")), "closed weeks are cached")

    def test_all_seasons_together_for_my_team(self):
        out, _tmp = self._run("--all")
        pooled = out[0]["across_seasons"]
        self.assertEqual(pooled["seasons"], 2)
        self.assertEqual(pooled["season_list"], ["2026", "2025"])
        total = sum(r["accounting"]["parts"]["total"]["wins"] for r in out)
        self.assertAlmostEqual(pooled["wins"], total, places=2)

    def test_another_teams_run_follows_that_teams_owner_into_older_seasons(self):
        """--team names a CURRENT team. Before F96 an older season fell back to the OWNER's
        roster, so a run for Bravo showed Old Alpha's 2025 -- someone else's history."""
        out, _tmp = self._run("--all", "--team", "Bravo")
        by = {r["season"]: r for r in out}
        self.assertEqual(by["2026"]["accounting"]["team"], "Bravo")
        self.assertEqual(by["2025"]["accounting"]["team"], "Old Bravo")

    def test_another_teams_seasons_pool_like_mine(self):
        out, _tmp = self._run("--all", "--team", "Bravo")
        pooled = out[0]["across_seasons"]
        self.assertEqual(pooled["season_list"], ["2026", "2025"])
        total = sum(r["accounting"]["parts"]["total"]["wins"] for r in out)
        self.assertAlmostEqual(pooled["wins"], total, places=2)

    def test_an_owner_absent_from_an_older_league_is_said_not_substituted(self):
        """Bravo's owner (u2) had no team in 2025: that season is reported as such, never
        replaced by another roster, and there is nothing to pool."""
        import io
        from contextlib import redirect_stderr
        err = io.StringIO()
        with redirect_stderr(err):
            out, _tmp = self._run("--all", "--team", "Bravo", owners={2: "someone-else"})
        self.assertEqual([r["season"] for r in out], ["2026"])
        self.assertNotIn("across_seasons", out[0])
        self.assertIn("2025", err.getvalue())
        self.assertIn("not in this league", err.getvalue())


TEAMS_NAMES = ("Alpha", "Bravo", "Charlie", "Delta")
