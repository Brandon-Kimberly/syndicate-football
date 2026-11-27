"""Luck accounting: how many wins luck moved, split into parts that add up exactly.

REGISTERED 2026-11-27 in docs/LUCK_LEDGER.md ("Addendum 2"), in a commit before this code,
and after the owner had seen the 2024-2026 numbers -- the file says so. Every choice below
(the projection basis, the noise scale, the null, the seed, the words) is fixed there.

    expected wins E   what the projections of the lineups actually started earned, on an
                      average schedule (all-play), plus the median games they earned
    performance luck  all-play wins from the real scores - all-play wins the projections earned
    schedule luck     actual head-to-head wins - all-play wins from the real scores
                      (fantasy_sim.luck_ledger's registered measure, unchanged)
    median luck       actual median wins - the median wins the projections earned
    total luck        the three added = actual wins - E. An identity, not a weighting.

Each part sums to zero across the league every week, so a bias every projection shares
cancels (the ledger's one methodological commitment). The five registered measures are
never added in: points against and close games are HOW schedule luck happens, and starters
who did not play are part of how a team misses its projection.

Addendum 3 (registered 2026-11-27, after the Addendum 2 numbers were seen, before this code):
given `best` -- each team-week's best-lineup projection from that week's roster -- it also
reports a DECISION measure beside the luck, never inside it:

    roster-earned E_best  E with my best lineup in place of the one I started, everyone else
                          as they started; the median half from the same simulated draws
    lineup calls          E - E_best, in wins (zero or negative), and in points a week
    identity              actual - E_best = lineup calls + total luck

Solving for the best lineup is the caller's (scripts.luck_ledger uses the web UI's solver);
this module stays pure.

Pure: stdlib only, no network, no engine. Callers pass plain dicts.
"""
import math
import random

from fantasy_sim.luck_ledger import MIN_WEEKS_FOR_INFERENCE, all_play

SIMULATIONS = 4000      # registered
SEED = 20261127         # registered

# Registered words for the one-sided share of simulated seasons at least as extreme.
WORD_CUTS = ((0.025, "rare"), (0.10, "unusual"), (0.25, "a bit unusual"))


def _phi(x):
    """Standard normal CDF."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def word(share):
    if share is None:
        return None
    for cut, w in WORD_CUTS:
        if share < cut:
            return w
    return "ordinary"


def noise_scale(scores, projected):
    """sigma: residuals S - P less that week's league-average residual, pooled over every
    team-week, sum of squares over (teams - 1) degrees of freedom per week. A team-week
    projected at 0 (an abandoned roster) is left out. None without enough data."""
    ss, df = 0.0, 0
    for w, row in projected.items():
        got = scores.get(w) or {}
        r = [got[t] - p for t, p in row.items() if p and p > 0 and got.get(t) is not None]
        if len(r) < 2:
            continue
        m = sum(r) / len(r)
        ss += sum((x - m) ** 2 for x in r)
        df += len(r) - 1
    if not df or ss <= 0:
        return None
    return math.sqrt(ss / df)


def _h2h(scores, w, a, b):
    sa, sb = scores[w][a], scores[w][b]
    return 1.0 if sa > sb else (0.0 if sa < sb else 0.5)


def _median_cut(vals):
    s = sorted(vals)
    n = len(s)
    return float(s[n // 2]) if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _share(obs, sims):
    """One-sided share of simulated values at least as extreme as `obs`, in obs's direction."""
    if not sims:
        return None
    if obs < 0:
        k = sum(1 for v in sims if v <= obs + 1e-12)
    elif obs > 0:
        k = sum(1 for v in sims if v >= obs - 1e-12)
    else:
        return 0.5
    return k / len(sims)


def _part(obs, sims, early):
    out = {"wins": round(obs, 3),
           "way": "lucky" if obs > 1e-9 else ("unlucky" if obs < -1e-9 else "neutral")}
    if early or sims is None:
        out.update(share=None, word=None, one_in=None, p=None)
        return out
    share = _share(obs, sims)
    out["share"] = round(share, 4)
    out["word"] = word(share)
    out["one_in"] = round(1.0 / share) if share > 0 else None       # None: rarer than 1 in len(sims)
    out["one_in_floor"] = len(sims)
    out["p"] = round(min(1.0, 2.0 * share), 4)
    return out


def across_seasons(seasons, seed=SEED):
    """Total luck summed over several seasons, with its own "how unusual".

    seasons  [(total_wins_of_luck, [simulated totals for that season]), ...]

    Added 2026-11-27 AFTER the per-season numbers were seen (docs/LUCK_LEDGER.md says so).
    The seasons are independent, so the null is the sum of one draw from each season's
    simulated totals; each season's draws are shuffled first (fixed seed) so that no two
    seasons share a random stream. None for fewer than two seasons."""
    seasons = [(t, s) for t, s in seasons if s]
    if len(seasons) < 2:
        return None
    rng = random.Random(seed)
    n = min(len(s) for _t, s in seasons)
    shuffled = []
    for _t, s in seasons:
        s = list(s)[:n]
        rng.shuffle(s)
        shuffled.append(s)
    pooled = [sum(col) for col in zip(*shuffled)]
    total = sum(t for t, _s in seasons)
    out = _part(total, pooled, False)
    out["seasons"] = len(seasons)
    return out


def accounting(scores, projected, pairs, results=None, median=False, starters=None,
               sims=SIMULATIONS, seed=SEED, keep_sims=False, best=None):
    """The registered wins accounting for every team in one season.

    scores     {week: {team: points as the league counted them}}
    projected  {week: {team: sum of the started players' projections}}
    pairs      {week: [(team_a, team_b), ...]}      head-to-head pairings
    results    {week: {team: (h2h_win, median_win)}} as the league counted them; a week or
               team it does not cover falls back to the scores
    median     whether the season had a median game
    starters   {week: {team: [(projected, scored), ...]}} optional, for the points lost to
               starters who scored 0.00
    best       {week: {team: the best lineup's projection}} optional (Addendum 3). A value
               below what was started is raised to it (the lineup started was legal); a
               team-week it does not cover counts as started. Without it, `roster_expected`
               and `lineup_calls` are None. It changes no luck part.

    Returns {"weeks", "left_out", "median", "sigma", "simulations", "seed", "early",
             "teams": {team: {...}}, "standings": [...]} or None without enough data.
    """
    weeks = sorted(w for w in scores
                   if w in projected and w in pairs and scores[w]
                   and all(projected[w].get(t) is not None for t in scores[w]))
    left_out = sorted(w for w in scores if w not in weeks)
    if not weeks:
        return None
    sub = {w: scores[w] for w in weeks}
    teams = sorted({t for w in weeks for t in scores[w]})
    sigma = noise_scale(sub, {w: projected[w] for w in weeks})
    if not sigma:
        return None
    early = len(weeks) < MIN_WEEKS_FOR_INFERENCE

    # --- what happened -------------------------------------------------------------
    ap = all_play(sub)
    games, h_act, m_act, opp = {}, {}, {}, {}
    for w in weeks:
        cut = _median_cut(list(sub[w].values()))
        for a, b in pairs[w]:
            if a not in sub[w] or b not in sub[w]:
                continue
            for me, them in ((a, b), (b, a)):
                games[me] = games.get(me, 0) + 1
                opp.setdefault(w, {})[me] = them
                rec = ((results or {}).get(w) or {}).get(me)
                h = rec[0] if rec and rec[0] is not None else _h2h(sub, w, me, them)
                h_act[me] = h_act.get(me, 0.0) + float(h)
        if median:
            for t, s in sub[w].items():
                rec = ((results or {}).get(w) or {}).get(t)
                m = rec[1] if rec and len(rec) > 1 and rec[1] is not None else (1.0 if s >= cut else 0.0)
                m_act[t] = m_act.get(t, 0.0) + float(m)

    # --- what the projections earned --------------------------------------------------
    scale = sigma * math.sqrt(2.0)
    q = {}
    for t in teams:
        tot, n = 0.0, 0
        for w in weeks:
            if t not in projected[w]:
                continue
            for o, po in projected[w].items():
                if o == t:
                    continue
                tot += _phi((projected[w][t] - po) / scale)
                n += 1
        q[t] = tot / n if n else 0.0

    # --- Addendum 3: what each roster's best lineups earned, the others as started ------
    def top(w, t):
        """P_best: never below what was started; a team-week `best` does not cover = started."""
        p = projected[w][t]
        b = ((best or {}).get(w) or {}).get(t)
        return max(float(b), p) if b is not None else p

    q_best = {}
    if best:
        for t in teams:
            tot, n = 0.0, 0
            for w in weeks:
                if t not in projected[w]:
                    continue
                for o, po in projected[w].items():
                    if o == t:
                        continue
                    tot += _phi((top(w, t) - po) / scale)
                    n += 1
            q_best[t] = tot / n if n else 0.0

    # --- the null: S = P + sigma * e, on the real schedule ----------------------------
    # One e per team-week, drawn in the same order as before Addendum 3, so the registered
    # numbers do not move; the best lineups reuse the same e (Addendum 3: shared draws).
    rng = random.Random(seed)
    sim_ap = {t: [] for t in teams}
    sim_h = {t: [] for t in teams}
    sim_m = {t: [] for t in teams}
    sim_mb = {t: [] for t in teams}
    for _ in range(sims):
        apw = dict.fromkeys(teams, 0.0)
        apn = dict.fromkeys(teams, 0)
        hw = dict.fromkeys(teams, 0.0)
        mw = dict.fromkeys(teams, 0.0)
        mwb = dict.fromkeys(teams, 0.0)
        for w in weeks:
            eps = {t: rng.gauss(0.0, 1.0) for t in sub[w]}
            draw = {t: projected[w][t] + sigma * eps[t] for t in sub[w]}
            order = sorted(draw, key=draw.get)
            n = len(order)
            for i, t in enumerate(order):
                apw[t] += i                      # beats everyone below (ties: probability 0)
                apn[t] += n - 1
                if median and i >= n - n // 2:   # top half
                    mw[t] += 1.0
            if best and median:
                for t in sub[w]:
                    mine = top(w, t) + sigma * eps[t]
                    below = sum(1 for o in sub[w] if o != t and draw[o] < mine)
                    if below >= n - n // 2:
                        mwb[t] += 1.0
            for t, o in (opp.get(w) or {}).items():
                if draw[t] > draw[o]:
                    hw[t] += 1.0
        for t in teams:
            g = games.get(t, 0)
            sim_ap[t].append((apw[t] / apn[t]) * g if apn[t] else 0.0)
            sim_h[t].append(hw[t])
            sim_m[t].append(mw[t])
            sim_mb[t].append(mwb[t])

    e_m = {t: (sum(sim_m[t]) / sims if median else 0.0) for t in teams}
    e_mb = {t: (sum(sim_mb[t]) / sims if median else 0.0) for t in teams}

    # --- where it came from (never added) ---------------------------------------------
    resid = {}
    for w in weeks:
        r = {t: sub[w][t] - projected[w][t] for t in sub[w]}
        m = sum(r.values()) / len(r)
        for t, v in r.items():
            resid.setdefault(t, []).append((v, v - m))
    dnp = {}
    if starters:
        for w in weeks:
            row = starters.get(w) or {}
            lost = {t: sum(p for p, s in (row.get(t) or []) if p and p > 0 and abs(s or 0.0) <= 1e-9)
                    for t in sub[w]}
            m = sum(lost.values()) / len(lost)
            for t, v in lost.items():
                dnp.setdefault(t, []).append((v, v - m))

    out = {}
    for t in teams:
        g = games.get(t, 0)
        w_ap, n_ap = ap.get(t, (0.0, 0))
        ap_wins = (w_ap / n_ap) * g if n_ap else 0.0
        e_h = q[t] * g
        perf = ap_wins - e_h
        sched = h_act.get(t, 0.0) - ap_wins
        med = (m_act.get(t, 0.0) - e_m[t]) if median else None
        total = perf + sched + (med or 0.0)
        s_perf = [a - e_h for a in sim_ap[t]]
        s_sched = [h - a for h, a in zip(sim_h[t], sim_ap[t])]
        s_med = [m - e_m[t] for m in sim_m[t]] if median else None
        s_tot = [p + s + (m if median else 0.0) for p, s, m in
                 zip(s_perf, s_sched, (s_med or [0.0] * sims))]
        rs = resid.get(t) or []
        ds = dnp.get(t) or []
        out[t] = {
            "games": g,
            "actual": {"h2h": h_act.get(t, 0.0), "median": m_act.get(t) if median else None,
                       "total": h_act.get(t, 0.0) + (m_act.get(t, 0.0) if median else 0.0)},
            "expected": {"h2h": round(e_h, 3), "median": round(e_m[t], 3) if median else None,
                         "total": round(e_h + e_m[t], 3)},
            "all_play_wins": round(ap_wins, 3),
            "parts": {"performance": _part(perf, s_perf, early),
                      "schedule": _part(sched, s_sched, early),
                      "median": _part(med, s_med, early) if median else None,
                      "total": _part(total, s_tot, early)},
            "explain": {
                "projected_per_week": round(sum(projected[w][t] for w in weeks if t in projected[w]) / len(weeks), 2),
                "scored_per_week": round(sum(sub[w][t] for w in weeks if t in sub[w]) / len(weeks), 2),
                "vs_projection_per_week": round(sum(v for v, _ in rs) / len(rs), 2) if rs else None,
                "vs_projection_relative": round(sum(d for _, d in rs) / len(rs), 2) if rs else None,
                "dnp_points_per_week": round(sum(v for v, _ in ds) / len(ds), 2) if ds else None,
                "dnp_points_relative": round(sum(d for _, d in ds) / len(ds), 2) if ds else None,
            },
        }
        if best:                                        # Addendum 3: a decision, not a luck part
            e_hb = q_best[t] * g
            calls = (e_h + e_m[t]) - (e_hb + e_mb[t])
            gaps = [projected[w][t] - top(w, t) for w in weeks if t in projected[w]]
            out[t]["roster_expected"] = {"h2h": round(e_hb, 3), "median": round(e_mb[t], 3) if median else None,
                                         "total": round(e_hb + e_mb[t], 3)}
            # zero or negative by construction (Addendum 3); + 0.0 turns a -0.0 into 0.0
            out[t]["lineup_calls"] = {"wins": round(calls, 3) + 0.0,
                                      "points_per_week": (round(sum(gaps) / len(gaps), 2) + 0.0) if gaps else 0.0,
                                      "weeks_short": sum(1 for x in gaps if x < -0.005)}
        else:
            out[t]["roster_expected"] = None
            out[t]["lineup_calls"] = None
        if keep_sims:                                   # for across_seasons; never saved
            out[t]["_sims_total"] = s_tot

    # --- standings, every team's luck taken out -----------------------------------------
    pf = {t: sum(sub[w].get(t, 0.0) for w in weeks) for t in teams}
    pp = {t: sum(projected[w].get(t, 0.0) for w in weeks) for t in teams}
    by_actual = sorted(teams, key=lambda t: (-out[t]["actual"]["total"], -pf[t]))
    by_neutral = sorted(teams, key=lambda t: (-out[t]["expected"]["total"], -pp[t]))
    standings = [{"team": t, "actual_wins": out[t]["actual"]["total"],
                  "neutral_wins": out[t]["expected"]["total"],
                  "luck": out[t]["parts"]["total"]["wins"],
                  "actual_rank": by_actual.index(t) + 1, "neutral_rank": by_neutral.index(t) + 1,
                  "points_for": round(pf[t], 2)}
                 for t in by_actual]
    if best:
        for r in standings:
            r["roster_wins"] = out[r["team"]]["roster_expected"]["total"]
            r["lineup_calls"] = out[r["team"]]["lineup_calls"]["wins"]
    for t in teams:
        out[t]["actual_rank"] = by_actual.index(t) + 1
        out[t]["neutral_rank"] = by_neutral.index(t) + 1
    return {"weeks": weeks, "left_out": left_out, "median": bool(median), "sigma": round(sigma, 2),
            "simulations": sims, "seed": seed, "early": early, "teams": out, "standings": standings}
