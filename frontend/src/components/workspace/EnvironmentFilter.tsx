"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, Search, CheckSquare, Square } from "lucide-react";
import clsx from "clsx";
import type { ProjectEnvironment } from "@/lib/environments";
import { environmentFilterLabel, isAllEnvironmentsSelected } from "@/lib/environments";

interface EnvironmentFilterProps {
  environments: ProjectEnvironment[];
  selectedEnvironmentIds: Set<string>;
  onChange: (ids: Set<string>) => void;
  className?: string;
  placeholder?: string;
}

export function EnvironmentFilter({
  environments,
  selectedEnvironmentIds,
  onChange,
  className,
  placeholder = "Filter by environment",
}: EnvironmentFilterProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const filtered = environments.filter((e) =>
    `${e.name} ${e.env_type}`.toLowerCase().includes(search.trim().toLowerCase())
  );

  const toggleAll = () => onChange(new Set());

  const toggleEnv = (id: string) => {
    const next = new Set(selectedEnvironmentIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(next);
  };

  return (
    <div ref={ref} className={clsx("relative", className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="ds-btn-secondary text-xs py-1.5 px-2 inline-flex items-center gap-1.5 min-w-[150px] justify-between"
      >
        <span className="truncate">
          {environmentFilterLabel(selectedEnvironmentIds, environments) || placeholder}
        </span>
        <ChevronDown className={clsx("w-3.5 h-3.5 shrink-0 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-72 rounded-md border border-[var(--border-default)] bg-[var(--surface-default)] shadow-lg">
          <div className="p-2 border-b border-[var(--border-default)]">
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search environments…"
                className="ds-input text-xs pl-7 py-1.5 w-full"
              />
            </div>
          </div>
          <div className="max-h-52 overflow-auto py-1">
            <button
              type="button"
              onClick={toggleAll}
              className="w-full text-left px-3 py-2 text-xs flex items-center gap-2 hover:bg-[var(--surface-sunken)]"
            >
              {isAllEnvironmentsSelected(selectedEnvironmentIds) ? (
                <CheckSquare className="w-3.5 h-3.5 text-brand-700 shrink-0" />
              ) : (
                <Square className="w-3.5 h-3.5 text-gray-400 shrink-0" />
              )}
              <span className="font-medium">All environments</span>
            </button>
            {filtered.length === 0 && (
              <p className="px-3 py-2 text-xs text-[var(--text-tertiary)]">No environments match</p>
            )}
            {filtered.map((e) => {
              const checked = selectedEnvironmentIds.has(e.id);
              return (
                <button
                  key={e.id}
                  type="button"
                  onClick={() => toggleEnv(e.id)}
                  className="w-full text-left px-3 py-2 text-xs flex items-center gap-2 hover:bg-[var(--surface-sunken)]"
                >
                  {checked ? (
                    <CheckSquare className="w-3.5 h-3.5 text-brand-700 shrink-0" />
                  ) : (
                    <Square className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                  )}
                  <span className="flex-1 truncate">
                    {e.name}
                    <span className="text-[var(--text-tertiary)] ml-1">({e.env_type})</span>
                    {e.is_default && (
                      <span className="text-[10px] text-brand-700 ml-1">default</span>
                    )}
                  </span>
                  {e.test_case_count > 0 && (
                    <span className="text-[10px] text-[var(--text-tertiary)]">{e.test_case_count}</span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/** Active environment selector (single) for create/commit flows. */
export function ActiveEnvironmentSelect({
  environments,
  value,
  onChange,
  className,
}: {
  environments: ProjectEnvironment[];
  value: string | null;
  onChange: (id: string) => void;
  className?: string;
}) {
  return (
    <select
      className={clsx("ds-input text-xs py-1.5", className)}
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value)}
    >
      {environments.map((e) => (
        <option key={e.id} value={e.id}>
          {e.name} ({e.env_type}){e.is_default ? " · default" : ""}
        </option>
      ))}
    </select>
  );
}

export function filterCasesByEnvironmentIds<T extends { environment_id?: string | null }>(
  items: T[],
  selectedEnvironmentIds: Set<string>
) {
  if (isAllEnvironmentsSelected(selectedEnvironmentIds)) return items;
  return items.filter(
    (item) => item.environment_id && selectedEnvironmentIds.has(item.environment_id)
  );
}
