"""Availability watchdog -- ADVISORY. Nothing here is read by the engine, a roster, a lineup or a
quote; it only tells a human where the engine's picture of who plays may be wrong.

Two classes (written 2026-10-12 after Caleb Williams, out since week 3, was carried at a healthy
19.4 and chosen at QB):

  carried_unprojected  Sleeper projects a rostered, non-bye player at nothing and he is not already
                       Out/IR by Sleeper's own status, so the sync CARRIED an earlier mean. The
                       engine does not treat 'Questionable' as an absence, so it values him as
                       healthy. Needs no outside data.
  ags_disagrees        the injury report any-given-stat publishes says Out/Doubtful for a player
                       Sleeper still shows healthy or merely Questionable (practice detail is in
                       the report, not in Sleeper's roster record).

It changes no number. Fixing the first class in the engine is a held MAJOR (see the held-fixes
memory); this exists so the cases are VISIBLE meanwhile, and so the evidence for that fix accrues.
"""
import json

from fantasy_sim.storage import ensure_dir_for

OUT_STATUSES = ("Out", "Doubtful")
# Sleeper statuses that already tell the engine a player is not playing (INITIAL_ABSENCE_STATUSES
# plus its own IR flag); a carry on top of one of these is handled, not a finding.
SLEEPER_ABSENT = ("IR", "PUP", "Out", "Sus", "DNR", "NA", "Doubtful")


def _owners(rosters):
    return {p.get("name"): team for team, players in (rosters or {}).items() for p in players}


def availability_findings(rosters, baselines, week, ags_players=None):
    """[{kind, name, pos, team, fantasy_team, detail}] for ROSTERED players only."""
    owner = _owners(rosters)
    ags_players = ags_players or {}
    out = []
    for name, b in (baselines or {}).items():
        if name not in owner or not isinstance(b, dict):
            continue
        if b.get("bye") == week:
            continue
        status, on_ir = b.get("injury_status"), bool(b.get("on_ir"))
        base = {"name": name, "pos": b.get("pos"), "team": b.get("team"), "fantasy_team": owner[name]}
        if str(b.get("projection_source") or "").startswith("carried") and not on_ir and status not in SLEEPER_ABSENT:
            out.append(dict(base, kind="carried_unprojected", detail=(
                f"Sleeper projects {name} at nothing this week (status {status or 'none'}); the engine is "
                f"using a carried mean of {float(b.get('mean') or 0):.1f} as if he plays.")))
        a = ags_players.get(str(b.get("player_id")))
        if a and a.get("week") == week and a.get("status") in OUT_STATUSES and status != a["status"] \
                and status not in SLEEPER_ABSENT and not on_ir:
            out.append(dict(base, kind="ags_disagrees", detail=(
                f"the injury report says {a['status']} ({a.get('headline') or 'no headline'}); "
                f"Sleeper shows {status or 'healthy'}.")))
    return out


def annotate_practice(baselines, ags_players, week):
    """Stamp `practice_status` ('full' | 'limited' | 'dnp') on a rostered-or-not baseline whose Sleeper
    status is Questionable when the NFL report for THIS week says Questionable too and names the
    practice: the engine's availability table for a Questionable player depends on it
    (SIM_CONFIG['QUESTIONABLE_PLAY_PROBABILITY_BY_PRACTICE']). Anything else is left unannotated, and a
    stale stamp from an earlier sync is removed -- an old practice report must never price a new week.
    Returns how many baselines were stamped."""
    n = 0
    for b in (baselines or {}).values():
        if not isinstance(b, dict):
            continue
        b.pop("practice_status", None)
        a = (ags_players or {}).get(str(b.get("player_id")))
        if (a and b.get("injury_status") == "Questionable" and a.get("status") == "Questionable"
                and a.get("week") == week and a.get("practice") in ("full", "limited", "dnp")):
            b["practice_status"] = a["practice"]
            n += 1
    return n


def write_availability_watch(path, rosters, baselines, week, ags_report=None, now=None):
    findings = availability_findings(rosters, baselines, week, (ags_report or {}).get("players"))
    doc = {"_meta": {"week": int(week), "ags_used": ags_report is not None,
                     "ags": (ags_report or {}).get("_meta"),
                     "written_at": (now.isoformat(timespec="seconds") if now else None)},
           "findings": findings}
    ensure_dir_for(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
    return findings
