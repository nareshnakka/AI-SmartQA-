"use client";

import { useActiveProject } from "@/context/ProjectContext";
import { useWorkspaceScope } from "@/lib/workspace";
import { WorkspaceHierarchy } from "@/components/workspace/WorkspaceHierarchy";

/** Top bar: Project (separate) → Environment → Module */
export function WorkspaceBar() {
  const { projectId, ready } = useActiveProject();
  const ws = useWorkspaceScope(projectId || undefined);

  if (!ready || !projectId) return null;

  return (
    <WorkspaceHierarchy
      environments={ws.environments}
      modules={ws.modules}
      activeEnvironmentId={ws.activeEnvironmentId}
      activeModuleId={ws.activeModuleId}
      onEnvironmentChange={ws.setActiveEnvironmentId}
      onModuleChange={ws.setActiveModuleId}
      compact
      className="min-w-0"
    />
  );
}
