"use client";

import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { Loader2, Plus, Trash2, RefreshCw, ChevronDown, ChevronRight, Save, X } from "lucide-react";
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

type Selection =
  | { kind: "environment"; id: string }
  | { kind: "module"; id: string; envId: string }
  | null;

function notifyHierarchyUpdated(projectId: string) {
  window.dispatchEvent(new CustomEvent("qeos-environments-updated", { detail: { projectId } }));
}

export function WorkspaceHierarchyPanel({ projectId }: { projectId: string }) {
  const [tree, setTree] = useState<WorkspaceHierarchy | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedEnv, setExpandedEnv] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection>(null);
  const [envName, setEnvName] = useState("");
  const [envBaseUrl, setEnvBaseUrl] = useState("");
  const [modName, setModName] = useState("");
  const [modEnvId, setModEnvId] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

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
      if (selection?.kind === "environment" && !data.environments.some((e) => e.id === selection.id)) {
        setSelection(null);
      }
      if (selection?.kind === "module") {
        const env = data.environments.find((e) => e.id === selection.envId);
        if (!env?.modules.some((m) => m.id === selection.id)) {
          setSelection(null);
        }
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

  const selectedEnv = useMemo(() => {
    if (!tree || selection?.kind !== "environment") return null;
    return tree.environments.find((e) => e.id === selection.id) ?? null;
  }, [tree, selection]);

  const selectedMod = useMemo(() => {
    if (!tree || selection?.kind !== "module") return null;
    const env = tree.environments.find((e) => e.id === selection.envId);
    return env?.modules.find((m) => m.id === selection.id) ?? null;
  }, [tree, selection]);

  const addEnv = async () => {
    if (!envName.trim()) return;
    setSaving(true);
    setMessage("");
    try {
      await createEnvironment(projectId, {
        name: envName.trim(),
        base_url: envBaseUrl.trim() || undefined,
        is_default: (tree?.environments.length ?? 0) === 0,
      });
      setEnvName("");
      setEnvBaseUrl("");
      setMessage("Environment created");
      await reload();
      notifyHierarchyUpdated(projectId);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not create environment");
    } finally {
      setSaving(false);
    }
  };

  const addModule = async () => {
    if (!modName.trim() || !modEnvId) return;
    setSaving(true);
    setMessage("");
    try {
      await createModule(projectId, modEnvId, modName.trim());
      setModName("");
      setMessage("Module created");
      await reload();
      notifyHierarchyUpdated(projectId);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not create module");
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
              Select an environment or module to edit and save — or add new ones below
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
                env={env}
                expanded={expandedEnv === env.id}
                selected={
                  selection?.kind === "environment" && selection.id === env.id
                    ? "environment"
                    : selection?.kind === "module" && selection.envId === env.id
                      ? "module"
                      : null
                }
                selectedModuleId={selection?.kind === "module" ? selection.id : null}
                onToggle={() => setExpandedEnv(expandedEnv === env.id ? null : env.id)}
                onSelectEnv={() => setSelection({ kind: "environment", id: env.id })}
                onSelectModule={(modId) => setSelection({ kind: "module", id: modId, envId: env.id })}
              />
            ))
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {selectedEnv ? (
          <EditEnvironmentCard
            projectId={projectId}
            env={selectedEnv}
            saving={saving}
            onSavingChange={setSaving}
            onMessage={setMessage}
            onSaved={async () => {
              await reload();
              notifyHierarchyUpdated(projectId);
            }}
            onDeleted={async () => {
              setSelection(null);
              await reload();
              notifyHierarchyUpdated(projectId);
            }}
            onCancel={() => setSelection(null)}
          />
        ) : selectedMod ? (
          <EditModuleCard
            projectId={projectId}
            mod={selectedMod}
            saving={saving}
            onSavingChange={setSaving}
            onMessage={setMessage}
            onSaved={async () => {
              await reload();
              notifyHierarchyUpdated(projectId);
            }}
            onDeleted={async () => {
              setSelection(null);
              await reload();
              notifyHierarchyUpdated(projectId);
            }}
            onCancel={() => setSelection(null)}
          />
        ) : (
          <div className="ds-card border-dashed">
            <div className="ds-card-body py-10 text-center">
              <p className="text-sm text-[var(--text-secondary)]">Select an environment or module to edit</p>
              <p className="text-xs text-[var(--text-tertiary)] mt-1">
                Click a row in the tree above, change fields, then Save
              </p>
            </div>
          </div>
        )}

        <div className="space-y-4">
          <div className="ds-card">
            <div className="ds-card-header"><h3 className="text-sm font-semibold">Add environment</h3></div>
            <div className="ds-card-body space-y-2">
              <input
                className="ds-input text-sm w-full"
                placeholder="Environment name (e.g. SIT, Pre-Prod, DR)"
                value={envName}
                onChange={(e) => setEnvName(e.target.value)}
                suppressHydrationWarning
              />
              <input
                className="ds-input text-sm font-mono w-full"
                placeholder="Base URL (optional)"
                value={envBaseUrl}
                onChange={(e) => setEnvBaseUrl(e.target.value)}
                suppressHydrationWarning
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
                suppressHydrationWarning
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
                suppressHydrationWarning
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

      {message && <p className="text-xs text-[var(--text-secondary)]">{message}</p>}
    </div>
  );
}

function EnvTreeNode({
  env,
  expanded,
  selected,
  selectedModuleId,
  onToggle,
  onSelectEnv,
  onSelectModule,
}: {
  env: ProjectEnvironment & { modules: ProjectModule[] };
  expanded: boolean;
  selected: "environment" | "module" | null;
  selectedModuleId: string | null;
  onToggle: () => void;
  onSelectEnv: () => void;
  onSelectModule: (modId: string) => void;
}) {
  const envSelected = selected === "environment";

  return (
    <div className="border border-[var(--border-default)] rounded-md overflow-hidden">
      <div
        className={clsx(
          "flex items-center gap-2 px-3 py-2.5 cursor-pointer transition-colors",
          envSelected ? "bg-brand-50 border-l-2 border-l-brand-700" : "bg-[var(--surface-sunken)] hover:bg-[var(--surface-hover)]"
        )}
        onClick={onSelectEnv}
      >
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onToggle();
          }}
          className="shrink-0 p-0.5"
        >
          {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>
        <span className="text-sm font-medium flex-1 min-w-0 truncate">{env.name}</span>
        {env.is_default && <Badge variant="success">Default</Badge>}
        <span className="text-xs text-[var(--text-tertiary)] shrink-0">{env.test_case_count} cases</span>
        {env.base_url && (
          <span className="text-[10px] font-mono text-[var(--text-tertiary)] truncate max-w-[140px] hidden sm:inline">
            {env.base_url}
          </span>
        )}
      </div>
      {expanded && (
        <div className="px-3 py-2 space-y-1 border-t border-[var(--border-default)]">
          {env.modules.length === 0 ? (
            <p className="text-xs text-[var(--text-tertiary)] py-2">No modules — add one on the right.</p>
          ) : (
            env.modules.map((mod) => (
              <button
                key={mod.id}
                type="button"
                onClick={() => onSelectModule(mod.id)}
                className={clsx(
                  "w-full flex items-center gap-2 pl-6 py-1.5 text-sm rounded text-left transition-colors",
                  selectedModuleId === mod.id
                    ? "bg-brand-50 border-l-2 border-l-brand-700"
                    : "hover:bg-[var(--surface-hover)]"
                )}
              >
                <ChevronRight className="w-3 h-3 text-[var(--text-tertiary)] shrink-0" />
                <span className="truncate">{mod.name}</span>
                <span className="font-mono text-[10px] text-[var(--text-tertiary)]">{mod.code}</span>
                <span className="text-xs text-[var(--text-tertiary)] ml-auto shrink-0">{mod.test_case_count} cases</span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

function EditEnvironmentCard({
  projectId,
  env,
  saving,
  onSavingChange,
  onMessage,
  onSaved,
  onDeleted,
  onCancel,
}: {
  projectId: string;
  env: ProjectEnvironment;
  saving: boolean;
  onSavingChange: (v: boolean) => void;
  onMessage: (msg: string) => void;
  onSaved: () => Promise<void>;
  onDeleted: () => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(env.name);
  const [baseUrl, setBaseUrl] = useState(env.base_url ?? "");
  const [secretsHint, setSecretsHint] = useState(env.secrets_hint ?? "");
  const [isDefault, setIsDefault] = useState(env.is_default);

  useEffect(() => {
    setName(env.name);
    setBaseUrl(env.base_url ?? "");
    setSecretsHint(env.secrets_hint ?? "");
    setIsDefault(env.is_default);
  }, [env.id, env.name, env.base_url, env.secrets_hint, env.is_default]);

  const dirty =
    name.trim() !== env.name ||
    baseUrl !== (env.base_url ?? "") ||
    secretsHint !== (env.secrets_hint ?? "") ||
    isDefault !== env.is_default;

  const save = async () => {
    if (!name.trim()) {
      onMessage("Environment name is required");
      return;
    }
    onSavingChange(true);
    onMessage("");
    try {
      await updateEnvironment(projectId, env.id, {
        name: name.trim(),
        base_url: baseUrl.trim(),
        secrets_hint: secretsHint.trim(),
        is_default: isDefault,
      });
      onMessage(`Saved environment "${name.trim()}"`);
      await onSaved();
    } catch (e) {
      onMessage(e instanceof Error ? e.message : "Could not save environment");
    } finally {
      onSavingChange(false);
    }
  };

  const remove = async () => {
    if (!window.confirm(`Delete environment "${env.name}" and its modules?`)) return;
    onSavingChange(true);
    try {
      await deleteEnvironment(projectId, env.id);
      await onDeleted();
      onMessage(`Deleted environment "${env.name}"`);
    } catch (e) {
      onMessage(e instanceof Error ? e.message : "Could not delete");
    } finally {
      onSavingChange(false);
    }
  };

  return (
    <div className="ds-card border-brand-200">
      <div className="ds-card-header flex items-center justify-between">
        <h3 className="text-sm font-semibold">Edit environment</h3>
        {dirty && <Badge variant="warning">Unsaved</Badge>}
      </div>
      <div className="ds-card-body space-y-3">
        <div>
          <label className="text-xs font-medium text-[var(--text-secondary)] block mb-1">Name</label>
          <input
            className="ds-input text-sm w-full"
            value={name}
            onChange={(e) => setName(e.target.value)}
            suppressHydrationWarning
          />
        </div>
        <div>
          <label className="text-xs font-medium text-[var(--text-secondary)] block mb-1">Base URL</label>
          <input
            className="ds-input text-sm font-mono w-full"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://your-app.example.com"
            suppressHydrationWarning
          />
          <p className="text-[10px] text-[var(--text-tertiary)] mt-1">
            Used by Discovery, Studio debug, and Executions for this environment
          </p>
        </div>
        <div>
          <label className="text-xs font-medium text-[var(--text-secondary)] block mb-1">Secrets hint (optional)</label>
          <input
            className="ds-input text-sm w-full"
            value={secretsHint}
            onChange={(e) => setSecretsHint(e.target.value)}
            placeholder="e.g. Vault path or credential profile name"
            suppressHydrationWarning
          />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={isDefault}
            onChange={(e) => setIsDefault(e.target.checked)}
            suppressHydrationWarning
          />
          Default environment for this project
        </label>
        <div className="flex flex-wrap gap-2 pt-1">
          <button
            type="button"
            onClick={save}
            disabled={saving || !dirty || !name.trim()}
            className="ds-btn-primary text-sm inline-flex items-center gap-1"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save changes
          </button>
          <button
            type="button"
            onClick={() => {
              setName(env.name);
              setBaseUrl(env.base_url ?? "");
              setSecretsHint(env.secrets_hint ?? "");
              setIsDefault(env.is_default);
            }}
            disabled={saving || !dirty}
            className="ds-btn-secondary text-sm inline-flex items-center gap-1"
          >
            <X className="w-4 h-4" />
            Reset
          </button>
          <button type="button" onClick={onCancel} className="ds-btn-ghost text-sm">
            Close
          </button>
          <button
            type="button"
            onClick={remove}
            disabled={saving}
            className="ds-btn-ghost text-sm text-red-600 ml-auto inline-flex items-center gap-1"
          >
            <Trash2 className="w-4 h-4" />
            Delete
          </button>
        </div>
        <p className="text-[10px] text-[var(--text-tertiary)]">
          {env.test_case_count} test case(s) in this environment
        </p>
      </div>
    </div>
  );
}

function EditModuleCard({
  projectId,
  mod,
  saving,
  onSavingChange,
  onMessage,
  onSaved,
  onDeleted,
  onCancel,
}: {
  projectId: string;
  mod: ProjectModule;
  saving: boolean;
  onSavingChange: (v: boolean) => void;
  onMessage: (msg: string) => void;
  onSaved: () => Promise<void>;
  onDeleted: () => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(mod.name);
  const [description, setDescription] = useState(mod.description ?? "");

  useEffect(() => {
    setName(mod.name);
    setDescription(mod.description ?? "");
  }, [mod.id, mod.name, mod.description]);

  const dirty = name.trim() !== mod.name || description !== (mod.description ?? "");

  const save = async () => {
    if (!name.trim()) {
      onMessage("Module name is required");
      return;
    }
    onSavingChange(true);
    onMessage("");
    try {
      await updateModule(projectId, mod.id, {
        name: name.trim(),
        description: description.trim(),
      });
      onMessage(`Saved module "${name.trim()}"`);
      await onSaved();
    } catch (e) {
      onMessage(e instanceof Error ? e.message : "Could not save module");
    } finally {
      onSavingChange(false);
    }
  };

  const remove = async () => {
    if (!window.confirm(`Delete module "${mod.name}"?`)) return;
    onSavingChange(true);
    try {
      await deleteModule(projectId, mod.id);
      await onDeleted();
      onMessage(`Deleted module "${mod.name}"`);
    } catch (e) {
      onMessage(e instanceof Error ? e.message : "Could not delete");
    } finally {
      onSavingChange(false);
    }
  };

  return (
    <div className="ds-card border-brand-200">
      <div className="ds-card-header flex items-center justify-between">
        <h3 className="text-sm font-semibold">Edit module</h3>
        {dirty && <Badge variant="warning">Unsaved</Badge>}
      </div>
      <div className="ds-card-body space-y-3">
        <div>
          <label className="text-xs font-medium text-[var(--text-secondary)] block mb-1">Name</label>
          <input
            className="ds-input text-sm w-full"
            value={name}
            onChange={(e) => setName(e.target.value)}
            suppressHydrationWarning
          />
        </div>
        <div>
          <label className="text-xs font-medium text-[var(--text-secondary)] block mb-1">Code prefix</label>
          <input className="ds-input text-sm font-mono w-full bg-[var(--surface-sunken)]" value={mod.code} readOnly />
          <p className="text-[10px] text-[var(--text-tertiary)] mt-1">Auto-updated from name when you save</p>
        </div>
        <div>
          <label className="text-xs font-medium text-[var(--text-secondary)] block mb-1">Description (optional)</label>
          <textarea
            className="ds-input text-sm w-full min-h-[72px]"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Short description for this module"
            suppressHydrationWarning
          />
        </div>
        <div className="flex flex-wrap gap-2 pt-1">
          <button
            type="button"
            onClick={save}
            disabled={saving || !dirty || !name.trim()}
            className="ds-btn-primary text-sm inline-flex items-center gap-1"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save changes
          </button>
          <button
            type="button"
            onClick={() => {
              setName(mod.name);
              setDescription(mod.description ?? "");
            }}
            disabled={saving || !dirty}
            className="ds-btn-secondary text-sm inline-flex items-center gap-1"
          >
            <X className="w-4 h-4" />
            Reset
          </button>
          <button type="button" onClick={onCancel} className="ds-btn-ghost text-sm">
            Close
          </button>
          <button
            type="button"
            onClick={remove}
            disabled={saving}
            className="ds-btn-ghost text-sm text-red-600 ml-auto inline-flex items-center gap-1"
          >
            <Trash2 className="w-4 h-4" />
            Delete
          </button>
        </div>
        <p className="text-[10px] text-[var(--text-tertiary)]">
          {mod.test_case_count} test case(s) in this module
        </p>
      </div>
    </div>
  );
}
