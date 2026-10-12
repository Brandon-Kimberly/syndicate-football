"""Which adopted change moves which golden scenario, and by how much.

Runs the three golden-master scenarios (tests/fixtures/golden/*) under the CURRENT constants and with
each of the four engine-visible changes reverted in turn, then all four together. The RNG stream is
identical across variants (nothing here adds a draw: thresholds and means move, not the draw order), so
a difference between two variants is a paired difference of the model change itself, not sampling noise.
More sims than the golden's 2 x 15 so the paired differences are readable.

    py -3.10 analysis/golden_attribution.py [--batches 4] [--sims 30]

Run it from the repo root with the repo's pinned runtime (it imports the engine; it does not need DuckDB).
The game-time-status draw and the nflverse repair are not in this table: the golden fixtures carry no
Questionable/Doubtful player and no Odds payload, so neither can move them."""
import argparse
import os
import sys
from contextlib import ExitStack
from unittest.mock import patch

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fantasy_sim.config import SIM_CONFIG  # noqa: E402
from fantasy_sim.simulation import FantasySimulationEngine  # noqa: E402
from tests.golden_master import SCENARIOS, STAGE_A_ARG_NAMES, _sandbox  # noqa: E402

OLD = {
    "env": {"ENV_SHARE_IN_PROJECTION": 0.0},
    "tier": {"DEF_TIER_BOTTOM_BONUS": 0.06},
    "te": {"VACATED_VOLUME_CAPTURE_BY_POSITION": {}},
}
OLD_RATES = {"LB": 0.025, "DB": 0.020}
VARIANTS = ("new", "env_off", "tier_off", "te_off", "rates_off", "all_old")


def run(scenario, variant, batches, sims):
    cfg = {}
    rates = {}
    if variant in ("env_off", "all_old"): cfg.update(OLD["env"])
    if variant in ("tier_off", "all_old"): cfg.update(OLD["tier"])
    if variant in ("te_off", "all_old"): cfg.update(OLD["te"])
    if variant in ("rates_off", "all_old"): rates = OLD_RATES
    captured = {}
    real_export = FantasySimulationEngine.export_and_visualize

    def grab(self, *a):
        if not captured:
            captured.update(zip(STAGE_A_ARG_NAMES, a))
        return real_export(self, *a)

    with ExitStack() as st, _sandbox(scenario, batches, sims) as _saved:
        st.enter_context(patch.dict(SIM_CONFIG, cfg))
        st.enter_context(patch.dict(SIM_CONFIG["INJURY_RATES"], rates))
        engine = FantasySimulationEngine()
        with patch.object(FantasySimulationEngine, "export_and_visualize", grab):
            engine.run_simulation()
    scores = captured["global_weekly_scores"]
    team_mean = {t: float(np.nanmean(np.where(np.asarray(a) > 0, a, np.nan))) for t, a in scores.items()}
    playoff = {t: float(np.mean(v)) for t, v in captured["b_playoffs"].items()}
    return team_mean, playoff, float(np.mean(list(team_mean.values())))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batches", type=int, default=4)
    ap.add_argument("--sims", type=int, default=30)
    args = ap.parse_args(argv)
    for scenario in SCENARIOS:
        res = {v: run(scenario, v, args.batches, args.sims) for v in VARIANTS}
        base_means, base_play, base_lg = res["all_old"]
        print(f"\n== {scenario}: league mean weekly team score and mean change in playoff share, vs ALL-OLD constants")
        print(f"   {'variant':10s} {'league mean pts':>16s} {'d pts vs all_old':>17s} {'max |d playoff share|':>22s}")
        for v in VARIANTS:
            means, play, lg = res[v]
            dpl = max(abs(play[t] - base_play[t]) for t in play)
            print(f"   {v:10s} {lg:16.2f} {lg - base_lg:+17.2f} {dpl:22.3f}")
        # what each single change is worth, as the drop when reverted from NEW
        _, _, new_lg = res["new"]
        for v, name in (("env_off", "environment neutralisation"), ("tier_off", "bottom-tier bonus 0.04"),
                        ("te_off", "TE capture 0.45"), ("rates_off", "LB/DB onset rates")):
            print(f"   {name:30s}: {new_lg - res[v][2]:+.2f} pts per team-week (new minus reverted)")


if __name__ == "__main__":
    main()
