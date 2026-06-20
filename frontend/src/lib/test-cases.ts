import { apiFetch } from "@/lib/api";

export type TestCaseStep = string | { description: string; disabled?: boolean };

export interface AutomationTestCase {
  id: string;
  title: string;
  case_code?: string | null;
  module_id?: string | null;
  module_name?: string | null;
  environment_id?: string | null;
  environment_name?: string | null;
  priority: string;
  status: string;
  steps?: TestCaseStep[];
  expected_results?: string[];
}

export function stepDescription(step: TestCaseStep): string {
  return typeof step === "string" ? step : step.description;
}

export function isStepDisabled(step: TestCaseStep): boolean {
  return typeof step === "object" && Boolean(step.disabled);
}

export function isAutomationEnabled(tc: { status: string }) {
  return tc.status?.toLowerCase() !== "disabled";
}

export async function updateTestCase(
  projectId: string,
  caseId: string,
  body: Partial<Pick<AutomationTestCase, "title" | "steps" | "expected_results" | "status" | "priority">>
) {
  return apiFetch<AutomationTestCase>(`/api/v1/projects/${projectId}/test-cases/${caseId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function bulkTestCaseAction(
  projectId: string,
  action: "delete" | "disable" | "enable",
  testCaseIds: string[]
) {
  return apiFetch<{ updated: number; deleted: number }>(
    `/api/v1/projects/${projectId}/test-cases/bulk-action`,
    {
      method: "POST",
      body: JSON.stringify({ action, test_case_ids: testCaseIds }),
    }
  );
}

export async function fetchTestCases(
  projectId: string,
  opts?: { forAutomation?: boolean; moduleIds?: string[]; environmentIds?: string[] }
) {
  const params = new URLSearchParams();
  if (opts?.forAutomation) params.set("for_automation", "true");
  if (opts?.moduleIds?.length) params.set("module_id", opts.moduleIds.join(","));
  if (opts?.environmentIds?.length) params.set("environment_id", opts.environmentIds.join(","));
  const qs = params.toString() ? `?${params}` : "";
  return apiFetch<AutomationTestCase[]>(`/api/v1/projects/${projectId}/test-cases${qs}`);
}

export async function createTestCase(
  projectId: string,
  body: {
    title?: string;
    description?: string;
    steps?: TestCaseStep[];
    expected_results?: string[];
    priority?: string;
    module_id?: string;
    module_name?: string;
    environment_id?: string;
  }
) {
  return apiFetch<AutomationTestCase>(`/api/v1/projects/${projectId}/test-cases`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
