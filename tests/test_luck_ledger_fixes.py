"""F95: four defects in the luck ledger, found reading its 2026 week-12 output (2026-11-27).

1. The standard error of opponent, DNP and scoring luck was the standard error of the LEAGUE
   MEAN (the spread of the other teams' values divided by sqrt(7)), not the standard error of
   one team's difference from it. Under a null where every team is identical the z-scores
   came out about 2.5x too large: Cosmic Badgers read z = -6.1 on points against over 11
   games. Pinned here as a calibration property -- under the null, |z| > 1.96 must happen
   about 5% of the time -- not as a re-derivation of the formula.
2. The script counted a week as played as soon as any team had a point. On Thanksgiving
   Friday week 12 had 5 to 12 of every team's 13 starters still to play, and every one of
   them counted as a starter who did not play.
3. The banked-record cross-check added MEDIAN wins for a season that had no median game
   (2025), so it found a "disagreement" (7 against 4) that does not exist and withheld
   schedule luck and close games for that season.
4. `--week` cut EVERY season in an `--all` run, so 2024 and 2025 lost their last two weeks
   when the web UI passed the current week.

The fixtures are fictional throughout: no league, team or person here is real.
"""
import io
import json
import random
import unittest
from contextlib import redirect_stdout
from unittest import mock

from fantasy_sim.luck_ledger import ledger


def _null_season(rng, teams=8, weeks=14):
    """One season in which every team is the same team: iid scores, random pairings,
    iid zero-scoring starters, projections that are right on average."""
    names = [f"T{i}" for i in range(teams)]
    scores, pairs, starters, proj = {}, {}, {}, {}
    for w in range(1, weeks + 1):
        scores[w] = {t: rng.gauss(150.0, 27.0) for t in names}
        order = names[:]
        rng.shuffle(order)
        pairs[w] = [(order[i], order[i + 1]) for i in range(0, teams, 2)]
        starters[w] = {t: [0.0 if rng.random() < 0.07 else 10.0 for _ in range(13)] for t in names}
        proj[w] = {t: (150.0, 27.0) for t in names}
    return scores, pairs, starters, proj


class TestUnderTheNullTheZScoresAreCalibrated(unittest.TestCase):
    """A league of identical teams has no luck to find beyond chance, so a two-sided 5% test
    must reject about 5% of the time. With the SE of the league mean it rejected far more
    often, which is how three teams of eight read as 'significant' on points against."""

    SEASONS = 300
    # Measured on this seed: before the fix 44% / 42% / 49% (opponent, DNP, scoring); after
    # it, with the spread pooled across the league, 2.0% / 5.3% / 4.3%. (A first version
    # used each team's own 14 differences: 8.0% / 10.3% / 5.7%, the SE itself too noisy --
    # docs/LUCK_LEDGER.md.) The bound exists to catch the 40%-plus failure, not to grade
    # the tail.
    BOUND = 0.10

    @classmethod
    def setUpClass(cls):
        rng = random.Random(20261127)
        cls.z = {"opponent_luck": [], "dnp_luck": [], "scoring_luck": []}
        for _ in range(cls.SEASONS):
            scores, pairs, starters, proj = _null_season(rng)
            out = ledger(scores, pairs, "T0", starter_points=starters, projections=proj)
            for k in cls.z:
                if out[k] and out[k].get("z") is not None:
                    cls.z[k].append(out[k]["z"])

    def _rate(self, key):
        zs = self.z[key]
        self.assertGreater(len(zs), self.SEASONS * 0.9, f"{key}: too few seasons produced a z")
        return sum(1 for z in zs if abs(z) > 1.96) / len(zs)

    def test_opponent_luck(self):
        rate = self._rate("opponent_luck")
        self.assertLess(rate, self.BOUND, f"opponent luck rejects {rate:.0%} of null seasons at 5%")
        self.assertGreater(rate, 0.01)

    def test_dnp_luck(self):
        rate = self._rate("dnp_luck")
        self.assertLess(rate, self.BOUND, f"DNP luck rejects {rate:.0%} of null seasons at 5%")
        self.assertGreater(rate, 0.01)

    def test_scoring_luck(self):
        rate = self._rate("scoring_luck")
        self.assertLess(rate, self.BOUND, f"scoring luck rejects {rate:.0%} of null seasons at 5%")
        self.assertGreater(rate, 0.01)


class TestTheDeltasThemselvesDoNotMove(unittest.TestCase):
    """F95 corrects the error bars only. Each delta is still my value minus the league's."""

    def test_points_against_delta_is_unchanged(self):
        # A always faces the 140s; league PA per game = mean of everyone's
        scores = {1: {"A": 100.0, "B": 140.0, "C": 120.0, "D": 100.0},
                  2: {"A": 110.0, "B": 150.0, "C": 90.0, "D": 130.0}}
        pairs = {1: [("A", "B"), ("C", "D")], 2: [("A", "B"), ("C", "D")]}
        o = ledger(scores, pairs, "A")["opponent_luck"]
        # A: (140+150)/2 = 145. B (100+110)/2 = 105, C (100+130)/2 = 115, D (120+90)/2 = 105
        # -> league 117.5, delta +27.5
        self.assertAlmostEqual(o["my_pa_per_game"], 145.0)
        self.assertAlmostEqual(o["league_avg_pa_per_game"], 117.5)
        self.assertAlmostEqual(o["delta"], 27.5)

    def test_the_league_wide_weekly_spread_gives_the_standard_error(self):
        """Hand-computed. Every team's PA minus that week's league average PA, pooled:
        week 1: PA A 140, B 100, C 100, D 120; mean 115; squares 625+225+225+25  = 1100
        week 2: PA A 150, B 110, C 130, D 90;  mean 120; squares 900+100+100+900 = 2000
        3100 over (3 + 3) degrees of freedom = 516.67; sd 22.730; A has 2 weeks:
        se = 22.730 / sqrt(2) = 16.07"""
        scores = {1: {"A": 100.0, "B": 140.0, "C": 120.0, "D": 100.0},
                  2: {"A": 110.0, "B": 150.0, "C": 90.0, "D": 130.0}}
        pairs = {1: [("A", "B"), ("C", "D")], 2: [("A", "B"), ("C", "D")]}
        o = ledger(scores, pairs, "A")["opponent_luck"]
        self.assertAlmostEqual(o["se"], 16.07, places=2)


# --------------------------------------------------------------------------- the script
# A fake Sleeper for scripts.luck_ledger.main: two seasons, four teams.
CUR, OLD = "L-cur", "L-old"
TEAMS = {1: "Alpha", 2: "Bravo", 3: "Charlie", 4: "Delta"}
OLD_TEAMS = {1: "Old Alpha", 2: "Old Bravo", 3: "Old Charlie", 4: "Old Delta"}


def _week_scores(season, wk):
    rng = random.Random(f"{season}-{wk}")
    return {rid: round(rng.uniform(100, 180), 2) for rid in TEAMS}


def _matchups(season, wk, partial=False):
    pts = _week_scores(season, wk)
    out = []
    for rid in TEAMS:
        starters = [f"p{rid}{i}" for i in range(4)]
        per = pts[rid] / 4
        pp = {s: (per if not partial or i == 0 else 0.0) for i, s in enumerate(starters)}
        out.append({"roster_id": rid, "matchup_id": 1 if rid in (1, 2) else 2,
                    "points": sum(pp.values()), "starters": starters, "players_points": pp})
    return out


def _record(season, weeks, median):
    """settings.wins/losses as the league banked them over `weeks` closed weeks."""
    rec = {rid: [0, 0, 0.0] for rid in TEAMS}
    for wk in range(1, weeks + 1):
        pts = _week_scores(season, wk)
        for a, b in ((1, 2), (3, 4)):
            win, lose = (a, b) if pts[a] > pts[b] else (b, a)
            rec[win][0] += 1
            rec[lose][1] += 1
            rec[a][2] += pts[b]
            rec[b][2] += pts[a]
        if median:
            cut = sorted(pts.values())[1:3]
            cut = sum(cut) / 2
            for rid in TEAMS:
                rec[rid][0 if pts[rid] >= cut else 1] += 1
    return rec


class FakeSleeper:
    def __init__(self, closed=11, in_progress=12):
        self.closed, self.in_progress = closed, in_progress
        self.info = {CUR: {"season": "2026", "league_id": CUR, "previous_league_id": None,
                           "settings": {"playoff_week_start": 15, "league_average_match": 1}},
                     OLD: {"season": "2025", "league_id": OLD, "previous_league_id": None,
                           "settings": {"playoff_week_start": 15, "league_average_match": 0}}}

    def rosters(self, lid):
        season, weeks, median = (("2026", self.closed, True) if lid == CUR else ("2025", 14, False))
        rec = _record(season, weeks, median)
        return [{"roster_id": rid, "owner_id": f"u{rid}",
                 "settings": {"wins": rec[rid][0], "losses": rec[rid][1], "ties": 0,
                              "fpts_against": int(rec[rid][2]),
                              "fpts_against_decimal": int(round((rec[rid][2] % 1) * 100))}}
                for rid in TEAMS]

    def __call__(self, url):
        tail = url.split("/v1/", 1)[-1]
        parts = tail.split("/")
        if parts[0] == "league":
            lid = parts[1]
            if len(parts) == 2:
                return self.info[lid]
            if parts[2] == "rosters":
                return self.rosters(lid)
            if parts[2] == "users":
                return [{"user_id": f"u{rid}", "display_name": n, "metadata": {"team_name": n}}
                        for rid, n in OLD_TEAMS.items()]
            if parts[2] == "matchups":
                wk = int(parts[3])
                season = self.info[lid]["season"]
                if lid == CUR and wk > self.in_progress:
                    return [{"roster_id": rid, "matchup_id": 1 if rid in (1, 2) else 2, "points": 0.0,
                             "starters": [], "players_points": {}} for rid in TEAMS]
                return _matchups(season, wk, partial=(lid == CUR and wk == self.in_progress))
        if parts[0] == "state":
            return {"season": "2026", "week": self.in_progress, "season_type": "regular"}
        if parts[0] == "projections":
            return {}
        raise AssertionError(f"unexpected URL {url}")


def _run(fake, *argv):
    from scripts import luck_ledger as sl
    chain = [("2026", CUR, fake.info[CUR]), ("2025", OLD, fake.info[OLD])]
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
            redirect_stdout(buf):
        sl.main(["--json", *argv])
    return {r["season"]: r for r in json.loads(buf.getvalue())}


class TestOnlyClosedWeeksAreCounted(unittest.TestCase):
    def test_a_week_in_progress_is_not_a_played_week(self):
        """The league has banked 11 weeks; week 12 has kicked off with most starters still to
        play. Before F95 week 12 was counted, with every unplayed starter a 'DNP'."""
        out = _run(FakeSleeper(closed=11, in_progress=12), "--season", "2026")
        self.assertEqual(out["2026"]["weeks"], list(range(1, 12)))

    def test_asking_for_the_week_in_progress_still_stops_at_the_last_closed_one(self):
        """The web UI passes the current week by default -- which is how --week 12 arrived."""
        out = _run(FakeSleeper(closed=11, in_progress=12), "--season", "2026", "--week", "12")
        self.assertEqual(out["2026"]["weeks"], list(range(1, 12)))


class TestASeasonWithoutMedianGames(unittest.TestCase):
    def test_its_head_to_head_record_is_not_called_a_rewrite(self):
        """2025 had no median game. Its banked wins are head-to-head wins only; counting
        median wins on top manufactured a disagreement and withheld schedule luck."""
        out = _run(FakeSleeper(), "--season", "2025", "--team", "Old Alpha")
        self.assertNotIn("banked_disagreement", out["2025"])
        self.assertIsNotNone(out["2025"]["schedule_luck"])


class TestTheWeekCutoffBelongsToTheCurrentSeason(unittest.TestCase):
    def test_a_finished_season_keeps_all_its_weeks_under_all(self):
        out = _run(FakeSleeper(closed=11, in_progress=12), "--all", "--week", "12")
        self.assertEqual(out["2025"]["weeks"], list(range(1, 15)))
        self.assertEqual(out["2026"]["weeks"], list(range(1, 12)))


if __name__ == "__main__":
    unittest.main()
