"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import {
  Bot, X, Send, Loader2, Sparkles, ChevronDown, Wrench, CheckCircle2, AlertCircle, Minimize2,
} from "lucide-react";
import { apiFetch, BACKEND_URL } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import { useActiveProject } from "@/context/ProjectContext";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCall[];
  streaming?: boolean;
}

interface ToolCall {
  tool: string;
  arguments?: Record<string, unknown>;
  result?: { ok?: boolean; error?: string };
}

interface CopilotStatus {
  name: string;
  provider: string;
  model: string;
  streaming: boolean;
}

const SUGGESTIONS = [
  "List my projects and test case counts",
  "Start browser discovery on our staging URL",
  "Run all Playwright tests in the background",
  "Show latest execution dashboard pass/fail",
  "Generate a k6 performance script from discovery replay",
  "What's the status of my last test run?",
];

export function GlobalCopilot() {
  const pathname = usePathname();
  const { projectId, setProjectId, projects } = useActiveProject();
  const [open, setOpen] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [status, setStatus] = useState<CopilotStatus | null>(null);
  const [activeTools, setActiveTools] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const hidden = pathname === "/login";

  useEffect(() => {
    if (hidden) return;
    apiFetch<CopilotStatus>("/api/v1/copilot/status").then(setStatus).catch(() => {});
  }, [hidden]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activeTools]);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || loading) return;
    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: "user", content: text.trim() };
    const assistantId = crypto.randomUUID();
    setMessages((m) => [...m, userMsg, { id: assistantId, role: "assistant", content: "", streaming: true }]);
    setInput("");
    setLoading(true);
    setActiveTools([]);

    const useStream = status?.streaming ?? false;
    const body = {
      message: text.trim(),
      session_id: sessionId,
      project_id: projectId || undefined,
      page_context: pathname,
    };

    try {
      if (useStream) {
        const res = await fetch(`${typeof window !== "undefined" ? "" : BACKEND_URL}/api/v1/copilot/chat/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify(body),
        });
        if (!res.ok || !res.body) throw new Error("Stream failed");
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let content = "";
        const toolCalls: ToolCall[] = [];

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const ev = JSON.parse(line.slice(6));
              if (ev.type === "meta" && ev.session_id) setSessionId(ev.session_id);
              if (ev.type === "tool_start") setActiveTools((t) => [...t, ev.tool]);
              if (ev.type === "tool_end") {
                setActiveTools((t) => t.filter((x) => x !== ev.tool));
                toolCalls.push({ tool: ev.tool, arguments: ev.arguments, result: ev.result });
              }
              if (ev.type === "token") {
                content += ev.content;
                setMessages((m) => m.map((msg) => msg.id === assistantId ? { ...msg, content, toolCalls } : msg));
              }
              if (ev.type === "done") {
                content = ev.content || content;
                setSessionId(ev.session_id || sessionId);
                setMessages((m) => m.map((msg) => msg.id === assistantId ? {
                  ...msg, content, toolCalls: ev.tool_calls || toolCalls, streaming: false,
                } : msg));
              }
            } catch { /* skip malformed */ }
          }
        }
      } else {
        const result = await apiFetch<{
          session_id: string; reply: string; tool_calls: ToolCall[]; provider: string;
        }>("/api/v1/copilot/chat", { method: "POST", body: JSON.stringify(body) });
        setSessionId(result.session_id);
        setMessages((m) => m.map((msg) => msg.id === assistantId ? {
          ...msg, content: result.reply, toolCalls: result.tool_calls, streaming: false,
        } : msg));
      }
    } catch (e) {
      setMessages((m) => m.map((msg) => msg.id === assistantId ? {
        ...msg,
        content: `Sorry, I encountered an error: ${e instanceof Error ? e.message : String(e)}. Configure OPENAI_API_KEY or Ollama for full LLM capabilities.`,
        streaming: false,
      } : msg));
    } finally {
      setLoading(false);
      setActiveTools([]);
    }
  }, [loading, sessionId, projectId, pathname, status?.streaming]);

  if (hidden) return null;

  return (
    <>
      {!open && (
        <button
          suppressHydrationWarning
          onClick={() => { setOpen(true); setMinimized(false); setTimeout(() => inputRef.current?.focus(), 200); }}
          className="fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-3 rounded-full bg-gradient-to-r from-brand-700 to-indigo-600 text-white shadow-lg hover:shadow-xl transition-all hover:scale-105"
          title="QEOS Copilot"
        >
          <Sparkles className="w-5 h-5" />
          <span className="text-sm font-semibold hidden sm:inline">QEOS Copilot</span>
        </button>
      )}

      {open && (
        <div className={`fixed z-50 flex flex-col bg-[var(--surface-raised)] border border-[var(--border-default)] shadow-2xl transition-all ${
          minimized ? "bottom-6 right-6 w-80 h-14 rounded-xl" : "bottom-4 right-4 top-4 w-[420px] max-w-[calc(100vw-2rem)] rounded-2xl"
        }`}>
          {/* Header */}
          <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--border-default)] bg-gradient-to-r from-brand-700/10 to-indigo-500/10 rounded-t-2xl shrink-0">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-700 to-indigo-600 flex items-center justify-center">
              <Bot className="w-4 h-4 text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold">QEOS Copilot</p>
              <p className="text-[10px] text-[var(--text-tertiary)] truncate">
                {status ? `${status.provider} · ${status.model}` : "AI Platform Agent"}
              </p>
            </div>
            <button onClick={() => setMinimized(!minimized)} className="ds-btn-ghost p-1.5"><Minimize2 className="w-4 h-4" /></button>
            <button onClick={() => setOpen(false)} className="ds-btn-ghost p-1.5"><X className="w-4 h-4" /></button>
          </div>

          {!minimized && (
            <>
              {/* Project + context */}
              <div className="px-3 py-2 border-b border-[var(--border-default)]/50 flex gap-2 items-center shrink-0">
                <select className="ds-input text-xs py-1 flex-1" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                  <option value="">No project context</option>
                  {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
                <span className="text-[10px] text-[var(--text-tertiary)] truncate max-w-[100px]" title={pathname}>{pathname.split("/").pop() || "home"}</span>
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3 min-h-0">
                {messages.length === 0 && (
                  <div className="space-y-3">
                    <p className="text-xs text-[var(--text-tertiary)] text-center py-4">
                      Ask me to run tests, start discovery, view dashboards, generate scripts, or anything on the platform.
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {SUGGESTIONS.map((s) => (
                        <button key={s} onClick={() => sendMessage(s)}
                          className="text-[11px] px-2.5 py-1.5 rounded-full border border-[var(--border-default)] hover:bg-brand-50 hover:border-brand-300 text-left">
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {messages.map((msg) => (
                  <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[92%] rounded-xl px-3 py-2 text-sm ${
                      msg.role === "user"
                        ? "bg-brand-700 text-white"
                        : "bg-[var(--surface-sunken)] border border-[var(--border-default)]"
                    }`}>
                      {msg.toolCalls && msg.toolCalls.length > 0 && (
                        <div className="mb-2 space-y-1">
                          {msg.toolCalls.map((tc, i) => (
                            <div key={i} className="flex items-center gap-1.5 text-[10px] font-mono bg-black/5 rounded px-2 py-1">
                              <Wrench className="w-3 h-3 shrink-0" />
                              <span className="truncate">{tc.tool}</span>
                              {tc.result?.ok ? <CheckCircle2 className="w-3 h-3 text-emerald-600 shrink-0" /> :
                                tc.result?.ok === false ? <AlertCircle className="w-3 h-3 text-red-500 shrink-0" /> : null}
                            </div>
                          ))}
                        </div>
                      )}
                      <div className="whitespace-pre-wrap break-words prose-sm">
                        {msg.content || (msg.streaming && <Loader2 className="w-4 h-4 animate-spin" />)}
                      </div>
                    </div>
                  </div>
                ))}

                {activeTools.length > 0 && (
                  <div className="flex items-center gap-2 text-xs text-brand-700 bg-brand-50 rounded-lg px-3 py-2">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    Running: {activeTools.join(", ")}
                  </div>
                )}
                <div ref={bottomRef} />
              </div>

              {/* Input */}
              <div className="p-3 border-t border-[var(--border-default)] shrink-0">
                <div className="flex gap-2 items-end">
                  <textarea
                    ref={inputRef}
                    className="ds-input text-sm flex-1 resize-none min-h-[44px] max-h-28 py-2.5"
                    rows={1}
                    placeholder="Ask Copilot to run, view, suggest, or drive anything…"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(input); }
                    }}
                    disabled={loading}
                  />
                  <button onClick={() => sendMessage(input)} disabled={loading || !input.trim()}
                    className="ds-btn-primary p-2.5 shrink-0 rounded-lg">
                    {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                  </button>
                </div>
                <p className="text-[10px] text-[var(--text-tertiary)] mt-1.5 flex items-center gap-1">
                  <ChevronDown className="w-3 h-3" /> Enter to send · Shift+Enter for newline
                </p>
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
}
