"""The any-given-stat site's published data -- read over HTTP, never from the owner's disk.

The scheduled runner cannot see C:\\, and a site that rebuilds daily already PUBLISHES what we want
as static JSON on GitHub Pages, so that is the interface. Two safeguards because it is another
project's output, not a contract: the feed is refused unless its `data_version` is one this client
was written against and it was generated recently, and every failure is one exception type the
caller can treat as "no second opinion this sync" (`try_fetch_injury_report` -> None).

Only what the availability watchdog needs is read: `meta.json` (version, freshness), `news.json`
(its `injury` items, built from the NFL's own injury report, with the practice detail Sleeper's
roster status lacks) and `fantasy_ids.json` (Sleeper id -> nflverse gsis id).
"""
import logging
from datetime import datetime, timezone

import requests

SITE = "https://brandon-kimberly.github.io/any-given-stat/data/"
# The data_version this client's parsing was written against (the site stamps it in meta.json and
# bumps it when a dataset's shape changes). A different number is refused, not guessed at.
SUPPORTED_DATA_VERSIONS = (5,)
# The site rebuilds daily in season plus extra Friday / Monday-Tuesday runs; two days old means a
# deploy has failed or stalled, and an old injury report is worse than none.
MAX_AGE_HOURS = 48


class FeedRejected(Exception):
    """The feed is reachable but not trustworthy (unknown version or too old)."""


def _parse_time(text):
    dt = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def check_meta(meta, now):
    ver = (meta or {}).get("data_version")
    if ver not in SUPPORTED_DATA_VERSIONS:
        raise FeedRejected(f"data_version {ver!r} is not one this client knows {SUPPORTED_DATA_VERSIONS}")
    try:
        age = (now - _parse_time(meta.get("generated_at"))).total_seconds() / 3600.0
    except (TypeError, ValueError):
        raise FeedRejected("meta.json has no readable generated_at")
    if age > MAX_AGE_HOURS:
        raise FeedRejected(f"the feed is {age:.0f} h old (limit {MAX_AGE_HOURS} h)")
    return age


def fetch_injury_report(get=None, now=None, timeout=20):
    """{"_meta": {...}, "players": {sleeper_id: {status, change, week, headline, detail, published}}}.
    Raises FeedRejected for an untrustworthy feed, and the underlying error for a network or HTTP
    failure."""
    get = get or requests.get
    now = now or datetime.now(timezone.utc)

    def j(name):
        r = get(SITE + name, timeout=timeout)
        r.raise_for_status()
        return r.json()

    meta = j("meta.json")
    age = check_meta(meta, now)
    news, ids = j("news.json"), j("fantasy_ids.json")
    to_sleeper = {gsis: sid for sid, gsis in (ids.get("sleeper") or {}).items()}
    players = {}
    for it in news.get("items") or []:
        if it.get("kind") != "injury":
            continue
        for gsis in it.get("players") or []:
            sid = to_sleeper.get(gsis)
            if sid:
                players[str(sid)] = {"status": it.get("status"), "change": it.get("change"),
                                     "week": it.get("week"), "headline": it.get("headline"),
                                     "detail": it.get("description"), "published": it.get("published")}
    report = news.get("injury_report") or {}
    return {"_meta": {"source": SITE, "generated_at": meta.get("generated_at"),
                      "data_version": meta.get("data_version"), "age_hours": round(age, 1),
                      "season": report.get("season"), "week": report.get("week"),
                      "fetched_at": now.isoformat(timespec="seconds")},
            "players": players}


def try_fetch_injury_report(get=None, now=None):
    """`fetch_injury_report`, or None on ANY failure -- a second opinion must never be the reason a
    sync fails. The reason is logged at INFO (an advisory miss is not a degradation)."""
    try:
        return fetch_injury_report(get=get, now=now)
    except Exception as ex:
        logging.info("AGS FEED: not used this sync (%s: %s).", type(ex).__name__, ex)
        return None
