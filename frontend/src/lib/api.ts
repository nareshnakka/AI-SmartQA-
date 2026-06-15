/** Direct backend URL (docs, exports). Browser API calls use same-origin proxy in next.config.js. */
export const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const API_BASE = typeof window !== "undefined" ? "" : BACKEND_URL;

import { authHeaders, clearSession } from "./auth";

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...options?.headers,
    },
  });

  if (response.status === 401 && typeof window !== "undefined") {
    clearSession();
    if (!window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new Error("Authentication required");
  }

  if (!response.ok) {
    const err = await response.text();
    throw new Error(err || `API error: ${response.status}`);
  }

  if (response.status === 204) return undefined as T;
  return response.json();
}

export async function apiUpload<T>(path: string, file: File, extra?: Record<string, string>): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const params = extra ? "?" + new URLSearchParams(extra).toString() : "";
  const response = await fetch(`${API_BASE}${path}${params}`, {
    method: "POST",
    body: form,
    headers: authHeaders(),
  });
  if (!response.ok) throw new Error(`Upload failed: ${response.status}`);
  return response.json();
}

export function exportUrl(projectId: string, format: "json" | "csv") {
  return `${BACKEND_URL}/api/v1/projects/${projectId}/export/${format}`;
}

export function automationExportUrl(projectId: string, assetId: string) {
  return `${BACKEND_URL}/api/v1/projects/${projectId}/automation/assets/${assetId}/export`;
}

export function executionVideoUrl(projectId: string, runId: string, videoId: string) {
  return `/api/v1/projects/${projectId}/executions/${runId}/videos/${videoId}`;
}

export function executionExportUrl(projectId: string, runId: string, format: "html" | "json" | "csv") {
  return `/api/v1/projects/${projectId}/executions/${runId}/export?format=${format}`;
}

export function performanceExportUrl(projectId: string, runId: string, format: "html" | "json" | "csv" = "html") {
  return `/api/v1/projects/${projectId}/performance/runs/${runId}/export?format=${format}`;
}

export { API_BASE, BACKEND_URL as API_BASE_DIRECT };
