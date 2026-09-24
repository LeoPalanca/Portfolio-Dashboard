"""Read-only release discovery for the dashboard update control."""

from __future__ import annotations

import re
import tomllib
import urllib.request


GITHUB_RAW = "https://raw.githubusercontent.com/LeoPalanca/Portfolio-Dashboard/main"
RELEASE_HEADING = re.compile(r"^## (\d+\.\d+\.\d+)\b.*$", re.MULTILINE)


def version_tuple(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise ValueError(f"Invalid release version: {value}")
    return tuple(int(part) for part in match.groups())


def newer_release_notes(changelog: str, current_version: str) -> str:
    """Return every changelog section newer than the installed base version."""
    current = version_tuple(current_version)
    matches = list(RELEASE_HEADING.finditer(changelog))
    sections = []
    for index, match in enumerate(matches):
        if version_tuple(match.group(1)) <= current:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(changelog)
        sections.append(changelog[match.start():end].strip())
    return "\n\n".join(sections)[:12000]


def github_release_status(current_version: str, timeout: float = 5) -> dict[str, str | bool]:
    def fetch_text(path: str, limit: int) -> str:
        request = urllib.request.Request(
            f"{GITHUB_RAW}/{path}", headers={"User-Agent": "portfolio-dashboard-update-check"}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("GitHub release metadata exceeded the size limit")
        return raw.decode("utf-8")

    project = tomllib.loads(fetch_text("pyproject.toml", 128_000))
    latest_version = str(project["project"]["version"])
    available = version_tuple(latest_version) > version_tuple(current_version)
    changelog = fetch_text("CHANGELOG.md", 256_000) if available else ""
    return {
        "current_version": current_version,
        "latest_version": latest_version,
        "available": available,
        "changelog": newer_release_notes(changelog, current_version) if available else "",
        "release_url": "https://github.com/LeoPalanca/Portfolio-Dashboard/blob/main/CHANGELOG.md",
    }
