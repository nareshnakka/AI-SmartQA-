"use client";

import { useEffect, useState } from "react";
import { Download, RefreshCw, Trash2, Database, Brain, Layers } from "lucide-react";
import { AppShell } from "@/components/shell/AppShell";
import { PageHeader, MetricCard, Badge } from "@/components/ui";
import { apiFetch } from "@/lib/api";

interface Stats {
  total_records: number;
  by_agent: Record<string, number>;
  collection_enabled: boolean;
}

export default function TrainingPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [patterns, setPatterns] = useState(0);
  const [hybrid, setHybrid] = useState(false);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const load = async () => {
    try {
      const [s, intel] = await Promise.all([
        apiFetch<Stats>("/api/v1/intelligence/training/stats"),
        apiFetch<{ pattern_count: number; hybrid_available: boolean }>("/api/v1/intelligence/status"),
      ]);
      setStats(s);
      setPatterns(intel.pattern_count);
      setHybrid(intel.hybrid_available);
    } catch {
      setMessage("Connect to backend to view training data");
    }
  };

  useEffect(() => { load(); }, []);

  const exportData = async () => {
    setLoading(true);
    try {
      const r = await apiFetch<{ records: number }>("/api/v1/intelligence/training/export", { method: "POST" });
      setMessage(`Exported ${r.records} training records`);
      await load();
    } finally {
      setLoading(false);
    }
  };

  const download = () => {
    const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    window.open(`${base}/api/v1/intelligence/training/download`, "_blank");
  };

  const clear = async () => {
    if (!confirm("Clear all collected training data?")) return;
    setLoading(true);
    try {
      const r = await apiFetch<{ cleared: number }>("/api/v1/intelligence/training/clear", { method: "DELETE" });
      setMessage(`Cleared ${r.cleared} records`);
      await load();
    } finally {
      setLoading(false);
    }
  };

  return (
    <AppShell title="Model Training">
      <PageHeader
        title="Model Training"
        subtitle="Collect agent outputs to fine-tune your custom QEOS quality model"
        breadcrumbs={[{ label: "Platform" }, { label: "Model Training" }]}
        actions={
          <Badge variant={stats?.collection_enabled ? "success" : "neutral"}>
            {stats?.collection_enabled ? "Auto-collect ON" : "Auto-collect OFF"}
          </Badge>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <MetricCard label="Training Records" value={stats?.total_records ?? 0} icon={<Database className="w-4 h-4" />} />
        <MetricCard label="QA Patterns" value={patterns} icon={<Layers className="w-4 h-4" />} />
        <MetricCard
          label="Hybrid Neural"
          value={hybrid ? "Available" : "Native Only"}
          change={hybrid ? "Ollama detected" : "Install Ollama for hybrid"}
          changeType={hybrid ? "positive" : "neutral"}
          icon={<Brain className="w-4 h-4" />}
        />
      </div>

      {stats && Object.keys(stats.by_agent).length > 0 && (
        <div className="ds-card mb-6">
          <div className="ds-card-header">
            <h2 className="text-sm font-semibold">Records by Agent</h2>
          </div>
          <div className="ds-card-body">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {Object.entries(stats.by_agent).map(([agent, count]) => (
                <div key={agent} className="p-3 rounded-md bg-[var(--surface-sunken)]">
                  <p className="text-xs text-[var(--text-tertiary)] capitalize">{agent.replace(/_/g, " ")}</p>
                  <p className="text-xl font-semibold tabular-nums mt-0.5">{count}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="ds-card mb-6">
        <div className="ds-card-header">
          <h2 className="text-sm font-semibold">Fine-Tuning Pipeline</h2>
        </div>
        <div className="ds-card-body">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {[
              { step: "1", title: "Collect", desc: "Agent runs saved automatically" },
              { step: "2", title: "Export", desc: "Download JSONL training pairs" },
              { step: "3", title: "Train", desc: "python training/train.py" },
              { step: "4", title: "Deploy", desc: "Ollama + qeos-hybrid mode" },
            ].map((item) => (
              <div key={item.step} className="flex gap-3">
                <div className="w-7 h-7 rounded-full bg-brand-50 text-brand-700 flex items-center justify-center text-xs font-bold shrink-0">
                  {item.step}
                </div>
                <div>
                  <p className="text-sm font-medium">{item.title}</p>
                  <p className="text-xs text-[var(--text-tertiary)]">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <button onClick={exportData} disabled={loading} className="ds-btn-primary">
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          Export JSONL
        </button>
        <button onClick={download} className="ds-btn-secondary">
          <Download className="w-4 h-4" />
          Download
        </button>
        <button onClick={clear} disabled={loading} className="ds-btn-secondary text-red-600">
          <Trash2 className="w-4 h-4" />
          Clear
        </button>
      </div>

      {message && (
        <p className="mt-4 text-sm text-[var(--text-secondary)] p-3 rounded-md bg-[var(--surface-sunken)]">{message}</p>
      )}
    </AppShell>
  );
}
