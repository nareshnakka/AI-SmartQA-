"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Search, Loader2 } from "lucide-react";
import { apiFetch } from "@/lib/api";

interface SearchResult {
  type: string;
  id: string;
  title: string;
  subtitle: string;
  href: string;
}

export function GlobalSearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const search = useCallback((q: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!q.trim()) {
      setResults([]);
      setOpen(false);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await apiFetch<{ results: SearchResult[] }>(
          `/api/v1/platform/search?q=${encodeURIComponent(q)}&limit=8`
        );
        setResults(data.results);
        setOpen(true);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 250);
  }, []);

  useEffect(() => () => { if (debounceRef.current) clearTimeout(debounceRef.current); }, []);

  const onSelect = (href: string) => {
    setOpen(false);
    setQuery("");
    router.push(href);
  };

  return (
    <div className="relative hidden md:block">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--text-tertiary)]" />
      {loading && (
        <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 animate-spin text-[var(--text-tertiary)]" />
      )}
      <input
        type="text"
        value={query}
        onChange={(e) => { setQuery(e.target.value); search(e.target.value); }}
        onFocus={() => query && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder="Search projects, tests, integrations..."
        className="w-64 pl-9 pr-3 py-1.5 text-sm bg-[var(--surface-sunken)] border border-transparent rounded-md
                   placeholder:text-[var(--text-tertiary)] focus:outline-none focus:bg-white focus:border-[var(--border-strong)]"
      />
      {open && results.length > 0 && (
        <div className="absolute top-full mt-1 w-80 right-0 bg-white border border-[var(--border-default)] rounded-md shadow-lg z-50 py-1">
          {results.map((r) => (
            <button
              key={`${r.type}-${r.id}`}
              onMouseDown={() => onSelect(r.href)}
              className="w-full text-left px-3 py-2 hover:bg-[var(--surface-sunken)]"
            >
              <p className="text-sm font-medium truncate">{r.title}</p>
              <p className="text-xs text-[var(--text-tertiary)] capitalize">{r.type} · {r.subtitle}</p>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
