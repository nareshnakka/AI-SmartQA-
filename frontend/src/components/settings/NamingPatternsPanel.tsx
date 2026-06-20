"use client";

import { useCallback, useEffect, useState } from "react";
import clsx from "clsx";
import { Loader2, RotateCcw, Save } from "lucide-react";
import {
  CATEGORY_DESCRIPTIONS,
  CATEGORY_LABELS,
  fetchNamingPatterns,
  previewNamingPattern,
  updateNamingPatterns,
  type CategoryPatternConfig,
  type NamingCategory,
  type NamingPatternsResponse,
} from "@/lib/naming-patterns";

const CATEGORIES: NamingCategory[] = ["functional", "automation", "performance", "security"];

export function NamingPatternsPanel({ projectId }: { projectId: string }) {
  const [data, setData] = useState<NamingPatternsResponse | null>(null);
  const [active, setActive] = useState<NamingCategory>("functional");
  const [draft, setDraft] = useState<Record<NamingCategory, CategoryPatternConfig> | null>(null);
  const [preview, setPreview] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [loadError, setLoadError] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const res = await fetchNamingPatterns(projectId);
      setData(res);
      setDraft(res.patterns);
      setPreview(res.previews?.functional ?? "");
    } catch (e) {
      setData(null);
      setDraft(null);
      setLoadError(e instanceof Error ? e.message : "Could not load naming patterns");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    reload();
  }, [reload]);

  const runPreview = useCallback(
    async (cat: NamingCategory, cfg: CategoryPatternConfig) => {
      try {
        const res = await previewNamingPattern(projectId, {
          pattern: cfg.pattern,
          seq_digits: cfg.seq_digits,
        });
        setPreview(res.preview);
      } catch {
        setPreview("(invalid pattern)");
      }
    },
    [projectId]
  );

  useEffect(() => {
    if (!draft) return;
    const t = setTimeout(() => runPreview(active, draft[active]), 300);
    return () => clearTimeout(t);
  }, [draft, active, runPreview]);

  const patchCategory = (cat: NamingCategory, patch: Partial<CategoryPatternConfig>) => {
    setDraft((prev) => {
      if (!prev) return prev;
      return { ...prev, [cat]: { ...prev[cat], ...patch } };
    });
  };

  const resetCategory = (cat: NamingCategory) => {
    if (!data) return;
    patchCategory(cat, { ...data.defaults[cat] });
  };

  const saveCategory = async () => {
    if (!draft) return;
    setSaving(true);
    setMessage("");
    try {
      const res = await updateNamingPatterns(projectId, { [active]: draft[active] });
      setData(res);
      setDraft(res.patterns);
      setMessage(`${CATEGORY_LABELS[active]} pattern saved`);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-[var(--text-tertiary)]">Loading naming patterns…</p>;
  }

  if (!data || !draft) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-[var(--text-tertiary)]">Could not load naming patterns.</p>
        {loadError && (
          <p className="text-xs text-red-600 dark:text-red-400 font-mono whitespace-pre-wrap">{loadError}</p>
        )}
        <p className="text-xs text-[var(--text-tertiary)]">
          If the API returns 404, restart the backend: <code>scripts\restart-all-auto.bat</code>
        </p>
        <button type="button" onClick={reload} className="ds-btn-secondary text-sm">
          Retry
        </button>
      </div>
    );
  }

  const cfg = draft[active];

  return (
    <div className="space-y-4">
      <div className="ds-card">
        <div className="ds-card-header">
          <div>
            <h2 className="text-sm font-semibold">Test case naming patterns</h2>
            <p className="text-xs text-[var(--text-tertiary)]">
              Per-project patterns for Functional, Automation, Performance, and Security
            </p>
          </div>
        </div>
        <div className="px-6 pt-2 border-b border-[var(--border-default)]">
          <div className="flex flex-wrap gap-1">
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                type="button"
                suppressHydrationWarning
                onClick={() => setActive(cat)}
                className={clsx(
                  "px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors",
                  active === cat
                    ? "border-brand-700 text-brand-700"
                    : "border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
                )}
              >
                {CATEGORY_LABELS[cat]}
              </button>
            ))}
          </div>
        </div>
        <div className="ds-card-body space-y-4">
          <p className="text-xs text-[var(--text-tertiary)]">{CATEGORY_DESCRIPTIONS[active]}</p>

          <div>
            <label className="text-xs font-medium text-[var(--text-secondary)] block mb-1">
              Pattern template
            </label>
            <input
              className="ds-input text-sm font-mono w-full"
              value={cfg.pattern}
              onChange={(e) => patchCategory(active, { pattern: e.target.value })}
              placeholder="{PROJ5}_{ENV5}_{MOD5}_FTC{SEQ5}"
              suppressHydrationWarning
            />
            <p className="text-[10px] text-[var(--text-tertiary)] mt-1.5">
              Tokens:{" "}
              {Object.entries(data.token_help).map(([k, v]) => (
                <span key={k} className="mr-2">
                  <code className="text-[10px]">{k}</code> — {v}
                </span>
              ))}
            </p>
          </div>

          <div className="w-32">
            <label className="text-xs font-medium text-[var(--text-secondary)] block mb-1">
              Sequence digits
            </label>
            <input
              type="number"
              min={1}
              max={10}
              className="ds-input text-sm w-full"
              value={cfg.seq_digits}
              onChange={(e) =>
                patchCategory(active, { seq_digits: Math.min(10, Math.max(1, Number(e.target.value) || 5)) })
              }
              suppressHydrationWarning
            />
          </div>

          <div className="rounded-md bg-[var(--surface-sunken)] px-4 py-3">
            <p className="text-[10px] uppercase tracking-wide text-[var(--text-tertiary)] mb-1">Preview</p>
            <p className="font-mono text-sm text-brand-700">{preview || "…"}</p>
            <p className="text-[10px] text-[var(--text-tertiary)] mt-1">
              Example using project &quot;{data.preview_context.project_name}&quot;, env &quot;
              {data.preview_context.environment_name}&quot;, module &quot;
              {data.preview_context.module_name}&quot;
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={saveCategory} disabled={saving} className="ds-btn-primary text-sm">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Save {CATEGORY_LABELS[active]}
            </button>
            <button
              type="button"
              onClick={() => resetCategory(active)}
              className="ds-btn-secondary text-sm inline-flex items-center gap-1"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Reset to default
            </button>
            {message && <span className="text-xs text-[var(--text-secondary)]">{message}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
