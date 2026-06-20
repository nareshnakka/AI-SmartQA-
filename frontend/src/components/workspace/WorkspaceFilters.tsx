"use client";

import { WorkspaceHierarchy } from "@/components/workspace/WorkspaceHierarchy";
import type { ProjectEnvironment } from "@/lib/environments";
import type { ProjectModule } from "@/lib/modules";

interface WorkspaceFiltersProps {
  environments: ProjectEnvironment[];
  modules: ProjectModule[];
  activeEnvironmentId: string | null;
  activeModuleId: string | null;
  onEnvironmentChange: (id: string) => void;
  onModuleChange: (id: string | null) => void;
  className?: string;
}

/** Page-level hierarchy selector (same as top bar). */
export function WorkspaceFilters({
  environments,
  modules,
  activeEnvironmentId,
  activeModuleId,
  onEnvironmentChange,
  onModuleChange,
  className,
}: WorkspaceFiltersProps) {
  return (
    <WorkspaceHierarchy
      environments={environments}
      modules={modules}
      activeEnvironmentId={activeEnvironmentId}
      activeModuleId={activeModuleId}
      onEnvironmentChange={onEnvironmentChange}
      onModuleChange={onModuleChange}
      className={className}
    />
  );
}
