/** Ring buffer of browser console output for Report Bug attachments. */

type Level = "log" | "info" | "warn" | "error" | "debug";

const MAX = 400;
const lines: string[] = [];
let installed = false;

function push(level: Level, args: unknown[]) {
  try {
    const ts = new Date().toISOString();
    const msg = args
      .map((a) => {
        if (typeof a === "string") return a;
        try {
          return JSON.stringify(a);
        } catch {
          return String(a);
        }
      })
      .join(" ");
    lines.push(`${ts} [${level}] ${msg}`.slice(0, 2000));
    if (lines.length > MAX) lines.splice(0, lines.length - MAX);
  } catch {
    /* ignore */
  }
}

/** Patch console.* once (safe to call repeatedly). */
export function installClientLogCapture() {
  if (typeof window === "undefined" || installed) return;
  installed = true;
  (["log", "info", "warn", "error", "debug"] as Level[]).forEach((level) => {
    const original = console[level].bind(console);
    console[level] = (...args: unknown[]) => {
      push(level, args);
      original(...args);
    };
  });
  window.addEventListener("error", (ev) => {
    push("error", [ev.message, ev.filename ? `${ev.filename}:${ev.lineno}` : ""]);
  });
  window.addEventListener("unhandledrejection", (ev) => {
    push("error", ["unhandledrejection", String(ev.reason)]);
  });
}

export function recentClientLogsText(limit = MAX): string {
  if (!lines.length) return "(No browser console lines captured yet.)\n";
  return lines.slice(-limit).join("\n") + "\n";
}
