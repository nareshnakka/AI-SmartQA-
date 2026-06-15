/** Persisted active project — shared across all QEOS pages until user changes it. */

export const ACTIVE_PROJECT_KEY = "qeos_active_project_id";
export const DEFAULT_LANDING_PATH = "/quality-studio";

export function getStoredProjectId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACTIVE_PROJECT_KEY);
}

export function setStoredProjectId(projectId: string | null): void {
  if (typeof window === "undefined") return;
  if (projectId) localStorage.setItem(ACTIVE_PROJECT_KEY, projectId);
  else localStorage.removeItem(ACTIVE_PROJECT_KEY);
}

export function landingPath(projectId?: string | null): string {
  if (projectId) return `${DEFAULT_LANDING_PATH}?project=${encodeURIComponent(projectId)}`;
  return DEFAULT_LANDING_PATH;
}
