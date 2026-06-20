"use client";

import { useRef, useEffect } from "react";
import clsx from "clsx";
import { CheckSquare, Square } from "lucide-react";

interface CodeEditorProps {
  value: string;
  onChange: (value: string) => void;
  language?: string;
  readOnly?: boolean;
  className?: string;
}

export function CodeEditor({ value, onChange, language = "typescript", readOnly, className }: CodeEditorProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lines = value.split("\n");

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Tab") {
      e.preventDefault();
      const ta = textareaRef.current;
      if (!ta) return;
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      const newVal = value.substring(0, start) + "  " + value.substring(end);
      onChange(newVal);
      requestAnimationFrame(() => {
        ta.selectionStart = ta.selectionEnd = start + 2;
      });
    }
  };

  return (
    <div className={clsx("flex font-mono text-xs bg-[#1e1e2e] rounded-md overflow-hidden border border-gray-800", className)}>
      {/* Line numbers */}
      <div className="select-none py-3 px-2 text-right text-gray-600 bg-[#181825] border-r border-gray-800 min-w-[3rem] overflow-hidden">
        {lines.map((_, i) => (
          <div key={i} className="leading-5 h-5">{i + 1}</div>
        ))}
      </div>
      {/* Editor */}
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        readOnly={readOnly}
        spellCheck={false}
        className="flex-1 py-3 px-4 bg-transparent text-gray-100 leading-5 resize-none outline-none min-h-[400px]"
        style={{ tabSize: 2 }}
      />
      {/* Language badge */}
      <div className="absolute top-2 right-2 text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-500 pointer-events-none"
        style={{ position: "relative", alignSelf: "flex-start", margin: "8px" }}>
        {language}
      </div>
    </div>
  );
}

interface FileTreeProps {
  files: { path: string; type?: string }[];
  activeFile: string | null;
  selectedPaths?: Set<string>;
  onSelect: (path: string) => void;
  onToggleSelect?: (path: string) => void;
}

export function FileTree({ files, activeFile, selectedPaths, onSelect, onToggleSelect }: FileTreeProps) {
  const grouped: Record<string, { path: string; type?: string }[]> = {};
  for (const f of files) {
    const parts = f.path.split("/");
    const dir = parts.length > 1 ? parts.slice(0, -1).join("/") : "/";
    grouped[dir] = grouped[dir] || [];
    grouped[dir].push(f);
  }

  return (
    <div className="py-2 text-xs">
      {Object.entries(grouped).map(([dir, dirFiles]) => (
        <div key={dir}>
          <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
            {dir === "/" ? "root" : dir}
          </p>
          {dirFiles.map((f) => {
            const name = f.path.split("/").pop()!;
            const isActive = f.path === activeFile;
            const isSelected = selectedPaths?.has(f.path) ?? false;
            return (
              <div
                key={f.path}
                className={clsx(
                  "flex items-center gap-0.5 transition-colors",
                  isActive
                    ? "bg-brand-50 text-brand-800 border-r-2 border-brand-700"
                    : "text-[var(--text-secondary)] hover:bg-[var(--surface-sunken)]"
                )}
              >
                {onToggleSelect && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onToggleSelect(f.path);
                    }}
                    className="p-1.5 shrink-0 opacity-70 hover:opacity-100"
                    title={isSelected ? "Deselect file" : "Select file"}
                  >
                    {isSelected ? (
                      <CheckSquare className="w-3.5 h-3.5 text-brand-700" />
                    ) : (
                      <Square className="w-3.5 h-3.5 text-gray-400" />
                    )}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => onSelect(f.path)}
                  className="flex-1 text-left py-1.5 pr-3 flex items-center gap-2 min-w-0"
                >
                  <span className={clsx(
                    "w-1.5 h-1.5 rounded-full shrink-0",
                    f.type === "page_object" ? "bg-purple-400" : "bg-emerald-400"
                  )} />
                  <span className="truncate">{name}</span>
                </button>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
