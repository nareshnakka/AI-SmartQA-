"""Export performance run reports — HTML, JSON, CSV."""

import csv
import io
import json
from html import escape


def export_performance_report(run_detail: dict, fmt: str) -> tuple[str | bytes, str, str]:
    fmt = fmt.lower()
    run = run_detail.get("run", {})
    run_id = run.get("id", "report")[:8]

    if fmt == "json":
        return json.dumps(run_detail, indent=2), "application/json", f"perf-run-{run_id}.json"

    if fmt == "csv":
        return _csv_export(run_detail), "text/csv", f"perf-run-{run_id}.csv"

    return _html_export(run_detail), "text/html", f"perf-run-{run_id}.html"


def _csv_export(detail: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Transaction", "Samples", "Avg ms", "Min ms", "Max ms", "P90 ms", "P95 ms", "P99 ms", "Error Rate", "Throughput RPS", "Status"])
    for t in detail.get("transactions", []):
        w.writerow([
            t.get("name"), t.get("samples"), t.get("avg_ms"), t.get("min_ms"), t.get("max_ms"),
            t.get("p90_ms"), t.get("p95_ms"), t.get("p99_ms"), t.get("error_rate"),
            t.get("throughput_rps"), t.get("status"),
        ])
    summary = detail.get("summary", {})
    w.writerow([])
    w.writerow(["Summary Metric", "Value"])
    for k, v in summary.items():
        w.writerow([k, v])
    return buf.getvalue()


def _html_export(detail: dict) -> str:
    run = detail.get("run", {})
    summary = detail.get("summary", {})
    transactions = detail.get("transactions", [])
    timeline = detail.get("timeline", [])
    percentiles = detail.get("percentiles", {})
    sla = detail.get("sla", {})

    txn_rows = "".join(
        f"""<tr>
          <td>{escape(str(t.get('name', '')))}</td>
          <td>{t.get('samples', 0)}</td>
          <td>{t.get('avg_ms', 0)}</td>
          <td>{t.get('p95_ms', 0)}</td>
          <td>{t.get('p99_ms', 0)}</td>
          <td>{round((t.get('error_rate', 0) or 0) * 100, 2)}%</td>
          <td>{t.get('throughput_rps', 0)}</td>
          <td class="{'pass' if t.get('status') == 'passed' else 'fail'}">{escape(str(t.get('status', '')))}</td>
        </tr>"""
        for t in transactions
    )

    max_avg = max((t.get("avg_ms", 0) for t in transactions), default=1) or 1
    bars = "".join(
        f"""<div class="bar-row">
          <span class="bar-label">{escape(str(t.get('name', ''))[:40])}</span>
          <div class="bar-track"><div class="bar-fill" style="width:{min(100, t.get('avg_ms', 0) / max_avg * 100):.0f}%"></div></div>
          <span class="bar-val">{t.get('avg_ms', 0)} ms</span>
        </div>"""
        for t in transactions[:15]
    )

    timeline_bars = "".join(
        f"""<div class="tl-point" style="height:{min(100, p.get('avg_ms', 0) / max(max_avg, 1) * 80 + 10):.0f}px" title="{escape(p.get('label', ''))}: {p.get('avg_ms')}ms"></div>"""
        for p in timeline
    )

    p95 = summary.get("http_req_duration_p95", percentiles.get("p95", 0))
    rps = summary.get("http_reqs_rate", 0)
    vus = summary.get("vus_max", 0)
    status_cls = "pass" if run.get("status") == "completed" else "fail"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Performance Report — {escape(run.get('asset_name', 'Run'))}</title>
<style>
  :root {{ --brand: #1e40af; --pass: #059669; --fail: #dc2626; --bg: #f8fafc; }}
  body {{ font-family: system-ui, sans-serif; margin: 0; background: var(--bg); color: #0f172a; }}
  header {{ background: linear-gradient(135deg, #1e3a8a, #3b82f6); color: white; padding: 2rem; }}
  header h1 {{ margin: 0 0 0.5rem; font-size: 1.5rem; }}
  .meta {{ opacity: 0.9; font-size: 0.875rem; }}
  main {{ max-width: 1200px; margin: -1rem auto 2rem; padding: 0 1rem; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }}
  .card {{ background: white; border-radius: 12px; padding: 1.25rem; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  .card label {{ font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: .05em; }}
  .card .val {{ font-size: 1.75rem; font-weight: 700; margin-top: 0.25rem; }}
  section {{ background: white; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  h2 {{ margin: 0 0 1rem; font-size: 1rem; color: #334155; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.8125rem; }}
  th, td {{ padding: 0.6rem 0.75rem; text-align: left; border-bottom: 1px solid #e2e8f0; }}
  th {{ background: #f1f5f9; font-weight: 600; }}
  .pass {{ color: var(--pass); font-weight: 600; }}
  .fail {{ color: var(--fail); font-weight: 600; }}
  .status-badge {{ display: inline-block; padding: 0.25rem 0.75rem; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }}
  .status-badge.{status_cls} {{ background: {'#d1fae5' if status_cls == 'pass' else '#fee2e2'}; color: {'#065f46' if status_cls == 'pass' else '#991b1b'}; }}
  .bar-row {{ display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem; font-size: 0.8125rem; }}
  .bar-label {{ width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .bar-track {{ flex: 1; height: 8px; background: #e2e8f0; border-radius: 4px; overflow: hidden; }}
  .bar-fill {{ height: 100%; background: linear-gradient(90deg, #3b82f6, #6366f1); border-radius: 4px; }}
  .bar-val {{ width: 70px; text-align: right; color: #64748b; }}
  .timeline {{ display: flex; align-items: flex-end; gap: 4px; height: 100px; padding-top: 1rem; }}
  .tl-point {{ flex: 1; background: linear-gradient(180deg, #6366f1, #3b82f6); border-radius: 4px 4px 0 0; min-height: 4px; }}
  .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }}
  @media (max-width: 768px) {{ .grid2 {{ grid-template-columns: 1fr; }} }}
  footer {{ text-align: center; padding: 2rem; color: #94a3b8; font-size: 0.75rem; }}
</style>
</head>
<body>
<header>
  <h1>Performance Test Report — {escape(run.get('asset_name', 'Load Test'))}</h1>
  <p class="meta">
    Run ID: {escape(str(run.get('id', '')))} ·
    Profile: {escape(str(run.get('workload_profile', '')))} ·
    Agent: {escape(str(run.get('agent', 'localhost')))} ·
    <span class="status-badge {status_cls}">{escape(str(run.get('status', '')).upper())}</span>
  </p>
</header>
<main>
  <div class="cards">
    <div class="card"><label>P95 Response</label><div class="val">{p95} ms</div></div>
    <div class="card"><label>Throughput</label><div class="val">{rps} req/s</div></div>
    <div class="card"><label>Max VUs</label><div class="val">{vus}</div></div>
    <div class="card"><label>Transactions</label><div class="val">{len(transactions)}</div></div>
    <div class="card"><label>SLA</label><div class="val {'pass' if sla.get('passed') else 'fail'}">{'PASS' if sla.get('passed') else 'FAIL'}</div></div>
  </div>

  <div class="grid2">
    <section>
      <h2>Response Time by Transaction</h2>
      {bars or '<p>No transaction data</p>'}
    </section>
    <section>
      <h2>Load Timeline</h2>
      <div class="timeline">{timeline_bars or '<p>No timeline data</p>'}</div>
    </section>
  </div>

  <section>
    <h2>Transaction Metrics (LoadRunner / JMeter style)</h2>
    <table>
      <thead><tr>
        <th>Transaction</th><th>Samples</th><th>Avg (ms)</th><th>P95 (ms)</th><th>P99 (ms)</th>
        <th>Error %</th><th>Throughput</th><th>Status</th>
      </tr></thead>
      <tbody>{txn_rows or '<tr><td colspan="8">No transactions recorded</td></tr>'}</tbody>
    </table>
  </section>

  <section>
    <h2>Percentile Distribution</h2>
    <table>
      <tr><th>P50 (avg)</th><td>{percentiles.get('p50', summary.get('http_req_duration_avg', 0))} ms</td></tr>
      <tr><th>P90</th><td>{percentiles.get('p90', 0)} ms</td></tr>
      <tr><th>P95</th><td>{percentiles.get('p95', p95)} ms</td></tr>
      <tr><th>P99</th><td>{percentiles.get('p99', 0)} ms</td></tr>
    </table>
  </section>
</main>
<footer>Generated by QEOS Performance Engineering · Browser replay-driven load scripts</footer>
</body>
</html>"""
