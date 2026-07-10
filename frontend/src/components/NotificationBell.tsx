"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { Bell, Download, Loader2, X } from "lucide-react";
import { apiFetch } from "@/lib/api";

type RunningItem = {
  type: string;
  id: string;
  name: string;
  status: string;
};

type AppNotification = {
  id: string;
  type: string;
  title: string;
  message: string;
  created_at?: string;
  read?: boolean;
  action?: { kind: string; label: string };
  meta?: {
    branch?: string;
    current_commit?: string;
    remote_commit?: string;
    commits_behind?: number;
  };
};

type UpdatesStatus = {
  update: {
    available?: boolean;
    supported?: boolean;
    summary?: string;
    error?: string;
    branch?: string;
    current_commit?: string;
    remote_commit?: string;
    commits_behind?: number;
  };
  running_activity: {
    has_active: boolean;
    count: number;
    items: RunningItem[];
  };
  notifications: AppNotification[];
  unread_count: number;
};

const POLL_MS = 5 * 60 * 1000;

function formatWhen(value?: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<UpdatesStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async (fetchRemote = false) => {
    setLoading(true);
    try {
      const data = await apiFetch<UpdatesStatus>(
        `/api/v1/updates/status?fetch=${fetchRemote ? "true" : "false"}`
      );
      setStatus(data);
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh(true);
    const timer = window.setInterval(() => void refresh(true), POLL_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (!open) return;
    void refresh(true);
  }, [open, refresh]);

  useEffect(() => {
    const onDocClick = (event: MouseEvent) => {
      if (!panelRef.current) return;
      if (!panelRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const unread = status?.unread_count ?? 0;
  const notifications = status?.notifications ?? [];

  const runInstall = async (force = false) => {
    setInstalling(true);
    setMessage(null);
    try {
      const result = await apiFetch<{ started: boolean; message?: string }>("/api/v1/updates/install", {
        method: "POST",
        body: JSON.stringify({ force }),
      });
      setMessage(result.message || "Update started. The app will restart shortly.");
      setConfirmOpen(false);
      setOpen(false);
    } catch (err) {
      const text = err instanceof Error ? err.message : "Update failed.";
      try {
        const parsed = JSON.parse(text) as { detail?: { message?: string; running_activity?: UpdatesStatus["running_activity"] } };
        if (parsed.detail?.running_activity?.has_active) {
          setStatus((prev) =>
            prev
              ? { ...prev, running_activity: parsed.detail!.running_activity! }
              : prev
          );
          setConfirmOpen(true);
          return;
        }
        setMessage(parsed.detail?.message || text);
      } catch {
        setMessage(text);
      }
    } finally {
      setInstalling(false);
    }
  };

  const onInstallClick = () => {
    if (status?.running_activity?.has_active) {
      setConfirmOpen(true);
      return;
    }
    void runInstall(false);
  };

  return (
    <>
      <div className="relative" ref={panelRef}>
        <button
          type="button"
          className="ds-btn-ghost p-2 relative"
          title="Notifications"
          aria-label="Notifications"
          onClick={() => setOpen((value) => !value)}
          suppressHydrationWarning
        >
          <Bell className="w-4 h-4" />
          {unread > 0 && (
            <span className="absolute top-1 right-1 min-w-[16px] h-4 px-1 rounded-full bg-amber-500 text-[10px] font-semibold text-white flex items-center justify-center">
              {unread}
            </span>
          )}
        </button>

        {open && (
          <div className="absolute right-0 mt-2 w-[360px] max-w-[90vw] ds-card shadow-lg border border-[var(--border-default)] z-50">
            <div className="ds-card-header flex items-center justify-between">
              <h2 className="text-sm font-semibold">Notifications</h2>
              <button type="button" className="ds-btn-ghost p-1" onClick={() => setOpen(false)} aria-label="Close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="ds-card-body max-h-[420px] overflow-y-auto space-y-3">
              {loading && !status && (
                <div className="flex items-center gap-2 text-sm text-[var(--text-tertiary)]">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Checking for updates...
                </div>
              )}

              {!loading && notifications.length === 0 && (
                <p className="text-sm text-[var(--text-tertiary)]">No new notifications.</p>
              )}

              {notifications.map((item) => (
                <div key={item.id} className="rounded-md border border-[var(--border-default)] p-3 bg-[var(--surface-sunken)]">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-medium text-[var(--text-primary)]">{item.title}</p>
                      <p className="text-xs text-[var(--text-secondary)] mt-1">{item.message}</p>
                      {item.meta?.branch && (
                        <p className="text-[11px] text-[var(--text-tertiary)] mt-2">
                          Branch {item.meta.branch}: {item.meta.current_commit} to {item.meta.remote_commit}
                        </p>
                      )}
                      {item.created_at && (
                        <p className="text-[10px] text-[var(--text-tertiary)] mt-1">{formatWhen(item.created_at)}</p>
                      )}
                    </div>
                  </div>
                  {item.action?.kind === "install_update" && (
                    <button
                      type="button"
                      className={clsx("ds-btn-primary mt-3 w-full text-sm", installing && "opacity-70")}
                      onClick={onInstallClick}
                      disabled={installing}
                    >
                      {installing ? (
                        <span className="inline-flex items-center gap-2">
                          <Loader2 className="w-4 h-4 animate-spin" />
                          Installing...
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-2">
                          <Download className="w-4 h-4" />
                          {item.action.label}
                        </span>
                      )}
                    </button>
                  )}
                </div>
              ))}

              {message && (
                <p className="text-xs p-2 rounded-md bg-[var(--surface-raised)] text-[var(--text-secondary)]">{message}</p>
              )}
            </div>
          </div>
        )}
      </div>

      {confirmOpen && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[60] p-4">
          <div className="ds-card w-full max-w-md">
            <div className="ds-card-header">
              <h2 className="text-sm font-semibold">Tests are still running</h2>
              <button type="button" className="ds-btn-ghost p-1" onClick={() => setConfirmOpen(false)}>
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="ds-card-body space-y-4">
              <p className="text-sm text-[var(--text-secondary)]">
                Installing the update will stop the app and restart it. Active work may be interrupted.
              </p>
              <ul className="text-xs text-[var(--text-tertiary)] space-y-1 max-h-32 overflow-y-auto">
                {(status?.running_activity?.items ?? []).map((item) => (
                  <li key={`${item.type}-${item.id}`}>
                    {item.name} ({item.type})
                  </li>
                ))}
              </ul>
              <div className="flex gap-2">
                <button
                  type="button"
                  className="ds-btn-primary flex-1"
                  onClick={() => void runInstall(true)}
                  disabled={installing}
                >
                  {installing ? "Installing..." : "Proceed and install"}
                </button>
                <button
                  type="button"
                  className="ds-btn-secondary flex-1"
                  onClick={() => setConfirmOpen(false)}
                  disabled={installing}
                >
                  Abort
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
