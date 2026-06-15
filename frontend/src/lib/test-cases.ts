import { apiFetch } from "@/lib/api";

export interface AutomationTestCase {
  id: string;
  title: string;
  priority: string;
  status: string;
  steps?: string[];
  expected_results?: string[];
}

export function isAutomationEnabled(tc: { status: string }) {
  return tc.status?.toLowerCase() !== "disabled";
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

export async function fetchTestCases(projectId: string, forAutomation = false) {
  const qs = forAutomation ? "?for_automation=true" : "";
  return apiFetch<AutomationTestCase[]>(`/api/v1/projects/${projectId}/test-cases${qs}`);
}
