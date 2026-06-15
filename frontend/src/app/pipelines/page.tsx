"use client";

import { useEffect, useState } from "react";
import { Play, Loader2, CheckCircle2, XCircle, Workflow } from "lucide-react";
import { AppShell } from "@/components/shell/AppShell";
import { PageHeader, Badge } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useActiveProject } from "@/context/ProjectContext";

interface PipelineTemplate {
  name: string; steps: string[]; description: string;
}
interface PipelineRun {
  id: string; name: string; status: string;
  pipeline: string[]; steps: { agent: string; status: string; output?: unknown; error?: string }[];
  created_at: string;
}

const SAMPLE = `As a customer, I want to browse products and checkout, so that I can purchase items online.

Acceptance Criteria:
- User can search and add items to cart
- Checkout requires payment details
- Order confirmation is displayed`;

export default function PipelinesPage() {
  const { projectId } = useActiveProject();
  const [templates, setTemplates] = useState<Record<string, PipelineTemplate>>({});
  const [selectedPipeline, setSelectedPipeline] = useState("full_quality");
  const [content, setContent] = useState(SAMPLE);
  const [running, setRunning] = useState(false);
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [activeRun, setActiveRun] = useState<PipelineRun | null>(null);

  useEffect(() => {
    if (!projectId) return;
    apiFetch<{ templates: Record<string, PipelineTemplate> }>(`/api/v1/projects/${projectId}/pipelines/templates`)
      .then((d) => setTemplates(d.templates)).catch(() => {});
    apiFetch<PipelineRun[]>(`/api/v1/projects/${projectId}/pipelines/runs`)
      .then(setRuns).catch(() => {});
  }, [projectId]);

  const run = async () => {
    if (!projectId) return;
    setRunning(true);
    try {
      const result = await apiFetch<PipelineRun>(`/api/v1/projects/${projectId}/pipelines/run`, {
        method: "POST",
        body: JSON.stringify({ pipeline_key: selectedPipeline, content, framework: "playwright", tool: "k6" }),
      });
      setActiveRun(result);
      setRuns((p) => [result, ...p]);
    } finally {
      setRunning(false);
    }
  };

  return (
    <AppShell title="Pipelines">
      <PageHeader
        title="Autonomous Pipelines"
        subtitle="Multi-agent orchestration — Requirements through Performance"
        breadcrumbs={[{ label: "Quality Engineering" }, { label: "Pipelines" }]}
        actions={<Badge variant="success">Phase 4</Badge>}
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 space-y-4">
          <div className="ds-card p-4 space-y-3">
            <div>
              <label className="block text-xs font-medium mb-1">Pipeline</label>
              {Object.entries(templates).map(([key, t]) => (
                <button key={key} onClick={() => setSelectedPipeline(key)}
                  className={`w-full text-left p-3 rounded-md border mb-2 transition-colors ${
                    selectedPipeline === key ? "border-brand-700 bg-brand-50" : "border-[var(--border-default)] hover:bg-[var(--surface-sunken)]"
                  }`}>
                  <p className="text-sm font-medium">{t.name}</p>
                  <p className="text-xs text-[var(--text-tertiary)] mt-0.5">{t.description}</p>
                  <div className="flex flex-wrap gap-1 mt-2">
                    {t.steps.map((s, i) => (
                      <span key={s} className="text-[10px] px-1.5 py-0.5 bg-gray-100 rounded">
                        {s}{i < t.steps.length - 1 && " →"}
                      </span>
                    ))}
                  </div>
                </button>
              ))}
            </div>
            <button onClick={run} disabled={running || !projectId} className="ds-btn-primary w-full">
              {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              Run Pipeline
            </button>
          </div>

          {runs.length > 0 && (
            <div className="ds-card p-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)] mb-2">History</p>
              {runs.map((r) => (
                <button key={r.id} onClick={() => setActiveRun(r)}
                  className="w-full text-left py-2 border-b border-[var(--border-default)] last:border-0">
                  <div className="flex items-center justify-between">
                    <span className="text-sm">{r.name}</span>
                    <Badge variant={r.status === "completed" ? "success" : "error"}>{r.status}</Badge>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="lg:col-span-2 space-y-4">
          <div className="ds-card">
            <div className="ds-card-header"><h2 className="text-sm font-semibold">Requirements Input</h2></div>
            <div className="ds-card-body pt-0">
              <textarea className="ds-input font-mono text-xs resize-none" rows={6} value={content} onChange={(e) => setContent(e.target.value)} />
            </div>
          </div>

          {(activeRun || running) && (
            <div className="ds-card">
              <div className="ds-card-header">
                <h2 className="text-sm font-semibold flex items-center gap-2">
                  <Workflow className="w-4 h-4" /> Pipeline Execution
                </h2>
                {activeRun && <Badge variant={activeRun.status === "completed" ? "success" : "warning"}>{activeRun.status}</Badge>}
              </div>
              <div className="ds-card-body space-y-3 pt-0">
                {(activeRun?.steps ?? []).map((step, i) => (
                  <div key={i} className="flex items-start gap-3 p-3 rounded-md bg-[var(--surface-sunken)]/50">
                    {step.status === "completed"
                      ? <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                      : <XCircle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />}
                    <div>
                      <p className="text-sm font-medium capitalize">{step.agent.replace(/_/g, " ")}</p>
                      {step.output != null && (
                        <pre className="text-xs text-[var(--text-tertiary)] mt-1 font-mono">
                          {JSON.stringify(step.output, null, 2)}
                        </pre>
                      )}
                      {step.error && <p className="text-xs text-red-600 mt-1">{step.error}</p>}
                    </div>
                  </div>
                ))}
                {running && !activeRun && (
                  <div className="flex items-center gap-2 text-sm text-[var(--text-tertiary)]">
                    <Loader2 className="w-4 h-4 animate-spin" /> Running pipeline...
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
