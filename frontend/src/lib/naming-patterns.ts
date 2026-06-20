import { apiFetch } from "@/lib/api";

export type NamingCategory = "functional" | "automation" | "performance" | "security";

export interface CategoryPatternConfig {
  pattern: string;
  seq_digits: number;
}

export interface NamingPatternsResponse {
  project_id: string;
  patterns: Record<NamingCategory, CategoryPatternConfig>;
  defaults: Record<NamingCategory, CategoryPatternConfig>;
  token_help: Record<string, string>;
  categories: NamingCategory[];
  preview_context: {
    project_name: string;
    environment_name: string;
    module_name: string;
  };
  previews?: Record<NamingCategory, string>;
}

export async function fetchNamingPatterns(projectId: string) {
  return apiFetch<NamingPatternsResponse>(`/api/v1/projects/${projectId}/naming-patterns`);
}

export async function updateNamingPatterns(
  projectId: string,
  updates: Partial<Record<NamingCategory, Partial<CategoryPatternConfig>>>
) {
  return apiFetch<NamingPatternsResponse>(`/api/v1/projects/${projectId}/naming-patterns`, {
    method: "PUT",
    body: JSON.stringify(updates),
  });
}

export async function previewNamingPattern(
  projectId: string,
  body: {
    pattern: string;
    seq_digits?: number;
    environment_name?: string;
    module_name?: string;
    seq?: number;
  }
) {
  return apiFetch<{ preview: string }>(`/api/v1/projects/${projectId}/naming-patterns/preview`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export const CATEGORY_LABELS: Record<NamingCategory, string> = {
  functional: "Functional",
  automation: "Automation",
  performance: "Performance",
  security: "Security",
};

export const CATEGORY_DESCRIPTIONS: Record<NamingCategory, string> = {
  functional: "Discovery and manual / generated functional test cases (FTC)",
  automation: "Playwright, Cypress, Selenium and other automation assets (AP_TC)",
  performance: "JMeter, k6 and load test assets (PJ_TC)",
  security: "Security test cases and scans (SEC_TC)",
};
