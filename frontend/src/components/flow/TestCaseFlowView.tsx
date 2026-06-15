"use client";

import { CheckCircle2, XCircle, Loader2, Circle, ChevronDown, Bug } from "lucide-react";
import clsx from "clsx";

export type FlowStepStatus = "pending" | "running" | "passed" | "failed" | "skipped" | "passed_with_warnings";

export interface FlowStep {
  order: number;
  description: string;
  expected?: string | null;
  status?: FlowStepStatus;
  action?: string;
  url?: string;
}

function statusIcon(status: FlowStepStatus | undefined, isActive: boolean) {
  if (status === "running" || isActive) {
    return (
      <span className="relative flex h-8 w-8 shrink-0 items-center justify-center">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-400 opacity-30" />
        <span className="relative flex h-8 w-8 items-center justify-center rounded-full bg-brand-700 text-white ring-4 ring-brand-100">
          <Loader2 className="h-4 w-4 animate-spin" />
        </span>
      </span>
    );
  }
  if (status === "passed" || status === "passed_with_warnings") {
    return (
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-700 ring-2 ring-emerald-200">
        <CheckCircle2 className="h-4 w-4" />
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-red-100 text-red-600 ring-2 ring-red-200">
        <XCircle className="h-4 w-4" />
      </span>
    );
  }
  return (
    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gray-100 text-gray-400 ring-2 ring-gray-200">
      <Circle className="h-3.5 w-3.5" />
    </span>
  );
}

function connectorClass(prevStatus: FlowStepStatus | undefined, nextActive: boolean) {
  if (prevStatus === "passed" || prevStatus === "passed_with_warnings") return "bg-emerald-400";
  if (prevStatus === "failed") return "bg-red-300";
  if (nextActive) return "bg-gradient-to-b from-brand-400 to-gray-200";
  return "bg-gray-200";
}

export function TestCaseFlowView({
  title,
  steps,
  activeStepIndex = null,
  showHeader = true,
  compact = false,
  onDebugStep,
}: {
  title?: string;
  steps: FlowStep[];
  activeStepIndex?: number | null;
  showHeader?: boolean;
  compact?: boolean;
  onDebugStep?: (step: FlowStep) => void;
}) {
  if (!steps.length) {
    return (
      <p className="text-xs text-[var(--text-tertiary)] py-6 text-center">No steps defined for this test case</p>
    );
  }

  return (
    <div className={clsx("w-full", compact ? "py-1" : "py-2")}>
      {showHeader && title && (
        <div className="mb-4 flex items-start gap-2">
          <div className="rounded-lg bg-brand-50 px-3 py-2 flex-1 border border-brand-100">
            <p className="text-[10px] uppercase tracking-wider text-brand-600 font-semibold">Test flow</p>
            <p className="text-sm font-medium text-[var(--text-primary)] mt-0.5">{title}</p>
          </div>
        </div>
      )}

      <div className="relative pl-1">
        {steps.map((step, index) => {
          const isActive = activeStepIndex === index || step.status === "running";
          const isLast = index === steps.length - 1;
          const prevStatus = index > 0 ? steps[index - 1].status : undefined;
          const nextActive = activeStepIndex === index + 1;

          return (
            <div key={step.order ?? index} className="relative flex gap-3 pb-1">
              {!isLast && (
                <div
                  className={clsx(
                    "absolute left-4 top-8 w-0.5 -translate-x-1/2 transition-colors duration-500",
                    compact ? "bottom-0" : "bottom-1"
                  )}
                  style={{ height: compact ? "calc(100% - 0.25rem)" : "calc(100% - 0.5rem)" }}
                >
                  <div className={clsx("w-full h-full rounded-full transition-all duration-700", connectorClass(prevStatus ?? step.status, nextActive))} />
                </div>
              )}

              <div className="z-10 shrink-0">{statusIcon(step.status, isActive)}</div>

              <div
                className={clsx(
                  "flex-1 min-w-0 rounded-lg border transition-all duration-300 mb-3",
                  isActive
                    ? "border-brand-400 bg-brand-50/80 shadow-sm shadow-brand-100 ring-1 ring-brand-200"
                    : step.status === "passed" || step.status === "passed_with_warnings"
                      ? "border-emerald-200 bg-emerald-50/40"
                      : step.status === "failed"
                        ? "border-red-200 bg-red-50/40"
                        : "border-[var(--border-default)] bg-[var(--surface-raised)]"
                )}
              >
                <div className={clsx("px-3", compact ? "py-2" : "py-2.5")}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-[10px] font-mono font-semibold text-[var(--text-tertiary)]">
                          STEP {step.order ?? index + 1}
                        </span>
                        {step.action && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 capitalize">
                            {step.action}
                          </span>
                        )}
                        {isActive && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-brand-700 text-white animate-pulse">
                            Executing…
                          </span>
                        )}
                      </div>
                      <p className={clsx("mt-1 text-[var(--text-primary)]", compact ? "text-xs" : "text-sm")}>
                        {step.description}
                      </p>
                      {step.url && (
                        <p className="text-[10px] font-mono text-[var(--text-tertiary)] mt-1 truncate" title={step.url}>
                          {step.url}
                        </p>
                      )}
                    </div>
                    {onDebugStep && (
                      <button
                        type="button"
                        onClick={() => onDebugStep(step)}
                        className="shrink-0 ds-btn-ghost p-1 opacity-60 hover:opacity-100"
                        title="Debug from this step"
                      >
                        <Bug className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                  {step.expected && (
                    <div className="mt-2 pt-2 border-t border-[var(--border-default)]/50 flex items-start gap-1.5">
                      <ChevronDown className="w-3 h-3 text-emerald-600 shrink-0 mt-0.5 rotate-[-90deg]" />
                      <p className="text-[11px] text-[var(--text-secondary)]">
                        <span className="font-medium text-emerald-700">Expected: </span>
                        {step.expected}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Parse Playwright/Cypress-style steps from automation script content */
export function parseStepsFromScript(content: string): FlowStep[] {
  const steps: FlowStep[] = [];
  const patterns = [
    /test\.step\(\s*['"`]([^'"`]+)['"`]/g,
    /cy\.log\(\s*['"`]([^'"`]+)['"`]/g,
    /await t\.(?:navigateTo|click|type)[^;]*;\s*\/\/\s*(.+)$/gm,
    /\/\/ Step:\s*(.+)$/gm,
  ];
  let order = 1;
  const seen = new Set<string>();
  for (const re of patterns) {
    let m;
    while ((m = re.exec(content)) !== null) {
      const desc = m[1]?.trim();
      if (desc && !seen.has(desc)) {
        seen.add(desc);
        steps.push({ order: order++, description: desc, status: "pending" });
      }
    }
  }
  return steps;
}

/** Build flow steps from string[] test case steps */
export function buildFlowSteps(
  rawSteps: (string | { description?: string; action?: string; url?: string; order?: number })[],
  expected?: string[],
  stepStatuses?: { order: number; status: string; description?: string; expected?: string }[]
): FlowStep[] {
  const statusMap = new Map((stepStatuses ?? []).map((s) => [s.order, s]));
  return rawSteps.map((s, i) => {
    const order = i + 1;
    const st = statusMap.get(order);
    if (typeof s === "string") {
      return {
        order,
        description: st?.description ?? s,
        expected: st?.expected ?? expected?.[i] ?? null,
        status: (st?.status as FlowStepStatus) ?? "pending",
      };
    }
    return {
      order: s.order ?? order,
      description: st?.description ?? s.description ?? String(s),
      action: s.action,
      url: s.url,
      expected: st?.expected ?? expected?.[i] ?? null,
      status: (st?.status as FlowStepStatus) ?? "pending",
    };
  });
}

/** Hook-style helper: derive active step index while a run is in progress */
export function deriveActiveStepIndex(
  steps: FlowStep[],
  runStatus: string,
  progress?: {
    current?: string | null;
    current_test_case_id?: string;
    current_step_index?: number;
    total_steps?: number;
    phase?: string;
    detail?: string;
    executor?: string;
  },
  testCaseTitle?: string,
  tick?: number,
  testCaseId?: string
): number | null {
  if (runStatus !== "running" || steps.length === 0) {
    return null;
  }
  if (progress?.current_test_case_id && testCaseId && progress.current_test_case_id !== testCaseId) {
    return null;
  }
  if (progress?.current && testCaseTitle && progress.current !== testCaseTitle && !progress.current_test_case_id) {
    return null;
  }
  const completed = steps.filter((s) => s.status === "passed" || s.status === "failed").length;
  if (completed > 0 && completed < steps.length) {
    return completed;
  }
  if (progress?.phase === "playwright_test" && tick != null) {
    return Math.min(Math.floor(tick / 2), steps.length - 1);
  }
  if (progress?.phase === "npm_install" || progress?.phase === "playwright_install") {
    return 0;
  }
  const backendIdx = progress?.current_step_index;
  if (backendIdx != null && backendIdx >= 0) {
    return Math.min(backendIdx, steps.length - 1);
  }
  if (tick != null) {
    return tick % steps.length;
  }
  return 0;
}

/** Merge execution result step statuses onto flow steps and apply live debug highlight */
export function applyDebugFlowSteps(
  baseSteps: FlowStep[],
  opts: {
    runStatus?: string;
    progress?: {
      current?: string | null;
      current_test_case_id?: string;
      current_step_index?: number;
      total_steps?: number;
    };
    testCaseTitle?: string;
    testCaseId?: string;
    animTick?: number;
    resultSteps?: { order: number; status: string; description?: string; expected?: string }[];
  }
): { steps: FlowStep[]; activeStepIndex: number | null } {
  let steps = baseSteps;
  if (opts.resultSteps?.length) {
    steps = buildFlowSteps(
      opts.resultSteps.map((s) => s.description ?? ""),
      opts.resultSteps.map((s) => s.expected ?? ""),
      opts.resultSteps
    );
  }
  const activeStepIndex =
    opts.runStatus === "running"
      ? deriveActiveStepIndex(
          steps,
          "running",
          opts.progress,
          opts.testCaseTitle,
          opts.animTick,
          opts.testCaseId
        )
      : null;
  const displaySteps = steps.map((s, i) => ({
    ...s,
    status: (opts.runStatus === "running" && activeStepIndex === i ? "running" : s.status) as FlowStepStatus,
  }));
  return { steps: displaySteps, activeStepIndex };
}
