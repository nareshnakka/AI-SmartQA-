"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/shell/AppShell";
import { PageHeader, Badge, StatusDot } from "@/components/ui";
import { apiFetch } from "@/lib/api";

export default function SettingsPage() {
  const [providers, setProviders] = useState<{ name: string; available: boolean; models: string[] }[]>([]);
  const [manifest, setManifest] = useState<{ version: string; extensions: { id: string; point: string; name: string }[] } | null>(null);
  const [capabilities, setCapabilities] = useState<Record<string, boolean>>({});
  const [authStatus, setAuthStatus] = useState<{ auth_enabled: boolean; user_count: number; default_admin?: string; sso_configured?: boolean } | null>(null);

  useEffect(() => {
    Promise.allSettled([
      apiFetch<{ providers: { name: string; available: boolean; models: string[] }[] }>("/api/v1/llm/providers"),
      apiFetch<{ version: string; extensions: { id: string; point: string; name: string }[] }>("/api/v1/platform/manifest"),
      apiFetch<Record<string, boolean>>("/api/v1/platform/capabilities"),
      apiFetch<{ auth_enabled: boolean; user_count: number; default_admin?: string; sso_configured?: boolean }>("/api/v1/auth/status"),
    ]).then(([p, m, c, a]) => {
      if (p.status === "fulfilled") setProviders(p.value.providers);
      if (m.status === "fulfilled") setManifest(m.value);
      if (c.status === "fulfilled") setCapabilities(c.value);
      if (a.status === "fulfilled") setAuthStatus(a.value);
    });
  }, []);

  return (
    <AppShell title="Settings">
      <PageHeader
        title="Platform Settings"
        subtitle="Intelligence engine, providers, and extension configuration"
        breadcrumbs={[{ label: "Platform" }, { label: "Settings" }]}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Intelligence */}
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
            <div className="ds-divider" />
            <div className="flex items-center justify-between py-2">
              <div>
                <p className="text-sm font-medium">Hybrid Mode</p>
                <p className="text-xs text-[var(--text-tertiary)]">Native + Ollama neural enhancement</p>
              </div>
              <Badge variant="neutral">Optional</Badge>
            </div>
          </div>
        </div>

        {/* Runners & Auth */}
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
            {authStatus?.default_admin && (
              <p className="text-xs text-[var(--text-tertiary)]">Default admin: {authStatus.default_admin}</p>
            )}
            <div className="flex items-center justify-between py-1">
              <span className="text-sm text-[var(--text-secondary)]">SSO (OIDC)</span>
              <Badge variant={authStatus?.sso_configured ? "success" : "neutral"}>
                {authStatus?.sso_configured ? "Configured" : "Not configured"}
              </Badge>
            </div>
          </div>
        </div>

        {/* Providers */}
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

        {/* Extensions */}
        <div className="ds-card lg:col-span-2">
          <div className="ds-card-header">
            <div>
              <h2 className="text-sm font-semibold">Registered Extensions</h2>
              <p className="text-xs text-[var(--text-tertiary)]">
                Platform v{manifest?.version ?? "0.2.0"} — {manifest?.extensions.length ?? 0} extensions
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
    </AppShell>
  );
}
