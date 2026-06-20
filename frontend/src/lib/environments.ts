import { apiFetch } from "@/lib/api";
import type { ProjectModule } from "@/lib/modules";

export interface ProjectEnvironment {
  id: string;
  project_id: string;
  name: string;
  env_type: string;
  base_url: string | null;
  config: Record<string, unknown> | null;
  secrets_hint: string | null;
  is_default: boolean;
  test_case_count: number;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceHierarchy {
  project_id: string;
  environments: (ProjectEnvironment & { modules: ProjectModule[] })[];
}

export async function fetchEnvironments(projectId: string) {
  return apiFetch<ProjectEnvironment[]>(`/api/v1/projects/${projectId}/environments`);
}

export async function fetchWorkspaceHierarchy(projectId: string) {
  return apiFetch<WorkspaceHierarchy>(`/api/v1/projects/${projectId}/environments/hierarchy`);
}

export async function createEnvironment(
  projectId: string,
  body: {
    name: string;
    base_url?: string;
    is_default?: boolean;
    secrets_hint?: string;
  }
) {
  return apiFetch<ProjectEnvironment>(`/api/v1/projects/${projectId}/environments`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateEnvironment(
  projectId: string,
  envId: string,
  body: Partial<Pick<ProjectEnvironment, "name" | "base_url" | "is_default" | "secrets_hint">>
) {
  return apiFetch<ProjectEnvironment>(`/api/v1/projects/${projectId}/environments/${envId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteEnvironment(projectId: string, envId: string) {
  return apiFetch<void>(`/api/v1/projects/${projectId}/environments/${envId}`, {
    method: "DELETE",
  });
}

export function defaultEnvironment(environments: ProjectEnvironment[]) {
  return environments.find((e) => e.is_default) ?? environments[0] ?? null;
}

export function hierarchyLabel(
  env: ProjectEnvironment | null | undefined,
  mod: ProjectModule | null | undefined
) {
  if (!env) return "Select environment";
  if (!mod) return `${env.name} · All modules`;
  return `${env.name} · ${mod.name}`;
}
