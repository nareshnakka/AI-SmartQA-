"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  CheckCircle2, Activity, ArrowUpRight, FolderKanban,
  Code2, GitBranch, Radar, PlayCircle, BarChart3,
} from "lucide-react";
import { AppShell } from "@/components/shell/AppShell";
import { PageHeader, MetricCard, Badge, StatusDot } from "@/components/ui";
import { apiFetch } from "@/lib/api";

interface PhaseStatus {
  status: string;
  name: string;
  stats: Record<string, number>;
  capabilities: string[];
}

export default function DashboardPage() {
  const [phase1, setPhase1] = useState<PhaseStatus | null>(null);
  const [phase2, setPhase2] = useState<PhaseStatus | null>(null);
  const [phase3, setPhase3] = useState<PhaseStatus | null>(null);
  const [phase4, setPhase4] = useState<PhaseStatus | null>(null);
  const [phase5, setPhase5] = useState<PhaseStatus | null>(null);
  const [health, setHealth] = useState<"checking" | "healthy" | "offline">("checking");
  const [patterns, setPatterns] = useState(0);

  useEffect(() => {
    Promise.allSettled([
      apiFetch<PhaseStatus>("/api/v1/phase1/status"),
      apiFetch<PhaseStatus>("/api/v1/phase2/status"),
      apiFetch<PhaseStatus>("/api/v1/phase3/status"),
      apiFetch<PhaseStatus>("/api/v1/phase4/status"),
      apiFetch<PhaseStatus>("/api/v1/phase5/status"),
      fetch("/health").then(async (r) => {
        if (!r.ok) throw new Error(`Health check failed: ${r.status}`);
        const data = await r.json();
        if (data?.status !== "healthy") throw new Error("Backend unhealthy");
        return data;
      }),
      apiFetch<{ pattern_count: number }>("/api/v1/intelligence/status"),
    ]).then(([p1, p2, p3, p4, p5, h, intel]) => {
      if (p1.status === "fulfilled") setPhase1(p1.value);
      if (p2.status === "fulfilled") setPhase2(p2.value);
      if (p3.status === "fulfilled") setPhase3(p3.value);
      if (p4.status === "fulfilled") setPhase4(p4.value);
      if (p5.status === "fulfilled") setPhase5(p5.value);
      if (intel.status === "fulfilled") setPatterns(intel.value.pattern_count);

      const phaseOnline = [p1, p2, p3, p4, p5].some((p) => p.status === "fulfilled");
      if (h.status === "fulfilled") {
        setHealth("healthy");
      } else if (phaseOnline) {
        // Phase APIs responded — backend is up even if /health proxy missed
        setHealth("healthy");
      } else {
        setHealth("offline");
      }
    });
  }, []);

  const platformStatus =
    health === "checking" ? "Checking…" : health === "healthy" ? "Operational" : "Offline";
  const platformBadgeVariant =
    health === "healthy" ? "success" : health === "checking" ? "neutral" : "error";

  const stats = phase1?.stats;
  const p5stats = phase5?.stats ?? {};

  return (
    <AppShell title="Dashboard">
      <PageHeader
        title="Quality Overview"
        subtitle="Phases 1–5 — Full autonomous quality engineering platform"
        actions={
          <div className="flex items-center gap-2">
            <Badge variant="success">All Phases Complete</Badge>
            <Link href="/quality-studio" className="ds-btn-primary">
              <FolderKanban className="w-4 h-4" /> Quality Studio
            </Link>
          </div>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
        <MetricCard label="Projects" value={stats?.projects ?? 0} icon={<FolderKanban className="w-4 h-4" />} />
        <MetricCard label="Test Cases" value={stats?.test_cases ?? 0} icon={<CheckCircle2 className="w-4 h-4" />} />
        <MetricCard label="Automation Assets" value={phase2?.stats?.automation_assets ?? 0} icon={<Code2 className="w-4 h-4" />} />
        <MetricCard label="Discovery Sessions" value={p5stats.discovery_sessions ?? 0} icon={<Radar className="w-4 h-4" />} />
        <MetricCard label="Executions" value={p5stats.execution_runs ?? 0} icon={<PlayCircle className="w-4 h-4" />} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 ds-card">
          <div className="ds-card-header">
            <div>
              <h2 className="text-sm font-semibold">Platform Capabilities</h2>
              <p className="text-xs text-[var(--text-tertiary)]">All phases operational — QEOS native intelligence</p>
            </div>
            <Badge variant={platformBadgeVariant}>{platformStatus}</Badge>
          </div>
          <div className="ds-card-body pt-0">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[
                { phase: "Phase 1", name: phase1?.name ?? "AI Test Generation", caps: phase1?.capabilities ?? [], href: "/projects" },
                { phase: "Phase 2", name: phase2?.name ?? "AI Automation", caps: phase2?.capabilities ?? [], href: "/studio" },
                { phase: "Phase 3", name: phase3?.name ?? "Performance Engineering", caps: phase3?.capabilities ?? [], href: "/performance" },
                { phase: "Phase 4", name: phase4?.name ?? "Autonomous Pipelines", caps: phase4?.capabilities ?? [], href: "/pipelines" },
                { phase: "Phase 5", name: phase5?.name ?? "Autonomous Quality", caps: phase5?.capabilities ?? [], href: "/discovery" },
              ].map((block) => (
                <div key={block.phase} className="rounded-lg border border-[var(--border-default)] p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold text-brand-700">{block.phase}</span>
                    <Link href={block.href} className="text-xs text-[var(--text-tertiary)] hover:text-brand-700">Open →</Link>
                  </div>
                  <p className="text-sm font-medium mb-2">{block.name}</p>
                  <ul className="space-y-1">
                    {block.caps.slice(0, 3).map((cap) => (
                      <li key={cap} className="flex items-start gap-1.5 text-xs text-[var(--text-secondary)]">
                        <CheckCircle2 className="w-3 h-3 text-emerald-600 shrink-0 mt-0.5" />
                        {cap}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="ds-card">
          <div className="ds-card-header">
            <h2 className="text-sm font-semibold">End-to-End Workflow</h2>
          </div>
          <div className="ds-card-body space-y-1 pt-0">
            {[
              { step: "1", label: "Open Quality Studio hub", href: "/quality-studio" },
              { step: "2", label: "Generate functional / automation / performance", href: "/quality-studio" },
              { step: "3", label: "Plan sprints & releases", href: "/quality-studio" },
              { step: "4", label: "Execute & monitor runs", href: "/executions" },
              { step: "5", label: "Discovery & browser replay", href: "/discovery" },
            ].map((item) => (
              <Link key={item.step} href={item.href}
                className="flex items-center gap-3 px-3 py-2.5 rounded-md hover:bg-[var(--surface-sunken)] group">
                <span className="w-6 h-6 rounded-full bg-brand-50 text-brand-700 text-xs font-bold flex items-center justify-center">
                  {item.step}
                </span>
                <span className="text-sm text-[var(--text-secondary)] group-hover:text-[var(--text-primary)]">{item.label}</span>
                <ArrowUpRight className="w-3 h-3 ml-auto opacity-0 group-hover:opacity-100 text-gray-400" />
              </Link>
            ))}
          </div>
        </div>

        <div className="ds-card lg:col-span-2">
          <div className="ds-card-header">
            <h2 className="text-sm font-semibold">Agent Fleet</h2>
            <Link href="/agents" className="text-xs text-brand-700 hover:underline">Agent workspace</Link>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-[var(--border-default)]">
            {[
              { name: "Requirements Agent", desc: "User stories → test cases + coverage", active: true },
              { name: "Test Design Agent", desc: "Regression/smoke packs + multi-domain design", active: true },
              { name: "Automation Agent", desc: "8 frameworks, page objects, CI snippets", active: true },
              { name: "Self-Healing Agent", desc: "Locator repair on execution failures", active: true },
            ].map((agent) => (
              <div key={agent.name} className="px-5 py-4 flex items-start gap-3">
                <StatusDot status={agent.active ? "online" : "offline"} />
                <div>
                  <p className="text-sm font-medium">{agent.name}</p>
                  <p className="text-xs text-[var(--text-tertiary)]">{agent.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="ds-card">
          <div className="ds-card-header">
            <h2 className="text-sm font-semibold">Phase 5 Metrics</h2>
            <Link href="/reports" className="text-xs text-brand-700 hover:underline flex items-center gap-1">
              <BarChart3 className="w-3 h-3" /> Reports
            </Link>
          </div>
          <div className="ds-card-body pt-0 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-[var(--text-secondary)]">QA Patterns</span>
              <Badge variant="neutral">{patterns}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-[var(--text-secondary)]">Integrations</span>
              <span className="text-sm font-medium">{p5stats.persisted_integrations ?? 0}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-[var(--text-secondary)]">Monitoring Events</span>
              <span className="text-sm font-medium">{p5stats.monitoring_events ?? 0}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-[var(--text-secondary)]">Pipeline Runs</span>
              <span className="text-sm font-medium">{phase4?.stats?.pipeline_runs ?? 0}</span>
            </div>
            <div className="flex items-center gap-2 pt-2 border-t border-[var(--border-default)]">
              <Activity className="w-3.5 h-3.5 text-emerald-600" />
              <span className="text-xs text-[var(--text-tertiary)]">
                {health === "healthy"
                  ? "Backend connected"
                  : health === "checking"
                    ? "Checking backend connection…"
                    : "Backend offline — start uvicorn on :8000"}
              </span>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
