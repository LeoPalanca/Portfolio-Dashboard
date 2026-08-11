"""Application version derived from installed metadata or ``pyproject.toml``."""

from __future__ import annotations

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _application_version() -> str:
    try:
        return version("portfolio-dashboard")
    except PackageNotFoundError:
        project_file = Path(__file__).resolve().parents[2] / "pyproject.toml"
        try:
            project = tomllib.loads(project_file.read_text(encoding="utf-8"))
            return str(project["project"]["version"])
        except (OSError, KeyError, tomllib.TOMLDecodeError):
            return "0.0.0+unknown"


APP_VERSION = _application_version()

