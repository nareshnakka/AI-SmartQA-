"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  Zap, Play, Loader2, Gauge, Save, GitCompare, Upload, Server,
  Database, Link2, Activity, Layers, LayoutDashboard, History, Download,
} from "lucide-react";
import { AppShell } from "@/components/shell/AppShell";
import { PageHeader, Badge, Tabs, MetricCard } from "@/components/ui";
import { CodeEditor, FileTree } from "@/components/studio/CodeEditor";
import { PerfRunDashboard, RunDetail } from "@/components/performance/PerfRunDashboard";
import { useActiveProject } from "@/context/ProjectContext";
import { apiFetch, performanceExportUrl } from "@/lib/api";

interface PerfAsset {
  id: string; name: string; tool: string; version?: number; status?: string;
  workload_model: Record<string, unknown>;
  scripts: { path: string; content: string; type?: string }[];
  scenarios: { id: string; name: string; weight: number; steps?: { action: string; url: string; name: string }[]; source?: string }[];
  correlation_rules: { name: string; extract_from: string; use_in: string }[];
  data_pools: { id: string; name: string; filename: string; content: string; columns?: string[] }[];
}
interface WorkloadProfile { id: string; name: string; description: string; virtual_users: number; target_rps?: number }
interface LoadAgent { id: string; name: string; host: string; status: string; max_vus: number; agent_type: string }
interface PerfRun {
  id: string; status: string; workload_profile: string;
  metrics: Record<string, number>; summary: Record<string, unknown>;
  created_at: string; completed_at?: string;
}
interface DiscoverySession { id: string; name: string; base_url: string; status: string }
interface PerfOverview {
  totals: { total_runs: number; passed: number; failed: number; running: number; pass_rate: number; avg_p95_ms: number; performance_assets: number };
  pie_chart: { passed: number; failed: number; running: number };
  timeline: { id: string; name: string; status: string; p95_ms: number; workload_profile: string; started_at: string; agent: string }[];
}

function OverviewPie({ passed, failed, running }: { passed: number; failed: number; running: number }) {
  const total = passed + failed + running || 1;
  const pPct = (passed / total) * 100;
  const fPct = (failed / total) * 100;
  const grad = `conic-gradient(#10b981 0 ${pPct}%, #ef4444 ${pPct}% ${pPct + fPct}%, #94a3b8 ${pPct + fPct}% 100%)`;
  return (
    <div className="flex items-center gap-6">
      <div className="w-28 h-28 rounded-full shrink-0" style={{ background: grad }} />
      <div className="space-y-1 text-xs">
        <p><span className="inline-block w-2 h-2 rounded-full bg-emerald-500 mr-1" />Passed {passed}</p>
        <p><span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-1" />Failed {failed}</p>
        <p><span className="inline-block w-2 h-2 rounded-full bg-gray-400 mr-1" />Running {running}</p>
      </div>
    </div>
  );
}

export default function PerformancePage() {
  const { projectId } = useActiveProject();
  const [mainTab, setMainTab] = useState<"studio" | "dashboard" | "history">("studio");
  const [tool, setTool] = useState("k6");
  const [profile, setProfile] = useState("load");
  const [baseUrl, setBaseUrl] = useState("https://opensource-demo.orangehrmlive.com");
  const [discoverySessionId, setDiscoverySessionId] = useState("");
  const [discoverySessions, setDiscoverySessions] = useState<DiscoverySession[]>([]);
  const [profiles, setProfiles] = useState<WorkloadProfile[]>([]);
  const [assets, setAssets] = useState<PerfAsset[]>([]);
  const [active, setActive] = useState<PerfAsset | null>(null);
  const [agents, setAgents] = useState<LoadAgent[]>([]);
  const [runs, setRuns] = useState<PerfRun[]>([]);
  const [overview, setOverview] = useState<PerfOverview | null>(null);
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [sideTab, setSideTab] = useState("scripts");
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [versions, setVersions] = useState<PerfAsset[]>([]);
  const [message, setMessage] = useState("");
  const [harJson, setHarJson] = useState("");
  const [throughputRps, setThroughputRps] = useState("200");
  const [p95Target, setP95Target] = useState("500");
  const prevProjectRef = useRef(projectId);

  useEffect(() => {
    if (prevProjectRef.current === projectId) return;
    prevProjectRef.current = projectId;
    setActive(null);
    setRunDetail(null);
    setSelectedRunId(null);
    setAssets([]);
  }, [projectId]);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    apiFetch<{ profiles: WorkloadProfile[] }>("/api/v1/projects/x/performance/workload-profiles")
      .then((d) => setProfiles(d.profiles)).catch(() => {});
  }, []);

  const loadData = useCallback(async () => {
    if (!projectId) return;
    const [list, agentList, runList, dash, sessions] = await Promise.allSettled([
      apiFetch<PerfAsset[]>(`/api/v1/projects/${projectId}/performance/assets`),
      apiFetch<LoadAgent[]>(`/api/v1/projects/${projectId}/performance/agents`),
      apiFetch<PerfRun[]>(`/api/v1/projects/${projectId}/performance/runs`),
      apiFetch<PerfOverview>(`/api/v1/projects/${projectId}/performance/dashboard`),
      apiFetch<DiscoverySession[]>(`/api/v1/projects/${projectId}/discovery/sessions`),
    ]);
    if (list.status === "fulfilled") { setAssets(list.value); if (list.value[0] && !active) selectAsset(list.value[0]); }
    if (agentList.status === "fulfilled") setAgents(agentList.value);
    if (runList.status === "fulfilled") setRuns(runList.value);
    if (dash.status === "fulfilled") setOverview(dash.value);
    if (sessions.status === "fulfilled") setDiscoverySessions(sessions.value.filter((s) => s.status === "completed"));
  }, [projectId, active]);

  useEffect(() => { loadData().catch(() => {}); }, [loadData]);

  const selectAsset = (asset: PerfAsset) => {
    setActive(asset);
    const main = asset.scripts.find((s) => s.path.endsWith(".js") || s.type === "k6") || asset.scripts[0];
    if (main) { setActiveFile(main.path); setFileContent(main.content); }
    setVersions([]);
  };

  const openRun = async (runId: string) => {
    if (!projectId) return;
    setSelectedRunId(runId);
    setMainTab("history");
    const detail = await apiFetch<RunDetail>(`/api/v1/projects/${projectId}/performance/runs/${runId}/dashboard`);
    setRunDetail(detail);
  };

  const pollRun = useCallback((runId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const run = await apiFetch<PerfRun>(`/api/v1/projects/${projectId}/performance/runs/${runId}`);
        setRuns((prev) => [run, ...prev.filter((r) => r.id !== runId)]);
        if (run.status !== "running") {
          clearInterval(pollRef.current!);
          pollRef.current = null;
          setExecuting(false);
          await openRun(runId);
          loadData();
        } else if (selectedRunId === runId) {
          const detail = await apiFetch<RunDetail>(`/api/v1/projects/${projectId}/performance/runs/${runId}/dashboard`);
          setRunDetail(detail);
        }
      } catch { setExecuting(false); }
    }, 2000);
  }, [projectId, loadData, selectedRunId]);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const generate = async () => {
    if (!projectId) return;
    setGenerating(true);
    setMessage("");
    try {
      const body: Record<string, unknown> = {
        tool, workload_profile: profile, base_url: baseUrl,
        throughput_config: { target_rps: parseInt(throughputRps) || 200, p95_ms: parseInt(p95Target) || 500, error_rate: 0.01 },
      };
      if (harJson.trim()) {
        try { body.har_content = JSON.parse(harJson); } catch { setMessage("Invalid HAR JSON"); return; }
      }
      if (discoverySessionId) body.discovery_session_id = discoverySessionId;
      const asset = await apiFetch<PerfAsset>(`/api/v1/projects/${projectId}/performance/generate`, {
        method: "POST", body: JSON.stringify(body),
      });
      setAssets((p) => [asset, ...p]);
      selectAsset(asset);
      const src = asset.scenarios?.[0]?.source ?? "browser replay";
      setMessage(`Generated ${asset.tool.toUpperCase()} from ${src} — ${asset.scenarios?.length ?? 0} scenarios with real URLs`);
    } catch (e) { setMessage(String(e)); }
    finally { setGenerating(false); }
  };

  const execute = async () => {
    if (!active || !projectId) return;
    setExecuting(true);
    try {
      const run = await apiFetch<PerfRun>(
        `/api/v1/projects/${projectId}/performance/assets/${active.id}/execute`,
        { method: "POST", body: JSON.stringify({ workload_profile: "smoke", background: true }) }
      );
      setRuns((r) => [run, ...r]);
      setSelectedRunId(run.id);
      setMainTab("history");
      if (run.status === "running") {
        pollRun(run.id);
        setMessage("Load test running on localhost agent…");
      } else {
        await openRun(run.id);
        setMessage(`Run ${run.status}`);
        setExecuting(false);
      }
    } catch (e) { setMessage(String(e)); setExecuting(false); }
  };

  const saveFile = async () => {
    if (!active || !activeFile || !projectId) return;
    setSaving(true);
    try {
      const updated = await apiFetch<PerfAsset>(
        `/api/v1/projects/${projectId}/performance/assets/${active.id}/files`,
        { method: "PUT", body: JSON.stringify({ path: activeFile, content: fileContent, save_version: true }) }
      );
      setActive(updated);
      setAssets((p) => [updated, ...p.filter((a) => a.id !== updated.id)]);
      setMessage(`Saved v${updated.version}`);
    } finally { setSaving(false); }
  };

  const applyWorkload = async (p: string) => {
    if (!active || !projectId) return;
    const updated = await apiFetch<PerfAsset>(
      `/api/v1/projects/${projectId}/performance/assets/${active.id}/workload`,
      { method: "PUT", body: JSON.stringify({ profile: p, throughput_config: { target_rps: parseInt(throughputRps), p95_ms: parseInt(p95Target), error_rate: 0.01 } }) }
    );
    setActive(updated);
    setProfile(p);
  };

  const applyHarCorrelation = async () => {
    if (!active || !projectId || !harJson.trim()) return;
    const content = JSON.parse(harJson);
    const updated = await apiFetch<PerfAsset>(
      `/api/v1/projects/${projectId}/performance/assets/${active.id}/correlation`,
      { method: "POST", body: JSON.stringify({ source_type: "har", content }) }
    );
    setActive(updated);
    setMessage(`Applied ${updated.correlation_rules.length} correlation rules`);
  };

  const localhostAgent = agents.find((a) => a.agent_type === "localhost" || a.name.includes("Localhost")) ?? agents[0];

  return (
    <AppShell title="Performance">
      <PageHeader
        title="Performance Engineering"
        subtitle="Scripts from browser replay · localhost agent · live metrics dashboard"
        breadcrumbs={[{ label: "Quality Engineering" }, { label: "Performance" }]}
        actions={
          localhostAgent ? (
            <Badge variant={localhostAgent.status === "online" ? "success" : "warning"}>
              <Server className="w-3 h-3" /> {localhostAgent.name}
            </Badge>
          ) : null
        }
      />

      <div className="flex gap-2 mb-4 border-b border-[var(--border-default)]">
        {(["studio", "dashboard", "history"] as const).map((t) => (
          <button key={t} onClick={() => setMainTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${mainTab === t ? "border-brand-700 text-brand-700" : "border-transparent text-[var(--text-tertiary)]"}`}>
            {t === "studio" && <><Zap className="w-3.5 h-3.5 inline mr-1" />Studio</>}
            {t === "dashboard" && <><LayoutDashboard className="w-3.5 h-3.5 inline mr-1" />Dashboard</>}
            {t === "history" && <><History className="w-3.5 h-3.5 inline mr-1" />Run History</>}
          </button>
        ))}
      </div>

      <div className="ds-card mb-4 px-4 py-3 flex flex-wrap items-end gap-3">
        {mainTab === "studio" && (
          <>
            <div>
              <label className="block text-xs font-medium mb-1">Tool</label>
              <select className="ds-input py-1.5 text-sm w-28" value={tool} onChange={(e) => setTool(e.target.value)}>
                <option value="k6">k6</option><option value="jmeter">JMeter</option>
                <option value="gatling">Gatling</option><option value="locust">Locust</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium mb-1">Browser Replay</label>
              <select className="ds-input py-1.5 text-sm w-48" value={discoverySessionId} onChange={(e) => {
                setDiscoverySessionId(e.target.value);
                const s = discoverySessions.find((x) => x.id === e.target.value);
                if (s) setBaseUrl(s.base_url);
              }}>
                <option value="">From test cases / HAR</option>
                {discoverySessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium mb-1">Base URL</label>
              <input className="ds-input py-1.5 text-sm w-56 font-mono" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
            </div>
            <button onClick={generate} disabled={generating || !projectId} className="ds-btn-primary">
              {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
              Generate from Replay
            </button>
            {active && (
              <button onClick={execute} disabled={executing} className="ds-btn-secondary">
                {executing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                Run on Localhost Agent
              </button>
            )}
          </>
        )}
      </div>

      {mainTab === "dashboard" && overview && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <MetricCard label="Total Runs" value={overview.totals.total_runs} />
            <MetricCard label="Pass Rate" value={`${overview.totals.pass_rate}%`} changeType="positive" />
            <MetricCard label="Avg P95" value={`${overview.totals.avg_p95_ms} ms`} />
            <MetricCard label="Scripts" value={overview.totals.performance_assets} />
            <MetricCard label="Running" value={overview.totals.running} />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="ds-card">
              <div className="ds-card-header"><h2 className="text-sm font-semibold">Run Results</h2></div>
              <div className="ds-card-body pt-0"><OverviewPie {...overview.pie_chart} /></div>
            </div>
            <div className="ds-card">
              <div className="ds-card-header"><h2 className="text-sm font-semibold">Recent Runs</h2></div>
              <ul className="ds-card-body pt-0 space-y-1 text-xs max-h-64 overflow-auto">
                {overview.timeline.map((t) => (
                  <li key={t.id}>
                    <button onClick={() => openRun(t.id)} className="w-full text-left p-2 rounded hover:bg-brand-50 flex justify-between">
                      <span className="truncate">{t.name}</span>
                      <span className="shrink-0 ml-2"><Badge variant={t.status === "completed" ? "success" : t.status === "failed" ? "error" : "neutral"}>{t.status}</Badge></span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {mainTab === "history" && (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          <div className="ds-card">
            <div className="ds-card-header"><h2 className="text-sm font-semibold">Run History</h2></div>
            <ul className="ds-card-body space-y-1 pt-0 max-h-[600px] overflow-auto text-xs">
              {runs.map((r) => (
                <button key={r.id} onClick={() => openRun(r.id)}
                  className={`w-full text-left p-2 rounded ${selectedRunId === r.id ? "bg-brand-50" : "hover:bg-[var(--surface-sunken)]"}`}>
                  <span className="font-medium flex items-center gap-1">
                    {r.status === "running" && <Loader2 className="w-3 h-3 animate-spin" />}
                    {r.workload_profile}
                  </span>
                  <span className="text-[var(--text-tertiary)]">p95: {r.metrics?.http_req_duration_p95 ?? "—"}ms · {new Date(r.created_at).toLocaleString()}</span>
                </button>
              ))}
              {runs.length === 0 && <p className="text-[var(--text-tertiary)] py-8 text-center">No runs yet</p>}
            </ul>
          </div>
          <div className="lg:col-span-3">
            {runDetail && projectId ? (
              <PerfRunDashboard projectId={projectId} detail={runDetail} />
            ) : (
              <div className="ds-card p-16 text-center text-sm text-[var(--text-tertiary)]">
                Select a run to view the 360° performance dashboard
              </div>
            )}
          </div>
        </div>
      )}

      {mainTab === "studio" && active && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-4">
            <MetricCard label="VUs" value={String(active.workload_model?.virtual_users ?? "—")} icon={<Gauge className="w-4 h-4" />} />
            <MetricCard label="Scenarios" value={active.scenarios?.length ?? 0} icon={<Layers className="w-4 h-4" />} />
            <MetricCard label="Replay Steps" value={active.scenarios?.[0]?.steps?.length ?? 0} icon={<Activity className="w-4 h-4" />} />
            <MetricCard label="Correlations" value={active.correlation_rules?.length ?? 0} icon={<Link2 className="w-4 h-4" />} />
            <MetricCard label="Agent" value={localhostAgent?.status ?? "—"} icon={<Server className="w-4 h-4" />} />
          </div>
          <div className="ds-card overflow-hidden" style={{ minHeight: 480 }}>
            <div className="grid grid-cols-12 divide-x divide-[var(--border-default)]" style={{ minHeight: 480 }}>
              <div className="col-span-4 bg-[var(--surface-sunken)]/30 p-3">
                <Tabs tabs={[
                  { id: "scripts", label: "Scripts", count: active.scripts.length },
                  { id: "scenarios", label: "Scenarios", count: active.scenarios?.length },
                  { id: "correlation", label: "Correlation", count: active.correlation_rules?.length },
                  { id: "workload", label: "Workload" },
                ]} active={sideTab} onChange={setSideTab} />
                {sideTab === "scripts" && (
                  <FileTree files={active.scripts} activeFile={activeFile} onSelect={(p) => {
                    setActiveFile(p);
                    setFileContent(active.scripts.find((x) => x.path === p)?.content ?? "");
                  }} />
                )}
                {sideTab === "scenarios" && (
                  <ul className="mt-3 space-y-2 text-xs">
                    {(active.scenarios || []).map((s) => (
                      <li key={s.id} className="p-2 rounded border">
                        <p className="font-medium">{s.name}</p>
                        <p className="text-[var(--text-tertiary)]">{s.steps?.length ?? 0} HTTP steps · {s.source ?? "replay"}</p>
                        {(s.steps ?? []).slice(0, 3).map((st, i) => (
                          <p key={i} className="font-mono truncate text-[10px]">{st.action} {st.url}</p>
                        ))}
                      </li>
                    ))}
                  </ul>
                )}
                {sideTab === "correlation" && (
                  <div className="mt-3">
                    <textarea className="ds-input text-xs font-mono" rows={4} placeholder="Paste HAR JSON…" value={harJson} onChange={(e) => setHarJson(e.target.value)} />
                    <button onClick={applyHarCorrelation} className="ds-btn-secondary text-xs mt-2 w-full"><Upload className="w-3 h-3 inline" /> Apply HAR</button>
                  </div>
                )}
                {sideTab === "workload" && (
                  <div className="mt-3 space-y-2">
                    {profiles.map((p) => (
                      <button key={p.id} onClick={() => applyWorkload(p.id)}
                        className={`w-full text-left p-2 rounded text-xs border ${profile === p.id ? "border-brand-700 bg-brand-50" : ""}`}>
                        <p className="font-medium">{p.name}</p>
                        <p className="text-[var(--text-tertiary)]">{p.virtual_users} VUs</p>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="col-span-8 flex flex-col">
                <div className="px-4 py-2 border-b flex justify-between bg-[var(--surface-sunken)]/20">
                  <span className="text-xs font-mono">{activeFile ?? "Select file"}</span>
                  {activeFile && (
                    <button onClick={saveFile} disabled={saving} className="ds-btn-secondary text-xs">
                      {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />} Save
                    </button>
                  )}
                </div>
                <div className="flex-1 p-2">
                  {activeFile ? (
                    <CodeEditor value={fileContent} onChange={setFileContent} language="javascript" />
                  ) : (
                    <div className="flex items-center justify-center h-full text-sm text-[var(--text-tertiary)]">Generate from browser replay to view script</div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </>
      )}

      {mainTab === "studio" && !active && (
        <div className="ds-card p-16 text-center">
          <Zap className="w-10 h-10 text-[var(--text-tertiary)] mx-auto mb-4" />
          <h3 className="text-sm font-semibold mb-1">Generate from Browser Replay</h3>
          <p className="text-xs text-[var(--text-tertiary)]">Select a discovery session or use test cases with URLs — scripts mirror real navigation paths</p>
        </div>
      )}

      {message && <p className="mt-3 text-sm p-3 rounded-md bg-[var(--surface-sunken)]">{message}</p>}
    </AppShell>
  );
}
