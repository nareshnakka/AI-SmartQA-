"use client";

import { useEffect, useState, useCallback, useRef, Suspense } from "react";
import Link from "next/link";
import {
  Radar, Loader2, Globe, Map, CheckCircle2, ChevronDown, ChevronRight,
  Bot, Play, CheckSquare, Square, GitCommitHorizontal,
} from "lucide-react";
import { AppShell } from "@/components/shell/AppShell";
import { PageHeader, Badge, MetricCard } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useActiveProject } from "@/context/ProjectContext";

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
  coverage_matrix: { coverage_percentage: number; screen_inventory: number; proposed_test_cases?: number };
  proposed_test_cases: ProposedTestCase[];
  navigation_log: NavEvent[];
}

function DiscoveryPageContent() {
  const { projectId } = useActiveProject();
  const prevProjectRef = useRef(projectId);
  const [baseUrl, setBaseUrl] = useState("https://opensource-demo.orangehrmlive.com");
  const [requirements, setRequirements] = useState(
    "As a user, I want to login, manage employees, and run reports."
  );
  const [running, setRunning] = useState(false);
  const [username, setUsername] = useState("Admin");
  const [password, setPassword] = useState("admin123");
  const [sessions, setSessions] = useState<DiscoverySession[]>([]);
  const [active, setActive] = useState<DiscoverySession | null>(null);
  const [message, setMessage] = useState("");
  const [committing, setCommitting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (prevProjectRef.current === projectId) return;
    prevProjectRef.current = projectId;
    setActive(null);
    setSessions([]);
    setSelected(new Set());
  }, [projectId]);

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
    pollRef.current = setInterval(async () => {
      try {
        const s = await refreshSession(pid, sid);
        if (s.status !== "running") {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setRunning(false);
          setMessage(`Discovery complete — ${s.proposed_test_cases?.length ?? 0} test cases proposed`);
          if (s.proposed_test_cases?.length) {
            setSelected(new Set(s.proposed_test_cases.map((t) => t.id)));
          }
        }
      } catch {
        if (pollRef.current) clearInterval(pollRef.current);
        setRunning(false);
      }
    }, 2000);
  }, [refreshSession]);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const run = async () => {
    if (!projectId) { setMessage("Select a project"); return; }
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
          username: username || undefined,
          password: password || undefined,
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
        if (session.proposed_test_cases?.length) {
          setSelected(new Set(session.proposed_test_cases.map((t) => t.id)));
        }
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

  const commitSelected = async () => {
    if (!projectId || !active || selected.size === 0) return;
    setCommitting(true);
    setMessage("");
    try {
      const result = await apiFetch<{ committed_count: number; test_cases: { id: string; title: string }[] }>(
        `/api/v1/projects/${projectId}/discovery/sessions/${active.id}/commit-tests`,
        { method: "POST", body: JSON.stringify({ test_ids: Array.from(selected) }) }
      );
      setMessage(`Committed ${result.committed_count} test case(s) to project`);
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
    return "•";
  };

  const proposed = active?.proposed_test_cases ?? [];
  const navLog = active?.navigation_log ?? [];

  return (
    <AppShell title="App Discovery">
      <PageHeader
        title="QA Agent Discovery"
        subtitle="AI navigates your app like a real QA user — captures test cases with steps for your review"
        breadcrumbs={[{ label: "Quality Engineering" }, { label: "Discovery" }]}
        actions={<Badge variant="success"><Bot className="w-3 h-3" /> QA Agent</Badge>}
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="space-y-4">
          <div className="ds-card">
            <div className="ds-card-header"><h2 className="text-sm font-semibold">Environment</h2></div>
            <div className="ds-card-body space-y-3 pt-0">
              <input className="ds-input text-sm font-mono" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://your-app.com" />
              <div className="grid grid-cols-2 gap-2">
                <input className="ds-input text-xs" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} />
                <input className="ds-input text-xs" type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
              </div>
              <textarea className="ds-input text-xs resize-none font-mono" rows={3} value={requirements} onChange={(e) => setRequirements(e.target.value)} placeholder="Context for the QA Agent…" />
              <button onClick={run} disabled={running} className="ds-btn-primary w-full">
                {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                {running ? "Agent Exploring…" : "Start QA Agent"}
              </button>
            </div>
          </div>

          {active?.status === "running" && (
            <div className="ds-card border-brand-200 bg-brand-50">
              <div className="ds-card-body flex items-center gap-2 py-3">
                <Loader2 className="w-4 h-4 animate-spin text-brand-700" />
                <p className="text-xs text-brand-800">Agent is navigating {active.base_url}…</p>
              </div>
            </div>
          )}

          <div className="ds-card">
            <div className="ds-card-header"><h2 className="text-sm font-semibold">Live Navigation</h2></div>
            <div className="ds-card-body pt-0 max-h-72 overflow-auto space-y-1">
              {navLog.length === 0 && (
                <p className="text-xs text-[var(--text-tertiary)]">Agent activity will appear here…</p>
              )}
              {[...navLog].reverse().slice(0, 50).map((e, i) => (
                <div key={i} className="text-xs flex gap-2 py-1 border-b border-[var(--border-default)]/50">
                  <span>{eventIcon(e.type)}</span>
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
                <MetricCard label="Proposed Tests" value={proposed.length} icon={<CheckCircle2 className="w-4 h-4" />} />
                <MetricCard label="Screens" value={active.screens.length} icon={<Globe className="w-4 h-4" />} />
                <MetricCard label="Flows" value={active.flow_map.length} icon={<Map className="w-4 h-4" />} />
                <MetricCard label="Status" value={active.status} />
              </div>

              <div className="ds-card">
                <div className="ds-card-header flex items-center justify-between flex-wrap gap-2">
                  <div>
                    <h2 className="text-sm font-semibold">AI-Proposed Test Cases</h2>
                    <p className="text-xs text-[var(--text-tertiary)]">Review steps, select cases to commit to your project</p>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={selectAll} className="ds-btn-secondary text-xs" disabled={!proposed.length}>
                      Select All
                    </button>
                    <button onClick={commitSelected} disabled={committing || selected.size === 0} className="ds-btn-primary text-xs">
                      {committing ? <Loader2 className="w-3 h-3 animate-spin" /> : <GitCommitHorizontal className="w-3 h-3" />}
                      Commit Selected ({selected.size})
                    </button>
                  </div>
                </div>
                <div className="ds-card-body space-y-2 pt-0">
                  {proposed.length === 0 && active.status === "running" && (
                    <p className="text-sm text-[var(--text-tertiary)] py-8 text-center">
                      QA Agent is exploring — test cases will appear as navigation progresses…
                    </p>
                  )}
                  {proposed.length === 0 && active.status !== "running" && (
                    <p className="text-sm text-[var(--text-tertiary)] py-8 text-center">No test cases proposed. Run the QA Agent again.</p>
                  )}
                  {proposed.map((tc) => (
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

              {projectId && (
                <p className="text-xs text-[var(--text-tertiary)]">
                  Committed test cases appear in{" "}
                  <Link href={`/projects/${projectId}`} className="text-brand-700 underline">Project → Test Cases</Link>
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
