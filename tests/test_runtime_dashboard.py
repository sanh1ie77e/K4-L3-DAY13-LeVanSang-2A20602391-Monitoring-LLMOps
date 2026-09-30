from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.dashboard import build_dashboard_snapshot, render_dashboard


def test_runtime_dashboard_uses_log_data(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    log_path = tmp_path / "logs.jsonl"
    records = [
        {"ts": now.isoformat(), "event": "request_received"},
        {
            "ts": now.isoformat(),
            "event": "response_sent",
            "latency_ms": 200,
            "ttft_ms": 50,
            "cost_usd": 0.01,
            "tokens_in": 20,
            "tokens_out": 80,
            "quality_score": 0.9,
            "tool_success": True,
        },
    ]
    log_path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

    snapshot = build_dashboard_snapshot(log_path, now=now)

    assert snapshot["traffic"] == 1
    assert snapshot["latency_p95"] == 200
    assert snapshot["retrieval_success_pct"] == 100
    assert snapshot["tokens_in"] == 20
    assert snapshot["tokens_out"] == 80

    html = render_dashboard(log_path)
    for panel_id in ("latency", "traffic", "errors", "cost", "tokens", "quality"):
        assert f'id="{panel_id}"' in html
