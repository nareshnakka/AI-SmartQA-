"use client";

import { Suspense, useCallback, useEffect, useState, useMemo } from "react";
import Link from "next/link";
import {
  Sparkles, Loader2, PlayCircle, Zap, GitBranch, FileText, Rocket,
  CheckCircle2, ArrowRight, Brain, Layers, Target, Calendar,
} from "lucide-react";
import { AppShell } from "@/components/shell/AppShell";
import { PageHeader, Badge, Tabs } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useActiveProject } from "@/context/ProjectContext";
import { fetchTestCases } from "@/lib/test-cases";
import { useWorkspaceScope } from "@/lib/workspace";

interface LlmProvider { name: string; models: string[]; available: boolean }
interface StudioOverview {
  stats: Record<string, number>;
  default_llm_provider: string;
  llm_providers: LlmProvider[];
  automation_input_types: { id: string; name: string; description: string }[];
  performance_input_types: { id: string; name: string; description: string }[];
}
interface Sprint { id: string; name: string; goal?: string; status: string; test_case_ids: string[] }
interface Release { id: string; name: string; version: string; status: string; sprint_ids: string[] }
interface TestCase { id: string; title: string; case_code?: string | null; module_id?: string | null; module_name?: string | null; steps?: string[] }

interface AutomationFile {
  path: string;
  content?: string;
  type?: string;
}

interface AutomationAsset {
  id: string;
  name: string;
  framework: string;
  language?: string;
  files: AutomationFile[];
  version?: number;
  status?: string;
}

interface AutomationGenerateResult {
  asset: AutomationAsset;
  source?: string;
  derived_cases?: number;
  llm_provider?: string;
}

interface PerformanceGenerateResult {
  asset?: { id: string; name?: string; tool?: string; files?: AutomationFile[] };
  source?: string;
}

const WORKLOADS = ["smoke", "load", "stress", "soak", "spike"];
const FRAMEWORKS = ["playwright", "cypress", "selenium", "webdriverio"];

function QualityStudioContent() {
  const { projectId, activeProject } = useActiveProject();
  const { moduleQueryIds, environmentQueryIds, activeEnvironment } = useWorkspaceScope(projectId);
  const [overview, setOverview] = useState<StudioOverview | null>(null);
  const [tab, setTab] = useState("overview");
  const [llmProvider, setLlmProvider] = useState("qeos-native");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const [functionalInput, setFunctionalInput] = useState("");
  const [functionalType, setFunctionalType] = useState("prompt");
  const [functionalResult, setFunctionalResult] = useState<{ count?: number; test_cases?: { id: string; title: string }[] } | null>(null);

  const [autoInput, setAutoInput] = useState("");
  const [autoType, setAutoType] = useState("prompt");
  const [framework, setFramework] = useState("playwright");
  const [baseUrl, setBaseUrl] = useState("");
  const [autoResult, setAutoResult] = useState<AutomationGenerateResult | null>(null);
  const [previewPath, setPreviewPath] = useState<string | null>(null);

  const [perfInput, setPerfInput] = useState("");
  const [perfType, setPerfType] = useState("prompt");
  const [workload, setWorkload] = useState("load");
  const [perfResult, setPerfResult] = useState<PerformanceGenerateResult | null>(null);

  const [sprints, setSprints] = useState<Sprint[]>([]);
  const [releases, setReleases] = useState<Release[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [newSprintName, setNewSprintName] = useState("");
  const [newReleaseName, setNewReleaseName] = useState("");
  const [selectedCases, setSelectedCases] = useState<Set<string>>(new Set());
  const [nfrTitle, setNfrTitle] = useState("");
  const [nfrContent, setNfrContent] = useState("");

  const loadStudio = useCallback(async () => {
    if (!projectId) return;
    const [ov, sp, rel, tc] = await Promise.all([
      apiFetch<StudioOverview>(`/api/v1/projects/${projectId}/quality-studio/overview`),
      apiFetch<Sprint[]>(`/api/v1/projects/${projectId}/quality-studio/sprints`),
      apiFetch<Release[]>(`/api/v1/projects/${projectId}/quality-studio/releases`),
      fetchTestCases(projectId, { moduleIds: moduleQueryIds, environmentIds: environmentQueryIds }),
    ]);
    setOverview(ov);
    setLlmProvider(ov.default_llm_provider || "qeos-native");
    setSprints(sp);
    setReleases(rel);
    setTestCases(tc);
  }, [projectId, moduleQueryIds, environmentQueryIds]);

  const filteredTestCases = testCases;

  useEffect(() => {
    if (activeEnvironment?.base_url && !baseUrl) {
      setBaseUrl(activeEnvironment.base_url);
    }
  }, [activeEnvironment, baseUrl]);

  useEffect(() => { loadStudio().catch(() => {}); }, [loadStudio]);

  const run = async <T,>(label: string, fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    setMessage("");
    try {
      const result = await fn();
      setMessage(`${label} — success`);
      await loadStudio();
      return result;
    } catch (e) {
      setMessage(String(e));
      return undefined;
    } finally {
      setBusy(false);
    }
  };

  const generateFunctional = async () => {
    const result = await run("Functional tests generated", () =>
      apiFetch<{ count?: number; test_cases?: { id: string; title: string }[] }>(
        `/api/v1/projects/${projectId}/quality-studio/functional/generate`,
        {
          method: "POST",
          body: JSON.stringify({ input_type: functionalType, content: functionalInput, llm_provider: llmProvider }),
        }
      )
    );
    if (result) {
      setFunctionalResult(result);
      setMessage(`Functional tests generated — ${result.count ?? result.test_cases?.length ?? 0} case(s)`);
    }
  };

  const generateAutomation = async () => {
    const result = await run("Automation scripts generated", () =>
      apiFetch<AutomationGenerateResult>(`/api/v1/projects/${projectId}/quality-studio/automation/generate`, {
        method: "POST",
        body: JSON.stringify({
          input_type: autoType, content: autoInput, framework, base_url: baseUrl, llm_provider: llmProvider,
        }),
      })
    );
    if (result?.asset) {
      setAutoResult(result);
      const files = result.asset.files || [];
      setPreviewPath(files[0]?.path ?? null);
      setMessage(
        `Automation scripts generated — ${files.length} file(s)` +
          (result.derived_cases ? `, ${result.derived_cases} derived case(s)` : "") +
          ` (${result.asset.framework})`
      );
    }
  };

  const generatePerformance = async () => {
    const result = await run("Performance scripts generated", () =>
      apiFetch<PerformanceGenerateResult>(`/api/v1/projects/${projectId}/quality-studio/performance/generate`, {
        method: "POST",
        body: JSON.stringify({
          input_type: perfType,
          content: perfInput,
          workload_profile: workload,
          base_url: baseUrl,
          llm_provider: llmProvider,
        }),
      })
    );
    if (result) {
      setPerfResult(result);
      const n = result.asset?.files?.length ?? 0;
      setMessage(`Performance scripts generated — ${n || "ok"} file(s)`);
    }
  };

  const previewFile = useMemo(() => {
    if (!autoResult?.asset?.files || !previewPath) return null;
    return autoResult.asset.files.find((f) => f.path === previewPath) ?? null;
  }, [autoResult, previewPath]);

  const createSprint = () => run("Sprint created", () =>
    apiFetch(`/api/v1/projects/${projectId}/quality-studio/sprints`, {
      method: "POST",
      body: JSON.stringify({
        name: newSprintName || `Sprint ${sprints.length + 1}`,
        test_case_ids: [...selectedCases],
      }),
    })
  );

  const createRelease = () => run("Release created", () =>
    apiFetch(`/api/v1/projects/${projectId}/quality-studio/releases`, {
      method: "POST",
      body: JSON.stringify({ name: newReleaseName || "Release", version: "1.0.0" }),
    })
  );

  const saveNfr = () => run("NFR document saved", () =>
    apiFetch(`/api/v1/projects/${projectId}/quality-studio/nfr`, {
      method: "POST",
      body: JSON.stringify({ title: nfrTitle || "NFR Document", content: nfrContent, source_type: "mixed" }),
    })
  );

  const executeSprint = (sprintId: string) => run("Sprint execution started", () =>
    apiFetch(`/api/v1/projects/${projectId}/quality-studio/sprints/execute`, {
      method: "POST",
      body: JSON.stringify({ sprint_id: sprintId, framework, base_url: baseUrl, mode: "live" }),
    })
  );

  const stats = overview?.stats;

  return (
    <AppShell title="Quality Studio">
      <PageHeader
        title="Quality Studio"
        subtitle="One-stop hub — functional tests, automation, performance, sprints & releases. No manual test cases required."
        actions={
          <div className="flex items-center gap-2">
            <Brain className="w-4 h-4 text-brand-700" />
            <select
              className="ds-input py-1.5 text-sm w-44"
              value={llmProvider}
              onChange={(e) => setLlmProvider(e.target.value)}
              title="LLM provider — QEOS Native is default (fast, no API key)"
            >
              {(overview?.llm_providers ?? [{ name: "qeos-native", available: true }]).map((p) => (
                <option key={p.name} value={p.name} disabled={!p.available}>
                  {p.name}{!p.available ? " (unavailable)" : p.name === "qeos-native" ? " ★ default" : ""}
                </option>
              ))}
            </select>
          </div>
        }
      />

      <div className="ds-card mb-4 px-4 py-3 flex flex-wrap items-center gap-3">
        {activeProject && (
          <span className="text-sm font-medium text-[var(--text-secondary)]">{activeProject.name}</span>
        )}
        {stats && (
          <div className="flex flex-wrap gap-2 text-xs">
            <Badge variant="neutral">{stats.test_cases} test cases</Badge>
            <Badge variant="neutral">{stats.automation_assets} automation</Badge>
            <Badge variant="neutral">{stats.performance_assets} performance</Badge>
            <Badge variant="neutral">{stats.sprints} sprints</Badge>
            <Badge variant="neutral">{stats.releases} releases</Badge>
          </div>
        )}
        <div className="ml-auto flex gap-2">
          <Link href={`/discovery?project=${projectId}`} className="ds-btn-secondary text-xs">Discovery</Link>
          <Link href={`/executions?project=${projectId}`} className="ds-btn-secondary text-xs">Executions</Link>
          <Link href={`/studio?project=${projectId}`} className="ds-btn-secondary text-xs">Automation IDE</Link>
        </div>
      </div>

      <Tabs
        tabs={[
          { id: "overview", label: "Overview" },
          { id: "functional", label: "Functional Tests" },
          { id: "automation", label: "Automation" },
          { id: "performance", label: "Performance" },
          { id: "sprint", label: "Sprint & Release" },
        ]}
        active={tab}
        onChange={setTab}
      />

      <div className="mt-4">
        {tab === "overview" && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[
              { icon: FileText, title: "Functional Tests", desc: "Generate from prompts, requirements, BDD — no manual authoring", tab: "functional", color: "brand" },
              { icon: Sparkles, title: "Automation", desc: "Playwright/Cypress/etc. from prompt, steps, HAR, OpenAPI, video — standalone", tab: "automation", color: "emerald" },
              { icon: Zap, title: "Performance", desc: "k6 scripts from NFR docs, prompts, steps, HAR — no automation dependency", tab: "performance", color: "amber" },
              { icon: Calendar, title: "Sprint & Release", desc: "Plan sprints, assign tests, execute & track by release", tab: "sprint", color: "violet" },
              { icon: PlayCircle, title: "Execute", desc: "Run automation & performance with live agent", href: "/executions", color: "blue" },
              { icon: Target, title: "Discovery", desc: "Browser crawl → auto-generate tests & scripts", href: "/discovery", color: "rose" },
            ].map((card) => (
              <button
                key={card.title}
                onClick={() => card.tab ? setTab(card.tab) : undefined}
                className="ds-card p-5 text-left hover:ring-2 hover:ring-brand-200 transition-all"
              >
                <card.icon className="w-8 h-8 text-brand-700 mb-3" />
                <h3 className="text-sm font-semibold mb-1">{card.title}</h3>
                <p className="text-xs text-[var(--text-tertiary)] mb-3">{card.desc}</p>
                {card.href ? (
                  <Link href={`${card.href}?project=${projectId}`} className="text-xs text-brand-700 flex items-center gap-1">
                    Open <ArrowRight className="w-3 h-3" />
                  </Link>
                ) : (
                  <span className="text-xs text-brand-700 flex items-center gap-1">Start <ArrowRight className="w-3 h-3" /></span>
                )}
              </button>
            ))}
          </div>
        )}

        {tab === "functional" && (
          <div className="ds-card p-5 space-y-4 max-w-3xl">
            <div className="flex items-center gap-2">
              <Layers className="w-5 h-5 text-brand-700" />
              <h2 className="text-sm font-semibold">Generate Functional Test Cases</h2>
            </div>
            <p className="text-xs text-[var(--text-tertiary)]">
              Uses <strong>{llmProvider}</strong> — QEOS Native is fastest with zero external API keys.
            </p>
            <select className="ds-input text-sm w-full" value={functionalType} onChange={(e) => setFunctionalType(e.target.value)}>
              <option value="prompt">Natural language prompt</option>
              <option value="requirements">Requirements / BRD</option>
              <option value="user_story">User stories</option>
              <option value="bdd">BDD / Gherkin</option>
              <option value="steps">Step list</option>
            </select>
            <textarea
              className="ds-input text-sm font-mono w-full resize-none"
              rows={10}
              placeholder="Describe what to test, paste requirements, user stories, or numbered steps…"
              value={functionalInput}
              onChange={(e) => setFunctionalInput(e.target.value)}
            />
            <button onClick={generateFunctional} disabled={busy || !functionalInput.trim() || !projectId} className="ds-btn-primary">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              Generate Test Cases
            </button>
            {functionalResult && (
              <div className="rounded-md border border-brand-200 bg-brand-50/50 p-3 space-y-2">
                <p className="text-xs font-medium">
                  Generated {functionalResult.count ?? functionalResult.test_cases?.length ?? 0} test case(s)
                </p>
                <ul className="text-xs space-y-1 max-h-40 overflow-y-auto">
                  {(functionalResult.test_cases || []).slice(0, 12).map((tc) => (
                    <li key={tc.id} className="truncate">• {tc.title}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {tab === "automation" && (
          <div className="ds-card p-5 space-y-4 max-w-3xl">
            <div className="flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-emerald-600" />
              <h2 className="text-sm font-semibold">Standalone Automation Generation</h2>
              <Badge variant="success">No manual test cases required</Badge>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <select className="ds-input text-sm" value={autoType} onChange={(e) => setAutoType(e.target.value)}>
                {(overview?.automation_input_types ?? []).map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
              <select className="ds-input text-sm" value={framework} onChange={(e) => setFramework(e.target.value)}>
                {FRAMEWORKS.map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
            </div>
            <input className="ds-input text-sm w-full" placeholder="Base URL" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
            <textarea
              className="ds-input text-sm font-mono w-full resize-none"
              rows={10}
              placeholder="Prompt, steps, paste OpenAPI/HAR JSON, or video session transcript…"
              value={autoInput}
              onChange={(e) => setAutoInput(e.target.value)}
            />
            <div className="flex gap-2">
              <button onClick={generateAutomation} disabled={busy || !autoInput.trim()} className="ds-btn-primary">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                Generate Automation
              </button>
              <Link
                href={`/studio?project=${projectId}${autoResult?.asset?.id ? `&asset=${autoResult.asset.id}` : ""}`}
                className="ds-btn-secondary"
              >
                Open in IDE
              </Link>
            </div>

            {autoResult?.asset && (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50/60 p-4 space-y-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-emerald-950 flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4" />
                      {autoResult.asset.name}
                    </p>
                    <p className="text-xs text-emerald-900/80 mt-1">
                      {autoResult.asset.framework}
                      {autoResult.asset.language ? ` · ${autoResult.asset.language}` : ""}
                      {" · "}
                      {(autoResult.asset.files || []).length} file(s)
                      {autoResult.derived_cases != null ? ` · ${autoResult.derived_cases} derived case(s)` : ""}
                      {autoResult.source ? ` · source: ${autoResult.source}` : ""}
                    </p>
                    <p className="text-[10px] font-mono text-emerald-900/60 mt-1">Asset ID: {autoResult.asset.id}</p>
                  </div>
                  <Link
                    href={`/studio?project=${projectId}&asset=${autoResult.asset.id}`}
                    className="ds-btn-primary text-xs py-1.5 px-3 inline-flex items-center gap-1"
                  >
                    Edit / Debug in IDE <ArrowRight className="w-3 h-3" />
                  </Link>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <ul className="md:col-span-1 space-y-1 max-h-56 overflow-y-auto">
                    {(autoResult.asset.files || []).map((f) => (
                      <li key={f.path}>
                        <button
                          type="button"
                          onClick={() => setPreviewPath(f.path)}
                          className={`w-full text-left text-xs px-2 py-1.5 rounded font-mono truncate ${
                            previewPath === f.path
                              ? "bg-emerald-700 text-white"
                              : "bg-white/80 text-emerald-950 hover:bg-white"
                          }`}
                          title={f.path}
                        >
                          {f.path}
                        </button>
                      </li>
                    ))}
                    {(autoResult.asset.files || []).length === 0 && (
                      <li className="text-xs text-emerald-900/70">No files in asset response.</li>
                    )}
                  </ul>
                  <pre className="md:col-span-2 text-[11px] font-mono bg-white border border-emerald-100 rounded-md p-3 max-h-56 overflow-auto whitespace-pre-wrap text-[var(--text-primary)]">
                    {previewFile?.content || "// Select a file to preview"}
                  </pre>
                </div>
              </div>
            )}
          </div>
        )}

        {tab === "performance" && (
          <div className="ds-card p-5 space-y-4 max-w-3xl">
            <div className="flex items-center gap-2">
              <Zap className="w-5 h-5 text-amber-600" />
              <h2 className="text-sm font-semibold">Standalone Performance Engineering</h2>
              <Badge variant="success">Independent of automation</Badge>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <select className="ds-input text-sm" value={perfType} onChange={(e) => setPerfType(e.target.value)}>
                {(overview?.performance_input_types ?? []).map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
              <select className="ds-input text-sm" value={workload} onChange={(e) => setWorkload(e.target.value)}>
                {WORKLOADS.map((w) => <option key={w} value={w}>{w}</option>)}
              </select>
            </div>
            <input className="ds-input text-sm w-full" placeholder="Target base URL" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
            <textarea
              className="ds-input text-sm font-mono w-full resize-none"
              rows={10}
              placeholder="NFR doc (p95 &lt; 500ms, 1000 RPS), user journey steps, prompt, HAR/OpenAPI JSON…"
              value={perfInput}
              onChange={(e) => setPerfInput(e.target.value)}
            />
            <div className="flex gap-2">
              <button onClick={generatePerformance} disabled={busy || !perfInput.trim()} className="ds-btn-primary">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                Generate k6 Scripts
              </button>
              <Link href={`/performance?project=${projectId}`} className="ds-btn-secondary">Performance Dashboard</Link>
            </div>
            {perfResult?.asset && (
              <div className="rounded-md border border-amber-200 bg-amber-50/60 p-3 text-xs space-y-1">
                <p className="font-medium">{perfResult.asset.name || "Performance asset"}</p>
                <p>
                  {(perfResult.asset.files || []).length} file(s)
                  {perfResult.asset.tool ? ` · ${perfResult.asset.tool}` : ""}
                </p>
                <ul className="font-mono space-y-0.5 max-h-28 overflow-y-auto">
                  {(perfResult.asset.files || []).map((f) => (
                    <li key={f.path}>{f.path}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {tab === "sprint" && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="ds-card p-5 space-y-4">
              <h2 className="text-sm font-semibold flex items-center gap-2"><GitBranch className="w-4 h-4" /> Sprints</h2>
              <input className="ds-input text-sm" placeholder="Sprint name" value={newSprintName} onChange={(e) => setNewSprintName(e.target.value)} /><div className="max-h-48 overflow-auto space-y-1 border rounded-md p-2">
                {filteredTestCases.map((tc) => (
                  <label key={tc.id} className="flex items-center gap-2 text-xs cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedCases.has(tc.id)}
                      onChange={(e) => {
                        setSelectedCases((prev) => {
                          const n = new Set(prev);
                          if (e.target.checked) n.add(tc.id); else n.delete(tc.id);
                          return n;
                        });
                      }}
                    />
                    <span className="truncate font-mono">{tc.case_code || tc.title}</span>
                    {tc.module_name && <span className="text-[var(--text-tertiary)] shrink-0">({tc.module_name})</span>}
                  </label>
                ))}
                {filteredTestCases.length === 0 && <p className="text-xs text-[var(--text-tertiary)]">No test cases for this module filter</p>}
              </div>
              <button onClick={createSprint} disabled={busy} className="ds-btn-primary text-sm">Create Sprint</button>
              <ul className="space-y-2">
                {sprints.map((s) => (
                  <li key={s.id} className="flex items-center justify-between text-sm p-2 rounded bg-[var(--surface-sunken)]">
                    <span>{s.name} <Badge variant="neutral">{s.test_case_ids.length} tests</Badge></span>
                    <button onClick={() => executeSprint(s.id)} disabled={busy || !s.test_case_ids.length} className="ds-btn-secondary text-xs py-1">
                      <PlayCircle className="w-3 h-3" /> Run
                    </button>
                  </li>
                ))}
              </ul>
            </div>

            <div className="ds-card p-5 space-y-4">
              <h2 className="text-sm font-semibold flex items-center gap-2"><Rocket className="w-4 h-4" /> Releases</h2>
              <input className="ds-input text-sm" placeholder="Release name" value={newReleaseName} onChange={(e) => setNewReleaseName(e.target.value)} />
              <button onClick={createRelease} disabled={busy} className="ds-btn-primary text-sm">Create Release</button>
              <ul className="space-y-2">
                {releases.map((r) => (
                  <li key={r.id} className="text-sm p-2 rounded bg-[var(--surface-sunken)]">
                    {r.name} <span className="text-[var(--text-tertiary)]">v{r.version}</span>
                    <span className="ml-2"><Badge variant="neutral">{r.status}</Badge></span>
                  </li>
                ))}
              </ul>

              <hr className="border-[var(--border-default)]" />
              <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">NFR Documents</h3>
              <input className="ds-input text-sm" placeholder="NFR title" value={nfrTitle} onChange={(e) => setNfrTitle(e.target.value)} />
              <textarea className="ds-input text-sm resize-none" rows={4} placeholder="SLA: p95 &lt; 300ms, 500 concurrent users, 2000 RPS…"
                value={nfrContent} onChange={(e) => setNfrContent(e.target.value)} />
              <button onClick={saveNfr} disabled={busy || !nfrContent.trim()} className="ds-btn-secondary text-sm">Save NFR → use in Performance tab</button>
            </div>
          </div>
        )}
      </div>

      {message && (
        <p className={`mt-4 text-sm p-3 rounded-md flex items-center gap-2 ${message.includes("success") ? "bg-emerald-50 text-emerald-800" : "bg-[var(--surface-sunken)]"}`}>
          {message.includes("success") && <CheckCircle2 className="w-4 h-4" />}
          {message}
        </p>
      )}
    </AppShell>
  );
}

export default function QualityStudioPage() {
  return (
    <Suspense fallback={
      <AppShell title="Quality Studio">
        <div className="flex justify-center p-16"><Loader2 className="w-6 h-6 animate-spin" /></div>
      </AppShell>
    }>
      <QualityStudioContent />
    </Suspense>
  );
}
