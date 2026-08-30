"""Application version derived from installed metadata or ``pyproject.toml``."""

from __future__ import annotations

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _application_version() -> str:
    try:
        installed_version = version("portfolio-dashboard")
        if installed_version:
            return installed_version
    except PackageNotFoundError:
        pass
    project_file = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        project = tomllib.loads(project_file.read_text(encoding="utf-8"))
        return str(project["project"]["version"])
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "0.0.0+unknown"


APP_VERSION = _application_version()


def display_version(base_version: str, edition_suffix: str = "") -> str:
    """Add an optional private-edition suffix without changing package metadata."""

    suffix = edition_suffix.strip()
    if not suffix:
        return base_version
    if not suffix.isalnum():
        raise ValueError("edition_suffix must contain only letters and numbers")
    return f"{base_version}{suffix}"
