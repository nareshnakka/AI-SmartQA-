/** Direct backend URL (docs, exports, fallback when Next proxy is down). */
export const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

import { authHeaders, clearSession } from "./auth";

function apiBases(): string[] {
  if (typeof window === "undefined") return [BACKEND_URL];
  // Same-origin via next.config rewrites first; direct URL if proxy/backend down.
  const bases = ["", BACKEND_URL];
  return [...new Set(bases)];
}

export function isBackendNetworkError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  const msg = err.message.toLowerCase();
  return (
    err.name === "TypeError" &&
    (msg.includes("failed to fetch") ||
      msg.includes("networkerror") ||
      msg.includes("load failed") ||
      msg.includes("cannot reach qeos api"))
  );
}

function backendUnreachableMessage(): string {
  return (
    `Cannot reach QEOS API at ${BACKEND_URL}. ` +
    "Start the backend: run scripts\\restart-backend.bat (or setup-and-run.bat). " +
    "Keep the backend terminal window open on port 8000."
  );
}

function wrapNetworkError(err: unknown): Error {
  if (isBackendNetworkError(err)) {
    return new Error(backendUnreachableMessage());
  }
  return err instanceof Error ? err : new Error(String(err));
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let lastError: unknown;

  for (const base of apiBases()) {
    try {
      const response = await fetch(`${base}${path}`, {
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
    } catch (err) {
      lastError = err;
      // Retry on direct backend URL only for network failures (not HTTP 4xx/5xx).
      if (base === "" && isBackendNetworkError(err)) {
        continue;
      }
      throw err;
    }
  }

  throw wrapNetworkError(lastError);
}

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  try {
    return await request<T>(path, options);
  } catch (err) {
    throw wrapNetworkError(err);
  }
}

export async function checkBackendHealth(): Promise<{
  ok: boolean;
  message?: string;
  execution_executor?: string;
  playwright_browsers?: boolean;
}> {
  try {
    const h = await apiFetch<{
      status?: string;
      execution_executor?: string;
      playwright_browsers?: boolean;
    }>("/health");
    if (h.execution_executor !== "asset_live_v2") {
      return {
        ok: false,
        message: "Backend is running but outdated — restart scripts\\restart-backend.bat",
        execution_executor: h.execution_executor,
        playwright_browsers: h.playwright_browsers,
      };
    }
    return {
      ok: true,
      execution_executor: h.execution_executor,
      playwright_browsers: h.playwright_browsers,
    };
  } catch (err) {
    return { ok: false, message: wrapNetworkError(err).message };
  }
}

export async function apiUpload<T>(path: string, file: File, extra?: Record<string, string>): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const params = extra ? "?" + new URLSearchParams(extra).toString() : "";
  let lastError: unknown;

  for (const base of apiBases()) {
    try {
      const response = await fetch(`${base}${path}${params}`, {
        method: "POST",
        body: form,
        headers: authHeaders(),
      });
      if (!response.ok) throw new Error(`Upload failed: ${response.status}`);
      return response.json();
    } catch (err) {
      lastError = err;
      if (base === "" && isBackendNetworkError(err)) continue;
      throw wrapNetworkError(err);
    }
  }
  throw wrapNetworkError(lastError);
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

export function executionLiveFrameUrl(projectId: string, runId: string, cacheBust?: number) {
  const q = cacheBust != null ? `?t=${cacheBust}` : "";
  return `${BACKEND_URL}/api/v1/projects/${projectId}/executions/${runId}/live-frame${q}`;
}

export function executionExportUrl(projectId: string, runId: string, format: "html" | "json" | "csv") {
  return `/api/v1/projects/${projectId}/executions/${runId}/export?format=${format}`;
}

export function performanceExportUrl(projectId: string, runId: string, format: "html" | "json" | "csv" = "html") {
  return `/api/v1/projects/${projectId}/performance/runs/${runId}/export?format=${format}`;
}

const API_BASE = typeof window !== "undefined" ? "" : BACKEND_URL;
export { API_BASE, BACKEND_URL as API_BASE_DIRECT };
