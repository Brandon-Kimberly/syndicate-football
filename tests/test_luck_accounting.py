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

    def _run(self, *argv):
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

            def __call__(self, url):
                if "/projections/" in url:
                    return {f"p{rid}{i}": {"pts": 36.0 + rid} for rid in TEAMS for i in range(4)}
                return super().__call__(url)

        fake = WithProjections()
        chain = [("2026", CUR, fake.info[CUR]), ("2025", OLD, fake.info[OLD])]
        tmp = tempfile.mkdtemp()
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
                mock.patch("fantasy_sim.storage.BANKED_SCORES_FILE", os.path.join(tmp, "absent.json")), \
                redirect_stdout(buf):
            sl.main(["--json", *argv])
        return json.loads(buf.getvalue()), tmp

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

    def test_another_teams_run_is_not_pooled_across_seasons(self):
        """--team names a CURRENT team; older seasons fall back to the owner's roster, so a
        pool would add two different teams' luck."""
        out, _tmp = self._run("--all", "--team", "Bravo")
        self.assertNotIn("across_seasons", out[0])


TEAMS_NAMES = ("Alpha", "Bravo", "Charlie", "Delta")
