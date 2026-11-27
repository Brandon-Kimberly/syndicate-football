"""Keep the Luck page current: after a LOCAL sync, rerun the luck ledger (2026-11-27).

The web UI's Luck page reads the newest data/local/luck/accounting_<season>.json, which
`scripts.luck_ledger` writes. Nothing ran it but a person, so the page went stale every week.
`scripts.run_sync` (the Sync page, or a terminal) and `scripts.weekly_report` (when it syncs)
call `refresh_after_sync` once the sync has succeeded.

Best effort, by design: the refresh runs in its own process with a timeout, and whatever
happens to it -- a failed fetch, a timeout, no interpreter -- is a one-line note in the log,
never an exception and never a changed exit code. It never runs on a GitHub runner, where
data/local does not survive the job. Luck is pulled, never pushed (owner, 2026-09-21): this
only refreshes the file the Luck page reads; nothing reaches the digest or Home.
"""
import os
import subprocess
import sys

TIMEOUT_S = 180         # ~5 s with the projection cache; a new week's first fetch is slower


def refresh_after_sync(run=None, env=None, timeout=TIMEOUT_S, log=None):
    """Rerun `scripts.luck_ledger --json` for the current season. Returns 'refreshed',
    'skipped: ...' or 'failed: ...'; never raises."""
    env = os.environ if env is None else env
    say = log or (lambda msg: print(msg, file=sys.stderr))
    if env.get("GITHUB_ACTIONS"):
        return "skipped: on a runner (data/local is local only)"
    run = run or subprocess.run
    try:
        done = run([sys.executable, "-m", "scripts.luck_ledger", "--json"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
        rc = getattr(done, "returncode", 0)
        out = "refreshed" if rc == 0 else f"failed: the luck ledger exited {rc}"
    except subprocess.TimeoutExpired:
        out = f"failed: the luck ledger took longer than {timeout} s"
    except Exception as ex:                       # best effort: nothing escapes
        out = f"failed: {type(ex).__name__}: {ex}"
    try:
        say(f"[luck] the Luck page's numbers: {out}")
    except Exception:
        pass
    return out
