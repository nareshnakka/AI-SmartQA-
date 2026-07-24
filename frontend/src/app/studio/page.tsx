"use client";

import { Suspense, useEffect, useState, useCallback, useRef, useMemo } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import {
  Play, Save, GitCompare, CheckCircle2, Loader2, Sparkles,
  ChevronDown, AlertCircle, Download, PlayCircle, Upload, Bug, GitBranch,
  CheckSquare, Square, Trash2, Ban, RotateCcw, Video,
} from "lucide-react";
import { AppShell } from "@/components/shell/AppShell";
import { PageHeader, Badge, Tabs } from "@/components/ui";
import { CodeEditor, FileTree } from "@/components/studio/CodeEditor";
import {
  TestCaseFlowView, buildFlowSteps, parseStepsFromScript, applyDebugFlowSteps, type FlowStep,
} from "@/components/flow/TestCaseFlowView";
import { useActiveProject } from "@/context/ProjectContext";
import { apiFetch, automationExportUrl, checkBackendHealth, executionLiveFrameUrl, executionVideoUrl } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import { bulkTestCaseAction, fetchTestCases, isAutomationEnabled, isStepDisabled, stepDescription, updateTestCase, type TestCaseStep, type TestCasesUpdatedDetail } from "@/lib/test-cases";
import { moduleFilterLabel } from "@/lib/modules";
import { useWorkspaceScope } from "@/lib/workspace";
import { WorkspaceFilters } from "@/components/workspace/WorkspaceFilters";
import Link from "next/link";

interface AutomationAsset {
  id: string; name: string; framework: string; language: string;
  files: { path: string; content: string; type?: string }[];
  dependencies: string[]; ci_pipeline_snippet: string | null;
  version: number; status: string; test_case_ids?: string[];
}
interface Framework { id: string; name: string; language: string }
interface TestCaseItem {
  id: string; title: string; case_code?: string | null; module_id?: string | null; module_name?: string | null;
  steps: TestCaseStep[]; expected_results: string[]; priority: string; status: string;
}

function StudioPageContent() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { projectId } = useActiveProject();
  const ws = useWorkspaceScope(projectId);
  const {
    environments,
    modules,
    activeModuleId,
    setActiveModuleId,
    activeEnvironmentId,
    setActiveEnvironmentId,
    moduleQueryIds,
    environmentQueryIds,
    activeEnvironment,
    activeModule,
    reloadHierarchy,
    reloadModules,
  } = ws;
  const prevProjectRef = useRef(projectId);
  const [frameworks, setFrameworks] = useState<Framework[]>([]);
  const [framework, setFramework] = useState("playwright");
  const [assets, setAssets] = useState<AutomationAsset[]>([]);
  const [activeAsset, setActiveAsset] = useState<AutomationAsset | null>(null);
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [validation, setValidation] = useState<{ valid: boolean; issues: { path: string; severity: string; message: string }[] } | null>(null);
  const [versions, setVersions] = useState<AutomationAsset[]>([]);
  const [sideTab, setSideTab] = useState("files");
  const [message, setMessage] = useState("");
  const [showCi, setShowCi] = useState(false);
  const [diffs, setDiffs] = useState<{ path: string; changed: boolean; diff: string }[] | null>(null);
  const [executing, setExecuting] = useState(false);
  const [execMessage, setExecMessage] = useState("");
  const [execRunId, setExecRunId] = useState<string | null>(null);
  const [showPush, setShowPush] = useState(false);
  const [integrations, setIntegrations] = useState<{ id: string; provider: string }[]>([]);
  const [pushForm, setPushForm] = useState({ integration_id: "", owner: "", repo: "", branch: "main", commit_message: "" });
  const [pushing, setPushing] = useState(false);
  const [showSources, setShowSources] = useState(false);
  const [sourceType, setSourceType] = useState("openapi");
  const [sourceJson, setSourceJson] = useState("");
  const [inputSources, setInputSources] = useState<{ id: string; name: string; description: string }[]>([]);
  const [testCases, setTestCases] = useState<TestCaseItem[]>([]);
  const [selectedTestCaseId, setSelectedTestCaseId] = useState<string | null>(null);
  const [baseUrl, setBaseUrl] = useState("");

  type DebugRunState = {
    id: string; status: string;
    progress?: {
      current?: string; current_test_case_id?: string; current_step_index?: number;
      phase?: string; detail?: string; executor?: string;
    };
    logs?: string;
    summary?: { executor?: string; headed?: boolean; embed_live?: boolean };
    results?: {
      test_case_id?: string; title: string; status: string; error?: string;
      has_video?: boolean; video_id?: string; video_url?: string;
      steps?: { order: number; description: string; status: string; expected?: string }[];
    }[];
  };
  const [debugRun, setDebugRun] = useState<DebugRunState | null>(null);
  const [liveFrameTick, setLiveFrameTick] = useState(0);
  const [liveFrameSrc, setLiveFrameSrc] = useState<string | null>(null);
  const liveFrameObjectUrlRef = useRef<string | null>(null);
  const debugPollStoppedRef = useRef(false);
  const [selectedCaseIds, setSelectedCaseIds] = useState<Set<string>>(new Set());
  const [selectedFilePaths, setSelectedFilePaths] = useState<Set<string>>(new Set());
  const [deletingFiles, setDeletingFiles] = useState(false);
  const [managingCases, setManagingCases] = useState(false);
  const [selectedFlowStepIndex, setSelectedFlowStepIndex] = useState<number | null>(null);
  const [savingStep, setSavingStep] = useState(false);

  useEffect(() => {
    apiFetch<{ sources: { id: string; name: string; description: string }[] }>(
      "/api/v1/projects/x/automation/input-sources"
    ).then((d) => setInputSources(d.sources)).catch(() => {});
    apiFetch<{ frameworks: Framework[] }>("/api/v1/projects/x/automation/frameworks")
      .then((d) => setFrameworks(d.frameworks)).catch(() => {});
  }, []);

  useEffect(() => {
    if (prevProjectRef.current === projectId) return;
    prevProjectRef.current = projectId;
    setActiveAsset(null);
    setAssets([]);
    setValidation(null);
    setDebugRun(null);
  }, [projectId]);

  const loadAssets = useCallback(async () => {
    if (!projectId) return;
    const list = await apiFetch<AutomationAsset[]>(`/api/v1/projects/${projectId}/automation/assets`);
    setAssets(list);
    const wanted = searchParams.get("asset");
    const match = wanted ? list.find((a) => a.id === wanted) : null;
    if (match) {
      selectAsset(match);
    } else if (list.length > 0) {
      selectAsset(list[0]);
    }
  }, [projectId, searchParams]);

  useEffect(() => { loadAssets().catch(() => {}); }, [loadAssets]);

  useEffect(() => {
    if (activeEnvironment?.base_url) {
      setBaseUrl(activeEnvironment.base_url);
    }
  }, [activeEnvironment?.id, activeEnvironment?.base_url]);

  useEffect(() => {
    if (!projectId) return;
    fetchTestCases(projectId, { moduleIds: moduleQueryIds, environmentIds: environmentQueryIds })
      .then(setTestCases).catch(() => setTestCases([]));
  }, [projectId, moduleQueryIds, environmentQueryIds]);

  useEffect(() => {
    if (!selectedTestCaseId) return;
    if (!testCases.some((tc) => tc.id === selectedTestCaseId)) {
      setSelectedTestCaseId(testCases[0]?.id ?? null);
    }
  }, [testCases, selectedTestCaseId]);

  const reloadTestCases = useCallback(async () => {
    if (!projectId) return;
    const list = await fetchTestCases(projectId, { moduleIds: moduleQueryIds, environmentIds: environmentQueryIds });
    setTestCases(list);
    return list;
  }, [projectId, moduleQueryIds, environmentQueryIds]);

  useEffect(() => {
    if (!projectId || pathname !== "/studio") return;
    reloadTestCases().catch(() => setTestCases([]));
    reloadModules().catch(() => {});
  }, [pathname, projectId, reloadTestCases, reloadModules]);

  useEffect(() => {
    if (!projectId) return;
    const onVisible = () => {
      if (document.visibilityState !== "visible" || pathname !== "/studio") return;
      reloadTestCases().catch(() => {});
      reloadModules().catch(() => {});
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [projectId, pathname, reloadTestCases, reloadModules]);

  useEffect(() => {
    if (!projectId) return;
    const onTestCasesUpdated = async (e: Event) => {
      const detail = (e as CustomEvent<TestCasesUpdatedDetail>).detail;
      if (detail?.projectId !== projectId) return;

      if (detail.environmentId && detail.environmentId !== activeEnvironmentId) {
        setActiveEnvironmentId(detail.environmentId);
      }
      if (detail.moduleIds?.length === 1) {
        setActiveModuleId(detail.moduleIds[0]!);
      } else if (detail.caseIds?.length) {
        setActiveModuleId(null);
      }

      await reloadHierarchy().catch(() => {});
      const list = await fetchTestCases(projectId, {
        environmentIds: detail.environmentId ? [detail.environmentId] : environmentQueryIds,
        moduleIds: detail.moduleIds?.length === 1 ? [detail.moduleIds[0]!] : undefined,
      }).catch(() => [] as TestCaseItem[]);
      setTestCases(list);
      if (detail.caseIds?.length) {
        const firstVisible = detail.caseIds.find((id) => list.some((tc) => tc.id === id));
        if (firstVisible) setSelectedTestCaseId(firstVisible);
        setSideTab("flow");
      }
    };
    window.addEventListener("qeos-test-cases-updated", onTestCasesUpdated);
    return () => window.removeEventListener("qeos-test-cases-updated", onTestCasesUpdated);
  }, [
    projectId,
    activeEnvironmentId,
    environmentQueryIds,
    setActiveEnvironmentId,
    setActiveModuleId,
    reloadHierarchy,
  ]);

  const toggleCaseSelect = (id: string) => {
    setSelectedCaseIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const bulkManageCases = async (action: "delete" | "disable" | "enable") => {
    if (!projectId || selectedCaseIds.size === 0) return;
    if (action === "delete" && !window.confirm(`Delete ${selectedCaseIds.size} test case(s)?`)) return;
    setManagingCases(true);
    try {
      await bulkTestCaseAction(projectId, action, Array.from(selectedCaseIds));
      setSelectedCaseIds(new Set());
      await reloadTestCases();
      await loadAssets();
    } finally {
      setManagingCases(false);
    }
  };

  const toggleFileSelect = (path: string) => {
    setSelectedFilePaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const selectAllFiles = () => {
    if (!activeAsset?.files.length) return;
    setSelectedFilePaths(new Set(activeAsset.files.map((f) => f.path)));
  };

  const applyAssetUpdate = (updated: AutomationAsset) => {
    setActiveAsset(updated);
    setAssets((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
  };

  const deleteSelectedFiles = async () => {
    if (!projectId || !activeAsset || selectedFilePaths.size === 0) return;
    const paths = Array.from(selectedFilePaths);
    const summary =
      paths.length === 1
        ? `"${paths[0].split("/").pop()}"`
        : `${paths.length} files`;
    if (
      !window.confirm(
        `Are you sure you want to delete ${summary}?\n\nThis cannot be undone. Deleted files cannot be restored.`
      )
    ) {
      return;
    }
    setDeletingFiles(true);
    setMessage("");
    const deletedActive = activeFile !== null && paths.includes(activeFile);
    try {
      const updated = await apiFetch<AutomationAsset>(
        `/api/v1/projects/${projectId}/automation/assets/${activeAsset.id}/files/delete`,
        { method: "POST", body: JSON.stringify({ paths, save_version: false }) }
      );
      applyAssetUpdate(updated);
      setSelectedFilePaths(new Set());
      if (deletedActive) {
        const first = updated.files[0];
        if (first) {
          setActiveFile(first.path);
          setFileContent(first.content);
        } else {
          setActiveFile(null);
          setFileContent("");
        }
      }
      setMessage(`Deleted ${paths.length} file(s) permanently`);
    } catch (e) {
      const err = String(e);
      setMessage(
        err.includes("Not Found")
          ? "Delete failed — run restart.bat so file delete is available, then try again."
          : err
      );
    } finally {
      setDeletingFiles(false);
    }
  };

  useEffect(() => {
    if (debugRun?.status !== "running" || !projectId || !debugRun.id) {
      setLiveFrameTick(0);
      if (liveFrameObjectUrlRef.current) {
        URL.revokeObjectURL(liveFrameObjectUrlRef.current);
        liveFrameObjectUrlRef.current = null;
      }
      setLiveFrameSrc(null);
      return;
    }
    const t = setInterval(() => setLiveFrameTick((n) => n + 1), 350);
    return () => clearInterval(t);
  }, [debugRun?.status, debugRun?.id, projectId]);

  useEffect(() => {
    if (debugRun?.status !== "running" || !projectId || !debugRun?.id) return;

    let cancelled = false;
    const loadFrame = async () => {
      try {
        const url = executionLiveFrameUrl(projectId, debugRun.id, liveFrameTick);
        const res = await fetch(url, { headers: { ...authHeaders() } });
        if (!res.ok || cancelled) return;
        const blob = await res.blob();
        if (cancelled) return;
        const objectUrl = URL.createObjectURL(blob);
        if (liveFrameObjectUrlRef.current) {
          URL.revokeObjectURL(liveFrameObjectUrlRef.current);
        }
        liveFrameObjectUrlRef.current = objectUrl;
        setLiveFrameSrc(objectUrl);
      } catch {
        /* live frame optional */
      }
    };

    loadFrame();
    return () => {
      cancelled = true;
    };
  }, [debugRun?.status, debugRun?.id, projectId, liveFrameTick]);

  const formatDebugError = (raw: string): string => {
    const text = raw.trim();
    if (!text) return text;
    if (text.includes("Not Found") && text.includes("detail")) {
      return "Debug session not found on the API — run restart.bat, then run Debug again.";
    }
    if (/\b404\b/i.test(text) || /not found/i.test(text)) {
      if (text.length < 120 && !text.includes("Error:")) {
        return `The browser loaded a "Not Found" page — check Base URL and the first navigate step URL. (${text})`;
      }
      return `${text}\n\nHint: If the live browser showed "Not Found", your Base URL or step URL may be wrong (404 page), not the test flow order.`;
    }
    return text;
  };

  useEffect(() => {
    if (!projectId) return;
    apiFetch<{ id: string; provider: string }[]>(`/api/v1/integrations?project_id=${projectId}`)
      .then((list) => setIntegrations(list.filter((i) => i.provider === "github")))
      .catch(() => setIntegrations([]));
  }, [projectId]);

  const selectAsset = (asset: AutomationAsset) => {
    setActiveAsset(asset);
    setSelectedFilePaths(new Set());
    const first = asset.files[0];
    if (first) {
      setActiveFile(first.path);
      setFileContent(first.content);
    } else {
      setActiveFile(null);
      setFileContent("");
    }
    setValidation(null);
  };

  const selectFile = (path: string) => {
    setActiveFile(path);
    const file = activeAsset?.files.find((f) => f.path === path);
    setFileContent(file?.content ?? "");
    if (sideTab === "flow" && file?.content) {
      const parsed = parseStepsFromScript(file.content);
      if (parsed.length && !selectedTestCaseId) {
        /* script-only flow preview */
      }
    }
  };

  const filteredTestCases = testCases;

  const selectedTestCase = testCases.find((tc) => tc.id === selectedTestCaseId) ?? filteredTestCases[0] ?? null;

  const scriptFlowSteps: FlowStep[] = activeFile && fileContent ? parseStepsFromScript(fileContent) : [];

  const flowStepsForSelected = (): FlowStep[] => {
    if (!selectedTestCase) return scriptFlowSteps;
    return buildFlowSteps(selectedTestCase.steps ?? [], selectedTestCase.expected_results ?? []);
  };

  const debugResult = selectedTestCase && debugRun?.results
    ? debugRun.results.find((r) => r.test_case_id === selectedTestCase.id) ?? debugRun.results[0]
    : null;

  const debugFlowState = selectedTestCase
    ? applyDebugFlowSteps(flowStepsForSelected(), {
        runStatus: debugRun?.status,
        progress: debugRun?.progress,
        testCaseTitle: selectedTestCase.title,
        testCaseId: selectedTestCase.id,
        resultSteps: debugRun?.results?.find((r) => r.test_case_id === selectedTestCase.id)?.steps,
      })
    : { steps: scriptFlowSteps, activeStepIndex: null };

  const stopDebugRun = async () => {
    if (!projectId || !debugRun?.id || debugRun.status !== "running") return;
    debugPollStoppedRef.current = true;
    setExecuting(false);
    setExecMessage("Stopping debug…");
    try {
      const updated = await apiFetch<DebugRunState>(
        `/api/v1/projects/${projectId}/executions/${debugRun.id}/cancel`,
        { method: "POST" }
      );
      setDebugRun(updated);
      setExecMessage("Debug stopped.");
    } catch (e) {
      setExecMessage(`Stop failed: ${e}`);
    }
  };

  useEffect(() => {
    setSelectedFlowStepIndex(null);
  }, [selectedTestCaseId]);

  const saveTestCaseSteps = async (steps: TestCaseStep[], expectedResults: string[]) => {
    if (!projectId || !selectedTestCase) return;
    setSavingStep(true);
    try {
      const updated = await updateTestCase(projectId, selectedTestCase.id, {
        steps,
        expected_results: expectedResults,
      });
      setTestCases((prev) => prev.map((tc) => (tc.id === updated.id ? { ...tc, ...updated } : tc)));
      setMessage(`Updated steps for "${updated.title}"`);
    } catch (e) {
      setExecMessage(String(e));
    } finally {
      setSavingStep(false);
    }
  };

  const disableSelectedFlowStep = async () => {
    if (!selectedTestCase || selectedFlowStepIndex == null) return;
    const steps = [...(selectedTestCase.steps ?? [])];
    const expected = [...(selectedTestCase.expected_results ?? [])];
    const raw = steps[selectedFlowStepIndex];
    if (!raw || isStepDisabled(raw)) return;
    steps[selectedFlowStepIndex] = { description: stepDescription(raw), disabled: true };
    await saveTestCaseSteps(steps, expected);
  };

  const enableSelectedFlowStep = async () => {
    if (!selectedTestCase || selectedFlowStepIndex == null) return;
    const steps = [...(selectedTestCase.steps ?? [])];
    const expected = [...(selectedTestCase.expected_results ?? [])];
    const raw = steps[selectedFlowStepIndex];
    if (!raw || !isStepDisabled(raw)) return;
    steps[selectedFlowStepIndex] = stepDescription(raw);
    await saveTestCaseSteps(steps, expected);
  };

  const deleteSelectedFlowStep = async () => {
    if (!selectedTestCase || selectedFlowStepIndex == null) return;
    const steps = [...(selectedTestCase.steps ?? [])];
    const expected = [...(selectedTestCase.expected_results ?? [])];
    const desc = stepDescription(steps[selectedFlowStepIndex] ?? "");
    if (!window.confirm(`Delete step ${selectedFlowStepIndex + 1}: "${desc.slice(0, 80)}"?`)) return;
    steps.splice(selectedFlowStepIndex, 1);
    expected.splice(selectedFlowStepIndex, 1);
    setSelectedFlowStepIndex(null);
    await saveTestCaseSteps(steps, expected);
  };

  const selectedFlowStep = selectedTestCase && selectedFlowStepIndex != null
    ? flowStepsForSelected()[selectedFlowStepIndex]
    : null;

  const debugTestCase = async (testCaseId: string) => {
    if (!projectId) return;
    if (!activeAsset) {
      setExecMessage("Select or generate an automation asset first. Debug runs your saved Playwright scripts via npm/npx — not the step list alone.");
      return;
    }
    const tc = testCases.find((t) => t.id === testCaseId);
    if (!tc || !isAutomationEnabled(tc)) {
      setExecMessage("Test case is disabled or not found — enable it to debug.");
      return;
    }
    const targetUrl = baseUrl.trim() || activeEnvironment?.base_url?.trim() || "";
    if (!targetUrl) {
      setExecMessage(
        "Set a Base URL before debugging — configure it on your environment in Settings → Environments & Modules."
      );
      return;
    }
    setSelectedTestCaseId(testCaseId);
    setSideTab("flow");
    setExecuting(true);
    setExecMessage(`Starting debug — live browser in Studio + video recording (asset "${activeAsset.name}")…`);
    setDebugRun(null);
    setLiveFrameTick(0);
    debugPollStoppedRef.current = false;
    try {
      const health = await checkBackendHealth();
      if (!health.ok) {
        setExecMessage(health.message ?? "Backend unavailable — run restart.bat");
        setExecuting(false);
        return;
      }

      const run = await apiFetch<DebugRunState & { summary?: unknown; logs?: string }>(
        `/api/v1/projects/${projectId}/executions/batch-run`,
        {
          method: "POST",
          body: JSON.stringify({
            test_case_ids: [testCaseId],
            mode: "live",
            embed_live: true,
            headed: false,
            background: true,
            framework: activeAsset.framework,
            base_url: targetUrl,
            asset_id: activeAsset.id,
            run_name: `Debug — ${tc.title}`,
          }),
        }
      );
      setDebugRun(run);
      setExecRunId(run.id);

      const poll = async () => {
        if (debugPollStoppedRef.current) return;
        try {
          const updated = await apiFetch<DebugRunState & { logs?: string; summary?: { executor?: string } }>(
            `/api/v1/projects/${projectId}/executions/${run.id}`
          );
          if (debugPollStoppedRef.current) return;
          setDebugRun(updated);
          if (updated.status === "running") {
            const phase = updated.progress?.detail ?? updated.progress?.phase ?? "Running Playwright…";
            const executor = updated.progress?.executor ?? updated.summary?.executor;
            if (executor && executor !== "asset_live_v2") {
              setExecMessage("Stale backend detected — restart port 8000. Running stub executor, not real Playwright.");
            } else {
              const live = updated.summary?.embed_live ? " (live view in panel)" : updated.summary?.headed ? " (visible browser)" : "";
              setExecMessage(`Live: ${phase}${live}`);
            }
            setTimeout(poll, 300);
            return;
          }
          const logs = updated.logs ?? "";
          const usedAsset = logs.includes("automation asset") || logs.includes("asset_live_v2");
          const result = updated.results?.find((r) => r.test_case_id === testCaseId) ?? updated.results?.[0];
          const label = result?.status ?? updated.status;
          const errText = (result?.error ?? "").trim();
          const err = errText ? `\n${errText.slice(0, 600)}` : "";
          const videos = updated.results?.filter((r) => r.has_video).length ?? 0;
          const videoNote = videos > 0 ? " Replay video is ready below." : "";
          if (!usedAsset) {
            setExecMessage(
              `Debug finished (${label}) but did NOT run saved scripts — restart backend on port 8000.${err}`
            );
          } else if (updated.status === "cancelled") {
            setExecMessage("Debug stopped.");
          } else if (label === "failed" && errText) {
            setExecMessage(`Debug complete — failed${videoNote}\n${formatDebugError(errText)}`);
          } else {
            setExecMessage(`Debug complete — ${label}${videoNote}${err ? `\n${formatDebugError(errText)}` : ""}`);
          }
        } catch (e) {
          setExecMessage(formatDebugError(String(e)));
        } finally {
          setExecuting(false);
        }
      };
      poll();
    } catch (e) {
      setExecMessage(String(e));
      setExecuting(false);
    }
  };

  const generateFromSource = async () => {
    if (!projectId || !sourceJson.trim()) { setMessage("Select project and paste source JSON"); return; }
    setGenerating(true);
    setMessage("");
    try {
      let content: unknown;
      try { content = JSON.parse(sourceJson); } catch { content = sourceJson; }
      const asset = await apiFetch<AutomationAsset>(
        `/api/v1/projects/${projectId}/automation/generate-from-source`,
        {
          method: "POST",
          body: JSON.stringify({ source_type: sourceType, content, framework }),
        }
      );
      setAssets((prev) => [asset, ...prev]);
      selectAsset(asset);
      setMessage(`Generated from ${sourceType}: ${asset.files.length} files`);
      setShowSources(false);
    } catch (e) { setMessage(String(e)); }
    finally { setGenerating(false); }
  };

  const generate = async () => {
    if (!projectId) { setMessage("Select a project first"); return; }
    setGenerating(true);
    setMessage("");
    try {
      const body: Record<string, unknown> = { framework };
      if (moduleQueryIds?.length) body.module_ids = moduleQueryIds;
      const asset = await apiFetch<AutomationAsset>(`/api/v1/projects/${projectId}/automation/generate`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setAssets((prev) => [asset, ...prev]);
      selectAsset(asset);
      setMessage(`Generated ${asset.files.length} files (${asset.framework})`);
    } catch (e) {
      setMessage(String(e));
    } finally {
      setGenerating(false);
    }
  };

  const save = async () => {
    if (!activeAsset || !activeFile) return;
    setSaving(true);
    try {
      const updated = await apiFetch<AutomationAsset>(
        `/api/v1/projects/${projectId}/automation/assets/${activeAsset.id}/files`,
        { method: "PUT", body: JSON.stringify({ path: activeFile, content: fileContent, save_version: true }) }
      );
      setActiveAsset(updated);
      setAssets((prev) => [updated, ...prev.filter((a) => a.id !== updated.id)]);
      setMessage(`Saved as v${updated.version}`);
    } finally {
      setSaving(false);
    }
  };

  const validate = async () => {
    if (!activeAsset) return;
    setValidating(true);
    try {
      const result = await apiFetch<{ valid: boolean; issues: { path: string; severity: string; message: string }[] }>(
        `/api/v1/projects/${projectId}/automation/assets/${activeAsset.id}/validate`,
        { method: "POST" }
      );
      setValidation(result);
    } finally {
      setValidating(false);
    }
  };

  const loadVersions = async () => {
    if (!activeAsset) return;
    const v = await apiFetch<AutomationAsset[]>(
      `/api/v1/projects/${projectId}/automation/assets/${activeAsset.id}/versions`
    );
    setVersions(v);
    setSideTab("versions");
    setDiffs(null);
  };

  const compareVersion = async (other: AutomationAsset) => {
    if (!activeAsset) return;
    const result = await apiFetch<{ diffs: { path: string; changed: boolean; diff: string }[] }>(
      `/api/v1/projects/${projectId}/automation/assets/${activeAsset.id}/diff/${other.id}`
    );
    setDiffs(result.diffs.filter((d) => d.changed));
    setSideTab("diff");
  };

  const runExecution = async () => {
    if (!activeAsset || !projectId) return;
    setExecuting(true);
    setExecMessage("");
    setExecRunId(null);
    const isLive = ["playwright", "cypress", "puppeteer", "testcafe", "webdriverio", "selenium", "robot_framework", "appium"]
      .includes(activeAsset.framework);
    try {
      const run = await apiFetch<{
        id: string;
        status: string;
        summary: { passed: number; warnings: number; failed: number; videos_captured?: number; framework?: string };
      }>(
        `/api/v1/projects/${projectId}/executions/run`,
        {
          method: "POST",
          body: JSON.stringify({
            asset_id: activeAsset.id,
            mode: isLive ? "live" : "dry_run",
            apply_healing: true,
            background: isLive,
          }),
        }
      );
      setExecRunId(run.id);
      if (run.status === "running") {
        setExecMessage(`Running in background — ${activeAsset.framework} is executing tests${run.summary?.framework === "playwright" || activeAsset.framework === "playwright" ? " and recording video" : ""}…`);
        const poll = async () => {
          const updated = await apiFetch<typeof run>(
            `/api/v1/projects/${projectId}/executions/${run.id}`
          );
          if (updated.status === "running") {
            setTimeout(poll, 2000);
            return;
          }
          const videos = updated.summary?.videos_captured ?? 0;
          setExecMessage(
            `Execution complete: ${updated.summary.passed} passed, ${updated.summary.warnings ?? 0} warnings, ${videos} video(s) captured. View recordings on the Executions page.`
          );
          setExecuting(false);
        };
        setTimeout(poll, 2000);
        return;
      }
      setExecMessage(`Execution complete: ${run.summary.passed} passed, ${run.summary.warnings ?? 0} warnings`);
    } catch (e) {
      setExecMessage(String(e));
    } finally {
      if (!isLive) setExecuting(false);
    }
  };

  const pushToGit = async () => {
    if (!activeAsset || !projectId || !pushForm.integration_id) return;
    setPushing(true);
    setMessage("");
    try {
      const result = await apiFetch<{ commit_sha?: string }>(
        `/api/v1/projects/${projectId}/automation/assets/${activeAsset.id}/push`,
        { method: "POST", body: JSON.stringify(pushForm) }
      );
      setMessage(`Pushed to GitHub${result.commit_sha ? ` (${result.commit_sha.slice(0, 7)})` : ""}`);
      setShowPush(false);
    } catch (e) {
      setMessage(String(e));
    } finally {
      setPushing(false);
    }
  };

  return (
    <AppShell title="QA Studio">
      <PageHeader
        title="QA Studio"
        subtitle="Generate, edit, and validate automation scripts"
        breadcrumbs={[{ label: "Quality Engineering" }, { label: "QA Studio" }]}
        actions={
          <div className="flex items-center gap-2">
            <Badge variant="success">Phase 2+5</Badge>
            {activeAsset && <Badge variant="neutral">v{activeAsset.version}</Badge>}
          </div>
        }
      />

      {/* Toolbar */}
      <div className="ds-card mb-4 px-4 py-3 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-col gap-1 min-w-[220px]">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
              Scope
            </span>
            <WorkspaceFilters
              environments={environments}
              modules={modules}
              activeEnvironmentId={activeEnvironmentId}
              activeModuleId={activeModuleId}
              onEnvironmentChange={setActiveEnvironmentId}
              onModuleChange={setActiveModuleId}
            />
          </div>
          <div className="h-8 w-px bg-[var(--border-default)] hidden sm:block" />
          <select className="ds-input py-1.5 text-sm w-40" value={framework} onChange={(e) => setFramework(e.target.value)}>
          {frameworks.map((f) => (
            <option key={f.id} value={f.id}>{f.name}</option>
          ))}
        </select>

        <button onClick={generate} disabled={generating || !projectId} className="ds-btn-primary">
          {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
          From Test Cases
        </button>

        <button onClick={() => setShowSources(!showSources)} disabled={!projectId} className="ds-btn-secondary">
          <Upload className="w-4 h-4" /> From Source
        </button>

        {activeAsset && (
          <>
            <button onClick={save} disabled={saving} className="ds-btn-secondary">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Save
            </button>
            <button onClick={validate} disabled={validating} className="ds-btn-secondary">
              {validating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              Validate
            </button>
            <button onClick={loadVersions} className="ds-btn-secondary">
              <GitCompare className="w-4 h-4" /> Versions
            </button>
            <button onClick={runExecution} disabled={executing} className="ds-btn-secondary">
              {executing ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlayCircle className="w-4 h-4" />}
              Execute
            </button>
            {activeAsset && (
              <a href={automationExportUrl(projectId, activeAsset.id)} className="ds-btn-secondary">
                <Download className="w-4 h-4" /> Export ZIP
              </a>
            )}
            {integrations.length > 0 && (
              <button onClick={() => setShowPush(true)} className="ds-btn-secondary">
                <Upload className="w-4 h-4" /> Push to GitHub
              </button>
            )}
            {activeAsset.ci_pipeline_snippet && (
              <button onClick={() => setShowCi(!showCi)} className="ds-btn-ghost text-xs">
                CI Pipeline <ChevronDown className="w-3 h-3" />
              </button>
            )}
          </>
        )}

        {assets.length > 1 && (
          <select
            className="ds-input py-1.5 text-sm w-48 ml-auto"
            value={activeAsset?.id ?? ""}
            onChange={(e) => { const a = assets.find((x) => x.id === e.target.value); if (a) selectAsset(a); }}
          >
            {assets.map((a) => (
              <option key={a.id} value={a.id}>{a.name} v{a.version}</option>
            ))}
          </select>
        )}
        </div>
        <p className="text-[11px] text-[var(--text-tertiary)]">
          {activeEnvironment?.name ?? "Environment"} · {moduleFilterLabel(activeModuleId, modules)} ·{" "}
          {testCases.length} test case{testCases.length === 1 ? "" : "s"} in scope
          {activeModule && ` (${activeModule.name})`}
          {" · "}
          <Link href="/settings" className="text-brand-700 hover:underline">Manage modules</Link>
        </p>
      </div>

      {showSources && (
        <div className="ds-card mb-4 p-4 space-y-3">
          <h3 className="text-sm font-semibold">Generate from Input Source</h3>
          <p className="text-xs text-[var(--text-tertiary)]">OpenAPI, HAR, Postman, Figma JSON, or Discovery — no test cases required</p>
          <select className="ds-input text-sm w-full" value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
            {inputSources.map((s) => (
              <option key={s.id} value={s.id}>{s.name} — {s.description}</option>
            ))}
          </select>
          <textarea className="ds-input text-xs font-mono resize-none" rows={8}
            placeholder="Paste OpenAPI / HAR / Postman / Figma JSON..."
            value={sourceJson} onChange={(e) => setSourceJson(e.target.value)} />
          <div className="flex gap-2">
            <button onClick={generateFromSource} disabled={generating} className="ds-btn-primary">
              {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : "Generate Automation"}
            </button>
            <button onClick={() => setShowSources(false)} className="ds-btn-secondary">Cancel</button>
          </div>
        </div>
      )}

      {showCi && activeAsset?.ci_pipeline_snippet && (
        <div className="ds-card mb-4 p-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)] mb-2">CI Pipeline Snippet</p>
          <pre className="text-xs font-mono bg-gray-900 text-gray-100 p-4 rounded-md overflow-auto">{activeAsset.ci_pipeline_snippet}</pre>
        </div>
      )}

      {showPush && (
        <div className="ds-card mb-4 p-4 space-y-3">
          <h3 className="text-sm font-semibold">Push to GitHub</h3>
          <select className="ds-input text-sm w-full" value={pushForm.integration_id}
            onChange={(e) => setPushForm((f) => ({ ...f, integration_id: e.target.value }))}>
            <option value="">Select GitHub integration...</option>
            {integrations.map((i) => <option key={i.id} value={i.id}>{i.provider}</option>)}
          </select>
          <div className="grid grid-cols-3 gap-2">
            <input className="ds-input text-sm" placeholder="Owner" value={pushForm.owner}
              onChange={(e) => setPushForm((f) => ({ ...f, owner: e.target.value }))} />
            <input className="ds-input text-sm" placeholder="Repo" value={pushForm.repo}
              onChange={(e) => setPushForm((f) => ({ ...f, repo: e.target.value }))} />
            <input className="ds-input text-sm" placeholder="Branch" value={pushForm.branch}
              onChange={(e) => setPushForm((f) => ({ ...f, branch: e.target.value }))} />
          </div>
          <input className="ds-input text-sm w-full" placeholder="Commit message (optional)" value={pushForm.commit_message}
            onChange={(e) => setPushForm((f) => ({ ...f, commit_message: e.target.value }))} />
          <div className="flex gap-2">
            <button onClick={pushToGit} disabled={pushing} className="ds-btn-primary">
              {pushing ? <Loader2 className="w-4 h-4 animate-spin" /> : "Push"}
            </button>
            <button onClick={() => setShowPush(false)} className="ds-btn-secondary">Cancel</button>
          </div>
        </div>
      )}

      {validation && (
        <div className={`ds-card mb-4 p-4 border-l-4 ${validation.valid ? "border-l-emerald-500" : "border-l-amber-500"}`}>
          <div className="flex items-center gap-2 mb-2">
            {validation.valid
              ? <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              : <AlertCircle className="w-4 h-4 text-amber-600" />}
            <span className="text-sm font-medium">{validation.valid ? "Validation passed" : "Review suggested"}</span>
          </div>
          {validation.issues.map((issue, i) => (
            <p key={i} className="text-xs text-[var(--text-secondary)] ml-6">
              [{issue.severity}] {issue.path}: {issue.message}
            </p>
          ))}
        </div>
      )}

      {/* IDE Layout */}
      {activeAsset ? (
        <div className="ds-card overflow-hidden" style={{ minHeight: 500 }}>
          <div className="grid grid-cols-12 divide-x divide-[var(--border-default)]" style={{ minHeight: 500 }}>
            {/* Sidebar */}
            <div className="col-span-3 bg-[var(--surface-sunken)]/30">
              <div className="px-3 pt-3">
                <Tabs
                  tabs={[
                    { id: "files", label: "Files", count: activeAsset.files.length },
                    { id: "flow", label: "Test Flow", count: filteredTestCases.length || scriptFlowSteps.length || undefined },
                    { id: "versions", label: "Versions", count: versions.length || undefined },
                    { id: "diff", label: "Diff", count: diffs?.length || undefined },
                    { id: "deps", label: "Deps" },
                  ]}
                  active={sideTab}
                  onChange={(tab) => {
                    setSideTab(tab);
                    if (tab === "flow" && !selectedTestCaseId && filteredTestCases[0]) {
                      setSelectedTestCaseId(filteredTestCases[0].id);
                    }
                  }}
                />
              </div>
              {sideTab === "files" && (
                <>
                  <div className="px-2 pb-2 flex flex-wrap items-center gap-1 border-b border-[var(--border-default)]">
                    <button
                      type="button"
                      onClick={selectAllFiles}
                      className="text-[10px] text-brand-700 px-1"
                      disabled={!activeAsset.files.length}
                    >
                      Select all
                    </button>
                    {selectedFilePaths.size > 0 && (
                      <button
                        type="button"
                        onClick={deleteSelectedFiles}
                        disabled={deletingFiles}
                        className="text-[10px] ds-btn-secondary py-0.5 px-1.5 text-red-700 inline-flex items-center gap-1"
                      >
                        {deletingFiles ? (
                          <Loader2 className="w-2.5 h-2.5 animate-spin" />
                        ) : (
                          <Trash2 className="w-2.5 h-2.5" />
                        )}
                        Delete ({selectedFilePaths.size})
                      </button>
                    )}
                  </div>
                  <FileTree
                    files={activeAsset.files}
                    activeFile={activeFile}
                    selectedPaths={selectedFilePaths}
                    onSelect={selectFile}
                    onToggleSelect={toggleFileSelect}
                  />
                </>
              )}
              {sideTab === "flow" && (
                <div className="py-2 px-1 max-h-[420px] overflow-auto space-y-1">
                  <p className="px-2 pb-2 text-[10px] text-[var(--text-tertiary)] border-b border-[var(--border-default)]">
                    {filteredTestCases.length} case{filteredTestCases.length === 1 ? "" : "s"} ·{" "}
                    {moduleFilterLabel(activeModuleId, modules)}
                    {activeModuleId ? "" : " — all modules in environment"}
                  </p>
                  {filteredTestCases.length > 0 && (
                    <div className="px-1 pb-2 mb-1 border-b border-[var(--border-default)] flex flex-wrap gap-1">
                      <button type="button" onClick={() => setSelectedCaseIds(new Set(filteredTestCases.map((t) => t.id)))} className="text-[10px] text-brand-700 px-1">Select all</button>
                      {selectedCaseIds.size > 0 && (
                        <>
                          <button type="button" disabled={managingCases} onClick={() => bulkManageCases("disable")} className="text-[10px] ds-btn-secondary py-0.5 px-1.5"><Ban className="w-2.5 h-2.5 inline" /> Disable</button>
                          <button type="button" disabled={managingCases} onClick={() => bulkManageCases("enable")} className="text-[10px] ds-btn-secondary py-0.5 px-1.5"><RotateCcw className="w-2.5 h-2.5 inline" /> Enable</button>
                          <button type="button" disabled={managingCases} onClick={() => bulkManageCases("delete")} className="text-[10px] ds-btn-secondary py-0.5 px-1.5 text-red-700"><Trash2 className="w-2.5 h-2.5 inline" /> Delete</button>
                        </>
                      )}
                    </div>
                  )}
                  {filteredTestCases.length === 0 && (
                    <p className="px-2 text-xs text-[var(--text-tertiary)]">
                      No test cases in scope — import from Discovery or widen the module filter above.
                    </p>
                  )}
                  {filteredTestCases.map((tc) => {
                    const disabled = !isAutomationEnabled(tc);
                    return (
                    <div key={tc.id} className={`flex items-start gap-1 ${disabled ? "opacity-60" : ""}`}>
                      <button type="button" onClick={() => toggleCaseSelect(tc.id)} className="p-1 shrink-0 mt-0.5">
                        {selectedCaseIds.has(tc.id) ? <CheckSquare className="w-3.5 h-3.5 text-brand-700" /> : <Square className="w-3.5 h-3.5 text-gray-400" />}
                      </button>
                      <button
                        onClick={() => setSelectedTestCaseId(tc.id)}
                        className={`flex-1 text-left px-1 py-2 rounded text-xs ${selectedTestCaseId === tc.id ? "bg-brand-50 ring-1 ring-brand-200" : "hover:bg-[var(--surface-sunken)]"}`}
                      >
                        <span className={`font-medium block truncate ${disabled ? "line-through" : ""}`}>{tc.case_code || tc.title}</span>
                        <span className="text-[var(--text-tertiary)]">{tc.module_name ? `${tc.module_name} · ` : ""}{tc.steps?.length ?? 0} steps · {tc.status}</span>
                      </button>
                      {!disabled && (
                        <button type="button" onClick={() => debugTestCase(tc.id)} disabled={executing} className="ds-btn-ghost p-1 shrink-0" title="Debug">
                          <Bug className="w-3 h-3 text-brand-700" />
                        </button>
                      )}
                    </div>
                  );})}
                </div>
              )}
              {sideTab === "versions" && (
                <div className="py-2">
                  {versions.length === 0 ? (
                    <p className="px-3 text-xs text-[var(--text-tertiary)]">No versions yet. Save to create versions.</p>
                  ) : versions.map((v) => (
                    <div key={v.id} className="flex items-center gap-1 px-1">
                      <button onClick={() => selectAsset(v)}
                        className="flex-1 text-left px-2 py-2 text-xs hover:bg-[var(--surface-sunken)] rounded">
                        <span className="font-medium">v{v.version}</span>
                        <span className="text-[var(--text-tertiary)] ml-2">{v.status}</span>
                      </button>
                      {activeAsset && v.id !== activeAsset.id && (
                        <button onClick={() => compareVersion(v)} className="ds-btn-ghost p-1" title="Diff">
                          <GitCompare className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {sideTab === "diff" && (
                <div className="p-2 space-y-2 max-h-96 overflow-auto">
                  {!diffs?.length ? (
                    <p className="px-2 text-xs text-[var(--text-tertiary)]">Select a version to compare</p>
                  ) : diffs.map((d) => (
                    <div key={d.path} className="text-xs">
                      <p className="font-mono font-medium px-2 py-1 bg-[var(--surface-sunken)]">{d.path}</p>
                      <pre className="p-2 text-[10px] overflow-auto max-h-40 bg-gray-900 text-gray-100 rounded mt-1">{d.diff || "Changed"}</pre>
                    </div>
                  ))}
                </div>
              )}
              {sideTab === "deps" && (
                <div className="p-3 space-y-1">
                  {activeAsset.dependencies.map((d) => (
                    <code key={d} className="block text-xs font-mono text-[var(--text-secondary)]">{d}</code>
                  ))}
                </div>
              )}
            </div>

            {/* Editor / Flow */}
            <div className="col-span-9 flex flex-col">
              {sideTab === "flow" ? (
                <div className="flex-1 flex flex-col min-h-0">
                  <div className="px-4 py-2 border-b border-[var(--border-default)] flex items-center justify-between bg-[var(--surface-sunken)]/20">
                    <span className="text-xs font-medium flex items-center gap-2">
                      <GitBranch className="w-3.5 h-3.5" />
                      {selectedTestCase?.title ?? activeFile ?? "Test flow"}
                    </span>
                    {selectedTestCase && (
                      <div className="flex items-center gap-2">
                        <input
                          className="ds-input text-xs font-mono w-52 py-1"
                          value={baseUrl}
                          onChange={(e) => setBaseUrl(e.target.value)}
                          placeholder="Base URL (from environment)"
                          title="Target application URL for Playwright navigation"
                          suppressHydrationWarning
                        />
                        {debugRun?.status === "running" && (
                          <button
                            type="button"
                            onClick={stopDebugRun}
                            className="ds-btn-secondary text-xs py-1 border-red-200 text-red-700 hover:bg-red-50"
                          >
                            <Square className="w-3 h-3 fill-current" />
                            Stop
                          </button>
                        )}
                        <button
                          onClick={() => debugTestCase(selectedTestCase.id)}
                          disabled={executing}
                          className="ds-btn-secondary text-xs py-1"
                        >
                          {executing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Bug className="w-3 h-3" />}
                          Debug flow
                        </button>
                      </div>
                    )}
                  </div>
                  <div className="flex-1 overflow-auto p-4">
                    {debugRun?.status === "running" && (
                      <div className="mb-4 rounded-xl border-2 border-brand-300 bg-black/95 shadow-lg overflow-hidden">
                        <div className="px-3 py-2 bg-brand-900/90 flex items-center justify-between">
                          <p className="text-xs font-semibold text-white flex items-center gap-2">
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            Live browser
                          </p>
                          <span className="text-[10px] text-brand-200">
                            {debugRun.progress?.detail ?? "Syncing with Playwright…"}
                          </span>
                        </div>
                        {projectId && debugRun.id && (
                          liveFrameSrc ? (
                            <img
                              alt="Live browser view"
                              className="w-full min-h-[280px] max-h-[420px] object-contain bg-slate-950"
                              src={liveFrameSrc}
                            />
                          ) : (
                            <div className="w-full min-h-[280px] max-h-[420px] flex items-center justify-center bg-slate-950 text-xs text-slate-400">
                              Waiting for browser frame…
                            </div>
                          )
                        )}
                        <p className="px-3 py-1.5 text-[10px] text-brand-200/80 border-t border-brand-800">
                          Step highlight updates as each action runs in the browser.
                        </p>
                      </div>
                    )}
                    {debugResult?.has_video && projectId && debugRun?.id && (
                      <div className="mb-4 rounded-lg border border-[var(--border-default)] bg-[var(--surface-sunken)]/30 p-3">
                        <p className="text-xs font-semibold mb-2 flex items-center gap-1.5 text-[var(--text-secondary)]">
                          <Video className="w-3.5 h-3.5" />
                          Debug replay
                        </p>
                        <video
                          key={`${debugRun.id}-${debugResult.video_id ?? "0"}`}
                          controls
                          className="w-full max-h-80 rounded-lg border border-[var(--border-default)] bg-black"
                          src={executionVideoUrl(projectId, debugRun.id, debugResult.video_id ?? "0")}
                          preload="metadata"
                        />
                        <p className="mt-2 text-[10px] text-[var(--text-tertiary)]">
                          Also available on{" "}
                          <Link href="/executions" className="text-brand-700 hover:underline">Executions</Link>
                        </p>
                      </div>
                    )}
                    {selectedTestCase && debugRun?.status !== "running" && (
                      <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-[var(--border-default)] bg-[var(--surface-sunken)]/40 px-3 py-2">
                        <span className="text-xs text-[var(--text-secondary)] mr-auto">
                          {selectedFlowStepIndex != null
                            ? `Step ${selectedFlowStepIndex + 1} selected`
                            : "Select a step to disable or delete"}
                        </span>
                        {selectedFlowStepIndex != null && (
                          <>
                            {!selectedFlowStep?.disabled && (
                              <button
                                type="button"
                                disabled={savingStep}
                                onClick={disableSelectedFlowStep}
                                className="ds-btn-secondary text-xs py-1"
                              >
                                <Ban className="w-3 h-3 inline" /> Disable step
                              </button>
                            )}
                            {selectedFlowStep?.disabled && (
                              <button
                                type="button"
                                disabled={savingStep}
                                onClick={enableSelectedFlowStep}
                                className="ds-btn-secondary text-xs py-1"
                              >
                                <RotateCcw className="w-3 h-3 inline" /> Enable step
                              </button>
                            )}
                            <button
                              type="button"
                              disabled={savingStep}
                              onClick={deleteSelectedFlowStep}
                              className="ds-btn-secondary text-xs py-1 text-red-700 border-red-200"
                            >
                              <Trash2 className="w-3 h-3 inline" /> Delete step
                            </button>
                          </>
                        )}
                        {savingStep && <Loader2 className="w-3.5 h-3.5 animate-spin text-brand-700" />}
                      </div>
                    )}
                    <TestCaseFlowView
                      title={selectedTestCase?.title ?? (activeFile ? `Script: ${activeFile}` : undefined)}
                      steps={debugRun?.status === "running" ? debugFlowState.steps : flowStepsForSelected()}
                      activeStepIndex={debugRun?.status === "running" ? debugFlowState.activeStepIndex : null}
                      selectedStepIndex={debugRun?.status === "running" ? null : selectedFlowStepIndex}
                      editable={Boolean(selectedTestCase && debugRun?.status !== "running")}
                      onSelectStep={(index) => setSelectedFlowStepIndex(index)}
                    />
                  </div>
                </div>
              ) : (
                <>
              {activeFile && (
                <div className="px-4 py-2 border-b border-[var(--border-default)] flex items-center gap-2 bg-[var(--surface-sunken)]/20">
                  <span className="text-xs font-mono text-[var(--text-secondary)]">{activeFile}</span>
                  <Badge variant="neutral">{activeAsset.framework}</Badge>
                </div>
              )}
              <div className="flex-1 p-2 flex flex-col min-h-0">
                {activeFile ? (
                  <>
                    <div className="flex-1 min-h-[240px]">
                      <CodeEditor
                        value={fileContent}
                        onChange={setFileContent}
                        language={activeAsset.language}
                      />
                    </div>
                    {scriptFlowSteps.length > 0 && (
                      <div className="mt-3 border-t border-[var(--border-default)] pt-3 max-h-[220px] overflow-auto">
                        <p className="text-[10px uppercase tracking-wider text-[var(--text-tertiary)] mb-2 font-semibold">Steps in this script</p>
                        <TestCaseFlowView steps={scriptFlowSteps} showHeader={false} compact />
                      </div>
                    )}
                  </>
                ) : (
                  <div className="flex items-center justify-center h-full text-sm text-[var(--text-tertiary)]">
                    Select a file from the tree or open Test Flow tab
                  </div>
                )}
              </div>
                </>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="ds-card p-16 text-center">
          <Sparkles className="w-10 h-10 text-[var(--text-tertiary)] mx-auto mb-4" />
          <h3 className="text-sm font-semibold mb-1">No automation assets yet</h3>
          <p className="text-xs text-[var(--text-tertiary)] mb-4">
            Select a project with test cases, choose a framework, and click Generate
          </p>
        </div>
      )}

      {message && <p className="mt-3 text-sm p-3 rounded-md bg-[var(--surface-sunken)]">{message}</p>}
      {execMessage && (
        <p className="mt-2 text-sm p-3 rounded-md bg-brand-50 text-brand-800">
          {execMessage}
          {execRunId && projectId && (
            <>{" "}<Link href="/executions" className="underline font-medium">Open Executions →</Link></>
          )}
        </p>
      )}
    </AppShell>
  );
}

export default function StudioPage() {
  return (
    <Suspense fallback={
      <AppShell title="QA Studio">
        <div className="flex items-center justify-center p-16">
          <Loader2 className="w-6 h-6 animate-spin text-[var(--text-tertiary)]" />
        </div>
      </AppShell>
    }>
      <StudioPageContent />
    </Suspense>
  );
}
