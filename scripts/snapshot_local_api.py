#!/usr/bin/env python3
"""Capture local API contracts without placing private payloads in Git."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlencode

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app as dashboard


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "tests" / "golden" / "local"
VOLATILE_KEYS = {
    "generated_at",
    "fetched_at",
    "last_updated",
    "timestamp",
}


def canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "<volatile>" if key in VOLATILE_KEYS else canonicalize(item)
            for key, item in sorted(value.items())
        }
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    return value


def slug(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value.lower()).strip("-") or "all"


def write_payload(path: Path, payload: Any) -> str:
    encoded = json.dumps(canonicalize(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    path.write_text(encoded, encoding="utf-8")
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def fetch_json(client: Any, endpoint: str, params: dict[str, str]) -> Any:
    response = client.get(f"{endpoint}?{urlencode(params)}")
    payload = response.get_json()
    if response.status_code != 200:
        raise RuntimeError(f"{endpoint} returned HTTP {response.status_code}: {payload}")
    return payload


def capture(include_news: bool, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    client = dashboard.app.test_client()
    users = [dashboard.SETTINGS.primary_portfolio_id, *dashboard.FAMILY_PORTFOLIOS]
    manifest: dict[str, Any] = {"files": {}}
    brokers: set[str] = {"all"}

    initial_payloads: dict[str, Any] = {}
    for user in users:
        print(f"Discovering brokers for {user}...", flush=True)
        payload = fetch_json(client, "/api/portfolio", {"person": user, "broker": "all"})
        initial_payloads[user] = payload
        brokers.update(str(item).lower() for item in payload.get("brokers", []) if item)

    for user in users:
        for broker in sorted(brokers):
            print(f"Capturing portfolio: {user} / {broker}", flush=True)
            params = {"person": user, "broker": broker}
            payload = initial_payloads[user] if broker == "all" else fetch_json(client, "/api/portfolio", params)
            filename = f"portfolio--{slug(user)}--{slug(broker)}.json"
            manifest["files"][filename] = write_payload(output_dir / filename, payload)
            if include_news:
                print(f"Capturing news: {user} / {broker}", flush=True)
                news = fetch_json(client, "/api/news", params)
                filename = f"news--{slug(user)}--{slug(broker)}.json"
                manifest["files"][filename] = write_payload(output_dir / filename, news)

    for broker in sorted(brokers):
        print(f"Capturing rankings: {broker}", flush=True)
        rankings = fetch_json(client, "/api/rankings", {"broker": broker})
        filename = f"rankings--{slug(broker)}.json"
        manifest["files"][filename] = write_payload(output_dir / filename, rankings)

    write_payload(output_dir / "manifest.json", manifest)
    print(f"Captured {len(manifest['files'])} payloads in {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-news", action="store_true", help="Skip the slower news endpoint.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    capture(include_news=not args.skip_news, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
