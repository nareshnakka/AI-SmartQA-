"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, Search, CheckSquare, Square } from "lucide-react";
import clsx from "clsx";
import type { ProjectModule } from "@/lib/modules";
import { isAllModulesSelected, moduleFilterLabel } from "@/lib/modules";

interface ModuleFilterProps {
  modules: ProjectModule[];
  selectedModuleIds: Set<string>;
  onChange: (ids: Set<string>) => void;
  className?: string;
  placeholder?: string;
}

export function ModuleFilter({
  modules,
  selectedModuleIds,
  onChange,
  className,
  placeholder = "Filter by module",
}: ModuleFilterProps) {
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

  const filtered = modules.filter((m) =>
    m.name.toLowerCase().includes(search.trim().toLowerCase())
  );

  const toggleAll = () => onChange(new Set());

  const toggleModule = (id: string) => {
    const next = new Set(selectedModuleIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(next);
  };

  return (
    <div ref={ref} className={clsx("relative", className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="ds-btn-secondary text-xs py-1.5 px-2 inline-flex items-center gap-1.5 min-w-[140px] justify-between"
      >
        <span className="truncate">{moduleFilterLabel(selectedModuleIds, modules) || placeholder}</span>
        <ChevronDown className={clsx("w-3.5 h-3.5 shrink-0 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-64 rounded-md border border-[var(--border-default)] bg-[var(--surface-default)] shadow-lg">
          <div className="p-2 border-b border-[var(--border-default)]">
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search modules…"
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
              {isAllModulesSelected(selectedModuleIds) ? (
                <CheckSquare className="w-3.5 h-3.5 text-brand-700 shrink-0" />
              ) : (
                <Square className="w-3.5 h-3.5 text-gray-400 shrink-0" />
              )}
              <span className="font-medium">All modules</span>
            </button>
            {filtered.length === 0 && (
              <p className="px-3 py-2 text-xs text-[var(--text-tertiary)]">No modules match</p>
            )}
            {filtered.map((m) => {
              const checked = selectedModuleIds.has(m.id);
              return (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => toggleModule(m.id)}
                  className="w-full text-left px-3 py-2 text-xs flex items-center gap-2 hover:bg-[var(--surface-sunken)]"
                >
                  {checked ? (
                    <CheckSquare className="w-3.5 h-3.5 text-brand-700 shrink-0" />
                  ) : (
                    <Square className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                  )}
                  <span className="flex-1 truncate">
                    {m.name}
                    <span className="text-[var(--text-tertiary)] ml-1">({m.code})</span>
                  </span>
                  {m.test_case_count > 0 && (
                    <span className="text-[10px] text-[var(--text-tertiary)]">{m.test_case_count}</span>
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

/** Filter proposed discovery cases by module name (string match). */
export function filterByModuleNames<T extends { module?: string; screen?: string }>(
  items: T[],
  selectedModuleIds: Set<string>,
  modules: ProjectModule[]
): T[] {
  if (isAllModulesSelected(selectedModuleIds)) return items;
  const names = new Set(
    modules.filter((m) => selectedModuleIds.has(m.id)).map((m) => m.name.toLowerCase())
  );
  return items.filter((item) => {
    const mod = (item.module || item.screen || "General").toLowerCase();
    return [...names].some((n) => mod.includes(n) || n.includes(mod));
  });
}

/** Filter saved test cases by module_id. */
export function filterCasesByModuleIds<T extends { module_id?: string | null }>(
  items: T[],
  selectedModuleIds: Set<string>
): T[] {
  if (isAllModulesSelected(selectedModuleIds)) return items;
  return items.filter((item) => item.module_id && selectedModuleIds.has(item.module_id));
}
