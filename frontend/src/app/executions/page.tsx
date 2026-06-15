"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  Play, Loader2, CheckCircle2, XCircle, Video, Download, History,
  LayoutDashboard, CheckSquare, Square, Server, BarChart3, Clock, Bug,
  Trash2, Ban, RotateCcw,
} from "lucide-react";
import { AppShell } from "@/components/shell/AppShell";
import { PageHeader, Badge, MetricCard } from "@/components/ui";
import { apiFetch, executionVideoUrl, executionExportUrl } from "@/lib/api";
import { useActiveProject } from "@/context/ProjectContext";
import { bulkTestCaseAction, isAutomationEnabled } from "@/lib/test-cases";
import {
  TestCaseFlowView, buildFlowSteps, applyDebugFlowSteps, type FlowStep,
} from "@/components/flow/TestCaseFlowView";

interface TestCase {
  id: string; title: string; priority: string; status: string;
  steps: string[]; expected_results: string[];
}
interface TestStep { order: number; description: string; status: string; expected?: string }
interface ExecutionResult {
  test_case_id?: string; title: string; status: string;
  steps?: TestStep[]; has_video?: boolean; video_id?: string; error?: string;
}
interface ExecutionRun {
  id: string; status: string; mode: string; run_name?: string;
  sprint?: string; release?: string;
  progress?: {
    total: number; completed: number; current?: string; percent: number;
    current_test_case_id?: string; current_step_index?: number; total_steps?: number;
  };
  summary: { passed: number; failed: number; warnings?: number; tests_detected?: number; videos_captured?: number; framework?: string };
  results: ExecutionResult[];
  logs: string; created_at: string; completed_at?: string | null;
  asset_type?: string;
}
interface Framework { id: string; name: string; language: string }
interface AutomationAsset { id: string; name: string; framework: string }
interface PerfAsset { id: string; name: string; tool: string }
interface FrameworkCap { live: boolean; video: boolean; hint: string }
interface RunnerAgent {
  name: string; status: string; ready: boolean;
  capabilities: Record<string, boolean | Record<string, boolean>>;
  framework_capabilities?: Record<string, FrameworkCap>;
  install_hint: string;
}
interface Dashboard {
  totals: { test_cases: number; execution_runs: number; passed: number; failed: number; running: number; pass_rate: number; steps_passed: number; steps_failed: number };
  pie_chart: { passed: number; failed: number; running: number };
  by_sprint: { sprint: string; passed: number; failed: number; runs: number }[];
  by_release: { release: string; passed: number; failed: number; runs: number }[];
  timeline: { id: string; name: string; status: string; passed: number; failed: number; started_at: string; ended_at?: string; sprint?: string; release?: string }[];
}

function PieChart({ passed, failed, running }: { passed: number; failed: number; running: number }) {
  const total = passed + failed + running || 1;
  const pPct = (passed / total) * 100;
  const fPct = (failed / total) * 100;
  const rPct = (running / total) * 100;
  const grad = `conic-gradient(#10b981 0 ${pPct}%, #ef4444 ${pPct}% ${pPct + fPct}%, #94a3b8 ${pPct + fPct}% 100%)`;
  return (
    <div className="flex items-center gap-6">
      <div className="w-32 h-32 rounded-full shrink-0" style={{ background: grad }} />
      <div className="space-y-1 text-xs">
        <p><span className="inline-block w-2 h-2 rounded-full bg-emerald-500 mr-1" /> Passed {passed} ({Math.round(pPct)}%)</p>
        <p><span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-1" /> Failed {failed} ({Math.round(fPct)}%)</p>
        <p><span className="inline-block w-2 h-2 rounded-full bg-gray-400 mr-1" /> Running {running} ({Math.round(rPct)}%)</p>
      </div>
    </div>
  );
}

export default function ExecutionsPage() {
  const { projectId } = useActiveProject();
  const [tab, setTab] = useState<"run" | "dashboard" | "history">("run");
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [runs, setRuns] = useState<ExecutionRun[]>([]);
  const [active, setActive] = useState<ExecutionRun | null>(null);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [agent, setAgent] = useState<RunnerAgent | null>(null);
  const [running, setRunning] = useState(false);
  const [sprint, setSprint] = useState("Sprint 1");
  const [release, setRelease] = useState("Release 1.0");
  const [baseUrl, setBaseUrl] = useState("https://opensource-demo.orangehrmlive.com");
  const [runType, setRunType] = useState("automation");
  const [framework, setFramework] = useState("playwright");
  const [frameworks, setFrameworks] = useState<Framework[]>([]);
  const [automationAssets, setAutomationAssets] = useState<AutomationAsset[]>([]);
  const [assetId, setAssetId] = useState("");
  const [perfAssets, setPerfAssets] = useState<PerfAsset[]>([]);
  const [perfAssetId, setPerfAssetId] = useState("");
  const [filterSprint, setFilterSprint] = useState("");
  const [flowPreviewId, setFlowPreviewId] = useState<string | null>(null);
  const [debugTestCaseId, setDebugTestCaseId] = useState<string | null>(null);
  const [animTick, setAnimTick] = useState(0);
  const [managing, setManaging] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const animRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    apiFetch<{ frameworks: Framework[] }>("/api/v1/projects/x/automation/frameworks")
      .then((d) => setFrameworks(d.frameworks)).catch(() => {});
  }, []);

  const loadProjectData = useCallback(async (pid: string) => {
    const [cases, runList, dash, ag, assets, perf] = await Promise.allSettled([
      apiFetch<TestCase[]>(`/api/v1/projects/${pid}/test-cases`),
      apiFetch<ExecutionRun[]>(`/api/v1/projects/${pid}/executions`),
      apiFetch<Dashboard>(`/api/v1/projects/${pid}/executions/dashboard${filterSprint ? `?sprint=${filterSprint}` : ""}`),
      apiFetch<RunnerAgent>(`/api/v1/projects/${pid}/executions/runner-agent`),
      apiFetch<AutomationAsset[]>(`/api/v1/projects/${pid}/automation/assets`),
      apiFetch<PerfAsset[]>(`/api/v1/projects/${pid}/performance/assets`),
    ]);
    if (cases.status === "fulfilled") setTestCases(cases.value);
    if (runList.status === "fulfilled") { setRuns(runList.value); if (runList.value[0]) setActive(runList.value[0]); }
    if (dash.status === "fulfilled") setDashboard(dash.value);
    if (ag.status === "fulfilled") setAgent(ag.value);
    if (assets.status === "fulfilled") setAutomationAssets(assets.value);
    if (perf.status === "fulfilled") setPerfAssets(perf.value);
  }, [filterSprint]);

  const filteredAssets = automationAssets.filter((a) => a.framework === framework);
  const fwCap = agent?.framework_capabilities?.[framework];

  useEffect(() => {
    if (!projectId) return;
    loadProjectData(projectId).catch(() => {});
  }, [projectId, loadProjectData]);

  const pollRun = useCallback((pid: string, runId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const run = await apiFetch<ExecutionRun>(`/api/v1/projects/${pid}/executions/${runId}`);
        setActive(run);
        setRuns((prev) => prev.map((r) => (r.id === runId ? run : r)));
        if (run.status !== "running") {
          clearInterval(pollRef.current!);
          pollRef.current = null;
          setRunning(false);
          setDebugTestCaseId(null);
          loadProjectData(pid);
        }
      } catch {
        setRunning(false);
      }
    }, 1500);
  }, [loadProjectData]);

  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (animRef.current) clearInterval(animRef.current);
  }, []);

  useEffect(() => {
    if (active?.status === "running") {
      if (animRef.current) clearInterval(animRef.current);
      animRef.current = setInterval(() => setAnimTick((t) => t + 1), 900);
    } else {
      if (animRef.current) clearInterval(animRef.current);
      animRef.current = null;
    }
  }, [active?.status, active?.id]);

  const toggle = (id: string) => {
    setSelected((p) => {
      const n = new Set(p);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
    setFlowPreviewId(id);
  };
  const selectAll = () => setSelected(new Set(testCases.filter(isAutomationEnabled).map((t) => t.id)));

  const runSelectedCount = Array.from(selected).filter((id) => {
    const tc = testCases.find((t) => t.id === id);
    return tc && isAutomationEnabled(tc);
  }).length;

  const bulkManage = async (action: "delete" | "disable" | "enable") => {
    if (!projectId || selected.size === 0) return;
    const label = action === "delete" ? "delete" : action;
    if (action === "delete" && !window.confirm(`Delete ${selected.size} test case(s)? This cannot be undone.`)) return;
    setManaging(true);
    try {
      await bulkTestCaseAction(projectId, action, Array.from(selected));
      setSelected(new Set());
      await loadProjectData(projectId);
    } finally {
      setManaging(false);
    }
  };

  const debugSingleTest = async (testCaseId: string) => {
    if (!projectId) return;
    const tc = testCases.find((t) => t.id === testCaseId);
    if (!tc || !isAutomationEnabled(tc)) return;
    const matchedAsset = assetId
      ? automationAssets.find((a) => a.id === assetId)
      : automationAssets.find((a) => a.framework === framework);
    if (!matchedAsset) {
      alert("Select an automation asset first. Debug runs saved Playwright scripts — not step stubs.");
      return;
    }
    setDebugTestCaseId(testCaseId);
    setFlowPreviewId(testCaseId);
    setRunning(true);
    setAnimTick(0);
    setTab("history");
    try {
      const run = await apiFetch<ExecutionRun>(`/api/v1/projects/${projectId}/executions/batch-run`, {
        method: "POST",
        body: JSON.stringify({
          test_case_ids: [testCaseId],
          mode: "live",
          background: true,
          framework: matchedAsset.framework,
          base_url: baseUrl,
          run_type: "automation",
          asset_id: matchedAsset.id,
          run_name: `Debug — ${tc.title}`,
        }),
      });
      setRuns((prev) => [run, ...prev]);
      setActive(run);
      pollRun(projectId, run.id);
    } catch {
      setRunning(false);
      setDebugTestCaseId(null);
    }
  };

  const previewCase = flowPreviewId ? testCases.find((t) => t.id === flowPreviewId) : null;
  const previewDebugResult = active?.results?.find((r) => r.test_case_id === previewCase?.id);
  const previewFlowState = previewCase
    ? applyDebugFlowSteps(buildFlowSteps(previewCase.steps ?? [], previewCase.expected_results ?? []), {
        runStatus: debugTestCaseId === previewCase.id ? active?.status : undefined,
        progress: active?.progress,
        testCaseTitle: previewCase.title,
        testCaseId: previewCase.id,
        animTick,
        resultSteps: previewDebugResult?.steps,
      })
    : { steps: [] as FlowStep[], activeStepIndex: null };

  const getResultSteps = (r: ExecutionResult, tc?: TestCase): FlowStep[] => {
    if (r.steps?.length) {
      return buildFlowSteps(
        r.steps.map((s) => s.description),
        r.steps.map((s) => s.expected ?? ""),
        r.steps
      );
    }
    if (tc) return buildFlowSteps(tc.steps ?? [], tc.expected_results ?? []);
    return [];
  };

  const resultFlowState = (r: ExecutionResult, tc?: TestCase) =>
    applyDebugFlowSteps(getResultSteps(r, tc), {
      runStatus: active?.status,
      progress: active?.progress,
      testCaseTitle: r.title,
      testCaseId: r.test_case_id,
      animTick,
      resultSteps: r.steps,
    });

  const batchRun = async () => {
    if (!projectId) return;
    const runnableIds = Array.from(selected).filter((id) => {
      const tc = testCases.find((t) => t.id === id);
      return tc && isAutomationEnabled(tc);
    });
    if (runType === "automation" && runnableIds.length === 0) return;
    if (runType === "performance" && !perfAssetId) return;
    setRunning(true);
    try {
      const run = await apiFetch<ExecutionRun>(`/api/v1/projects/${projectId}/executions/batch-run`, {
        method: "POST",
        body: JSON.stringify({
          test_case_ids: runnableIds,
          mode: "live",
          background: true,
          sprint,
          release,
          base_url: baseUrl,
          run_type: runType,
          framework: runType === "automation" ? framework : undefined,
          asset_id: runType === "automation" && assetId ? assetId : undefined,
          performance_asset_id: runType === "performance" ? perfAssetId : undefined,
          run_name: `${runType === "performance" ? "Performance" : frameworks.find((f) => f.id === framework)?.name ?? framework} — ${runType === "performance" ? "load test" : `${runnableIds.length} tests`}`,
        }),
      });
      setRuns((prev) => [run, ...prev]);
      setActive(run);
      setTab("history");
      pollRun(projectId, run.id);
    } catch {
      setRunning(false);
    }
  };

  return (
    <AppShell title="Test Execution">
      <PageHeader
        title="Test Execution Dashboard"
        subtitle="Select test cases, choose an automation framework, run on localhost agent, track live status, view reports & videos"
        breadcrumbs={[{ label: "Quality Engineering" }, { label: "Executions" }]}
        actions={
          <div className="flex items-center gap-2">
            {agent && (
              <Badge variant={agent.ready ? "success" : "warning"}>
                <Server className="w-3 h-3" /> {agent.name} — {agent.status}
              </Badge>
            )}
          </div>
        }
      />

      <div className="flex gap-2 mb-4 border-b border-[var(--border-default)]">
        {(["run", "dashboard", "history"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${tab === t ? "border-brand-700 text-brand-700" : "border-transparent text-[var(--text-tertiary)]"}`}>
            {t === "run" && <><Play className="w-3.5 h-3.5 inline mr-1" />Run Tests</>}
            {t === "dashboard" && <><LayoutDashboard className="w-3.5 h-3.5 inline mr-1" />Dashboard</>}
            {t === "history" && <><History className="w-3.5 h-3.5 inline mr-1" />History & Reports</>}
          </button>
        ))}
      </div>

      {tab === "dashboard" && (
        <div className="ds-card mb-4 px-4 py-3 flex flex-wrap items-center gap-3">
          <select className="ds-input py-1.5 text-sm w-36" value={filterSprint} onChange={(e) => setFilterSprint(e.target.value)}>
            <option value="">All sprints</option>
            <option value="Sprint 1">Sprint 1</option>
            <option value="Sprint 2">Sprint 2</option>
          </select>
        </div>
      )}

      {tab === "run" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-4">
            <div className="ds-card">
              <div className="ds-card-header flex flex-wrap justify-between gap-2 items-center">
                <h2 className="text-sm font-semibold">
                  Automation Test Cases ({testCases.length})
                  {testCases.some((t) => !isAutomationEnabled(t)) && (
                    <span className="text-[var(--text-tertiary)] font-normal ml-1">
                      · {testCases.filter(isAutomationEnabled).length} active
                    </span>
                  )}
                </h2>
                <div className="flex flex-wrap items-center gap-2">
                  <button type="button" onClick={selectAll} className="text-xs text-brand-700">Select active</button>
                  {selected.size > 0 && (
                    <>
                      <button type="button" onClick={() => bulkManage("disable")} disabled={managing} className="ds-btn-secondary text-xs py-1">
                        <Ban className="w-3 h-3" /> Disable ({selected.size})
                      </button>
                      <button type="button" onClick={() => bulkManage("enable")} disabled={managing} className="ds-btn-secondary text-xs py-1">
                        <RotateCcw className="w-3 h-3" /> Enable
                      </button>
                      <button type="button" onClick={() => bulkManage("delete")} disabled={managing} className="ds-btn-secondary text-xs py-1 text-red-700">
                        <Trash2 className="w-3 h-3" /> Delete
                      </button>
                    </>
                  )}
                </div>
              </div>
              <div className="ds-card-body pt-0 max-h-[280px] overflow-auto space-y-1">
                {testCases.map((tc) => {
                  const disabled = !isAutomationEnabled(tc);
                  return (
                  <div key={tc.id}
                    className={`flex items-start gap-3 p-2 rounded-md cursor-pointer ${selected.has(tc.id) || flowPreviewId === tc.id ? "bg-brand-50 ring-1 ring-brand-200" : "hover:bg-[var(--surface-sunken)]"} ${disabled ? "opacity-60" : ""}`}
                    onClick={() => toggle(tc.id)}>
                    {selected.has(tc.id) ? <CheckSquare className="w-4 h-4 text-brand-700 shrink-0" /> : <Square className="w-4 h-4 text-gray-400 shrink-0" />}
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-medium truncate ${disabled ? "line-through" : ""}`}>{tc.title}</p>
                      <p className="text-xs text-[var(--text-tertiary)]">{tc.steps?.length ?? 0} steps · {tc.priority}</p>
                    </div>
                    {!disabled && (
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); debugSingleTest(tc.id); }}
                      className="ds-btn-ghost p-1.5 shrink-0"
                      title="Debug this test case"
                    >
                      <Bug className="w-3.5 h-3.5 text-brand-700" />
                    </button>
                    )}
                    <Badge variant={disabled ? "warning" : "neutral"}>{tc.status}</Badge>
                  </div>
                );})}
                {testCases.length === 0 && <p className="text-sm text-[var(--text-tertiary)] py-8 text-center">No test cases — create via Discovery or Projects</p>}
              </div>
            </div>

            {previewCase && (
              <div className="ds-card">
                <div className="ds-card-header flex justify-between items-center">
                  <h2 className="text-sm font-semibold">Test Flow Preview</h2>
                  <button onClick={() => debugSingleTest(previewCase.id)} disabled={running} className="ds-btn-secondary text-xs py-1">
                    <Bug className="w-3 h-3" /> Debug flow
                  </button>
                </div>
                <div className="ds-card-body pt-0 max-h-[420px] overflow-auto">
                  <TestCaseFlowView
                    title={previewCase.title}
                    steps={previewFlowState.steps}
                    activeStepIndex={previewFlowState.activeStepIndex}
                  />
                </div>
              </div>
            )}
          </div>

          <div className="space-y-4">
            <div className="ds-card">
              <div className="ds-card-header"><h2 className="text-sm font-semibold">Run Configuration</h2></div>
              <div className="ds-card-body space-y-3 pt-0">
                <select className="ds-input text-sm" value={runType} onChange={(e) => setRunType(e.target.value)}>
                  <option value="automation">Automation Framework</option>
                  <option value="performance">Performance (k6)</option>
                </select>
                {runType === "automation" && (
                  <>
                    <select className="ds-input text-sm" value={framework} onChange={(e) => { setFramework(e.target.value); setAssetId(""); }}>
                      {frameworks.map((f) => (
                        <option key={f.id} value={f.id}>{f.name} ({f.language})</option>
                      ))}
                      {frameworks.length === 0 && (
                        <>
                          <option value="playwright">Playwright</option>
                          <option value="cypress">Cypress</option>
                          <option value="selenium">Selenium</option>
                          <option value="webdriverio">WebdriverIO</option>
                          <option value="robot_framework">Robot Framework</option>
                          <option value="appium">Appium</option>
                          <option value="puppeteer">Puppeteer</option>
                          <option value="testcafe">TestCafe</option>
                        </>
                      )}
                    </select>
                    {filteredAssets.length > 0 && (
                      <select className="ds-input text-sm" value={assetId} onChange={(e) => setAssetId(e.target.value)}>
                        <option value="">Generated specs (from test cases)</option>
                        {filteredAssets.map((a) => (
                          <option key={a.id} value={a.id}>{a.name}</option>
                        ))}
                      </select>
                    )}
                    {fwCap && !fwCap.live && (
                      <p className="text-xs text-amber-700 bg-amber-50 p-2 rounded-md">{fwCap.hint}</p>
                    )}
                  </>
                )}
                {runType === "performance" && (
                  <select className="ds-input text-sm" value={perfAssetId} onChange={(e) => setPerfAssetId(e.target.value)}>
                    <option value="">Select performance script…</option>
                    {perfAssets.map((a) => (
                      <option key={a.id} value={a.id}>{a.name} ({a.tool})</option>
                    ))}
                  </select>
                )}
                <input className="ds-input text-sm font-mono" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="Base URL" />
                <input className="ds-input text-sm" value={sprint} onChange={(e) => setSprint(e.target.value)} placeholder="Sprint" />
                <input className="ds-input text-sm" value={release} onChange={(e) => setRelease(e.target.value)} placeholder="Release" />
                <button onClick={batchRun} disabled={running || (runType === "automation" ? runSelectedCount === 0 : !perfAssetId)} className="ds-btn-primary w-full">
                  {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                  Run {runSelectedCount} test(s) in background
                </button>
              </div>
            </div>
            {agent && !agent.ready && (
              <p className="text-xs text-amber-700 bg-amber-50 p-3 rounded-md">{agent.install_hint}</p>
            )}
          </div>
        </div>
      )}

      {tab === "dashboard" && dashboard && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <MetricCard label="Test Cases" value={dashboard.totals.test_cases} />
            <MetricCard label="Pass Rate" value={`${dashboard.totals.pass_rate}%`} changeType="positive" />
            <MetricCard label="Passed" value={dashboard.totals.passed} changeType="positive" />
            <MetricCard label="Failed" value={dashboard.totals.failed} changeType="negative" />
            <MetricCard label="Running" value={dashboard.totals.running} />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="ds-card">
              <div className="ds-card-header"><h2 className="text-sm font-semibold">Pass / Fail</h2></div>
              <div className="ds-card-body pt-0">
                <PieChart passed={dashboard.pie_chart.passed} failed={dashboard.pie_chart.failed} running={dashboard.pie_chart.running} />
              </div>
            </div>
            <div className="ds-card">
              <div className="ds-card-header"><h2 className="text-sm font-semibold">By Sprint</h2></div>
              <ul className="ds-card-body pt-0 space-y-2 text-xs">
                {dashboard.by_sprint.map((s) => (
                  <li key={s.sprint} className="flex justify-between">
                    <span>{s.sprint}</span>
                    <span className="text-emerald-600">{s.passed}P</span>
                    <span className="text-red-500">{s.failed}F</span>
                    <span className="text-[var(--text-tertiary)]">{s.runs} runs</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="ds-card">
              <div className="ds-card-header"><h2 className="text-sm font-semibold">By Release</h2></div>
              <ul className="ds-card-body pt-0 space-y-2 text-xs">
                {dashboard.by_release.map((r) => (
                  <li key={r.release} className="flex justify-between">
                    <span>{r.release}</span>
                    <span className="text-emerald-600">{r.passed}P</span>
                    <span className="text-red-500">{r.failed}F</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <div className="ds-card">
            <div className="ds-card-header"><h2 className="text-sm font-semibold">Execution Timeline</h2></div>
            <table className="ds-table">
              <thead><tr><th>Run</th><th>Status</th><th>Passed</th><th>Failed</th><th>Sprint</th><th>Release</th><th>Started</th><th>Ended</th></tr></thead>
              <tbody>
                {dashboard.timeline.map((t) => (
                  <tr key={t.id} className="text-xs cursor-pointer hover:bg-brand-50" onClick={() => { setActive(runs.find(r => r.id === t.id) || null); setTab("history"); }}>
                    <td>{t.name}</td>
                    <td><Badge variant={t.status === "completed" ? "success" : t.status === "failed" ? "error" : "neutral"}>{t.status}</Badge></td>
                    <td>{t.passed}</td>
                    <td>{t.failed}</td>
                    <td>{t.sprint || "—"}</td>
                    <td>{t.release || "—"}</td>
                    <td className="font-mono">{new Date(t.started_at).toLocaleString()}</td>
                    <td className="font-mono">{t.ended_at ? new Date(t.ended_at).toLocaleString() : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === "history" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="ds-card">
            <div className="ds-card-header"><h2 className="text-sm font-semibold">Run History</h2></div>
            <div className="ds-card-body space-y-1 pt-0 max-h-[520px] overflow-auto">
              {runs.map((r) => (
                <button key={r.id} onClick={() => setActive(r)}
                  className={`w-full text-left px-3 py-2 rounded-md text-xs ${active?.id === r.id ? "bg-brand-50" : "hover:bg-[var(--surface-sunken)]"}`}>
                  <span className="font-medium flex items-center gap-1">
                    {r.status === "running" && <Loader2 className="w-3 h-3 animate-spin" />}
                    {r.run_name || r.mode}
                  </span>
                  <span className="block text-[var(--text-tertiary)]">
                    {r.summary?.framework ? `${r.summary.framework} · ` : ""}
                    {r.summary?.passed ?? 0}P / {r.summary?.failed ?? 0}F · {new Date(r.created_at).toLocaleString()}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div className="lg:col-span-2 space-y-4">
            {active?.status === "running" && active.progress && (
              <div className="ds-card border-brand-200 bg-brand-50 px-4 py-3">
                <div className="flex justify-between text-xs mb-2">
                  <span>Running: {active.progress.current || "…"}</span>
                  <span>{active.progress.completed}/{active.progress.total} ({active.progress.percent}%)</span>
                </div>
                <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-full bg-brand-700 transition-all" style={{ width: `${active.progress.percent}%` }} />
                </div>
              </div>
            )}

            {active && (
              <>
                <div className="flex flex-wrap gap-2 items-center justify-between">
                  <div className="flex gap-2 text-xs">
                    <Clock className="w-4 h-4" />
                    Started {new Date(active.created_at).toLocaleString()}
                    {active.completed_at && <> · Ended {new Date(active.completed_at).toLocaleString()}</>}
                  </div>
                  <div className="flex gap-2">
                    {(["html", "json", "csv"] as const).map((fmt) => (
                      <a key={fmt} href={executionExportUrl(projectId, active.id, fmt)} className="ds-btn-secondary text-xs py-1">
                        <Download className="w-3 h-3" /> {fmt.toUpperCase()}
                      </a>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-4 gap-3">
                  <MetricCard label="Passed" value={active.summary?.passed ?? 0} changeType="positive" />
                  <MetricCard label="Failed" value={active.summary?.failed ?? 0} changeType="negative" />
                  <MetricCard label="Tests" value={active.summary?.tests_detected ?? active.results?.length ?? 0} />
                  <MetricCard label="Videos" value={active.summary?.videos_captured ?? 0} />
                </div>

                {(active.results ?? []).map((r, i) => {
                  const tc = testCases.find((t) => t.id === r.test_case_id);
                  const flow = resultFlowState(r, tc);
                  const isDebugging = debugTestCaseId === r.test_case_id && active.status === "running";

                  return (
                  <div key={r.test_case_id || i} className="ds-card">
                    <div className="ds-card-header flex justify-between">
                      <h3 className="text-sm font-semibold flex items-center gap-2">
                        {r.status === "passed" ? <CheckCircle2 className="w-4 h-4 text-emerald-600" /> : r.status === "running" ? <Loader2 className="w-4 h-4 animate-spin text-brand-700" /> : <XCircle className="w-4 h-4 text-red-500" />}
                        {r.title}
                        {isDebugging && <Loader2 className="w-3.5 h-3.5 animate-spin text-brand-700" />}
                      </h3>
                      <Badge variant={r.status === "passed" ? "success" : r.status === "running" ? "neutral" : "error"}>{r.status}</Badge>
                    </div>
                    <div className="ds-card-body pt-0 space-y-3">
                      <TestCaseFlowView
                        title={undefined}
                        steps={flow.steps}
                        activeStepIndex={flow.activeStepIndex}
                        showHeader={false}
                      />
                      {r.has_video && projectId && (
                        <div>
                          <p className="text-xs font-medium mb-2 flex items-center gap-1"><Video className="w-3.5 h-3.5" /> Execution recording</p>
                          <video controls className="w-full max-h-72 rounded-lg border border-[var(--border-default)] bg-black"
                            src={executionVideoUrl(projectId, active.id, r.video_id ?? String(i))} preload="metadata" />
                        </div>
                      )}
                      {r.error && <p className="text-xs text-red-600">{r.error}</p>}
                    </div>
                  </div>
                  );
                })}
              </>
            )}
            {!active && <p className="text-sm text-[var(--text-tertiary)] text-center py-16">Select a run from history</p>}
          </div>
        </div>
      )}
    </AppShell>
  );
}
