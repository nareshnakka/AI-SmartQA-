import { apiFetch } from "@/lib/api";

export interface ProjectModule {
  id: string;
  project_id: string;
  environment_id: string | null;
  name: string;
  code: string;
  description: string;
  test_case_count: number;
  created_at: string;
}

export async function fetchModules(projectId: string, environmentId: string) {
  return apiFetch<ProjectModule[]>(
    `/api/v1/projects/${projectId}/modules?environment_id=${encodeURIComponent(environmentId)}`
  );
}

export async function createModule(
  projectId: string,
  environmentId: string,
  name: string,
  description?: string
) {
  return apiFetch<ProjectModule>(`/api/v1/projects/${projectId}/modules`, {
    method: "POST",
    body: JSON.stringify({ name, environment_id: environmentId, description }),
  });
}

export async function updateModule(
  projectId: string,
  moduleId: string,
  body: { name?: string; description?: string }
) {
  return apiFetch<ProjectModule>(`/api/v1/projects/${projectId}/modules/${moduleId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteModule(projectId: string, moduleId: string) {
  return apiFetch<{ deleted: boolean }>(`/api/v1/projects/${projectId}/modules/${moduleId}`, {
    method: "DELETE",
  });
}

export function isAllModulesSelected(activeModuleId: string | null) {
  return !activeModuleId;
}

export function moduleFilterLabel(activeModuleId: string | null, modules: ProjectModule[]) {
  if (isAllModulesSelected(activeModuleId)) return "All modules";
  return modules.find((m) => m.id === activeModuleId)?.name ?? "Module";
}
