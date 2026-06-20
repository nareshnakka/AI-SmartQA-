"use client";

import Link from "next/link";
import { ChevronDown, ChevronRight } from "lucide-react";
import clsx from "clsx";
import type { ProjectEnvironment } from "@/lib/environments";
import type { ProjectModule } from "@/lib/modules";

interface WorkspaceHierarchyProps {
  environments: ProjectEnvironment[];
  modules: ProjectModule[];
  activeEnvironmentId: string | null;
  activeModuleId: string | null;
  onEnvironmentChange: (id: string) => void;
  onModuleChange: (id: string | null) => void;
  className?: string;
  compact?: boolean;
}

/** Cascading selector using user-defined environment and module names. */
export function WorkspaceHierarchy({
  environments,
  modules,
  activeEnvironmentId,
  activeModuleId,
  onEnvironmentChange,
  onModuleChange,
  className,
  compact = false,
}: WorkspaceHierarchyProps) {
  if (environments.length === 0) {
    return (
      <Link
        href="/settings"
        className={clsx(
          "text-xs text-brand-700 hover:underline whitespace-nowrap",
          className
        )}
      >
        Configure environments →
      </Link>
    );
  }

  return (
    <div className={clsx("flex items-center gap-1 min-w-0", className)}>
      <div className="relative shrink-0">
        <select
          className={clsx(
            "ds-input appearance-none pr-7",
            compact ? "text-xs py-1.5 min-w-[120px]" : "text-sm py-1.5 min-w-[140px]"
          )}
          value={activeEnvironmentId ?? ""}
          onChange={(e) => onEnvironmentChange(e.target.value)}
          title="Environment"
          suppressHydrationWarning
        >
          {environments.map((e) => (
            <option key={e.id} value={e.id}>
              {e.name}{e.is_default ? " (default)" : ""}
            </option>
          ))}
        </select>
        <ChevronDown className="w-3.5 h-3.5 absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-[var(--text-tertiary)]" />
      </div>

      <ChevronRight className="w-3.5 h-3.5 shrink-0 text-[var(--text-tertiary)]" />

      <div className="relative shrink-0 min-w-0">
        <select
          className={clsx(
            "ds-input appearance-none pr-7 max-w-[200px]",
            compact ? "text-xs py-1.5 min-w-[120px]" : "text-sm py-1.5 min-w-[140px]"
          )}
          value={activeModuleId ?? ""}
          onChange={(e) => onModuleChange(e.target.value || null)}
          disabled={!activeEnvironmentId}
          title="Module"
          suppressHydrationWarning
        >
          <option value="">All modules</option>
          {modules.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name} ({m.test_case_count})
            </option>
          ))}
        </select>
        <ChevronDown className="w-3.5 h-3.5 absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-[var(--text-tertiary)]" />
      </div>
    </div>
  );
}
