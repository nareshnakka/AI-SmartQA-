"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ExternalLink, Check, X, Settings2 } from "lucide-react";
import { AppShell } from "@/components/shell/AppShell";
import { PageHeader, Badge, Tabs } from "@/components/ui";
import { useActiveProject } from "@/context/ProjectContext";
import { apiFetch } from "@/lib/api";

interface Integration {
  id: string;
  name: string;
  description: string;
  category: string;
  implemented: boolean;
}

const CATEGORY_LABELS: Record<string, string> = {
  source_control: "Source Control",
  ci_cd: "CI/CD",
  alm: "Application Lifecycle",
};

export default function IntegrationsPage() {
  const { projectId } = useActiveProject();
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [connected, setConnected] = useState<{ id: string; provider: string; status: string }[]>([]);
  const [activeTab, setActiveTab] = useState("all");
  const [connectTarget, setConnectTarget] = useState<Integration | null>(null);
  const [token, setToken] = useState("");
  const [domain, setDomain] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    apiFetch<{ integrations: Integration[] }>("/api/v1/platform/integrations/catalog")
      .then((d) => setIntegrations(d.integrations))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!projectId) { setConnected([]); return; }
    apiFetch<{ id: string; provider: string; status: string }[]>(`/api/v1/integrations?project_id=${projectId}`)
      .then(setConnected)
      .catch(() => setConnected([]));
  }, [projectId, refreshKey]);

  const categories = ["all", ...new Set(integrations.map((i) => i.category))];
  const filtered = activeTab === "all" ? integrations : integrations.filter((i) => i.category === activeTab);
  const tabs = categories.map((cat) => ({
    id: cat,
    label: cat === "all" ? "All" : CATEGORY_LABELS[cat] ?? cat,
    count: cat === "all" ? integrations.length : integrations.filter((i) => i.category === cat).length,
  }));

  const connect = async () => {
    if (!connectTarget || !projectId) { setMessage("Select a project first"); return; }
    const credentials: Record<string, string> = {};
    if (connectTarget.id === "jira") {
      credentials.domain = domain;
      credentials.email = email;
      credentials.api_token = token;
    } else {
      credentials.token = token;
      credentials.access_token = token;
    }
    try {
      await apiFetch("/api/v1/integrations/connect", {
        method: "POST",
        body: JSON.stringify({
          provider: connectTarget.id,
          project_id: projectId,
          credentials,
        }),
      });
      setMessage(`${connectTarget.name} connected successfully`);
      setConnectTarget(null);
      setToken("");
      setRefreshKey((k) => k + 1);
    } catch (e) {
      setMessage(`Connection failed: ${e}`);
    }
  };

  return (
    <AppShell title="Integrations">
      <PageHeader
        title="Integration Hub"
        subtitle="Connect Git, ALM, and CI/CD — extensible via plugins"
        breadcrumbs={[{ label: "Platform" }, { label: "Integrations" }]}
      />

      {connected.length > 0 && (
        <div className="ds-card mb-4 p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)] mb-2">Connected</h3>
          <div className="flex flex-wrap gap-2">
            {connected.map((c) => (
              <Badge key={c.id} variant="success">{c.provider} · {c.status}</Badge>
            ))}
          </div>
        </div>
      )}

      <div className="mb-6"><Tabs tabs={tabs} active={activeTab} onChange={setActiveTab} /></div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.map((integration) => (
          <div key={integration.id} className="ds-card">
            <div className="ds-card-body">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-9 h-9 rounded-md bg-[var(--surface-sunken)] flex items-center justify-center">
                    <span className="text-xs font-bold text-[var(--text-secondary)] uppercase">
                      {integration.name.slice(0, 2)}
                    </span>
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold">{integration.name}</h3>
                    <p className="text-[10px] font-mono text-[var(--text-tertiary)]">{integration.id}</p>
                  </div>
                </div>
                {integration.implemented
                  ? <Badge variant="success"><Check className="w-3 h-3" /> Ready</Badge>
                  : <Badge variant="neutral">Planned</Badge>}
              </div>
              <p className="text-xs text-[var(--text-secondary)] leading-relaxed mb-4 min-h-[36px]">
                {integration.description}
              </p>
              <div className="flex items-center justify-between pt-3 border-t border-[var(--border-default)]">
                <Badge variant="neutral">{CATEGORY_LABELS[integration.category] ?? integration.category}</Badge>
                <button
                  onClick={() => setConnectTarget(integration)}
                  disabled={!integration.implemented}
                  className="ds-btn-secondary text-xs py-1.5 px-3"
                >
                  <Settings2 className="w-3 h-3" /> Configure
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Connect modal */}
      {connectTarget && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="ds-card w-full max-w-md">
            <div className="ds-card-header">
              <h2 className="text-sm font-semibold">Connect {connectTarget.name}</h2>
              <button onClick={() => setConnectTarget(null)} className="ds-btn-ghost p-1"><X className="w-4 h-4" /></button>
            </div>
            <div className="ds-card-body space-y-4">
              {connectTarget.id === "jira" && (
                <>
                  <div>
                    <label className="block text-xs font-medium mb-1.5">Domain</label>
                    <input className="ds-input" placeholder="yourcompany.atlassian.net" value={domain} onChange={(e) => setDomain(e.target.value)} />
                  </div>
                  <div>
                    <label className="block text-xs font-medium mb-1.5">Email</label>
                    <input className="ds-input" placeholder="user@company.com" value={email} onChange={(e) => setEmail(e.target.value)} />
                  </div>
                </>
              )}
              <div>
                <label className="block text-xs font-medium mb-1.5">
                  {connectTarget.id === "jira" ? "API Token" : "Access Token / PAT"}
                </label>
                <input className="ds-input font-mono text-xs" type="password" value={token} onChange={(e) => setToken(e.target.value)} />
              </div>
              <div className="flex gap-2">
                <button onClick={connect} className="ds-btn-primary flex-1">Connect</button>
                <button onClick={() => setConnectTarget(null)} className="ds-btn-secondary">Cancel</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {message && <p className="mt-4 text-sm p-3 rounded-md bg-[var(--surface-sunken)]">{message}</p>}
    </AppShell>
  );
}
