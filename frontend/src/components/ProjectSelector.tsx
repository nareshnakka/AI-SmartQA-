"use client";

import { useEffect, useState, useCallback } from "react";
import { useActiveProject } from "@/context/ProjectContext";
import { fetchProjects, type ProjectListItem } from "@/lib/projects";

type Project = ProjectListItem;

interface ProjectSelectorProps {
  value: string;
  onChange: (id: string) => void;
  className?: string;
  showCounts?: boolean;
}

export function ProjectSelector({
  value,
  onChange,
  className = "ds-input py-1.5 text-sm w-48",
  showCounts = true,
}: ProjectSelectorProps) {
  const { projects } = useProjectsList();

  return (
    <select
      className={className}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      suppressHydrationWarning
    >
      <option value="">Select project...</option>
      {projects.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name}
          {showCounts && p.test_case_count != null ? ` (${p.test_case_count} tests)` : ""}
        </option>
      ))}
    </select>
  );
}

/** Global active project — synced via context + localStorage (shown in top bar). */
export function ActiveProjectSelector({
  className = "ds-input py-1.5 text-sm w-52",
  showCounts = true,
}: {
  className?: string;
  showCounts?: boolean;
}) {
  const { projectId, setProjectId, projects, loading, activeProject } = useActiveProject();

  if (loading && !projects.length) {
    return (
      <select className={className} disabled suppressHydrationWarning>
        <option>Loading projects…</option>
      </select>
    );
  }

  return (
    <select
      className={className}
      value={projectId}
      onChange={(e) => setProjectId(e.target.value)}
      title={activeProject?.name ?? "Active project"}
      suppressHydrationWarning
    >
      {projects.length === 0 && <option value="">No projects</option>}
      {projects.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name}
          {showCounts && p.test_case_count != null ? ` (${p.test_case_count})` : ""}
        </option>
      ))}
    </select>
  );
}

function useProjectsList() {
  const { projects, loading } = useActiveProject();
  const [local, setLocal] = useState<Project[]>([]);

  useEffect(() => {
    if (projects.length) return;
    fetchProjects().then(setLocal).catch(() => setLocal([]));
  }, [projects.length]);

  return { projects: projects.length ? projects : local, loading };
}

export function useProjects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback((refresh = true) => {
    setLoading(true);
    setError(null);
    fetchProjects({ refresh })
      .then(setProjects)
      .catch((e: Error) => setError(e.message || "Failed to load projects"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    reload(false);
  }, [reload]);

  return { projects, loading, error, reload };
}
