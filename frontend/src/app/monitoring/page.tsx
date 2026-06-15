"use client";

import { useEffect, useState } from "react";
import { Activity, AlertTriangle } from "lucide-react";
import { AppShell } from "@/components/shell/AppShell";
import { PageHeader, Badge } from "@/components/ui";
import { apiFetch, BACKEND_URL } from "@/lib/api";

interface MonitoringEvent {
  id: string; source: string; event_type: string; severity: string;
  title: string; created_at: string;
}

interface Connector {
  id: string; name: string; webhook_path: string; configured: boolean;
}

export default function MonitoringPage() {
  const [events, setEvents] = useState<MonitoringEvent[]>([]);
  const [connectors, setConnectors] = useState<Connector[]>([]);

  useEffect(() => {
    Promise.allSettled([
      apiFetch<MonitoringEvent[]>("/api/v1/monitoring/events"),
      apiFetch<{ connectors: Connector[] }>("/api/v1/monitoring/connectors"),
    ]).then(([e, c]) => {
      if (e.status === "fulfilled") setEvents(e.value);
      if (c.status === "fulfilled") setConnectors(c.value.connectors);
    });
  }, []);

  const severityVariant = (s: string) =>
    s === "error" ? "error" : s === "warning" ? "warning" : "neutral";

  return (
    <AppShell title="Monitoring">
      <PageHeader
        title="Production Monitoring"
        subtitle="Datadog, Sentry, and custom event ingestion"
        breadcrumbs={[{ label: "Platform" }, { label: "Monitoring" }]}
        actions={<Badge variant="success">Phase 5</Badge>}
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        {connectors.map((c) => (
          <div key={c.id} className="ds-card">
            <div className="ds-card-header">
              <h2 className="text-sm font-semibold">{c.name}</h2>
              <Badge variant={c.configured ? "success" : "neutral"}>{c.configured ? "Secured" : "Open"}</Badge>
            </div>
            <div className="ds-card-body pt-0">
              <p className="text-xs font-mono text-[var(--text-tertiary)] break-all">
                POST {BACKEND_URL}{c.webhook_path}
              </p>
            </div>
          </div>
        ))}
      </div>

      <div className="ds-card">
        <div className="ds-card-header">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <Activity className="w-4 h-4" /> Recent Events
          </h2>
          <span className="text-xs text-[var(--text-tertiary)]">{events.length} events</span>
        </div>
        <div className="ds-card-body space-y-2 pt-0">
          {events.length === 0 ? (
            <p className="text-sm text-[var(--text-tertiary)]">No events yet — configure Datadog or Sentry webhooks.</p>
          ) : events.map((e) => (
            <div key={e.id} className="flex items-start gap-3 p-3 rounded-md bg-[var(--surface-sunken)]/50">
              <AlertTriangle className={`w-4 h-4 shrink-0 mt-0.5 ${e.severity === "error" ? "text-red-500" : "text-amber-500"}`} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium truncate">{e.title}</span>
                  <Badge variant={severityVariant(e.severity) as "error" | "warning" | "neutral"}>{e.source}</Badge>
                </div>
                <p className="text-xs text-[var(--text-tertiary)]">{e.event_type} · {new Date(e.created_at).toLocaleString()}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
