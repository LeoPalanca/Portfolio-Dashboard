"""Privileged, opt-in updater for the Pi systemd installation.

The web process can only queue a request under /var/lib. This service fetches
GitHub into a separate Git checkout, merges the Pi-only customization commit,
and copies only changed tracked code files after checking for local drift.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


SOURCE = Path("/opt/portfolio-dashboard-source")
TARGET = Path("/opt/portfolio-dashboard")
STATE = Path("/var/lib/portfolio-dashboard/update")
REQUEST = STATE / "request.json"
STATUS = STATE / "status.json"
DEPLOYED_HEAD = STATE / "deployed-head"
HEALTH_URL = "http://127.0.0.1:8050/"


def run(*args: str, cwd: Path = SOURCE, timeout: int = 120) -> bytes:
    result = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        detail = (result.stderr or result.stdout).decode("utf-8", "replace").strip()[-1500:]
        raise RuntimeError(f"{' '.join(args[:2])} failed: {detail}")
    return result.stdout


def write_status(state: str, **details: str) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    payload = {"state": state, "updated_at": datetime.now(timezone.utc).isoformat(), **details}
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=STATE, delete=False) as handle:
        json.dump(payload, handle)
        temporary = Path(handle.name)
    os.chmod(temporary, 0o644)
    os.replace(temporary, STATUS)


def version(path: Path) -> tuple[int, int, int]:
    value = tomllib.loads(path.read_text(encoding="utf-8"))["project"]["version"]
    parts = str(value).split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise RuntimeError(f"Unsupported release version: {value}")
    return tuple(int(part) for part in parts)


def healthy(expected_version: str, timeout: int = 420) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=5) as response:
                page = response.read(100_000).decode("utf-8", "replace")
            if f"Portfolio Dashboard v{expected_version}" in page:
                return True
        except (OSError, ValueError):
            pass
        time.sleep(5)
    return False


def changed_paths(old_head: str, new_head: str) -> list[Path]:
    raw = run("git", "diff", "--name-only", "-z", old_head, new_head)
    paths = [Path(item.decode("utf-8")) for item in raw.split(b"\0") if item]
    for path in paths:
        if path.is_absolute() or ".." in path.parts or path.parts[0] in {"data", "cache", ".git"}:
            raise RuntimeError(f"Update touches a protected path: {path}")
        if path.name in {"config.toml", ".env"}:
            raise RuntimeError(f"Update touches private configuration: {path}")
        if not (SOURCE / path).is_file() or (SOURCE / path).is_symlink():
            raise RuntimeError(f"Update removes or links a file; review manually: {path}")
    return paths


def install() -> None:
    if not REQUEST.exists():
        return
    REQUEST.unlink()
    write_status("running", message="Fetching GitHub release")
    if not (SOURCE / ".git").is_dir() or not DEPLOYED_HEAD.exists():
        raise RuntimeError("Update checkout is not configured; install the Pi updater first")
    if run("git", "status", "--porcelain").strip():
        raise RuntimeError("Update checkout has uncommitted changes; review them before updating")

    old_head = DEPLOYED_HEAD.read_text(encoding="utf-8").strip()
    run("git", "cat-file", "-e", f"{old_head}^{{commit}}")
    run("git", "fetch", "origin", "main", timeout=180)
    try:
        run("git", "merge", "--no-edit", "origin/main", timeout=60)
    except RuntimeError:
        if (SOURCE / ".git" / "MERGE_HEAD").exists():
            run("git", "merge", "--abort")
        raise RuntimeError("GitHub update conflicts with Pi-only changes; no installed files were changed") from None
    new_head = run("git", "rev-parse", "HEAD").decode().strip()
    new_version = ".".join(str(part) for part in version(SOURCE / "pyproject.toml"))
    if version(SOURCE / "pyproject.toml") <= version(TARGET / "pyproject.toml"):
        write_status("done", version=new_version, message="Already up to date")
        return

    paths = changed_paths(old_head, new_head)
    for path in paths:
        destination = TARGET / path
        old_blob = subprocess.run(
            ["git", "show", f"{old_head}:{path.as_posix()}"], cwd=SOURCE, capture_output=True, check=False
        )
        if destination.is_symlink() or (old_blob.returncode == 0 and (
            not destination.is_file() or destination.read_bytes() != old_blob.stdout
        )) or (old_blob.returncode != 0 and destination.exists()):
            raise RuntimeError(f"Installed file differs from the last release; review before updating: {path}")

    backup = Path(tempfile.mkdtemp(prefix="backup-", dir=STATE))
    installed: list[Path] = []
    try:
        write_status("running", version=new_version, message="Installing verified code files")
        for path in paths:
            destination = TARGET / path
            if destination.exists():
                (backup / path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, backup / path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / path, destination)
            installed.append(path)
        run(str(TARGET / ".venv/bin/python"), "-m", "py_compile", str(TARGET / "app.py"), cwd=TARGET)
        run("systemctl", "restart", "portfolio-dashboard.service", cwd=TARGET)
        if not healthy(new_version):
            raise RuntimeError("Updated dashboard did not become healthy within seven minutes")
        DEPLOYED_HEAD.write_text(new_head + "\n", encoding="utf-8")
        write_status("done", version=new_version, message="Update installed")
    except Exception:
        for path in reversed(installed):
            destination = TARGET / path
            if (backup / path).exists():
                shutil.copy2(backup / path, destination)
            else:
                destination.unlink(missing_ok=True)
        run("systemctl", "restart", "portfolio-dashboard.service", cwd=TARGET)
        raise


if __name__ == "__main__":
    try:
        install()
    except Exception as exc:
        write_status("error", error=str(exc))
        print(f"Portfolio update failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
