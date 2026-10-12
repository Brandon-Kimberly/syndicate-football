"""Where the analysis scripts read from. Run them from this directory with the any-given-stat
environment (it has DuckDB; this repo's pinned runtime does not):

    cd analysis && uv run --project ../../any-given-stat/pipeline python a1_status.py

AGS_ROOT overrides the default sibling checkout (../any-given-stat relative to this repo, else ~/any-given-stat)."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
_CANDIDATES = [os.path.join(os.path.dirname(REPO), "any-given-stat"), os.path.expanduser("~/any-given-stat")]
AGS = os.environ.get("AGS_ROOT") or next((c for c in _CANDIDATES if os.path.isdir(c)), _CANDIDATES[0])
RAW = os.path.join(AGS, "data", "raw") + "/"                       # nflverse parquet/csv as downloaded
SITE = os.path.join(AGS, "web", "static", "data") + "/"            # the site's published JSON
DATA = os.path.join(REPO, "data") + "/"
LOGS = os.path.join(DATA, "logs") + "/"
