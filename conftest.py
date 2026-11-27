"""Run the tests against throwaway directories.

Settings are read when ``app`` is first imported. Without this, a developer's
``config.toml`` or environment would point the tests at the real source files,
movement ledger and caches, which some tests open and could migrate.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

_ROOT = Path(tempfile.mkdtemp(prefix="portfolio-dashboard-tests-"))
atexit.register(shutil.rmtree, _ROOT, True)
for name in ("source", "data", "cache"):
    (_ROOT / name).mkdir()
os.environ["PORTFOLIO_SOURCE_DIR"] = str(_ROOT / "source")
os.environ["PORTFOLIO_DATA_DIR"] = str(_ROOT / "data")
os.environ["PORTFOLIO_CACHE_DIR"] = str(_ROOT / "cache")
os.environ["PORTFOLIO_SCAN_DOWNLOADS"] = "false"
# Listing lookups (OpenFIGI) reach the network; tests that need them enable them.
os.environ["PORTFOLIO_VENUE_LOOKUP"] = "off"
