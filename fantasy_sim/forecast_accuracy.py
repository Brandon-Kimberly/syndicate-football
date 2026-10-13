"""Forecast accuracy across the league: the canonical pre-kickoff quote against the banked result.

Read-only. The rule for which quote counts is the one `read_predictions_log` uses for the
consumers (F18/F19): a canonical row, logged before the week's first kickoff. Coverage uses the
quoted sd_total as the band width: an 80% band is |z| <= 1.2816, a 50% band is |z| <= 0.6745."""
import math

Z80 = 1.2816
Z50 = 0.6745


def pre_kickoff_record(rows, week, kickoff):
    """The latest canonical week_predictions row for `week` logged before `kickoff` (ISO UTC),
    or None. Rows are the parsed predictions log; the file order is not used."""
    cands = [r for r in rows or []
             if r.get("record_type") == "week_predictions" and r.get("canonical")
             and str(r.get("week")) == str(week) and str(r.get("logged_at", "")) < kickoff]
    return max(cands, key=lambda r: r["logged_at"]) if cands else None


def team_errors(record, actuals):
    """{team: {quote, actual, error, z}} for every team with both a quote and a banked actual.
    A team with no actual is left out, never counted as zero."""
    out = {}
    for team, m in (record or {}).get("median", {}).items():
        if team not in actuals or m.get("expected_total") is None:
            continue
        quote, sd = float(m["expected_total"]), float(m.get("sd_total") or 0.0)
        actual = float(actuals[team])
        err = actual - quote
        out[team] = {"quote": quote, "actual": actual, "error": err,
                     "z": (err / sd) if sd > 0 else None}
    return out


def summarise(errors):
    """League summary of a {team: {error, z}} mapping. Empty input gives None fields."""
    errs = list(errors.values())
    n = len(errs)
    if n == 0:
        return {"n": 0, "mean_error": None, "mae": None, "rms_z": None,
                "coverage80": None, "coverage50": None}
    zs = [e["z"] for e in errs if e.get("z") is not None]
    return {
        "n": n,
        "mean_error": sum(e["error"] for e in errs) / n,
        "mae": sum(abs(e["error"]) for e in errs) / n,
        "rms_z": math.sqrt(sum(z * z for z in zs) / len(zs)) if zs else None,
        "coverage80": (sum(1 for z in zs if abs(z) <= Z80) / len(zs)) if zs else None,
        "coverage50": (sum(1 for z in zs if abs(z) <= Z50) / len(zs)) if zs else None,
    }


def week_result(rows, banked, kickoffs, week):
    """One week's outcome: {week, status, quote_logged_at, commit, errors}. status is one of
    scored | pending | no_kickoff | no_quote | no_overlap. Never guesses: a week that cannot be
    scored says why and carries no errors."""
    out = {"week": week, "status": None, "quote_logged_at": None, "commit": None, "errors": {}}
    kick = (kickoffs or {}).get(str(week))
    if not kick:
        out["status"] = "no_kickoff"
        return out
    rec = pre_kickoff_record(rows, week, min(kick))
    if rec is None:
        out["status"] = "no_quote"
        return out
    out["quote_logged_at"], out["commit"] = rec["logged_at"], str(rec.get("commit") or "")[:7]
    block = (banked or {}).get(f"week_{week}")
    if not block:
        out["status"] = "pending"
        return out
    errs = team_errors(rec, {t: v["points"] for t, v in block.items()})
    if not errs:
        out["status"] = "no_overlap"
        return out
    out["status"], out["errors"] = "scored", errs
    return out


def build_record(season, rows, banked, kickoffs, generated_at):
    """The whole season's accuracy as one JSON-able record: per-week outcomes (scored weeks carry
    their summary and per-team errors) and a pooled summary over the scored team-weeks."""
    weeks = []
    pooled = {}
    for w in sorted({int(r["week"]) for r in rows or [] if r.get("record_type") == "week_predictions"}):
        r = week_result(rows, banked, kickoffs, w)
        entry = {"week": w, "status": r["status"], "quote_logged_at": r["quote_logged_at"],
                 "commit": r["commit"]}
        if r["status"] == "scored":
            s = summarise(r["errors"])
            entry.update({k: s[k] for k in ("n", "mean_error", "mae", "rms_z", "coverage80", "coverage50")})
            entry["teams"] = {t: round(e["error"], 2) for t, e in r["errors"].items()}
            for t, e in r["errors"].items():
                pooled[f"{t}|{w}"] = e
        weeks.append(entry)
    return {"record_type": "forecast_accuracy", "season": str(season), "generated_at": generated_at,
            "weeks": weeks, "pooled": summarise(pooled)}


def append_if_changed(path, record):
    """Append `record` as one JSON line unless the scored content equals the last line's. The
    timestamp is ignored in that comparison, so a daily run writes only when a number moves.
    Returns True when a line was written."""
    import json
    def content(rec):
        return json.dumps({k: v for k, v in rec.items() if k != "generated_at"}, sort_keys=True)
    last = None
    try:
        with open(path, encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]
        last = json.loads(lines[-1]) if lines else None
    except FileNotFoundError:
        pass
    if last is not None and content(last) == content(record):
        return False
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
    return True
