"use client";

import { useEffect, useState } from "react";
import { BarChart3, TrendingUp, Shield, Clock, CheckCircle2 } from "lucide-react";
import { AppShell } from "@/components/shell/AppShell";
import { PageHeader, MetricCard, Badge, Tabs } from "@/components/ui";
import { useActiveProject } from "@/context/ProjectContext";
import { apiFetch } from "@/lib/api";

interface ReportOverview {
  quality_score: number;
  release_risk: string;
  automation_roi_percent: number;
  avg_cycle_hours: number;
  coverage_average: number;
  totals: Record<string, number>;
  tester_dashboard: { pass_rate: number; tests_generated: number; executions_run: number };
  engineering_dashboard: { automation_coverage: number; pipeline_success_rate: number; failed_executions: number };
  executive_dashboard: { quality_score: number; estimated_manual_hours_saved: number; automation_assets: number };
}

export default function ReportsPage() {
  const { projectId, activeProject } = useActiveProject();
  const [data, setData] = useState<ReportOverview | null>(null);
  const [projectData, setProjectData] = useState<ReportOverview | null>(null);
  const [tab, setTab] = useState("platform");
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<ReportOverview>("/api/v1/reports/overview")
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!projectId) { setProjectData(null); return; }
    apiFetch<ReportOverview>(`/api/v1/reports/projects/${projectId}`)
      .then(setProjectData)
      .catch((e) => setError(String(e)));
  }, [projectId]);

  const view = tab === "platform" ? data : projectData;

  const riskVariant = view?.release_risk === "low" ? "success" : view?.release_risk === "medium" ? "warning" : "error";

  return (
    <AppShell title="Reports">
      <PageHeader
        title="Quality Reports"
        subtitle="Live metrics from projects, executions, and pipelines"
        breadcrumbs={[{ label: "Quality Engineering" }, { label: "Reports" }]}
        actions={<Badge variant="success">Phase 5 — Live Data</Badge>}
      />

      <div className="mb-4 flex flex-wrap items-center gap-4">
        <Tabs
          tabs={[
            { id: "platform", label: "Platform Overview" },
            { id: "project", label: "Project Report" },
          ]}
          active={tab}
          onChange={setTab}
        />
        {tab === "project" && activeProject && (
          <span className="text-sm text-[var(--text-secondary)]">{activeProject.name}</span>
        )}
      </div>

      {error && <p className="text-sm text-red-600 mb-4">{error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <MetricCard label="Quality Score" value={view?.quality_score ?? "—"} icon={<BarChart3 className="w-4 h-4" />} />
        <MetricCard
          label="Release Risk"
          value={view?.release_risk ?? "—"}
          change={`${view?.coverage_average ?? 0}% avg coverage`}
          changeType={view?.release_risk === "low" ? "positive" : "negative"}
          icon={<Shield className="w-4 h-4" />}
        />
        <MetricCard label="Automation ROI" value={`${view?.automation_roi_percent ?? 0}%`} icon={<TrendingUp className="w-4 h-4" />} />
        <MetricCard label="Avg Cycle Time" value={`${view?.avg_cycle_hours ?? 0}h`} icon={<Clock className="w-4 h-4" />} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {[
          {
            title: "Tester Dashboard",
            items: [
              `Pass rate: ${view?.tester_dashboard.pass_rate ?? 0}%`,
              `Tests generated: ${view?.tester_dashboard.tests_generated ?? 0}`,
              `Executions run: ${view?.tester_dashboard.executions_run ?? 0}`,
            ],
          },
          {
            title: "Engineering Dashboard",
            items: [
              `Automation coverage: ${view?.engineering_dashboard.automation_coverage ?? 0} assets/project`,
              `Pipeline success: ${view?.engineering_dashboard.pipeline_success_rate ?? 0}%`,
              `Failed executions: ${view?.engineering_dashboard.failed_executions ?? 0}`,
            ],
          },
          {
            title: "Executive Dashboard",
            items: [
              `Quality score: ${view?.executive_dashboard.quality_score ?? 0}/100`,
              `Hours saved (est.): ${view?.executive_dashboard.estimated_manual_hours_saved ?? 0}`,
              `Automation assets: ${view?.executive_dashboard.automation_assets ?? 0}`,
            ],
          },
        ].map((dash) => (
          <div key={dash.title} className="ds-card">
            <div className="ds-card-header">
              <h2 className="text-sm font-semibold">{dash.title}</h2>
              <Badge variant={riskVariant as "success" | "warning" | "error"}>Live</Badge>
            </div>
            <ul className="ds-card-body space-y-2 pt-0">
              {dash.items.map((item) => (
                <li key={item} className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {view && (
        <div className="ds-card mt-6">
          <div className="ds-card-header"><h2 className="text-sm font-semibold">Totals</h2></div>
          <div className="ds-card-body grid grid-cols-2 md:grid-cols-4 gap-4 pt-0">
            {Object.entries(view.totals).map(([k, v]) => (
              <div key={k}>
                <p className="text-xs text-[var(--text-tertiary)] capitalize">{k.replace(/_/g, " ")}</p>
                <p className="text-lg font-semibold">{v}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </AppShell>
  );
}
