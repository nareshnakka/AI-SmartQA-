import { useCallback, useEffect, useMemo, useState } from "react";
import {
  defaultEnvironment,
  fetchWorkspaceHierarchy,
  type ProjectEnvironment,
} from "@/lib/environments";
import { fetchModules, type ProjectModule } from "@/lib/modules";

interface WorkspacePersist {
  activeEnvId: string | null;
  activeModuleId: string | null;
}

function storageKey(projectId: string) {
  return `qeos-workspace-v2-${projectId}`;
}

function loadPersist(projectId: string): WorkspacePersist {
  if (typeof window === "undefined") {
    return { activeEnvId: null, activeModuleId: null };
  }
  try {
    const raw = localStorage.getItem(storageKey(projectId));
    if (raw) return JSON.parse(raw) as WorkspacePersist;
    const legacy = localStorage.getItem(`qeos-workspace-${projectId}`);
    if (legacy) {
      const old = JSON.parse(legacy) as {
        activeEnvId?: string | null;
        envFilterIds?: string[];
        moduleFilterIds?: string[];
      };
      return {
        activeEnvId: old.activeEnvId ?? old.envFilterIds?.[0] ?? null,
        activeModuleId: old.moduleFilterIds?.length === 1 ? old.moduleFilterIds[0] : null,
      };
    }
  } catch {
    /* ignore */
  }
  return { activeEnvId: null, activeModuleId: null };
}

function savePersist(projectId: string, state: WorkspacePersist) {
  if (typeof window === "undefined") return;
  localStorage.setItem(storageKey(projectId), JSON.stringify(state));
  window.dispatchEvent(new CustomEvent("qeos-workspace-change", { detail: { projectId } }));
}

/** Hierarchical scope: Project → Environment → Module (all user-configured names). */
export function useWorkspaceScope(projectId: string | null | undefined) {
  const [environments, setEnvironments] = useState<ProjectEnvironment[]>([]);
  const [modules, setModules] = useState<ProjectModule[]>([]);
  const [activeEnvironmentId, setActiveEnvironmentIdState] = useState<string | null>(null);
  const [activeModuleId, setActiveModuleIdState] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const persist = useCallback(
    (envId: string | null, modId: string | null) => {
      if (!projectId) return;
      savePersist(projectId, { activeEnvId: envId, activeModuleId: modId });
    },
    [projectId]
  );

  const setActiveEnvironmentId = useCallback(
    (id: string | null) => {
      setActiveEnvironmentIdState(id);
      setActiveModuleIdState(null);
      persist(id, null);
    },
    [persist]
  );

  const setActiveModuleId = useCallback(
    (id: string | null) => {
      setActiveModuleIdState(id);
      persist(activeEnvironmentId, id);
    },
    [persist, activeEnvironmentId]
  );

  const reloadHierarchy = useCallback(async () => {
    if (!projectId) {
      setEnvironments([]);
      setModules([]);
      return;
    }
    setLoading(true);
    try {
      const tree = await fetchWorkspaceHierarchy(projectId);
      setEnvironments(tree.environments);
      const saved = loadPersist(projectId);
      const envId =
        saved.activeEnvId && tree.environments.some((e) => e.id === saved.activeEnvId)
          ? saved.activeEnvId
          : defaultEnvironment(tree.environments)?.id ?? null;
      setActiveEnvironmentIdState(envId);
      const envNode = tree.environments.find((e) => e.id === envId);
      const mods = envNode?.modules ?? (envId ? await fetchModules(projectId, envId) : []);
      setModules(mods);
      const modId =
        saved.activeModuleId && mods.some((m) => m.id === saved.activeModuleId)
          ? saved.activeModuleId
          : null;
      setActiveModuleIdState(modId);
    } catch {
      setEnvironments([]);
      setModules([]);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  const reloadModules = useCallback(async () => {
    if (!projectId || !activeEnvironmentId) {
      setModules([]);
      return;
    }
    try {
      setModules(await fetchModules(projectId, activeEnvironmentId));
    } catch {
      setModules([]);
    }
  }, [projectId, activeEnvironmentId]);

  useEffect(() => {
    if (!projectId) {
      setActiveEnvironmentIdState(null);
      setActiveModuleIdState(null);
      setEnvironments([]);
      setModules([]);
      return;
    }
    reloadHierarchy();
    const onChange = (e: Event) => {
      const detail = (e as CustomEvent<{ projectId: string }>).detail;
      if (detail?.projectId === projectId) {
        const saved = loadPersist(projectId);
        setActiveEnvironmentIdState(saved.activeEnvId);
        setActiveModuleIdState(saved.activeModuleId);
      }
    };
    window.addEventListener("qeos-workspace-change", onChange);
    return () => window.removeEventListener("qeos-workspace-change", onChange);
  }, [projectId, reloadHierarchy]);

  useEffect(() => {
    reloadModules();
  }, [reloadModules]);

  const activeEnvironment = useMemo(
    () => environments.find((e) => e.id === activeEnvironmentId) ?? defaultEnvironment(environments),
    [environments, activeEnvironmentId]
  );

  const activeModule = useMemo(
    () => modules.find((m) => m.id === activeModuleId) ?? null,
    [modules, activeModuleId]
  );

  const scopeEnvironmentId = activeEnvironment?.id ?? null;
  const moduleQueryIds = useMemo(() => (activeModuleId ? [activeModuleId] : undefined), [activeModuleId]);
  const environmentQueryIds = useMemo(
    () => (scopeEnvironmentId ? [scopeEnvironmentId] : undefined),
    [scopeEnvironmentId]
  );

  return {
    environments,
    modules,
    loading,
    activeEnvironmentId: scopeEnvironmentId,
    activeEnvironment,
    activeModuleId,
    activeModule,
    setActiveEnvironmentId,
    setActiveModuleId,
    reloadHierarchy,
    reloadModules,
    scopeEnvironmentId,
    moduleQueryIds,
    environmentQueryIds,
  };
}

export const useWorkspaceFilter = useWorkspaceScope;
