"use client";

import { useCallback, useEffect, useState } from "react";
import { Bug, Camera, ExternalLink, Loader2, X } from "lucide-react";
import { toBlob } from "html-to-image";
import { apiFetch, BACKEND_URL } from "@/lib/api";
import { authHeaders, getStoredUser } from "@/lib/auth";
import { installClientLogCapture, recentClientLogsText } from "@/lib/clientLogs";

type BugStatus = {
  configured: boolean;
  owner?: string;
  repo?: string;
  branch?: string;
  remote_url?: string;
  has_token?: boolean;
  message?: string;
};

type BugResult = {
  ok: boolean;
  issue_number?: number;
  html_url?: string;
  attachments_url?: string;
  message?: string;
};

async function captureActivePageScreenshot(): Promise<{ file: File; previewUrl: string } | null> {
  if (typeof document === "undefined") return null;
  const root =
    (document.querySelector("main") as HTMLElement | null) ||
    (document.getElementById("__next") as HTMLElement | null) ||
    document.body;

  try {
    const blob = await toBlob(root, {
      cacheBust: true,
      pixelRatio: Math.min(window.devicePixelRatio || 1, 1.5),
      filter: (node) => {
        if (!(node instanceof HTMLElement)) return true;
        // Skip the Report Bug overlay if somehow present
        if (node.dataset?.bugModal === "true") return false;
        return true;
      },
    });
    if (!blob) return null;
    const file = new File([blob], `qeos-page-${Date.now()}.png`, { type: "image/png" });
    return { file, previewUrl: URL.createObjectURL(blob) };
  } catch {
    return null;
  }
}

export function ReportBugButton() {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<BugStatus | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [steps, setSteps] = useState("");
  const [screenshot, setScreenshot] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [capturing, setCapturing] = useState(false);
  const [captureNote, setCaptureNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<BugResult | null>(null);

  useEffect(() => {
    installClientLogCapture();
  }, []);

  const loadStatus = useCallback(() => {
    apiFetch<BugStatus>("/api/v1/support/bug-report/status")
      .then(setStatus)
      .catch(() =>
        setStatus({
          configured: false,
          message: "Could not reach support API.",
        })
      );
  }, []);

  const revokePreview = useCallback((url: string | null) => {
    if (url) URL.revokeObjectURL(url);
  }, []);

  const openReporter = async () => {
    setResult(null);
    setError("");
    setCaptureNote("");
    setCapturing(true);
    // Capture the live page BEFORE the modal covers it
    const shot = await captureActivePageScreenshot();
    setCapturing(false);
    if (shot) {
      setPreviewUrl((prev) => {
        revokePreview(prev);
        return shot.previewUrl;
      });
      setScreenshot(shot.file);
      setCaptureNote("Current page screenshot captured automatically.");
    } else {
      setScreenshot(null);
      setPreviewUrl((prev) => {
        revokePreview(prev);
        return null;
      });
      setCaptureNote("Could not auto-capture the page — you can attach a screenshot manually.");
    }
    setOpen(true);
  };

  useEffect(() => {
    if (!open) return;
    loadStatus();
  }, [open, loadStatus]);

  useEffect(() => {
    return () => revokePreview(previewUrl);
  }, [previewUrl, revokePreview]);

  const submit = async () => {
    setSubmitting(true);
    setError("");
    setResult(null);
    try {
      // Prefer a fresh capture if somehow missing
      let shot = screenshot;
      if (!shot) {
        const again = await captureActivePageScreenshot();
        if (again) {
          shot = again.file;
          setScreenshot(again.file);
          setPreviewUrl((prev) => {
            revokePreview(prev);
            return again.previewUrl;
          });
        }
      }

      const form = new FormData();
      form.append("title", title.trim());
      form.append("description", description.trim());
      form.append("steps_to_reproduce", steps.trim());
      form.append("page_url", typeof window !== "undefined" ? window.location.href : "");
      form.append("include_diagnostics", "true");
      form.append("client_logs", recentClientLogsText());
      const user = getStoredUser();
      if (user?.email) form.append("reporter", user.email);
      if (shot) form.append("screenshot", shot);

      const response = await fetch(`${BACKEND_URL}/api/v1/support/bug-report`, {
        method: "POST",
        body: form,
        headers: {
          ...authHeaders(),
        },
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof data.detail === "string" ? data.detail : data.message || response.statusText;
        throw new Error(detail || "Failed to submit bug report");
      }

      setResult(data as BugResult);
      setTitle("");
      setDescription("");
      setSteps("");
      setScreenshot(null);
      setPreviewUrl((prev) => {
        revokePreview(prev);
        return null;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const close = () => {
    setOpen(false);
    setPreviewUrl((prev) => {
      revokePreview(prev);
      return null;
    });
  };

  return (
    <>
      <button
        type="button"
        className="ds-btn-ghost p-2"
        title="Report Bug"
        aria-label="Report Bug"
        disabled={capturing}
        onClick={() => void openReporter()}
      >
        {capturing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Bug className="w-4 h-4" />}
      </button>

      {open && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[70] p-4" data-bug-modal="true">
          <div className="ds-card w-full max-w-lg max-h-[90vh] overflow-y-auto" data-bug-modal="true">
            <div className="ds-card-header flex items-center justify-between">
              <h2 className="text-sm font-semibold flex items-center gap-2">
                <Bug className="w-4 h-4" />
                Report Bug
              </h2>
              <button type="button" className="ds-btn-ghost p-1" onClick={close} aria-label="Close">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="ds-card-body space-y-3">
              <p className="text-xs text-[var(--text-secondary)]">
                Files a GitHub issue with an automatic page screenshot plus app and browser logs so you can fix it
                locally and push the update back.
              </p>

              {status && (
                <p
                  className={`text-xs rounded-md px-2 py-1.5 ${
                    status.configured
                      ? "bg-emerald-50 text-emerald-900 border border-emerald-200"
                      : "bg-amber-50 text-amber-950 border border-amber-200"
                  }`}
                >
                  {status.configured
                    ? `Ready → ${status.owner}/${status.repo} (${status.branch})`
                    : status.message}
                </p>
              )}

              {result?.html_url ? (
                <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-950 space-y-2">
                  <p className="font-medium">{result.message || `Bug #${result.issue_number} created`}</p>
                  <a
                    href={result.html_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs underline"
                  >
                    Open issue <ExternalLink className="w-3 h-3" />
                  </a>
                  {result.attachments_url && (
                    <a
                      href={result.attachments_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block text-xs underline"
                    >
                      View attachments folder
                    </a>
                  )}
                  <button type="button" className="ds-btn-secondary text-xs mt-1" onClick={close}>
                    Close
                  </button>
                </div>
              ) : (
                <>
                  <div>
                    <label className="block text-xs font-medium mb-1">Title</label>
                    <input
                      className="ds-input text-sm"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      placeholder="Short summary of the bug"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium mb-1">Description</label>
                    <textarea
                      className="ds-input text-sm resize-none w-full"
                      rows={4}
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      placeholder="What went wrong? Expected vs actual."
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium mb-1">Steps to reproduce (optional)</label>
                    <textarea
                      className="ds-input text-sm resize-none w-full"
                      rows={3}
                      value={steps}
                      onChange={(e) => setSteps(e.target.value)}
                      placeholder={"1. Open Discovery\n2. Run Flipkart prompt\n3. …"}
                    />
                  </div>

                  <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-2 space-y-2">
                    <div className="flex items-center gap-2 text-xs font-medium">
                      <Camera className="w-3.5 h-3.5" />
                      Auto attachments
                    </div>
                    <p className="text-[10px] text-[var(--text-tertiary)]">
                      {captureNote || "Page screenshot + diagnostics + application/browser logs are attached automatically."}
                    </p>
                    {previewUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={previewUrl}
                        alt="Captured page"
                        className="w-full max-h-40 object-contain rounded border border-[var(--border-subtle)] bg-white"
                      />
                    ) : (
                      <p className="text-[10px] text-amber-800">No auto screenshot — attach one below if needed.</p>
                    )}
                    <label className="block text-[10px] text-[var(--text-tertiary)]">
                      Replace screenshot (optional)
                      <input
                        type="file"
                        accept="image/*"
                        className="block w-full text-xs mt-1"
                        onChange={(e) => {
                          const file = e.target.files?.[0] ?? null;
                          setScreenshot(file);
                          setPreviewUrl((prev) => {
                            revokePreview(prev);
                            return file ? URL.createObjectURL(file) : null;
                          });
                          if (file) setCaptureNote(`Using manual screenshot: ${file.name}`);
                        }}
                      />
                    </label>
                  </div>

                  {error && (
                    <p className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-md px-2 py-1.5">{error}</p>
                  )}

                  <div className="flex gap-2 pt-1">
                    <button
                      type="button"
                      className="ds-btn-primary flex-1 text-sm inline-flex items-center justify-center gap-2"
                      disabled={submitting || !title.trim() || !description.trim() || status?.configured === false}
                      onClick={() => void submit()}
                    >
                      {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Bug className="w-4 h-4" />}
                      {submitting ? "Filing…" : "Submit to GitHub"}
                    </button>
                    <button type="button" className="ds-btn-secondary" onClick={close} disabled={submitting}>
                      Cancel
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
