"""Fixed bridge proxy and focused research boundaries; no external requests."""

import json
import re
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from flask import Flask

from src.portfolio_dashboard.ibkr_monitor import create_ibkr_blueprint
from scripts.ibkr_cash_bridge import execution_enabled


def client_for(tmp_path):
    app = Flask(__name__, template_folder="templates")
    app.register_blueprint(create_ibkr_blueprint(tmp_path))
    client = app.test_client()
    token = re.search(r'name="ibkr-token" content="([^"]+)"', client.get("/ibkr").text)[1]
    return client, {"X-IBKR-Token": token}


def test_proxy_requires_token_same_origin_and_fixed_routes(tmp_path):
    client, headers = client_for(tmp_path)
    for path, extra in [("orders/submit", {}), ("orders/submit", {**headers, "Origin": "https://evil.example"})]:
        assert client.post("/api/ibkr/desk/" + path, json={"confirm": "BUY"}, headers=extra).status_code == 403
    assert client.post("/api/ibkr/desk/cash", json={}, headers=headers).status_code == 404
    assert client.get("/api/ibkr/desk/orders/submit").status_code == 404
    assert client.get("/api/ibkr/desk/research/jobs/../../cash").status_code == 404
    assert client.post("/api/ibkr/desk/research/start", data="x" * 16001, headers=headers).status_code == 400


def test_proxy_preserves_server_job_and_draft(tmp_path):
    client, headers = client_for(tmp_path)
    response = Mock(status=202)
    response.read.return_value = b'{"job_id":"abc"}'
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    with patch("src.portfolio_dashboard.ibkr_monitor.urllib.request.urlopen", return_value=response) as urlopen:
        result = client.post(
            "/api/ibkr/desk/research/start", json={"symbol": "AAPL", "question": "Why the drop?"}, headers=headers
        )
        assert result.status_code == 202
        req = urlopen.call_args.args[0]
        assert req.full_url == "http://127.0.0.1:8766/research/start"
        assert json.loads(req.data)["symbol"] == "AAPL"


def test_live_flag_requires_both_explicit_settings(tmp_path, monkeypatch):
    config = tmp_path / "connection.json"
    monkeypatch.setenv("IBKR_CONNECTION_CONFIG", str(config))
    assert not execution_enabled()
    for settings in (
        {},
        {"execution_enabled": True},
        {"execution_enabled": True, "read_only": True},
        {"execution_enabled": "true", "read_only": False},
    ):
        config.write_text(json.dumps(settings))
        assert not execution_enabled()
    config.write_text(json.dumps({"execution_enabled": True, "read_only": False}))
    assert execution_enabled()


def test_focused_chat_preserves_scheduled_report(tmp_path):
    import sys
    from scripts.ibkr_research import main

    request = tmp_path / "request.json"
    request.write_text(json.dumps({"symbol": "AAPL", "question": "Why the drop?", "history": []}))
    latest = tmp_path / "latest.json"
    latest.write_text('{"report":"scheduled report"}')
    result = tmp_path / "answer.json"
    snapshot = {
        "rows": [{"symbol": "AAPL", "reference_usable": True, "price_time": 12345}],
        "captured_at": "2026-01-01T00:00:00Z",
        "cash_status": "cached",
    }
    argv = [
        "research",
        "--account-suffix",
        "1111",
        "--opencode",
        "opencode",
        "--state-dir",
        str(tmp_path),
        "--request-file",
        str(request),
        "--result-file",
        str(result),
    ]
    with (
        patch.object(sys, "argv", argv),
        patch("scripts.ibkr_research.market_open", return_value=False),
        patch("scripts.ibkr_research.research_snapshot", return_value=snapshot) as collect,
        patch("scripts.ibkr_research.collect_evidence", return_value={"symbols": ["AAPL"]}),
        patch(
            "scripts.ibkr_research.run_models", return_value={"model_status": "ready", "report": "stock answer"}
        ) as model,
    ):
        main()
    assert json.loads(latest.read_text())["report"] == "scheduled report"
    assert json.loads(result.read_text())["report"] == "stock answer"
    assert collect.call_args.args[-1] == "AAPL"
    assert "Why the drop?" in model.call_args.args[1]
    assert result.stat().st_mode & 0o777 == 0o600
