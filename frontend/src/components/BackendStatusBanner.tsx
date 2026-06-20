"use client";

import { useEffect, useState } from "react";
import { AlertCircle } from "lucide-react";
import { checkBackendHealth } from "@/lib/api";

export function BackendStatusBanner() {
  const [issue, setIssue] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      const h = await checkBackendHealth();
      if (cancelled) return;
      setIssue(h.ok ? null : h.message ?? "Backend unavailable");
    };
    check();
    const id = setInterval(check, 30_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (!issue) return null;

  return (
    <div className="bg-amber-50 border-b border-amber-200 px-4 py-2 text-sm text-amber-950 flex items-start gap-2">
      <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
      <p>{issue}</p>
    </div>
  );
}
