"use client";

import { useEffect, useState } from "react";
import { Loader2, Plus, Trash2, RefreshCw, ChevronDown, ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui";
import {
  createEnvironment,
  deleteEnvironment,
  fetchWorkspaceHierarchy,
  updateEnvironment,
  type ProjectEnvironment,
  type WorkspaceHierarchy,
} from "@/lib/environments";
import {
  createModule,
  deleteModule,
  updateModule,
  type ProjectModule,
} from "@/lib/modules";

export function WorkspaceHierarchyPanel({ projectId }: { projectId: string }) {
  const [tree, setTree] = useState<WorkspaceHierarchy | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedEnv, setExpandedEnv] = useState<string | null>(null);
  const [envName, setEnvName] = useState("");
  const [envBaseUrl, setEnvBaseUrl] = useState("");
  const [modName, setModName] = useState("");
  const [modEnvId, setModEnvId] = useState("");
  const [saving, setSaving] = useState(false);

  const reload = async () => {
    setLoading(true);
    try {
      const data = await fetchWorkspaceHierarchy(projectId);
      setTree(data);
      if (!expandedEnv && data.environments[0]) {
        setExpandedEnv(data.environments[0].id);
        setModEnvId(data.environments[0].id);
      } else if (modEnvId && !data.environments.some((e) => e.id === modEnvId)) {
        setModEnvId(data.environments[0]?.id ?? "");
      }
    } catch {
      setTree(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    reload();
  }, [projectId]);

  const addEnv = async () => {
    if (!envName.trim()) return;
    setSaving(true);
    try {
      await createEnvironment(projectId, {
        name: envName.trim(),
        base_url: envBaseUrl.trim() || undefined,
        is_default: (tree?.environments.length ?? 0) === 0,
      });
      setEnvName("");
      setEnvBaseUrl("");
      await reload();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Could not create environment");
    } finally {
      setSaving(false);
    }
  };

  const addModule = async () => {
    if (!modName.trim() || !modEnvId) return;
    setSaving(true);
    try {
      await createModule(projectId, modEnvId, modName.trim());
      setModName("");
      await reload();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Could not create module");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="ds-card">
        <div className="ds-card-header flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold">Project hierarchy</h2>
            <p className="text-xs text-[var(--text-tertiary)]">
              Define your own environment names (Dev, SIT, UAT, Prod, etc.) — nothing is fixed
            </p>
          </div>
          <button type="button" onClick={reload} className="ds-btn-ghost p-1.5" title="Refresh">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
        <div className="ds-card-body space-y-3">
          {loading ? (
            <p className="text-sm text-[var(--text-tertiary)]">Loading hierarchy…</p>
          ) : !tree?.environments.length ? (
            <div className="text-center py-8 border border-dashed border-[var(--border-default)] rounded-md">
              <p className="text-sm text-[var(--text-secondary)] mb-1">No environments yet</p>
              <p className="text-xs text-[var(--text-tertiary)] mb-4">
                Add environments using the names your team uses — not preset labels.
              </p>
            </div>
          ) : (
            tree.environments.map((env) => (
              <EnvTreeNode
                key={env.id}
                projectId={projectId}
                env={env}
                expanded={expandedEnv === env.id}
                onToggle={() => setExpandedEnv(expandedEnv === env.id ? null : env.id)}
                onReload={reload}
              />
            ))
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="ds-card">
          <div className="ds-card-header"><h3 className="text-sm font-semibold">Add environment</h3></div>
          <div className="ds-card-body space-y-2">
            <input
              className="ds-input text-sm w-full"
              placeholder="Environment name (e.g. SIT, Pre-Prod, DR)"
              value={envName}
              onChange={(e) => setEnvName(e.target.value)}
            />
            <input
              className="ds-input text-sm font-mono w-full"
              placeholder="Base URL (optional)"
              value={envBaseUrl}
              onChange={(e) => setEnvBaseUrl(e.target.value)}
            />
            <button
              type="button"
              onClick={addEnv}
              disabled={saving || !envName.trim()}
              className="ds-btn-primary text-sm w-full inline-flex items-center justify-center gap-1"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              Add environment
            </button>
          </div>
        </div>
        <div className="ds-card">
          <div className="ds-card-header"><h3 className="text-sm font-semibold">Add module</h3></div>
          <div className="ds-card-body space-y-2">
            <select
              className="ds-input text-sm w-full"
              value={modEnvId}
              onChange={(e) => setModEnvId(e.target.value)}
              disabled={!tree?.environments.length}
            >
              <option value="">Select environment</option>
              {(tree?.environments ?? []).map((e) => (
                <option key={e.id} value={e.id}>{e.name}</option>
              ))}
            </select>
            <input
              className="ds-input text-sm w-full"
              placeholder="Module name (e.g. Payroll, Admin)"
              value={modName}
              onChange={(e) => setModName(e.target.value)}
            />
            <button
              type="button"
              onClick={addModule}
              disabled={saving || !modName.trim() || !modEnvId}
              className="ds-btn-primary text-sm w-full inline-flex items-center justify-center gap-1"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              Add module
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function EnvTreeNode({
  projectId,
  env,
  expanded,
  onToggle,
  onReload,
}: {
  projectId: string;
  env: ProjectEnvironment & { modules: ProjectModule[] };
  expanded: boolean;
  onToggle: () => void;
  onReload: () => void;
}) {
  const setDefault = async () => {
    await updateEnvironment(projectId, env.id, { is_default: true });
    onReload();
  };

  const removeEnv = async () => {
    if (!window.confirm(`Delete environment "${env.name}" and its modules?`)) return;
    try {
      await deleteEnvironment(projectId, env.id);
      onReload();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Could not delete");
    }
  };

  return (
    <div className="border border-[var(--border-default)] rounded-md overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2.5 bg-[var(--surface-sunken)]">
        <button type="button" onClick={onToggle} className="shrink-0 p-0.5">
          {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>
        <input
          className="ds-input text-sm font-medium flex-1 min-w-0 py-1"
          defaultValue={env.name}
          onBlur={async (e) => {
            const next = e.target.value.trim();
            if (next && next !== env.name) {
              try {
                await updateEnvironment(projectId, env.id, { name: next });
                onReload();
              } catch (err) {
                alert(err instanceof Error ? err.message : "Could not rename");
                e.target.value = env.name;
              }
            }
          }}
          title="Click to rename environment"
        />
        {env.is_default && <Badge variant="success">Default</Badge>}
        <span className="text-xs text-[var(--text-tertiary)] shrink-0">{env.test_case_count} cases</span>
        {!env.is_default && (
          <button type="button" className="ds-btn-secondary text-[10px] py-0.5 px-1.5 shrink-0" onClick={setDefault}>
            Set default
          </button>
        )}
        <button type="button" onClick={removeEnv} className="ds-btn-ghost p-1 text-red-600 shrink-0" title="Delete">
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
      {expanded && (
        <div className="px-3 py-2 space-y-2 border-t border-[var(--border-default)]">
          <input
            className="ds-input text-xs font-mono w-full"
            defaultValue={env.base_url ?? ""}
            placeholder="Base URL"
            onBlur={async (e) => {
              if (e.target.value !== (env.base_url ?? "")) {
                await updateEnvironment(projectId, env.id, { base_url: e.target.value || undefined });
                onReload();
              }
            }}
          />
          {env.modules.length === 0 ? (
            <p className="text-xs text-[var(--text-tertiary)] py-2">No modules — add one below.</p>
          ) : (
            env.modules.map((mod) => (
              <ModuleTreeRow key={mod.id} projectId={projectId} mod={mod} onReload={onReload} />
            ))
          )}
        </div>
      )}
    </div>
  );
}

function ModuleTreeRow({
  projectId,
  mod,
  onReload,
}: {
  projectId: string;
  mod: ProjectModule;
  onReload: () => void;
}) {
  const remove = async () => {
    if (!window.confirm(`Delete module "${mod.name}"?`)) return;
    try {
      await deleteModule(projectId, mod.id);
      onReload();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Could not delete");
    }
  };

  return (
    <div className="flex items-center gap-2 pl-6 py-1.5 text-sm">
      <ChevronRight className="w-3 h-3 text-[var(--text-tertiary)] shrink-0" />
      <input
        className="ds-input text-xs flex-1 max-w-[180px]"
        defaultValue={mod.name}
        onBlur={async (e) => {
          if (e.target.value.trim() && e.target.value !== mod.name) {
            await updateModule(projectId, mod.id, { name: e.target.value.trim() });
            onReload();
          }
        }}
      />
      <span className="font-mono text-[10px] text-[var(--text-tertiary)]">{mod.code}</span>
      <span className="text-xs text-[var(--text-tertiary)]">{mod.test_case_count} cases</span>
      <button type="button" onClick={remove} className="ds-btn-ghost p-1 text-red-600 ml-auto">
        <Trash2 className="w-3 h-3" />
      </button>
    </div>
  );
}
