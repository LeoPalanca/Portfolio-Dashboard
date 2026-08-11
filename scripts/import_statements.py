"""Import statement files into the raw archive and normalized SQLite ledger."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app import import_statement_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+")
    parser.add_argument("--source", default="auto")
    args = parser.parse_args()
    failed = False
    for raw_path in args.files:
        path = Path(raw_path).expanduser().resolve()
        try:
            result = import_statement_path(path, requested_source=args.source)
            print(json.dumps({"file": path.name, **result}, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001 - one failed file must not hide results for the others
            failed = True
            print(json.dumps({"file": path.name, "status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
