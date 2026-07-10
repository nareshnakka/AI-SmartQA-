"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import { AppShell } from "@/components/shell/AppShell";
import { PageHeader, Badge, StatusDot } from "@/components/ui";
import { WorkspaceHierarchyPanel } from "@/components/settings/WorkspaceHierarchyPanel";
import { NamingPatternsPanel } from "@/components/settings/NamingPatternsPanel";
import { useActiveProject } from "@/context/ProjectContext";
import { apiFetch } from "@/lib/api";

type SettingsTab = "platform" | "workspace" | "naming";

export default function SettingsPage() {
  const { projectId, activeProject, ready } = useActiveProject();
  const [tab, setTab] = useState<SettingsTab>("platform");
  const [providers, setProviders] = useState<{ name: string; available: boolean; models: string[] }[]>([]);
  const [manifest, setManifest] = useState<{ version: string; version_label?: string; build?: number; extensions: { id: string; point: string; name: string }[] } | null>(null);
  const [capabilities, setCapabilities] = useState<Record<string, boolean>>({});
  const [authStatus, setAuthStatus] = useState<{ auth_enabled: boolean; user_count: number; default_admin?: string; sso_configured?: boolean } | null>(null);

  useEffect(() => {
    Promise.allSettled([
      apiFetch<{ providers: { name: string; available: boolean; models: string[] }[] }>("/api/v1/llm/providers"),
      apiFetch<{ version: string; version_label?: string; build?: number; extensions: { id: string; point: string; name: string }[] }>("/api/v1/platform/manifest"),
      apiFetch<Record<string, boolean>>("/api/v1/platform/capabilities"),
      apiFetch<{ auth_enabled: boolean; user_count: number; default_admin?: string; sso_configured?: boolean }>("/api/v1/auth/status"),
    ]).then(([p, m, c, a]) => {
      if (p.status === "fulfilled") setProviders(p.value.providers);
      if (m.status === "fulfilled") setManifest(m.value);
      if (c.status === "fulfilled") setCapabilities(c.value);
      if (a.status === "fulfilled") setAuthStatus(a.value);
    });
  }, []);

  const tabs: { id: SettingsTab; label: string }[] = [
    { id: "platform", label: "Platform" },
    { id: "workspace", label: "Environments & Modules" },
    { id: "naming", label: "Test Case Naming" },
  ];

  return (
    <AppShell title="Settings">
      <PageHeader
        title="Settings"
        subtitle={
          tab === "platform"
            ? "Intelligence engine, providers, and extension configuration"
            : tab === "workspace"
              ? `Project → Environment → Module${activeProject ? ` — ${activeProject.name}` : ""}`
              : `Naming patterns${activeProject ? ` — ${activeProject.name}` : ""}`
        }
        breadcrumbs={[{ label: "Platform" }, { label: "Settings" }]}
      />

      <div className="flex gap-2 mb-6 border-b border-[var(--border-default)]">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            suppressHydrationWarning
            className={clsx(
              "px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
              tab === t.id
                ? "border-brand-700 text-brand-700"
                : "border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "workspace" && (
        !ready || !projectId ? (
          <p className="text-sm text-[var(--text-tertiary)]">Select a project to configure the hierarchy.</p>
        ) : (
          <WorkspaceHierarchyPanel projectId={projectId} />
        )
      )}

      {tab === "naming" && (
        !ready || !projectId ? (
          <p className="text-sm text-[var(--text-tertiary)]">Select a project to configure naming patterns.</p>
        ) : (
          <NamingPatternsPanel projectId={projectId} />
        )
      )}

      {tab === "platform" && (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="ds-card">
          <div className="ds-card-header">
            <h2 className="text-sm font-semibold">Intelligence Engine</h2>
          </div>
          <div className="ds-card-body space-y-4">
            <div className="flex items-center justify-between py-2">
              <div>
                <p className="text-sm font-medium">Default Provider</p>
                <p className="text-xs text-[var(--text-tertiary)]">qeos-native — no external LLM</p>
              </div>
              <Badge variant="success">Active</Badge>
            </div>
            <div className="ds-divider" />
            <div className="flex items-center justify-between py-2">
              <div>
                <p className="text-sm font-medium">Training Collection</p>
                <p className="text-xs text-[var(--text-tertiary)]">Auto-save agent outputs</p>
              </div>
              <Badge variant="success">Enabled</Badge>
            </div>
          </div>
        </div>

        <div className="ds-card">
          <div className="ds-card-header">
            <h2 className="text-sm font-semibold">Phase 5 Runners</h2>
          </div>
          <div className="ds-card-body space-y-3">
            {[
              ["Node.js (live execution)", capabilities.node_available],
              ["Playwright Python (browser discovery)", capabilities.playwright_python],
              ["Playwright browsers installed", capabilities.playwright_browsers],
            ].map(([label, ok]) => (
              <div key={String(label)} className="flex items-center justify-between py-1">
                <span className="text-sm text-[var(--text-secondary)]">{label}</span>
                <Badge variant={ok ? "success" : "neutral"}>{ok ? "Ready" : "Not available"}</Badge>
              </div>
            ))}
            <div className="ds-divider" />
            <div className="flex items-center justify-between py-1">
              <span className="text-sm text-[var(--text-secondary)]">RBAC / Auth</span>
              <Badge variant={authStatus?.auth_enabled ? "success" : "neutral"}>
                {authStatus?.auth_enabled ? "Enforced" : "Open (dev)"}
              </Badge>
            </div>
          </div>
        </div>

        <div className="ds-card">
          <div className="ds-card-header">
            <h2 className="text-sm font-semibold">LLM Providers</h2>
          </div>
          <div className="divide-y divide-[var(--border-default)]">
            {providers.map((p) => (
              <div key={p.name} className="px-6 py-3 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <StatusDot status={p.available ? "online" : "offline"} />
                  <div>
                    <p className="text-sm font-medium font-mono">{p.name}</p>
                    <p className="text-xs text-[var(--text-tertiary)]">{p.models.slice(0, 2).join(", ")}</p>
                  </div>
                </div>
                <Badge variant={p.available ? "success" : "neutral"}>
                  {p.available ? "Available" : "Not configured"}
                </Badge>
              </div>
            ))}
          </div>
        </div>

        <div className="ds-card lg:col-span-2">
          <div className="ds-card-header">
            <div>
              <h2 className="text-sm font-semibold">Registered Extensions</h2>
              <p className="text-xs text-[var(--text-tertiary)]">
                Platform {manifest?.version_label ?? `v${manifest?.version ?? "2.0"}`} — {manifest?.extensions.length ?? 0} extensions
              </p>
            </div>
          </div>
          <div className="ds-card-body p-0">
            <table className="ds-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Name</th>
                  <th>Extension Point</th>
                </tr>
              </thead>
              <tbody>
                {(manifest?.extensions ?? []).map((ext) => (
                  <tr key={ext.id}>
                    <td className="font-mono text-xs">{ext.id}</td>
                    <td className="font-medium text-[var(--text-primary)]">{ext.name}</td>
                    <td><Badge variant="neutral">{ext.point}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      )}
    </AppShell>
  );
}
