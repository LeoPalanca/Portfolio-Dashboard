"""Browser-facing protections for a dashboard that has no login of its own.

The dashboard is meant to be reachable only from localhost or a private network,
so the realistic attacker is a web page open in a browser on that network. These
checks stop such a page from talking to the dashboard:

* the Host header must name this machine (blocks DNS rebinding), and
* state-changing requests must come from the dashboard's own origin (blocks
  cross-site form and ``fetch`` submissions, which need no CORS preflight).

Responses also carry a Content-Security-Policy that keeps data from being sent to
other origins, plus the usual framing and MIME-sniffing headers.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Iterable
from urllib.parse import urlsplit

from flask import Flask, Response, jsonify, request

TRUSTED_HOSTS_ENV = "PORTFOLIO_TRUSTED_HOSTS"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CSP_DIRECTIVES: tuple[str, ...] = (
    "default-src 'self'",
    # Inline handlers are still used by the templates; connect-src below is
    # what keeps an injected script from exporting data to another origin.
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: https://assets.parqet.com",
    "font-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
)
CONTENT_SECURITY_POLICY = "; ".join(CSP_DIRECTIVES)
SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}


def host_name(host_header: str | None) -> str:
    """Return the lower-case host name from a Host header, without port or brackets."""

    raw = (host_header or "").strip().lower()
    if raw.startswith("["):
        end = raw.find("]")
        return raw[1:end] if end > 0 else ""
    if raw.count(":") > 1:
        return raw
    return raw.partition(":")[0].rstrip(".")


def configured_trusted_hosts(value: str | None = None) -> tuple[str, ...]:
    """Parse the optional comma-separated ``PORTFOLIO_TRUSTED_HOSTS`` list."""

    raw = os.environ.get(TRUSTED_HOSTS_ENV, "") if value is None else value
    return tuple(item.strip().lower().rstrip(".") for item in raw.split(",") if item.strip())


def is_trusted_host(
    host_header: str | None,
    extra_hosts: Iterable[str] = (),
    machine_name: str | None = None,
) -> bool:
    """Accept IP literals, localhost, this machine's names, and configured extras.

    A DNS-rebinding page can only send its own domain name as Host, so IP
    literals and the machine's own names are safe to accept. Extras starting with
    a dot match that domain and its subdomains.
    """

    name = host_name(host_header)
    if not name:
        return False
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        pass
    if name == "localhost" or name.endswith(".localhost"):
        return True
    machine = (machine_name if machine_name is not None else socket.gethostname()).split(".")[0].lower()
    if machine and (
        name in {machine, f"{machine}.local"} or (name.startswith(f"{machine}.") and name.endswith(".ts.net"))
    ):
        return True
    for entry in extra_hosts:
        if entry.startswith("."):
            if name == entry[1:] or name.endswith(entry):
                return True
        elif name == entry:
            return True
    return False


def is_same_origin(origin: str, host_header: str | None) -> bool:
    """True when an Origin header names the host the request was sent to."""

    parts = urlsplit(origin.strip())
    return (
        parts.scheme in {"http", "https"} and bool(parts.netloc) and parts.netloc.lower() == (host_header or "").lower()
    )


def install_web_security(app: Flask, extra_hosts: Iterable[str] | None = None) -> None:
    """Register the Host/Origin checks and security headers on a Flask app."""

    trusted_extras = tuple(extra_hosts) if extra_hosts is not None else configured_trusted_hosts()

    @app.before_request
    def reject_untrusted_requests() -> tuple[Response, int] | None:
        if not is_trusted_host(request.host, trusted_extras):
            return jsonify({"error": "Untrusted Host header. Add the name to PORTFOLIO_TRUSTED_HOSTS."}), 400
        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("Origin")
            if origin is not None:
                if not is_same_origin(origin, request.host):
                    return jsonify({"error": "Cross-origin requests are not allowed."}), 403
            elif request.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
                return jsonify({"error": "Cross-origin requests are not allowed."}), 403
        return None

    @app.after_request
    def add_security_headers(response: Response) -> Response:
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response


def restrict_pdf_resource_access() -> None:
    """Stop ReportLab from fetching remote URLs named in exported statement text.

    ReportLab reads these settings the first time it opens a resource, so this
    must run before the first PDF export.
    """

    from reportlab import rl_config  # type: ignore[import-untyped]

    rl_config.trustedHosts = ["portfolio-dashboard.invalid"]
    rl_config.trustedSchemes = ["file", "data"]
