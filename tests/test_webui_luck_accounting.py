"""The wins accounting in the web UI (docs/LUCK_LEDGER.md Addendum 2; owner ruling 2026-11-27).

Two places show it, in both views (CLAUDE.md rule 10): the luck page, from the league-wide file
scripts.luck_ledger saves under data/local/luck/, and the luck ledger's job page, from the
script's JSON. Pinned: the parts and their total appear together and the total never appears
alone; the five registered measures stay five; the bars share one scale; a stale or missing
file says what to do; the simple view carries no developer vocabulary. Fictional fixture.
"""
import json
import os
import random
import re
import tempfile
import unittest

try:
    import flask  # noqa: F401 -- availability probe
    from fantasy_sim.config import MY_TEAM
    from fantasy_sim.luck_accounting import accounting
    from webui import objects, render
    from webui.app import create_app
    from webui.live import LiveBoard
    from webui.luck import bar_rows
    from webui.paths import Root
    from webui.settings import Settings
    from tests.test_webui_launch import FakeRunner
    from tests.test_webui_modes import DEV_TERMS, visible_text
    from tests.test_webui_objects import plant
    HAVE_FLASK = True
except ImportError:          # pragma: no cover
    HAVE_FLASK = False

OK = "OK"


def _league_accounting(teams, weeks, seed=1):
    rng = random.Random(seed)
    scores, proj, pairs = {}, {}, {}
    for w in weeks:
        proj[w] = {t: 150.0 + rng.gauss(0, 8) for t in teams}
        scores[w] = {t: proj[w][t] + rng.gauss(0, 25) for t in teams}
        order = list(teams)
        rng.shuffle(order)
        pairs[w] = [(order[i], order[i + 1]) for i in range(0, len(order) - 1, 2)]
    return accounting(scores, proj, pairs, median=True, sims=200)


@unittest.skipUnless(HAVE_FLASK, "flask not installed")
class Case(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        plant(self.td.name)
        self.root = Root(self.td.name)
        self.teams = objects._teams(self.root)

    def tearDown(self):
        self.td.cleanup()

    def save(self, acc, season="2026"):
        d = os.path.join(self.td.name, "data", "local", "luck")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"accounting_{season}.json"), "w", encoding="utf-8") as fh:
            json.dump(dict(acc, season=season, computed_at="2026-11-27T21:00:00Z"), fh)

    def get(self, path, mode="dev", runner=None):
        st = Settings(self.root)
        st.set_mode(mode)
        app = create_app(self.root, runner=runner or FakeRunner(), csrf_token="tok", settings=st,
                         live=LiveBoard(self.root, MY_TEAM, league_id=None, fetch=None))
        app.testing = True
        r = app.test_client().get(path)
        self.assertEqual(r.status_code, 200, path)
        return r.get_data(as_text=True)


class TestTheLuckPage(Case):
    def test_it_leads_with_wins_and_keeps_the_five(self):
        self.save(_league_accounting(self.teams, range(1, 3)))
        for mode in ("dev", "simple"):
            with self.subTest(mode=mode):
                body = self.get("/luck", mode)
                text = visible_text(body)
                self.assertIn("Wins and luck", text)
                for label in ("Players vs projection", "Players vs projection, median games", "Schedule", "Total"):
                    self.assertIn(label, text)
                self.assertEqual(body.count('<div class="lb"') + body.count('<div class="lb tot"'), 4,
                                 "three parts and their total, no more")
                self.assertEqual(body.count('<tr class="measure"'), 5, "the five registered measures stay five")
                self.assertIn("Standings with every team's luck taken out", text)
                self.assertLess(text.index("Wins and luck"), text.index("The five measures set before the season"))
                if mode == "simple":
                    self.assertEqual([t for t in DEV_TERMS if t in text], [])

    def test_the_total_is_never_shown_without_its_parts(self):
        """The owner's ruling allows one total because it is an identity; a bare total is the
        "luck score" the registration still refuses."""
        self.save(_league_accounting(self.teams, range(1, 3)))
        body = self.get("/luck")
        total = body.index('<div class="lb tot"')
        for label in ("Players vs projection", "Schedule"):
            self.assertLess(body.index(f"<b>{label}</b>"), total)
        for combined in ("luck score", "luck index", "overall luck"):
            self.assertNotIn(combined, visible_text(body).lower())

    def test_a_file_older_than_the_closed_weeks_says_to_rerun(self):
        self.save(_league_accounting(self.teams, [1]))            # the fixture has two weeks played
        text = visible_text(self.get("/luck", "simple"))
        self.assertIn("Weeks have finished since this was worked out", text)
        self.assertIn('href="/tools/luck_ledger"', self.get("/luck", "simple"))

    def test_without_a_file_it_says_how_to_get_one(self):
        body = self.get("/luck", "simple")
        self.assertIn("shows here once the luck ledger has run", visible_text(body))
        self.assertIn('href="/tools/luck_ledger"', body)
        self.assertNotIn("Wins and luck", visible_text(body))

    def test_another_team_gets_its_own_numbers(self):
        acc = _league_accounting(self.teams, range(1, 3))
        self.save(acc)
        other = next(t for t in self.teams if t != MY_TEAM)
        body = self.get(f"/luck?team={render.slug(other)}", "simple")
        want = f"{acc['teams'][other]['parts']['total']['wins']:+.1f}"
        self.assertIn(want, visible_text(body))


class TestTheBars(unittest.TestCase):
    def test_one_scale_for_every_bar(self):
        view = {"parts": {"performance": {"wins": -1.0, "share": 0.3, "word": "ordinary", "way": "unlucky", "one_in": 3},
                          "schedule": {"wins": -2.0, "share": 0.1, "word": "a bit unusual", "way": "unlucky", "one_in": 10},
                          "median": None,
                          "total": {"wins": -3.0, "share": 0.05, "word": "unusual", "way": "unlucky", "one_in": 20}}}
        rows = bar_rows(view)
        self.assertEqual([r["label"] for r in rows], ["Players vs projection", "Schedule", "Total"])
        perf, sched, total = rows
        # scale 3 wins = half the track: -1 -> 1/6 of the track left of centre
        self.assertAlmostEqual(perf["left"], 50 - 50 / 3, places=2)
        self.assertAlmostEqual(perf["width"], 50 / 3, places=2)
        self.assertAlmostEqual(total["left"], 0.0)
        self.assertAlmostEqual(total["width"], 50.0)
        self.assertEqual(total["tone"], "neg")
        self.assertIn("about 1 in 20 seasons this unlucky or more", total["odds"])

    def test_a_lucky_part_grows_right_of_centre(self):
        rows = bar_rows({"parts": {"schedule": {"wins": 0.5, "share": 0.4, "word": "ordinary", "way": "lucky", "one_in": 2},
                                   "total": {"wins": 0.5, "share": 0.4, "word": "ordinary", "way": "lucky", "one_in": 2}}})
        self.assertEqual(rows[0]["left"], 50.0)
        self.assertEqual(rows[0]["tone"], "pos")


class TestTheJobPage(Case):
    def _job(self, payload):
        runner = FakeRunner()
        jid = runner.launch(["py", "-m", "scripts.luck_ledger", "--json", "--all"], "luck_ledger")
        runner.metas[jid].update(state=OK, finished_at="2026-11-27T21:00:03Z", rc=0)
        runner.log_text = lambda j: json.dumps(payload, indent=1)      # as the script prints it
        return runner, jid

    def _payload(self):
        acc = _league_accounting(self.teams, range(1, 9))
        from scripts.luck_ledger import team_view
        mine = team_view(acc, MY_TEAM)
        older = dict(mine, team="Old Name")
        five = {"schedule_luck": {"delta": -1.0, "se": 1.5, "z": -0.67}, "opponent_luck": None, "close_games": None,
                "dnp_luck": None, "scoring_luck": None}
        return [dict(five, team=MY_TEAM, season="2026", weeks=list(range(1, 9)), accounting=mine,
                     across_seasons={"wins": -4.0, "share": 0.06, "word": "unusual", "way": "unlucky", "one_in": 17,
                                     "one_in_floor": 4000, "seasons": 2, "season_list": ["2026", "2025"]}),
                dict(five, team="Old Name", season="2025", weeks=list(range(1, 15)), accounting=older)]

    def test_the_view_leads_with_the_accounting(self):
        view = render.record_view(self._payload(), tool="luck_ledger")
        self.assertEqual([t["k"] for t in view["tiles"]], ["luck, in wins", "how unusual", "standings", "across 2 seasons"])
        self.assertEqual(view["sections"][0]["title"], "Season by season")
        kinds = [s["kind"] for s in view["sections"]]
        self.assertEqual(kinds.count("bars"), 2, "one set of bars per season")
        five = [s for s in view["sections"] if s["title"].startswith("The five measures")]
        self.assertTrue(five and all(s["collapsed"] for s in five), "the five follow, folded")

    def test_without_an_accounting_the_old_view_is_unchanged(self):
        view = render.record_view([{"team": MY_TEAM, "season": "2026", "weeks": [1, 2, 3],
                                    "schedule_luck": {"actual_wins": 2, "expected_wins": 2.29, "delta": -0.29, "se": 0.74, "z": None}}],
                                  tool="luck_ledger")
        self.assertEqual(view["tiles"][0]["k"], "schedule luck")
        self.assertFalse(view["sections"][0]["collapsed"])

    def test_the_page_draws_the_bars_in_both_views(self):
        runner, jid = self._job(self._payload())
        for mode in ("dev", "simple"):
            with self.subTest(mode=mode):
                body = self.get(render.job_url({"id": jid}), mode, runner=runner)
                self.assertGreaterEqual(len(re.findall(r'<div class="lb tot"', body)), 2)
                text = visible_text(body)
                self.assertIn("Where the luck went", text)
                self.assertIn("Season by season", text)
                if mode == "simple":
                    self.assertEqual([t for t in DEV_TERMS if t in text], [])


if __name__ == "__main__":
    unittest.main()
