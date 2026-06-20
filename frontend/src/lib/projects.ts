import { apiFetch } from "@/lib/api";

export interface ProjectListItem {
  id: string;
  name: string;
  description?: string | null;
  requirement_count?: number;
  test_case_count?: number;
  created_at?: string;
  updated_at?: string | null;
}

const CACHE_TTL_MS = 30_000;

let cache: ProjectListItem[] | null = null;
let cacheAt = 0;
let inflight: Promise<ProjectListItem[]> | null = null;

export function invalidateProjectsCache(): void {
  cache = null;
  cacheAt = 0;
}

export async function fetchProjects(options?: { refresh?: boolean }): Promise<ProjectListItem[]> {
  const now = Date.now();
  if (!options?.refresh && cache && now - cacheAt < CACHE_TTL_MS) {
    return cache;
  }

  if (inflight && !options?.refresh) {
    return inflight;
  }

  inflight = apiFetch<ProjectListItem[]>("/api/v1/projects")
    .then((list) => {
      cache = list;
      cacheAt = Date.now();
      return list;
    })
    .finally(() => {
      inflight = null;
    });

  return inflight;
}
