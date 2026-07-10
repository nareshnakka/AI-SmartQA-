"use client";

import { useEffect, useState, useCallback, useRef, Suspense, useMemo } from "react";
import Link from "next/link";
import {
  Radar, Loader2, Globe, Map as MapIcon, CheckCircle2, ChevronDown, ChevronRight,
  Bot, Play, CheckSquare, Square, GitCommitHorizontal, Trash2, Eraser,
} from "lucide-react";
import { AppShell } from "@/components/shell/AppShell";
import { PageHeader, Badge, MetricCard } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useActiveProject } from "@/context/ProjectContext";
import { WorkspaceFilters } from "@/components/workspace/WorkspaceFilters";
import { createModule, type ProjectModule } from "@/lib/modules";
import { useWorkspaceScope } from "@/lib/workspace";
import { bulkTestCaseAction, fetchTestCases, notifyTestCasesUpdated, type AutomationTestCase } from "@/lib/test-cases";

interface TestStep {
  order: number;
  action: string;
  description: string;
  url?: string;
  element?: string;
  expected?: string;
}

interface ProposedTestCase {
  id: string;
  title: string;
  type: string;
  priority: string;
  source: string;
  risk: string;
  module?: string;
  screen?: string;
  steps: TestStep[];
  expected_results: string[];
}

interface NavEvent {
  type: string;
  message: string;
  timestamp?: string;
  url?: string;
}

interface DiscoverySession {
  id: string; name: string; base_url: string; status: string;
  flow_map: { id: string; name: string; entry_url: string; risk: string; steps?: string[] }[];
  screens: { name: string; url_pattern: string }[];
  apis: { method: string; path: string; purpose: string }[];
  critical_journeys: { name: string; priority: string; test_coverage: string }[];
  coverage_matrix: {
    coverage_percentage?: number;
    screen_inventory?: number;
    proposed_test_cases?: number;
    agent_progress?: {
      phase?: string;
      message?: string;
      url?: string;
      updated_at?: string;
      log_count?: number;
    };
  };
  proposed_test_cases: ProposedTestCase[];
  navigation_log: NavEvent[];
}

function DiscoveryPageContent() {
  const { projectId } = useActiveProject();
  const ws = useWorkspaceScope(projectId);
  const {
    environments,
    modules,
    activeModuleId,
    setActiveModuleId,
    activeEnvironmentId,
    setActiveEnvironmentId,
    activeEnvironment,
    reloadModules,
    moduleQueryIds,
    environmentQueryIds,
  } = ws;
  const prevProjectRef = useRef(projectId);
  const [baseUrl, setBaseUrl] = useState("");
  const [requirements, setRequirements] = useState(
    "Submit enquiry form:\nName: Jane Doe\nEmail: jane@example.com\nPhone: 555-0100\nMessage: I would like a product demo"
  );
  const [running, setRunning] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [sessions, setSessions] = useState<DiscoverySession[]>([]);
  const [active, setActive] = useState<DiscoverySession | null>(null);
  const [message, setMessage] = useState("");
  const [committing, setCommitting] = useState(false);
  const [dismissing, setDismissing] = useState(false);
  const [clearingNav, setClearingNav] = useState(false);
  const [clearingSession, setClearingSession] = useState(false);
  const [commitModuleId, setCommitModuleId] = useState<string>("");
  const [savedCases, setSavedCases] = useState<AutomationTestCase[]>([]);
  const [selectedSaved, setSelectedSaved] = useState<Set<string>>(new Set());
  const [deletingSaved, setDeletingSaved] = useState(false);
  const [newModuleName, setNewModuleName] = useState("");
  const [creatingModule, setCreatingModule] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [playwrightHint, setPlaywrightHint] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const navLogRef = useRef<HTMLDivElement | null>(null);
  const proposedPanelRef = useRef<HTMLDivElement | null>(null);
  const runStartedAtRef = useRef<number | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);

  useEffect(() => {
    const loadHealth = () => {
      apiFetch<{ playwright_browsers?: boolean; playwright_hint?: string }>("/health")
        .then((h) => {
          if (!h.playwright_browsers) {
            const hint = h.playwright_hint ?? "";
            const staleBackend =
              hint.toLowerCase().includes("sync api") || hint.toLowerCase().includes("asyncio loop");
            setPlaywrightHint(
              staleBackend
                ? "Backend is outdated or multiple backends are running on port 8000. Close all QEOS Backend windows, run restart.bat once, then refresh this page."
                : hint ||
                    "Playwright Chromium not installed. Run update-and-install.bat, then restart.bat."
            );
          } else {
            setPlaywrightHint(null);
          }
        })
        .catch(() => {});
    };
    loadHealth();
    const onFocus = () => loadHealth();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, []);

  useEffect(() => {
    if (prevProjectRef.current === projectId) return;
    prevProjectRef.current = projectId;
    setActive(null);
    setSessions([]);
    setSelected(new Set());
    setSavedCases([]);
  }, [projectId]);

  useEffect(() => {
    if (activeEnvironment?.base_url && !baseUrl) {
      setBaseUrl(activeEnvironment.base_url);
    }
  }, [activeEnvironment, baseUrl]);

  const reloadSavedCases = useCallback(async () => {
    if (!projectId || !activeEnvironmentId) return;
    try {
      setSavedCases(
        await fetchTestCases(projectId, {
          moduleIds: moduleQueryIds,
          environmentIds: environmentQueryIds,
        })
      );
    } catch {
      setSavedCases([]);
    }
  }, [projectId, activeEnvironmentId, moduleQueryIds, environmentQueryIds]);

  useEffect(() => {
    reloadSavedCases();
  }, [reloadSavedCases]);

  const refreshSession = useCallback(async (pid: string, sid: string) => {
    const s = await apiFetch<DiscoverySession>(`/api/v1/projects/${pid}/discovery/sessions/${sid}`);
    setActive(s);
    setSessions((prev) => prev.map((x) => (x.id === sid ? s : x)));
    return s;
  }, []);

  useEffect(() => {
    if (!projectId) return;
    apiFetch<DiscoverySession[]>(`/api/v1/projects/${projectId}/discovery/sessions`)
      .then((list) => { setSessions(list); if (list[0] && !active) setActive(list[0]); })
      .catch(() => {});
  }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  const startPolling = useCallback((pid: string, sid: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    runStartedAtRef.current = Date.now();
    setElapsedSec(0);
    pollRef.current = setInterval(async () => {
      try {
        const s = await refreshSession(pid, sid);
        const last = s.navigation_log?.[s.navigation_log.length - 1];
        if (s.status === "running" && last?.message) {
          setMessage(`Agent: ${last.message}`);
        }
        if (runStartedAtRef.current) {
          setElapsedSec(Math.floor((Date.now() - runStartedAtRef.current) / 1000));
        }
        if (s.status !== "running") {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          runStartedAtRef.current = null;
          setRunning(false);
          setStopping(false);
          const count = s.proposed_test_cases?.length ?? 0;
          const ids = (s.proposed_test_cases ?? []).map((t) => t.id);
          setSelected(new Set(ids));
          setExpanded(new Set(ids.slice(0, Math.min(3, ids.length))));
          window.setTimeout(() => {
            proposedPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
          }, 300);
          if (s.status === "cancelled") {
            setMessage(
              count > 0
                ? `Discovery stopped — ${count} test case(s) captured. Review below, then Import to Project.`
                : "Discovery stopped — no test cases captured"
            );
          } else if (s.status === "failed") {
            setMessage("Discovery failed — check the navigation log for details");
          } else {
            setMessage(
              count > 0
                ? `Discovery complete — ${count} test case(s) ready. Review below → Import to Project.`
                : "Discovery complete — no test cases were generated"
            );
          }
        }
      } catch {
        if (pollRef.current) clearInterval(pollRef.current);
        setRunning(false);
        runStartedAtRef.current = null;
      }
    }, 800);
  }, [refreshSession]);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const run = async () => {
    if (!projectId) { setMessage("Select a project"); return; }
    if (playwrightHint) {
      setMessage(`Live browser discovery unavailable: ${playwrightHint}`);
      return;
    }
    setRunning(true);
    setMessage("");
    setSelected(new Set());
    try {
      const session = await apiFetch<DiscoverySession>(`/api/v1/projects/${projectId}/discovery/run`, {
        method: "POST",
        body: JSON.stringify({
          base_url: baseUrl,
          requirements,
          mode: "agent",
          background: true,
        }),
      });
      setSessions((prev) => [session, ...prev]);
      setActive(session);
      if (session.status === "running") {
        setMessage("QA Agent is navigating the application in real time…");
        startPolling(projectId, session.id);
      } else {
        setRunning(false);
        setMessage(`Discovered ${session.proposed_test_cases?.length ?? 0} test cases`);
        setSelected(new Set());
      }
    } catch (e) {
      setMessage(String(e));
      setRunning(false);
    }
  };

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => {
    if (!active?.proposed_test_cases) return;
    setSelected(new Set(active.proposed_test_cases.map((t) => t.id)));
  };

  const deselectAll = () => setSelected(new Set());

  const applySessionUpdate = (session: DiscoverySession) => {
    setActive(session);
    setSessions((prev) => prev.map((x) => (x.id === session.id ? session : x)));
    setSelected(new Set());
    setExpanded(new Set());
  };

  const stopAgent = async () => {
    if (!projectId || !active || active.status !== "running") return;
    setStopping(true);
    setMessage("Stopping agent…");
    try {
      const session = await apiFetch<DiscoverySession>(
        `/api/v1/projects/${projectId}/discovery/sessions/${active.id}/cancel`,
        { method: "POST" }
      );
      applySessionUpdate(session);
    } catch (e) {
      setMessage(String(e));
      setStopping(false);
    }
  };

  const clearNavigation = async () => {
    if (!projectId || !active) return;
    setClearingNav(true);
    setMessage("");
    try {
      const session = await apiFetch<DiscoverySession>(
        `/api/v1/projects/${projectId}/discovery/sessions/${active.id}/clear-navigation`,
        { method: "POST", body: JSON.stringify({}) }
      );
      applySessionUpdate(session);
      setMessage("Live navigation log cleared");
    } catch (e) {
      const err = String(e);
      setMessage(
        err.includes("Not Found")
          ? "Clear failed — run restart.bat so new Discovery APIs load, then try again."
          : err
      );
    } finally {
      setClearingNav(false);
    }
  };

  const clearSession = async () => {
    if (!projectId || !active) return;
    const label = active.name || active.base_url;
    if (
      !window.confirm(
        `Delete discovery session "${label}"? This removes all proposed tests, navigation log, and flow data for this session.`
      )
    ) {
      return;
    }
    setClearingSession(true);
    setMessage("");
    const sid = active.id;
    const wasRunning = active.status === "running";
    try {
      await apiFetch<{ deleted: boolean }>(
        `/api/v1/projects/${projectId}/discovery/sessions/${sid}`,
        { method: "DELETE" }
      );
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      if (wasRunning) setRunning(false);
      const list = await apiFetch<DiscoverySession[]>(
        `/api/v1/projects/${projectId}/discovery/sessions`
      );
      setSessions(list);
      setActive(list[0] ?? null);
      setSelected(new Set());
      setExpanded(new Set());
      setMessage("Discovery session cleared");
    } catch (e) {
      const err = String(e);
      setMessage(
        err.includes("Not Found")
          ? "Delete failed — run restart.bat so new Discovery APIs load, then try again."
          : err
      );
    } finally {
      setClearingSession(false);
    }
  };

  const removeSelected = async () => {
    if (!projectId || !active || selected.size === 0) return;
    if (!window.confirm(`Remove ${selected.size} proposed test case(s) from this session? (Not deleted from project if already committed.)`)) {
      return;
    }
    setDismissing(true);
    setMessage("");
    try {
      const result = await apiFetch<{
        removed_count: number;
        remaining_count: number;
        session?: DiscoverySession;
      }>(
        `/api/v1/projects/${projectId}/discovery/sessions/${active.id}/dismiss-tests`,
        { method: "POST", body: JSON.stringify({ test_ids: Array.from(selected) }) }
      );
      if (result.session) {
        applySessionUpdate(result.session);
      } else if (projectId) {
        await refreshSession(projectId, active.id);
        setSelected(new Set());
      }
      setMessage(`Removed ${result.removed_count} proposed test case(s) — ${result.remaining_count} remaining`);
    } catch (e) {
      setMessage(String(e));
    } finally {
      setDismissing(false);
    }
  };

  const commitSelected = async () => {
    if (!projectId || !active || selected.size === 0) return;
    setCommitting(true);
    setMessage("");
    try {
      const result = await apiFetch<{
        committed_count: number;
        test_cases: { id: string; title: string; case_code?: string; module_id?: string | null; environment_id?: string | null }[];
        remaining_proposed?: number;
        session?: DiscoverySession;
      }>(
        `/api/v1/projects/${projectId}/discovery/sessions/${active.id}/commit-tests`,
        {
          method: "POST",
          body: JSON.stringify({
            test_ids: Array.from(selected),
            module_id: commitModuleId && !commitModuleId.startsWith("temp-") ? commitModuleId : undefined,
            environment_id: activeEnvironmentId ?? undefined,
          }),
        }
      );
      if (result.session) {
        applySessionUpdate(result.session);
      } else if (projectId) {
        await refreshSession(projectId, active.id);
        setSelected(new Set());
      }
      await reloadModules();
      const importEnvId = activeEnvironmentId ?? result.test_cases[0]?.environment_id ?? undefined;
      try {
        setSavedCases(
          await fetchTestCases(projectId, {
            environmentIds: importEnvId ? [importEnvId] : environmentQueryIds,
          })
        );
      } catch {
        await reloadSavedCases();
      }
      const moduleIds = [
        ...new Set(result.test_cases.map((c) => c.module_id).filter((id): id is string => Boolean(id))),
      ];
      notifyTestCasesUpdated({
        projectId,
        caseIds: result.test_cases.map((c) => c.id),
        environmentId: importEnvId ?? null,
        moduleIds,
      });
      setMessage(
        `Saved ${result.committed_count} test case(s) with FTC naming` +
          (result.remaining_proposed != null ? ` — ${result.remaining_proposed} still in review` : "") +
          " — open Automation IDE to debug or generate scripts."
      );
    } catch (e) {
      setMessage(String(e));
    } finally {
      setCommitting(false);
    }
  };

  const eventIcon = (type: string) => {
    if (type === "navigate") return "🌐";
    if (type === "click") return "👆";
    if (type === "fill") return "⌨️";
    if (type === "verify") return "✅";
    if (type === "inspect") return "🔍";
    if (type === "error") return "❌";
    if (type === "agent_complete") return "🏁";
    if (type === "status") return "⏳";
    if (type === "warning") return "⚠️";
    if (type === "observe") return "👁️";
    if (type === "action") return "🤖";
    return "•";
  };

  const proposed = active?.proposed_test_cases ?? [];
  const navLog = active?.navigation_log ?? [];
  const agentProgress = active?.coverage_matrix?.agent_progress;

  useEffect(() => {
    if (!navLogRef.current || navLog.length === 0) return;
    navLogRef.current.scrollTop = navLogRef.current.scrollHeight;
  }, [navLog.length, agentProgress?.updated_at]);

  const displayModules = useMemo((): ProjectModule[] => {
    const byName = new Map(modules.map((m) => [m.name.toLowerCase(), m]));
    for (const p of proposed) {
      const name = p.module || p.screen || "General";
      if (!byName.has(name.toLowerCase())) {
        byName.set(name.toLowerCase(), {
          id: `temp-${name}`,
          project_id: projectId || "",
          environment_id: activeEnvironmentId,
          name,
          code: name.replace(/[^A-Za-z0-9]/g, "").slice(0, 5).toUpperCase().padEnd(5, "X"),
          description: "Discovered module",
          test_case_count: 0,
          created_at: "",
        });
      }
    }
    return [...byName.values()].sort((a, b) => a.name.localeCompare(b.name));
  }, [modules, proposed, projectId, activeEnvironmentId]);

  // Show all proposed cases — workspace module filter only applies to saved cases below.
  const reviewProposed = proposed;

  const filteredSaved = savedCases;

  const addModule = async () => {
    if (!projectId || !newModuleName.trim() || !activeEnvironmentId) return;
    setCreatingModule(true);
    try {
      await createModule(projectId, activeEnvironmentId, newModuleName.trim());
      setNewModuleName("");
      await reloadModules();
      setMessage(`Module "${newModuleName.trim()}" created`);
    } catch (e) {
      setMessage(String(e));
    } finally {
      setCreatingModule(false);
    }
  };

  const deleteSavedSelected = async () => {
    if (!projectId || selectedSaved.size === 0) return;
    if (
      !window.confirm(
        `Delete ${selectedSaved.size} saved test case(s)?\n\nThis cannot be undone. Deleted test cases cannot be restored.`
      )
    ) {
      return;
    }
    setDeletingSaved(true);
    const count = selectedSaved.size;
    try {
      await bulkTestCaseAction(projectId, "delete", Array.from(selectedSaved));
      setSelectedSaved(new Set());
      await reloadSavedCases();
      await reloadModules();
      setMessage(`Deleted ${count} test case(s)`);
    } catch (e) {
      setMessage(String(e));
    } finally {
      setDeletingSaved(false);
    }
  };

  const selectAllFiltered = () => {
    setSelected(new Set(reviewProposed.map((t) => t.id)));
  };

  return (
    <AppShell title="App Discovery">
      <PageHeader
        title="QA Agent Discovery"
        subtitle="AI navigates your app like a real QA user — captures test cases with steps for your review"
        breadcrumbs={[{ label: "Quality Engineering" }, { label: "Discovery" }]}
        actions={<Badge variant="success"><Bot className="w-3 h-3" /> QA Agent</Badge>}
      />

      {playwrightHint && (
        <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950">
          <p className="font-medium">Playwright not ready — QA Agent will only do a basic HTTP crawl until this is fixed.</p>
          <p className="mt-1 text-xs">{playwrightHint}</p>
          <p className="mt-2 text-xs font-mono">update-and-install.bat → restart.bat</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="space-y-4">
          <div className="ds-card">
            <div className="ds-card-header"><h2 className="text-sm font-semibold">Environment</h2></div>
            <div className="ds-card-body space-y-3 pt-0">
              <input className="ds-input text-sm font-mono" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://your-app.com" />
              <div>
                <label className="text-xs font-medium text-[var(--text-secondary)] block mb-1">
                  Discovery prompt
                </label>
                <textarea
                  className="ds-input text-xs resize-none w-full"
                  rows={5}
                  value={requirements}
                  onChange={(e) => setRequirements(e.target.value)}
                  placeholder={
                    "Describe exactly what the agent should do — it follows these instructions only.\n\n" +
                    "Examples:\n" +
                    "• Submit enquiry form with fields:\n  Name: Jane Doe\n  Email: jane@example.com\n  Message: Product demo request\n" +
                    "• Login as admin/admin123, open Payroll and verify employee list\n" +
                    "• No login — open Contact page and submit the form\n\n" +
                    "Use field labels that match the form (Name, Email, Message, etc.). Add 'explore all modules' only for broad discovery."
                  }
                  suppressHydrationWarning
                />
                <p className="text-[10px] text-[var(--text-tertiary)] mt-1.5">
                  Put the site URL in <strong>Base URL</strong> above only — do not repeat it in this prompt.
                  The agent fills and submits forms when you list field names and values (Name, Email, Message, etc.).
                </p>
              </div>
              <div className="flex gap-2">
                <button onClick={run} disabled={running || !!playwrightHint} className="ds-btn-primary flex-1">
                  {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                  {running ? "Agent Exploring…" : "Start QA Agent"}
                </button>
                {running && (
                  <button
                    type="button"
                    onClick={stopAgent}
                    disabled={stopping}
                    className="ds-btn-secondary shrink-0 inline-flex items-center gap-1.5 px-3 border-red-200 text-red-700 hover:bg-red-50"
                    title="Stop the running discovery agent"
                  >
                    {stopping ? <Loader2 className="w-4 h-4 animate-spin" /> : <Square className="w-4 h-4 fill-current" />}
                    Stop Agent
                  </button>
                )}
              </div>
            </div>
          </div>

          {active?.status === "running" && (
            <div className="ds-card border-brand-200 bg-brand-50">
              <div className="ds-card-body flex items-center justify-between gap-2 py-3">
                <div className="flex items-center gap-2 min-w-0">
                  <Loader2 className="w-4 h-4 animate-spin text-brand-700 shrink-0" />
                  <p className="text-xs text-brand-800 truncate">Agent is navigating {active.base_url}…</p>
                </div>
                <button
                  type="button"
                  onClick={stopAgent}
                  disabled={stopping}
                  className="text-xs py-1 px-2 inline-flex items-center gap-1 rounded-md border border-red-200 text-red-700 hover:bg-red-50 disabled:opacity-50 shrink-0"
                >
                  {stopping ? <Loader2 className="w-3 h-3 animate-spin" /> : <Square className="w-3 h-3 fill-current" />}
                  Stop
                </button>
              </div>
            </div>
          )}

          <div className="ds-card">
            <div className="ds-card-header"><h2 className="text-sm font-semibold">Environment & Modules</h2></div>
            <div className="ds-card-body space-y-2 pt-0">
              <WorkspaceFilters
                environments={environments}
                modules={displayModules}
                activeEnvironmentId={activeEnvironmentId}
                activeModuleId={activeModuleId}
                onEnvironmentChange={setActiveEnvironmentId}
                onModuleChange={setActiveModuleId}
              />
              <div className="flex gap-1">
                <input
                  className="ds-input text-xs flex-1"
                  placeholder="New module name"
                  value={newModuleName}
                  onChange={(e) => setNewModuleName(e.target.value)}
                />
                <button type="button" onClick={addModule} disabled={creatingModule || !newModuleName.trim()} className="ds-btn-secondary text-xs px-2">
                  Add
                </button>
              </div>
              <p className="text-[10px] text-[var(--text-tertiary)]">
                Naming: {"{PROJ5}_{ENV5}_{MOD5}_FTC#####"} · scoped per environment + module
              </p>
            </div>
          </div>

          <div className="ds-card">
            <div className="ds-card-header flex items-center justify-between gap-2">
              <div>
                <h2 className="text-sm font-semibold">Live Navigation</h2>
                {running && (
                  <p className="text-[10px] text-brand-700 mt-0.5 flex items-center gap-1">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Running {elapsedSec > 0 ? `· ${elapsedSec}s` : ""}
                    {navLog.length > 0 ? ` · ${navLog.length} events` : ""}
                  </p>
                )}
              </div>
              {active && (
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={clearNavigation}
                    disabled={clearingNav || navLog.length === 0}
                    className="ds-btn-secondary text-[10px] py-1 px-2 inline-flex items-center gap-1"
                    title="Clear the live navigation log for this session"
                  >
                    {clearingNav ? <Loader2 className="w-3 h-3 animate-spin" /> : <Eraser className="w-3 h-3" />}
                    Clear log
                  </button>
                  <button
                    type="button"
                    onClick={clearSession}
                    disabled={clearingSession}
                    className="text-[10px] py-1 px-2 inline-flex items-center gap-1 rounded-md border border-red-200 text-red-700 hover:bg-red-50 disabled:opacity-50"
                    title="Delete this discovery session entirely"
                  >
                    {clearingSession ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                    Clear session
                  </button>
                </div>
              )}
            </div>
            {running && agentProgress?.message && (
              <div className="px-4 py-2 bg-brand-50 border-b border-brand-100 text-xs text-brand-800">
                <span className="font-medium capitalize">{agentProgress.phase ?? "status"}:</span>{" "}
                {agentProgress.message}
              </div>
            )}
            <div
              ref={navLogRef}
              className="ds-card-body pt-0 max-h-72 overflow-auto space-y-1 font-mono"
            >
              {navLog.length === 0 && running && (
                <p className="text-xs text-[var(--text-tertiary)]">
                  Waiting for agent… (browser launch can take 10–30s)
                </p>
              )}
              {navLog.length === 0 && !running && (
                <p className="text-xs text-[var(--text-tertiary)]">Agent activity will appear here…</p>
              )}
              {navLog.map((e, i) => (
                <div key={`${i}-${e.timestamp ?? e.message}`} className="text-xs flex gap-2 py-1 border-b border-[var(--border-default)]/50">
                  <span className="shrink-0">{eventIcon(e.type)}</span>
                  <span className="text-[var(--text-secondary)] flex-1">{e.message}</span>
                </div>
              ))}
            </div>
          </div>

          {sessions.length > 0 && (
            <div className="ds-card">
              <div className="ds-card-header"><h2 className="text-sm font-semibold">Sessions</h2></div>
              <div className="ds-card-body space-y-1 pt-0">
                {sessions.map((s) => (
                  <button key={s.id} onClick={() => setActive(s)}
                    className={`w-full text-left px-3 py-2 rounded-md text-xs ${active?.id === s.id ? "bg-brand-50" : "hover:bg-[var(--surface-sunken)]"}`}>
                    <span className="font-medium flex items-center gap-1">
                      {s.status === "running" && <Loader2 className="w-3 h-3 animate-spin" />}
                      {s.name}
                    </span>
                    <span className="block text-[var(--text-tertiary)] truncate">{s.base_url}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="lg:col-span-2 space-y-4">
          {active ? (
            <>
              <div className="grid grid-cols-4 gap-3">
                <MetricCard label="Proposed Tests" value={reviewProposed.length} icon={<CheckCircle2 className="w-4 h-4" />} />
                <MetricCard label="Screens" value={active.screens.length} icon={<Globe className="w-4 h-4" />} />
                <MetricCard label="Flows" value={active.flow_map.length} icon={<MapIcon className="w-4 h-4" />} />
                <MetricCard label="Status" value={active.status} />
              </div>

              {reviewProposed.length > 0 && active.status !== "running" && (
                <div className="rounded-lg border border-brand-200 bg-brand-50 px-4 py-3 text-sm text-brand-900">
                  <p className="font-medium">Next step: import test cases into your project</p>
                  <ol className="mt-1.5 text-xs text-brand-800 list-decimal list-inside space-y-0.5">
                    <li>Review each proposed test — click the row to expand steps and expected results</li>
                    <li>Check the boxes for cases you want (or use Select All)</li>
                    <li>Choose a target module if needed, then click <strong>Import to Project</strong></li>
                  </ol>
                </div>
              )}

              <div className="ds-card" ref={proposedPanelRef}>
                <div className="ds-card-header flex items-center justify-between flex-wrap gap-2">
                  <div>
                    <h2 className="text-sm font-semibold">AI-Proposed Test Cases</h2>
                    <p className="text-xs text-[var(--text-tertiary)]">
                      Review discovery results here · import saves under Project → Environment → Module
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2 items-center">
                    <select
                      className="ds-input text-xs py-1.5"
                      value={commitModuleId}
                      onChange={(e) => setCommitModuleId(e.target.value)}
                      title="Target module when importing selected cases"
                    >
                      <option value="">Auto module (from discovery)</option>
                      {displayModules.map((m) => (
                        <option key={m.id} value={m.id.startsWith("temp-") ? "" : m.id}>{m.name}</option>
                      ))}
                    </select>
                    <button onClick={selectAllFiltered} className="ds-btn-secondary text-xs" disabled={!reviewProposed.length}>
                      Select All
                    </button>
                    <button onClick={deselectAll} className="ds-btn-secondary text-xs" disabled={selected.size === 0}>
                      Deselect All
                    </button>
                    <button
                      onClick={removeSelected}
                      disabled={dismissing || selected.size === 0}
                      className="ds-btn-secondary text-xs text-red-700 border-red-200 hover:bg-red-50"
                    >
                      {dismissing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                      Remove Selected ({selected.size})
                    </button>
                    <button onClick={commitSelected} disabled={committing || selected.size === 0} className="ds-btn-primary text-xs">
                      {committing ? <Loader2 className="w-3 h-3 animate-spin" /> : <GitCommitHorizontal className="w-3 h-3" />}
                      Import to Project ({selected.size})
                    </button>
                  </div>
                </div>
                <div className="ds-card-body space-y-2 pt-0">
                  {reviewProposed.length === 0 && active.status === "running" && (
                    <p className="text-sm text-[var(--text-tertiary)] py-8 text-center">
                      QA Agent is exploring — test cases will appear as navigation progresses…
                    </p>
                  )}
                  {reviewProposed.length === 0 && active.status !== "running" && (
                    <p className="text-sm text-[var(--text-tertiary)] py-8 text-center">
                      No test cases were generated for this session. Try a longer discovery run or a different prompt.
                    </p>
                  )}
                  {reviewProposed.map((tc) => (
                    <div key={tc.id} className={`rounded-lg border p-3 ${selected.has(tc.id) ? "border-brand-300 bg-brand-50/30" : "border-[var(--border-default)]"}`}>
                      <div className="flex items-start gap-3">
                        <button onClick={() => toggleSelect(tc.id)} className="mt-0.5 shrink-0">
                          {selected.has(tc.id)
                            ? <CheckSquare className="w-4 h-4 text-brand-700" />
                            : <Square className="w-4 h-4 text-gray-400" />}
                        </button>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-medium">{tc.title}</span>
                            {(tc.module || tc.screen) && (
                              <Badge variant="neutral">{tc.module || tc.screen}</Badge>
                            )}
                            <Badge variant={tc.priority === "critical" || tc.priority === "high" ? "error" : "neutral"}>{tc.priority}</Badge>
                            <Badge variant="info">{tc.type}</Badge>
                          </div>
                          <button onClick={() => toggleExpand(tc.id)} className="flex items-center gap-1 text-xs text-brand-700 mt-2">
                            {expanded.has(tc.id) ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                            {tc.steps?.length ?? 0} steps · {tc.expected_results?.length ?? 0} expected results
                          </button>
                          {expanded.has(tc.id) && (
                            <div className="mt-3 space-y-3">
                              <div>
                                <p className="text-xs font-semibold text-[var(--text-secondary)] mb-1.5">Test Steps</p>
                                <ol className="space-y-1.5">
                                  {(tc.steps ?? []).map((step) => (
                                    <li key={step.order} className="text-xs flex gap-2">
                                      <span className="w-5 h-5 rounded-full bg-gray-100 text-gray-600 flex items-center justify-center shrink-0 font-mono">{step.order}</span>
                                      <div>
                                        <span className="font-medium capitalize text-brand-700">{step.action}</span>
                                        {" — "}{step.description}
                                        {step.url && <span className="block font-mono text-[var(--text-tertiary)] truncate">{step.url}</span>}
                                      </div>
                                    </li>
                                  ))}
                                </ol>
                              </div>
                              <div>
                                <p className="text-xs font-semibold text-[var(--text-secondary)] mb-1">Expected Results</p>
                                <ul className="text-xs space-y-0.5 text-[var(--text-secondary)]">
                                  {(tc.expected_results ?? []).map((er, i) => (
                                    <li key={i}>• {er}</li>
                                  ))}
                                </ul>
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="ds-card">
                <div className="ds-card-header flex items-center justify-between flex-wrap gap-2">
                  <div>
                    <h2 className="text-sm font-semibold">Saved Test Cases ({filteredSaved.length})</h2>
                    <p className="text-xs text-[var(--text-tertiary)]">Project modules · FTC naming · filter with sidebar</p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setSelectedSaved(new Set(filteredSaved.map((c) => c.id)))}
                      className="ds-btn-secondary text-xs"
                      disabled={!filteredSaved.length}
                    >
                      Select all
                    </button>
                    <button
                      type="button"
                      onClick={deleteSavedSelected}
                      disabled={deletingSaved || selectedSaved.size === 0}
                      className="ds-btn-secondary text-xs text-red-700"
                    >
                      {deletingSaved ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                      Delete ({selectedSaved.size})
                    </button>
                  </div>
                </div>
                <div className="ds-card-body space-y-1 pt-0 max-h-64 overflow-auto">
                  {filteredSaved.length === 0 && (
                    <p className="text-xs text-[var(--text-tertiary)] py-4 text-center">No saved cases for this module filter.</p>
                  )}
                  {filteredSaved.map((tc) => (
                    <div key={tc.id} className="flex items-start gap-2 py-1.5 border-b border-[var(--border-default)]/40">
                      <button type="button" onClick={() => {
                        setSelectedSaved((prev) => {
                          const next = new Set(prev);
                          if (next.has(tc.id)) next.delete(tc.id); else next.add(tc.id);
                          return next;
                        });
                      }} className="shrink-0 mt-0.5">
                        {selectedSaved.has(tc.id) ? (
                          <CheckSquare className="w-3.5 h-3.5 text-brand-700" />
                        ) : (
                          <Square className="w-3.5 h-3.5 text-gray-400" />
                        )}
                      </button>
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-mono font-medium truncate">{tc.case_code || tc.title}</p>
                        <p className="text-[10px] text-[var(--text-tertiary)] truncate">
                          {tc.environment_name && <Badge variant="neutral">{tc.environment_name}</Badge>}
                          {tc.module_name || "General"} · {tc.priority} · {tc.status}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {projectId && (
                <p className="text-xs text-[var(--text-tertiary)]">
                  Imported test cases appear in{" "}
                  <Link href={`/projects/${projectId}`} className="text-brand-700 underline">Project → Test Cases</Link>
                  {" "}and in Studio for automation.
                </p>
              )}
            </>
          ) : (
            <div className="ds-card p-16 text-center">
              <Radar className="w-10 h-10 text-[var(--text-tertiary)] mx-auto mb-4" />
              <p className="text-sm text-[var(--text-tertiary)]">Enter an environment URL and start the QA Agent</p>
            </div>
          )}
        </div>
      </div>

      {message && <p className="mt-4 text-sm p-3 rounded-md bg-[var(--surface-sunken)]">{message}</p>}
    </AppShell>
  );
}

export default function DiscoveryPage() {
  return (
    <Suspense fallback={<div className="p-6">Loading…</div>}>
      <DiscoveryPageContent />
    </Suspense>
  );
}
