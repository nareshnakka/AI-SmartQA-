"use client";

import { Download, CheckCircle2, XCircle, Activity } from "lucide-react";
import { Badge, MetricCard } from "@/components/ui";
import { performanceExportUrl } from "@/lib/api";

interface Transaction {
  name: string; samples?: number; avg_ms?: number; min_ms?: number; max_ms?: number;
  p90_ms?: number; p95_ms?: number; p99_ms?: number; error_rate?: number;
  throughput_rps?: number; status?: string;
}

interface RunDetail {
  run: {
    id: string; asset_name: string; workload_profile: string; status: string;
    agent: string; created_at: string; completed_at?: string;
    summary?: { progress?: { percent: number; phase: string } };
  };
  summary: Record<string, number>;
  transactions: Transaction[];
  timeline: { bucket: number; label: string; avg_ms: number; throughput: number; errors: number }[];
  percentiles: Record<string, number>;
  sla: { passed?: boolean; thresholds?: { name: string; passed: boolean }[] };
  errors: { type: string; rate?: number; count?: number }[];
}

function BarChart({ transactions }: { transactions: Transaction[] }) {
  const max = Math.max(...transactions.map((t) => t.avg_ms || 0), 1);
  return (
    <div className="space-y-2">
      {transactions.slice(0, 12).map((t) => (
        <div key={t.name} className="flex items-center gap-2 text-xs">
          <span className="w-36 truncate text-[var(--text-secondary)]" title={t.name}>{t.name}</span>
          <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
            <div className="h-full bg-gradient-to-r from-brand-600 to-indigo-500 rounded-full transition-all"
              style={{ width: `${Math.min(100, ((t.avg_ms || 0) / max) * 100)}%` }} />
          </div>
          <span className="w-16 text-right font-mono text-[var(--text-tertiary)]">{t.avg_ms ?? 0} ms</span>
        </div>
      ))}
    </div>
  );
}

function TimelineChart({ timeline }: { timeline: RunDetail["timeline"] }) {
  const max = Math.max(...timeline.map((p) => p.avg_ms), 1);
  return (
    <div className="flex items-end gap-1 h-24 pt-2">
      {timeline.map((p) => (
        <div key={p.bucket} className="flex-1 flex flex-col items-center gap-1" title={`${p.label}: ${p.avg_ms}ms`}>
          <div className="w-full bg-gradient-to-t from-brand-700 to-brand-400 rounded-t"
            style={{ height: `${Math.max(8, (p.avg_ms / max) * 80)}px` }} />
          <span className="text-[9px] text-[var(--text-tertiary)]">{p.bucket}</span>
        </div>
      ))}
    </div>
  );
}

function PieChart({ passed, failed }: { passed: number; failed: number }) {
  const total = passed + failed || 1;
  const pPct = (passed / total) * 100;
  const grad = `conic-gradient(#10b981 0 ${pPct}%, #ef4444 ${pPct}% 100%)`;
  return (
    <div className="flex items-center gap-4">
      <div className="w-24 h-24 rounded-full shrink-0" style={{ background: grad }} />
      <div className="text-xs space-y-1">
        <p><span className="inline-block w-2 h-2 rounded-full bg-emerald-500 mr-1" />Passed SLA {passed}</p>
        <p><span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-1" />Failed {failed}</p>
      </div>
    </div>
  );
}

export function PerfRunDashboard({ projectId, detail }: { projectId: string; detail: RunDetail }) {
  const { run, summary, transactions, timeline, percentiles, sla, errors } = detail;
  const isRunning = run.status === "running";
  const txnPassed = transactions.filter((t) => t.status === "passed").length;
  const txnFailed = transactions.filter((t) => t.status === "failed").length;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            {run.status === "completed" ? <CheckCircle2 className="w-5 h-5 text-emerald-600" /> :
              run.status === "failed" ? <XCircle className="w-5 h-5 text-red-500" /> :
              <Activity className="w-5 h-5 text-brand-600 animate-pulse" />}
            {run.asset_name}
          </h2>
          <p className="text-xs text-[var(--text-tertiary)] mt-1">
            {run.workload_profile} · {run.agent} · {new Date(run.created_at).toLocaleString()}
            {run.completed_at && ` → ${new Date(run.completed_at).toLocaleString()}`}
          </p>
        </div>
        <div className="flex gap-2">
          <Badge variant={run.status === "completed" ? "success" : run.status === "failed" ? "error" : "neutral"}>
            {run.status}
          </Badge>
          {(["html", "json", "csv"] as const).map((fmt) => (
            <a key={fmt} href={performanceExportUrl(projectId, run.id, fmt)} className="ds-btn-secondary text-xs py-1">
              <Download className="w-3 h-3" /> {fmt.toUpperCase()}
            </a>
          ))}
        </div>
      </div>

      {isRunning && run.summary?.progress && (
        <div className="ds-card border-brand-200 bg-brand-50 px-4 py-3">
          <div className="flex justify-between text-xs mb-2">
            <span>{run.summary.progress.phase}</span>
            <span>{run.summary.progress.percent}%</span>
          </div>
          <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
            <div className="h-full bg-brand-700 transition-all" style={{ width: `${run.summary.progress.percent}%` }} />
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <MetricCard label="P95 Response" value={`${summary.http_req_duration_p95 ?? percentiles.p95 ?? "—"} ms`} />
        <MetricCard label="Throughput" value={`${summary.http_reqs_rate ?? 0} req/s`} changeType="positive" />
        <MetricCard label="Max VUs" value={summary.vus_max ?? 0} />
        <MetricCard label="Total Requests" value={summary.total_requests ?? summary.iterations ?? 0} />
        <MetricCard label="SLA" value={sla.passed ? "PASS" : "FAIL"} changeType={sla.passed ? "positive" : "negative"} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="ds-card">
          <div className="ds-card-header"><h3 className="text-sm font-semibold">Transaction Pass / Fail</h3></div>
          <div className="ds-card-body pt-0"><PieChart passed={txnPassed} failed={txnFailed} /></div>
        </div>
        <div className="ds-card lg:col-span-2">
          <div className="ds-card-header"><h3 className="text-sm font-semibold">Response Time by Transaction</h3></div>
          <div className="ds-card-body pt-0">
            {transactions.length > 0 ? <BarChart transactions={transactions} /> : <p className="text-xs text-[var(--text-tertiary)]">No transaction data yet</p>}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="ds-card">
          <div className="ds-card-header"><h3 className="text-sm font-semibold">Load Timeline</h3></div>
          <div className="ds-card-body pt-0">
            {timeline.length > 0 ? <TimelineChart timeline={timeline} /> : <p className="text-xs text-[var(--text-tertiary)]">Timeline available after run completes</p>}
          </div>
        </div>
        <div className="ds-card">
          <div className="ds-card-header"><h3 className="text-sm font-semibold">Percentile Distribution</h3></div>
          <div className="ds-card-body pt-0">
            <table className="w-full text-xs">
              <tbody>
                {[["P50 (avg)", percentiles.p50 ?? summary.http_req_duration_avg], ["P90", percentiles.p90], ["P95", percentiles.p95 ?? summary.http_req_duration_p95], ["P99", percentiles.p99]].map(([k, v]) => (
                  <tr key={String(k)} className="border-t border-[var(--border-default)]/50">
                    <td className="py-2 font-medium">{k}</td>
                    <td className="py-2 text-right font-mono">{v ?? "—"} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="ds-card">
        <div className="ds-card-header"><h3 className="text-sm font-semibold">Transaction Metrics</h3></div>
        <div className="overflow-x-auto">
          <table className="ds-table text-xs">
            <thead>
              <tr>
                <th>Transaction</th><th>Samples</th><th>Avg</th><th>Min</th><th>Max</th>
                <th>P90</th><th>P95</th><th>P99</th><th>Error %</th><th>RPS</th><th>Status</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((t) => (
                <tr key={t.name}>
                  <td className="font-medium max-w-[200px] truncate" title={t.name}>{t.name}</td>
                  <td>{t.samples ?? "—"}</td>
                  <td className="font-mono">{t.avg_ms ?? "—"}</td>
                  <td className="font-mono">{t.min_ms ?? "—"}</td>
                  <td className="font-mono">{t.max_ms ?? "—"}</td>
                  <td className="font-mono">{t.p90_ms ?? "—"}</td>
                  <td className="font-mono">{t.p95_ms ?? "—"}</td>
                  <td className="font-mono">{t.p99_ms ?? "—"}</td>
                  <td>{((t.error_rate ?? 0) * 100).toFixed(2)}%</td>
                  <td>{t.throughput_rps ?? "—"}</td>
                  <td><Badge variant={t.status === "passed" ? "success" : "error"}>{t.status ?? "—"}</Badge></td>
                </tr>
              ))}
              {transactions.length === 0 && (
                <tr><td colSpan={11} className="text-center py-8 text-[var(--text-tertiary)]">No transactions — run a load test to see metrics</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {errors.length > 0 && (
        <div className="ds-card border-red-200">
          <div className="ds-card-header"><h3 className="text-sm font-semibold text-red-700">Errors</h3></div>
          <ul className="ds-card-body pt-0 text-xs space-y-1">
            {errors.map((e, i) => <li key={i}>{e.type}: rate {e.rate ?? 0} · count {e.count ?? 0}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

export type { RunDetail };
