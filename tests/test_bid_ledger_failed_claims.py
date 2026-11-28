"""F88's open half: the bid ledger reads the lost claims Sleeper does report.

B14 built the ledger on "a lost claim never becomes a transaction"; F88 (2026-09-29) found that
false -- Sleeper returns each lost claim as a `waiver` with `status: "failed"`, and the sync logs
them to data/logs/failed_claims.jsonl, each outbid one paired (`won_by`) with the claim that beat
it. Pinned here, for `bid_ledger.reconcile(ledger, decisions, failed)`:

  * a ledger claim whose own failed row matches it (same player, inside the match window) is a
    LOSS, not unresolved -- including the failures nobody won (`roster_full`), which no completed
    transaction can ever resolve;
  * an outbid loss carries the winner's bid, exactly as a rival's completed claim would;
  * a WIN gets its rival bids from the failed rows paired to the winning transaction, which is
    what `record_rival_bids` was typing in by hand (the real 4046 claim: [21, 20] both ways);
    a hand-recorded list is kept, and a disagreement is surfaced, never silently replaced;
  * an uncontested win stays on the censored rule: the log cannot tell "no rival" from "a rival
    the sync never saw", and a clearing price of 0 would score every suggestion as right;
  * calibration does not call a loss with no price (roster full) "unresolved", and does not
    score it either -- it says nothing about the bid;
  * without the failed rows, reconcile is exactly what it was.
Fictional players and teams.
"""
import unittest


def _ledger(pid="4046", week=3, placed_at="2026-09-23T13:02:00Z", bid=29, **kw):
    row = {"player_id": pid, "week": week, "placed_at": placed_at, "bid_placed": bid,
           "player": "Claimed Guy", "suggested_v1": 12, "suggested_v2_point": 4}
    row.update(kw)
    return row


def _txn(pid="4046", week=2, created="2026-09-22T19:25:27Z", bid=29, mine=True, tid="T-win"):
    return {"type": "waiver", "week": week, "faab_bid": bid, "is_mine": mine, "transaction_id": tid,
            "created": created, "adds": [{"name": "Claimed Guy", "player_id": pid}]}


def _failed(pid="4046", bid=21, mine=False, reason="outbid", created="2026-09-22T20:00:00Z",
            won_by="T-win", won_bid=29, tid="F1"):
    return {"type": "waiver", "player_id": pid, "faab_bid": bid, "is_mine": mine, "reason": reason,
            "created": created, "transaction_id": tid, "team": "Someone Else",
            "won_by": ({"faab_bid": won_bid, "team": "Winner", "transaction_id": won_by} if won_by else None)}


class TestALostClaimIsALoss(unittest.TestCase):
    def test_a_claim_that_failed_with_nobody_winning_is_a_loss_not_unresolved(self):
        from fantasy_sim.bid_ledger import reconcile
        got = reconcile([_ledger(pid="11624", bid=2, placed_at="2026-09-25T14:30:00Z")], [],
                        [_failed(pid="11624", bid=2, mine=True, reason="roster_full",
                                 created="2026-09-25T14:24:46Z", won_by=None)])[0]
        self.assertIs(got["won"], False)
        self.assertIsNone(got["winning_bid_if_visible"], "nobody won: there is no price")
        self.assertEqual(got["lost_reason"], "roster_full")

    def test_an_outbid_loss_carries_the_winners_bid(self):
        from fantasy_sim.bid_ledger import reconcile
        got = reconcile([_ledger(pid="12545", bid=3, placed_at="2026-09-23T10:20:40Z")], [],
                        [_failed(pid="12545", bid=3, mine=True, created="2026-09-23T10:17:02Z",
                                 won_by="T-rival", won_bid=5)])[0]
        self.assertIs(got["won"], False)
        self.assertEqual(got["winning_bid_if_visible"], 5)
        self.assertEqual(got["lost_reason"], "outbid")

    def test_someone_elses_failed_claim_is_not_mine(self):
        from fantasy_sim.bid_ledger import reconcile
        got = reconcile([_ledger(pid="12545", bid=3, placed_at="2026-09-23T10:20:40Z")], [],
                        [_failed(pid="12545", bid=2, mine=False, created="2026-09-23T10:00:00Z")])[0]
        self.assertIsNone(got["won"], "a rival's failure says nothing about my claim")

    def test_a_failed_claim_a_week_away_is_another_claim(self):
        from fantasy_sim.bid_ledger import reconcile
        got = reconcile([_ledger(pid="12545", bid=3, placed_at="2026-09-23T10:20:40Z")], [],
                        [_failed(pid="12545", bid=3, mine=True, created="2026-09-30T10:00:00Z")])[0]
        self.assertIsNone(got["won"])


class TestAWinsRivalBidsComeFromTheLog(unittest.TestCase):
    def test_the_bids_that_lost_to_my_win_are_its_rivals(self):
        """The real 4046 claim: the owner typed [21, 20]; the log pairs exactly those two."""
        from fantasy_sim.bid_ledger import clearing_price, reconcile
        got = reconcile([_ledger()], [_txn()],
                        [_failed(bid=20, tid="F1"), _failed(bid=21, tid="F2"),
                         _failed(bid=30, tid="F3", won_by="T-other")])[0]
        self.assertIs(got["won"], True)
        self.assertEqual(got["rival_bids"], [21, 20])
        self.assertEqual(got["rival_bids_source"], "failed_claims")
        self.assertEqual(clearing_price(got), 22)

    def test_a_hand_recorded_list_is_kept_and_a_disagreement_is_surfaced(self):
        from fantasy_sim.bid_ledger import reconcile
        same = reconcile([_ledger(rival_bids=[21, 20])], [_txn()],
                         [_failed(bid=20, tid="F1"), _failed(bid=21, tid="F2")])[0]
        self.assertEqual(same["rival_bids"], [21, 20])
        self.assertNotIn("rival_bids_logged", same)
        differ = reconcile([_ledger(rival_bids=[18])], [_txn()], [_failed(bid=21, tid="F2")])[0]
        self.assertEqual(differ["rival_bids"], [18], "the owner's record is not overwritten")
        self.assertEqual(differ["rival_bids_logged"], [21])

    def test_an_uncontested_win_stays_censored(self):
        from fantasy_sim.bid_ledger import clearing_price, reconcile
        got = reconcile([_ledger()], [_txn()], [_failed(bid=30, won_by="T-other")])[0]
        self.assertIs(got["won"], True)
        self.assertNotIn("rival_bids", got)
        self.assertIsNone(clearing_price(got))


class TestCalibrationKnowsALossWithoutAPrice(unittest.TestCase):
    def test_it_is_neither_unresolved_nor_scored(self):
        from fantasy_sim.bid_ledger import calibration, reconcile
        rows = reconcile([_ledger(pid="11624", bid=2, placed_at="2026-09-25T14:30:00Z"),
                          _ledger(pid="999", bid=5, placed_at="2026-09-26T14:30:00Z")], [],
                         [_failed(pid="11624", bid=2, mine=True, reason="roster_full",
                                  created="2026-09-25T14:24:46Z", won_by=None)])
        cal = calibration(rows)
        self.assertEqual(cal["n"], 0)
        self.assertEqual(cal["unresolved"], 1, "only 999, whose run is unknown")
        self.assertEqual(cal["lost_without_price"], 1)
        self.assertIn("1 lost without a price", cal["note"])


class TestWithoutTheLogNothingChanges(unittest.TestCase):
    def test_reconcile_is_what_it_was(self):
        from fantasy_sim.bid_ledger import reconcile
        rows = [_ledger(), _ledger(pid="12545", bid=3, placed_at="2026-09-23T10:20:40Z")]
        txns = [_txn(), _txn(pid="12545", bid=5, mine=False, tid="T-r", created="2026-09-23T09:00:00Z")]
        self.assertEqual(reconcile(rows, txns), reconcile(rows, txns, None))
        self.assertEqual(reconcile(rows, txns), reconcile(rows, txns, []))


class TestTheReviewReadsTheLog(unittest.TestCase):
    def test_bid_review_passes_the_failed_claims(self):
        import inspect
        from scripts import bid_review
        src = inspect.getsource(bid_review.main)
        self.assertIn("reconcile(load(), _decisions(), _failed())", src)


if __name__ == "__main__":
    unittest.main()
