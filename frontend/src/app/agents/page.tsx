"use client";

import { useEffect, useState } from "react";
import { Play, Loader2, ChevronRight, Copy, Check } from "lucide-react";
import { AppShell } from "@/components/shell/AppShell";
import { PageHeader, Badge, Tabs, StatusDot } from "@/components/ui";
import { useActiveProject } from "@/context/ProjectContext";
import { apiFetch } from "@/lib/api";

interface Agent {
  type: string;
  name: string;
  description: string;
}

const SAMPLE_INPUT = `As a registered customer, I want to add items to my shopping cart and proceed to checkout, so that I can complete my purchase online.

Acceptance Criteria:
- User can add multiple items to cart
- Cart total updates correctly
- Checkout requires valid payment details
- Order confirmation is displayed after successful payment`;

export default function AgentsPage() {
  const { projectId } = useActiveProject();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selected, setSelected] = useState("requirements");
  const [input, setInput] = useState(SAMPLE_INPUT);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState("output");

  useEffect(() => {
    apiFetch<{ agents: Agent[] }>("/api/v1/agents")
      .then((d) => setAgents(d.agents))
      .catch(() => {});
  }, []);

  const selectedAgent = agents.find((a) => a.type === selected);

  const runAgent = async () => {
    if (!projectId) { setError("Select a project first"); return; }
    setRunning(true);
    setResult(null);
    setError(null);
    try {
      const response = await apiFetch<{ status: string; output?: Record<string, unknown>; error?: string }>(
        "/api/v1/agents/run",
        {
          method: "POST",
          body: JSON.stringify({
            agent_type: selected,
            project_id: projectId,
            input_data: { content: input, source_type: "user_story" },
          }),
        }
      );
      if (response.error) setError(response.error);
      else setResult(response.output ?? null);
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
    }
  };

  const copyOutput = () => {
    if (result) {
      navigator.clipboard.writeText(JSON.stringify(result, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const testCaseCount = result?.test_cases ? (result.test_cases as unknown[]).length : 0;

  return (
    <AppShell title="Agents">
      <PageHeader
        title="Agent Workspace"
        subtitle="Run quality engineering agents powered by QEOS Native Intelligence"
        breadcrumbs={[{ label: "Quality Engineering" }, { label: "Agents" }]}
        actions={
          <div className="flex items-center gap-2">
            <Badge variant="info">qeos-native</Badge>
            <Badge variant="neutral">No external LLM</Badge>
          </div>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Agent list */}
        <div className="lg:col-span-3 space-y-1">
          {agents.map((agent) => (
            <button
              key={agent.type}
              onClick={() => { setSelected(agent.type); setResult(null); setError(null); }}
              className={`w-full text-left px-4 py-3 rounded-lg border transition-all ${
                selected === agent.type
                  ? "border-brand-700 bg-brand-50 shadow-xs"
                  : "border-[var(--border-default)] bg-white hover:border-[var(--border-strong)]"
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <StatusDot status="online" />
                <span className="text-sm font-medium text-[var(--text-primary)]">{agent.name}</span>
              </div>
              <p className="text-xs text-[var(--text-tertiary)] leading-relaxed pl-4">{agent.description}</p>
            </button>
          ))}
        </div>

        {/* Workspace */}
        <div className="lg:col-span-9 space-y-4">
          {/* Input panel */}
          <div className="ds-card">
            <div className="ds-card-header">
              <div>
                <h2 className="text-sm font-semibold">{selectedAgent?.name ?? "Agent"}</h2>
                <p className="text-xs text-[var(--text-tertiary)]">Input requirements or test data</p>
              </div>
              <button
                onClick={runAgent}
                disabled={running || !input.trim() || !projectId}
                className="ds-btn-primary"
              >
                {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                Execute
              </button>
            </div>
            <div className="ds-card-body pt-0">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                rows={10}
                className="ds-input font-mono text-xs leading-relaxed resize-none"
                placeholder="Paste user stories, acceptance criteria, BRD content..."
              />
            </div>
          </div>

          {/* Output panel */}
          {(result || error) && (
            <div className="ds-card">
              <div className="px-6 pt-4">
                <Tabs
                  tabs={[
                    { id: "output", label: "Output", count: testCaseCount || undefined },
                    { id: "raw", label: "Raw JSON" },
                  ]}
                  active={activeTab}
                  onChange={setActiveTab}
                />
              </div>

              {error ? (
                <div className="ds-card-body">
                  <div className="p-4 rounded-md bg-red-50 border border-red-200 text-sm text-red-700">{error}</div>
                </div>
              ) : activeTab === "output" && result ? (
                <div className="ds-card-body space-y-4 pt-4">
                  {!!result.test_scenarios && (
                    <div>
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)] mb-2">
                        Scenarios ({(result.test_scenarios as string[]).length})
                      </h3>
                      <ul className="space-y-1.5">
                        {(result.test_scenarios as string[]).map((s, i) => (
                          <li key={i} className="flex items-start gap-2 text-sm text-[var(--text-secondary)]">
                            <ChevronRight className="w-3.5 h-3.5 mt-0.5 shrink-0 text-brand-700" />
                            {s}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {!!result.test_cases && (
                    <div>
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)] mb-2">
                        Test Cases
                      </h3>
                      <div className="space-y-2">
                        {(result.test_cases as Record<string, unknown>[]).map((tc, i) => (
                          <div key={i} className="p-3 rounded-md border border-[var(--border-default)] bg-[var(--surface-sunken)]/50">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-sm font-medium text-[var(--text-primary)]">{tc.title as string}</span>
                              <Badge variant={tc.priority === "high" ? "error" : tc.priority === "low" ? "neutral" : "warning"}>
                                {tc.priority as string}
                              </Badge>
                            </div>
                            <p className="text-xs text-[var(--text-tertiary)]">{tc.description as string}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {!!result.risk_analysis && (
                    <div className="p-4 rounded-md border border-amber-200 bg-amber-50">
                      <h3 className="text-xs font-semibold text-amber-800 mb-1">Risk Analysis</h3>
                      <p className="text-sm text-amber-700">
                        Overall risk: {(result.risk_analysis as Record<string, string>).overall_risk_score}
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                <div className="ds-card-body pt-4">
                  <div className="relative">
                    <button onClick={copyOutput} className="absolute top-2 right-2 ds-btn-ghost p-1.5">
                      {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                    </button>
                    <pre className="p-4 rounded-md bg-gray-900 text-gray-100 text-xs font-mono overflow-auto max-h-96 leading-relaxed">
                      {JSON.stringify(result, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
