from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from statistics import mean
from typing import Any, Callable

from .logging_config import LOG_PATH


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    items = sorted(values)
    index = max(0, min(len(items) - 1, round((percentile / 100) * len(items) + 0.5) - 1))
    return float(items[index])


def _timestamp(record: dict[str, Any]) -> datetime | None:
    value = record.get("ts")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _load_recent_records(path: Path, *, now: datetime, minutes: int = 60) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    cutoff = now - timedelta(minutes=minutes)
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = _timestamp(record)
        if ts is not None and cutoff <= ts <= now:
            records.append(record)
    return records


def _minute_series(
    records: list[dict[str, Any]],
    minutes: list[datetime],
    selector: Callable[[list[dict[str, Any]]], float],
) -> list[float]:
    buckets: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        ts = _timestamp(record)
        if ts is not None:
            buckets[ts.replace(second=0, microsecond=0)].append(record)
    return [selector(buckets[minute]) for minute in minutes]


def build_dashboard_snapshot(
    path: Path = LOG_PATH, *, now: datetime | None = None
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    minute_end = now.replace(second=0, microsecond=0)
    minutes = [minute_end - timedelta(minutes=index) for index in range(59, -1, -1)]
    records = _load_recent_records(path, now=now)
    requests = [record for record in records if record.get("event") == "request_received"]
    responses = [record for record in records if record.get("event") == "response_sent"]
    failures = [record for record in records if record.get("event") == "request_failed"]
    tool_events = [record for record in records if isinstance(record.get("tool_success"), bool)]

    latencies = [float(record["latency_ms"]) for record in responses if isinstance(record.get("latency_ms"), (int, float))]
    ttfts = [float(record["ttft_ms"]) for record in responses if isinstance(record.get("ttft_ms"), (int, float))]
    costs = [float(record["cost_usd"]) for record in responses if isinstance(record.get("cost_usd"), (int, float))]
    tokens_in = [int(record["tokens_in"]) for record in responses if isinstance(record.get("tokens_in"), int)]
    tokens_out = [int(record["tokens_out"]) for record in responses if isinstance(record.get("tokens_out"), int)]
    quality = [float(record["quality_score"]) for record in responses if isinstance(record.get("quality_score"), (int, float))]

    request_series = _minute_series(requests, minutes, lambda rows: float(len(rows)))
    latency_series = _minute_series(
        responses,
        minutes,
        lambda rows: _percentile(
            [float(row["latency_ms"]) for row in rows if isinstance(row.get("latency_ms"), (int, float))],
            95,
        ),
    )
    error_series = _minute_series(
        records,
        minutes,
        lambda rows: (
            100.0 * sum(row.get("event") == "request_failed" for row in rows)
            / max(1, sum(row.get("event") == "request_received" for row in rows))
        ),
    )
    cost_series = _minute_series(
        responses,
        minutes,
        lambda rows: sum(float(row.get("cost_usd", 0.0)) for row in rows),
    )
    token_series = _minute_series(
        responses,
        minutes,
        lambda rows: float(sum(int(row.get("tokens_in", 0)) + int(row.get("tokens_out", 0)) for row in rows)),
    )
    quality_series = _minute_series(
        responses,
        minutes,
        lambda rows: mean(
            [float(row["quality_score"]) for row in rows if isinstance(row.get("quality_score"), (int, float))]
        )
        if rows
        else 0.0,
    )

    return {
        "generated_at": now,
        "latency_p50": _percentile(latencies, 50),
        "latency_p95": _percentile(latencies, 95),
        "latency_p99": _percentile(latencies, 99),
        "ttft_p95": _percentile(ttfts, 95),
        "traffic": len(requests),
        "rate_per_minute": len(requests) / 60,
        "error_rate_pct": 100.0 * len(failures) / max(1, len(requests)),
        "retrieval_success_pct": 100.0
        * sum(record["tool_success"] is True for record in tool_events)
        / max(1, len(tool_events)),
        "total_cost": sum(costs),
        "tokens_in": sum(tokens_in),
        "tokens_out": sum(tokens_out),
        "quality_avg": mean(quality) if quality else 0.0,
        "series": {
            "latency": latency_series,
            "traffic": request_series,
            "errors": error_series,
            "cost": cost_series,
            "tokens": token_series,
            "quality": quality_series,
        },
    }


def _sparkline(values: list[float], *, threshold: float, lower_is_better: bool) -> str:
    width, height, padding = 360, 92, 10
    ceiling = max([threshold, *values, 1.0])
    points = []
    for index, value in enumerate(values):
        x = padding + index * (width - 2 * padding) / max(1, len(values) - 1)
        y = height - padding - (value / ceiling) * (height - 2 * padding)
        points.append(f"{x:.1f},{y:.1f}")
    threshold_y = height - padding - (threshold / ceiling) * (height - 2 * padding)
    direction = "≤" if lower_is_better else "≥"
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="60 minute trend">'
        f'<line class="threshold" x1="{padding}" y1="{threshold_y:.1f}" x2="{width-padding}" y2="{threshold_y:.1f}" />'
        f'<polyline class="trend" points="{" ".join(points)}" />'
        f'<text x="{width-padding}" y="{max(12, threshold_y-4):.1f}" text-anchor="end">SLO {direction} {threshold:g}</text>'
        "</svg>"
    )


def _panel(panel_id: str, title: str, values: str, detail: str, chart: str) -> str:
    return (
        f'<section class="panel" id="{escape(panel_id)}">'
        f'<h2>{escape(title)}</h2><div class="values">{values}</div>'
        f'<p>{escape(detail)}</p>{chart}</section>'
    )


def render_dashboard(path: Path = LOG_PATH) -> str:
    snapshot = build_dashboard_snapshot(path)
    series = snapshot["series"]
    panels = "".join(
        [
            _panel(
                "latency",
                "Latency percentiles and TTFT",
                f'<strong>{snapshot["latency_p95"]:.0f} ms</strong><span>P95</span>',
                f'P50 {snapshot["latency_p50"]:.0f} ms · P99 {snapshot["latency_p99"]:.0f} ms · TTFT P95 {snapshot["ttft_p95"]:.0f} ms',
                _sparkline(series["latency"], threshold=3000, lower_is_better=True),
            ),
            _panel(
                "traffic",
                "Request traffic",
                f'<strong>{snapshot["traffic"]}</strong><span>requests / 60 min</span>',
                f'Average {snapshot["rate_per_minute"]:.2f} requests/min · threshold ≥ 1 request/min',
                _sparkline(series["traffic"], threshold=1, lower_is_better=False),
            ),
            _panel(
                "errors",
                "Error rate and retrieval success",
                f'<strong>{snapshot["error_rate_pct"]:.1f}%</strong><span>errors</span>',
                f'Retrieval success {snapshot["retrieval_success_pct"]:.1f}% · error threshold ≤ 2% · retrieval target ≥ 90%',
                _sparkline(series["errors"], threshold=2, lower_is_better=True),
            ),
            _panel(
                "cost",
                "Cost over time",
                f'<strong>${snapshot["total_cost"]:.4f}</strong><span>USD / 60 min</span>',
                'Budget threshold ≤ $2.50 per 60-minute view',
                _sparkline(series["cost"], threshold=2.5, lower_is_better=True),
            ),
            _panel(
                "tokens",
                "Input and output tokens",
                f'<strong>{snapshot["tokens_in"] + snapshot["tokens_out"]:,}</strong><span>total tokens</span>',
                f'Input {snapshot["tokens_in"]:,} · Output {snapshot["tokens_out"]:,} · threshold ≤ 50,000',
                _sparkline(series["tokens"], threshold=50000, lower_is_better=True),
            ),
            _panel(
                "quality",
                "Quality proxy",
                f'<strong>{snapshot["quality_avg"]:.2f}</strong><span>score 0–1</span>',
                'Quality target ≥ 0.75',
                _sparkline(series["quality"], threshold=0.75, lower_is_better=False),
            ),
        ]
    )
    generated_at = snapshot["generated_at"].astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="30">
  <title>K4-L3B Monitoring Dashboard</title>
  <style>
    :root {{ color-scheme: light dark; --bg:#0b1020; --card:#151c2f; --text:#f3f6ff; --muted:#aab4ce; --line:#60a5fa; --threshold:#f59e0b; --border:#29334d; }}
    * {{ box-sizing:border-box; }} body {{ margin:0; font-family:Inter,Segoe UI,sans-serif; background:var(--bg); color:var(--text); }}
    main {{ max-width:1200px; margin:auto; padding:28px; }} header {{ display:flex; justify-content:space-between; gap:20px; align-items:end; margin-bottom:22px; }}
    h1 {{ margin:0 0 6px; font-size:28px; }} h2 {{ margin:0; font-size:17px; font-weight:600; }} p {{ color:var(--muted); margin:8px 0 12px; min-height:38px; }}
    .meta {{ color:var(--muted); text-align:right; }} .grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; }}
    .panel {{ background:var(--card); border:1px solid var(--border); border-radius:14px; padding:18px; min-width:0; }}
    .values {{ display:flex; align-items:baseline; gap:9px; margin-top:18px; }} .values strong {{ font-size:30px; }} .values span {{ color:var(--muted); }}
    svg {{ width:100%; height:auto; overflow:visible; }} .trend {{ fill:none; stroke:var(--line); stroke-width:3; }} .threshold {{ stroke:var(--threshold); stroke-width:1.5; stroke-dasharray:5 4; }}
    svg text {{ fill:var(--threshold); font-size:11px; }} footer {{ color:var(--muted); margin-top:18px; }}
    @media (max-width:900px) {{ .grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}
    @media (max-width:600px) {{ main {{ padding:16px; }} header {{ display:block; }} .meta {{ text-align:left; margin-top:8px; }} .grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body><main>
  <header><div><h1>K4-L3B Monitoring &amp; LLMOps</h1><div>Source: <code>data/logs.jsonl</code></div></div><div class="meta">Last 60 minutes<br>Auto-refresh: 30 seconds<br>{escape(generated_at)}</div></header>
  <div class="grid">{panels}</div>
  <footer>Threshold lines follow <code>config/dashboard.yaml</code>. Times in logs are UTC; display time uses the local browser/server timezone.</footer>
</main></body></html>"""
