"""Send less over slow links: smaller dashboard responses, compressed and cached assets.

The dashboard is often opened through a relayed VPN connection with little bandwidth,
so bytes on the wire, not server time, decide how fast it feels. Saved snapshots stay
complete (exports read them); only what the browser receives is trimmed here.
"""

from __future__ import annotations

import gzip
import threading
from collections.abc import Mapping
from typing import Any

from flask import Flask, Response, request

COMPRESSIBLE_TYPES = frozenset(
    {"text/css", "text/javascript", "application/javascript", "image/svg+xml", "text/html", "text/plain"}
)
MINIMUM_COMPRESSED_BYTES = 1024
# Fields of ``distribution.source_rows`` the browser reads when a composition source is selected.
SOURCE_ROW_FIELDS = ("source_asset", "source_isin", "holding_name", "holding_ticker", "market_value_eur", "asset_class")


def compact_floats(value: Any, key: str = "") -> Any:
    """Round floats to what the page can show: cents for EUR amounts, six decimals otherwise."""

    if isinstance(value, float):
        return round(value, 2 if key.endswith("_eur") else 6)
    if isinstance(value, Mapping):
        return {name: compact_floats(item, str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [compact_floats(item, key) for item in value]
    return value


def slim_dashboard_response(payload: Mapping[str, Any]) -> dict[str, Any]:
    """The dashboard payload without what the browser never reads or loads separately.

    * Income and expense rows come from ``/api/expenses``, which the page requests
      in parallel, so only their status travels with the portfolio.
    * Drill-down data (a fund's holdings, a sector's holdings) is fetched from
      ``/api/portfolio/distribution-details`` when the user opens it.
    * Floats are rounded to the precision the page displays.
    """

    slim = dict(payload)
    expenses = payload.get("expenses")
    if isinstance(expenses, Mapping):
        slim["expenses"] = {
            "status": expenses.get("status"),
            "message": expenses.get("message"),
            "rows": [],
            "deferred": True,
        }
    distribution = payload.get("distribution")
    if isinstance(distribution, Mapping):
        distribution = dict(distribution)
        distribution.pop("source_rows", None)
        distribution["sectors"] = [
            {**{key: value for key, value in sector.items() if key != "holdings"}, "holdings_count": len(sector.get("holdings") or [])}
            for sector in distribution.get("sectors") or []
            if isinstance(sector, Mapping)
        ]
        distribution["details_deferred"] = True
        slim["distribution"] = compact_floats(distribution)
    stats = payload.get("stats")
    if isinstance(stats, Mapping):
        slim["stats"] = compact_floats(stats)
    return slim


def distribution_details(payload: Mapping[str, Any]) -> dict[str, Any]:
    """The drill-down rows left out of the trimmed response."""

    distribution = payload.get("distribution") or {}
    return compact_floats(
        {
            "source_rows": [
                {field: row.get(field) for field in SOURCE_ROW_FIELDS}
                for row in distribution.get("source_rows") or []
                if isinstance(row, Mapping)
            ],
            "sector_holdings": {
                str(sector.get("sector")): sector.get("holdings") or []
                for sector in distribution.get("sectors") or []
                if isinstance(sector, Mapping)
            },
        }
    )


class SlimResponseCache:
    """Remember the trimmed form of each saved snapshot object, which can be several MB."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[Mapping[str, Any], dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def get(self, key: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry[0] is payload:
                return entry[1]
        slim = slim_dashboard_response(payload)
        with self._lock:
            if len(self._entries) >= 32:
                self._entries.clear()
            self._entries[key] = (payload, slim)
        return slim


def install_asset_delivery(app: Flask) -> None:
    """Cache versioned static files for a year and gzip text responses for browsers that accept it."""

    compressed: dict[tuple[str, str], bytes] = {}
    lock = threading.Lock()

    @app.after_request
    def deliver(response: Response) -> Response:
        is_static = request.path.startswith("/static/")
        if is_static and response.status_code == 200 and request.args.get("v"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        if (
            response.status_code != 200
            or "Content-Encoding" in response.headers
            or response.mimetype not in COMPRESSIBLE_TYPES
            or not request.accept_encodings["gzip"]
        ):
            return response
        response.direct_passthrough = False
        data = response.get_data()
        if len(data) < MINIMUM_COMPRESSED_BYTES:
            return response
        etag, weak = response.get_etag()
        key = (request.path, etag or "")
        body = None
        if is_static and etag:
            with lock:
                body = compressed.get(key)
        if body is None:
            body = gzip.compress(data, compresslevel=6)
            if is_static and etag:
                with lock:
                    if len(compressed) >= 64:
                        compressed.clear()
                    compressed[key] = body
        response.set_data(body)
        response.headers["Content-Encoding"] = "gzip"
        response.vary.add("Accept-Encoding")
        if etag:
            response.set_etag(f"{etag}-gzip", weak=bool(weak))
        return response
