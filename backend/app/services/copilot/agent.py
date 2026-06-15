"""QEOS Global Copilot — LLM-driven platform agent with tool execution."""

import json
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog

from app.config import settings
from app.llm.base import LLMMessage, MessageRole
from app.llm.router import get_llm_router
from app.services.copilot.tools import TOOL_DEFINITIONS, execute_tool, tools_prompt_json

logger = structlog.get_logger()

COPILOT_SYSTEM = """You are QEOS Copilot, the global AI assistant for the Quality Engineering Operating System.
You help users run tests, manage discovery, execute automation & performance load tests, view dashboards, and drive the entire platform via natural language.

You have access to platform tools. When you need data or must perform an action, respond with ONLY valid JSON (no markdown fences):
{{"action": "tool", "tool": "<tool_name>", "arguments": {{...}}, "thought": "brief reason"}}

When ready to answer the user, respond with ONLY:
{{"action": "reply", "content": "<markdown response with clear next steps, links like /executions, /performance, /discovery>"}}

Rules:
- Prefer calling tools over guessing — list projects, test cases, runs before acting when IDs are unknown
- Confirm destructive or long-running actions in your reply after executing
- For run/stop: use check_run_status to poll; background runs cannot be cancelled mid-flight yet — explain status
- Use the active project_id from context when provided
- Be concise, actionable, and expert in QA/automation/performance engineering
- Suggest best practices (discovery → test cases → automation → execution → performance)

Available tools:
{tools}
"""

# Prefer QEOS native first — fast, no external dependency; fall back to external LLMs when configured
PROVIDER_PRIORITY = ["qeos-native", "qeos-hybrid", "openai", "anthropic", "ollama"]


@dataclass
class CopilotMessage:
    role: str
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class CopilotSession:
    id: str
    project_id: str | None
    messages: list[CopilotMessage] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


_sessions: dict[str, CopilotSession] = {}


def get_or_create_session(session_id: str | None, project_id: str | None) -> CopilotSession:
    sid = session_id or str(uuid.uuid4())
    if sid not in _sessions:
        _sessions[sid] = CopilotSession(id=sid, project_id=project_id)
    session = _sessions[sid]
    if project_id:
        session.project_id = project_id
    return session


def _select_copilot_provider() -> tuple[str, str]:
    router = get_llm_router()
    available = {p["name"] for p in router.list_providers()}
    for name in PROVIDER_PRIORITY:
        if name in available:
            provider = router.get_provider(name)
            models = provider.list_models()
            if name == "openai":
                model = "gpt-4o-mini" if "gpt-4o-mini" in models else models[0]
            elif name == "anthropic":
                model = models[0] if models else "claude-3-5-sonnet-20241022"
            elif name == "ollama":
                model = settings.ollama_model
            else:
                model = models[0]
            return name, model
    return settings.default_llm_provider, settings.default_llm_model


def _parse_agent_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return None


class CopilotAgent:
    MAX_TOOL_ITERATIONS = 8

    def __init__(self, db):
        self.db = db
        self.router = get_llm_router()

    async def chat(
        self,
        user_message: str,
        session_id: str | None = None,
        project_id: str | None = None,
        page_context: str | None = None,
    ) -> dict:
        session = get_or_create_session(session_id, project_id)
        session.messages.append(CopilotMessage(role="user", content=user_message))

        provider_name, model = _select_copilot_provider()
        tool_results: list[dict] = []
        final_reply = ""

        for _ in range(self.MAX_TOOL_ITERATIONS):
            llm_messages = self._build_messages(session, page_context, tool_results)
            response = await self.router.complete(
                llm_messages, model=model, provider=provider_name, temperature=0.3, max_tokens=4096,
            )
            parsed = _parse_agent_json(response.content)

            if not parsed:
                final_reply = response.content
                break

            if parsed.get("action") == "reply":
                final_reply = parsed.get("content", response.content)
                break

            if parsed.get("action") == "tool":
                tool_name = parsed.get("tool", "")
                arguments = parsed.get("arguments") or {}
                if session.project_id and "project_id" not in arguments:
                    arguments["project_id"] = session.project_id
                result = await execute_tool(self.db, tool_name, arguments)
                tool_results.append({
                    "tool": tool_name,
                    "arguments": arguments,
                    "result": result,
                    "thought": parsed.get("thought", ""),
                })
                continue

            final_reply = response.content

        if not final_reply:
            final_reply = "I completed the requested operations. Check the tool results above or ask for a summary."

        session.messages.append(CopilotMessage(
            role="assistant",
            content=final_reply,
            tool_calls=tool_results,
        ))

        return {
            "session_id": session.id,
            "reply": final_reply,
            "tool_calls": tool_results,
            "provider": provider_name,
            "model": model,
            "messages": [{"role": m.role, "content": m.content, "tool_calls": m.tool_calls} for m in session.messages[-10:]],
        }

    async def stream_chat(
        self,
        user_message: str,
        session_id: str | None = None,
        project_id: str | None = None,
        page_context: str | None = None,
    ) -> AsyncIterator[dict]:
        session = get_or_create_session(session_id, project_id)
        session.messages.append(CopilotMessage(role="user", content=user_message))

        provider_name, model = _select_copilot_provider()
        yield {"type": "meta", "provider": provider_name, "model": model, "session_id": session.id}

        tool_results: list[dict] = []
        final_reply = ""

        for iteration in range(self.MAX_TOOL_ITERATIONS):
            yield {"type": "thinking", "message": f"Reasoning (step {iteration + 1})…"}
            llm_messages = self._build_messages(session, page_context, tool_results)
            response = await self.router.complete(
                llm_messages, model=model, provider=provider_name, temperature=0.3, max_tokens=4096,
            )
            parsed = _parse_agent_json(response.content)

            if not parsed:
                final_reply = response.content
                break

            if parsed.get("action") == "reply":
                final_reply = parsed.get("content", response.content)
                break

            if parsed.get("action") == "tool":
                tool_name = parsed.get("tool", "")
                arguments = parsed.get("arguments") or {}
                if session.project_id and "project_id" not in arguments:
                    arguments["project_id"] = session.project_id
                yield {"type": "tool_start", "tool": tool_name, "arguments": arguments, "thought": parsed.get("thought")}
                result = await execute_tool(self.db, tool_name, arguments)
                entry = {"tool": tool_name, "arguments": arguments, "result": result}
                tool_results.append(entry)
                yield {"type": "tool_end", **entry}
                continue

            final_reply = response.content
            break

        if not final_reply:
            final_reply = self._summarize_tool_results(tool_results) if tool_results else "How can I help with quality engineering?"

        async for event in self._stream_text(final_reply, provider_name, model):
            yield event

        session.messages.append(CopilotMessage(role="assistant", content=final_reply, tool_calls=tool_results))
        yield {"type": "done", "content": final_reply, "tool_calls": tool_results, "session_id": session.id}

    async def _stream_text(self, text: str, provider_name: str, model: str) -> AsyncIterator[dict]:
        if provider_name == "openai" and settings.openai_api_key:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.openai_api_key)
            stream = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Deliver this response to the user with clear markdown formatting:"},
                    {"role": "user", "content": text},
                ],
                temperature=0.2,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    yield {"type": "token", "content": delta}
            return

        for i in range(0, len(text), 35):
            yield {"type": "token", "content": text[i:i + 35]}

    def _build_messages(
        self, session: CopilotSession, page_context: str | None, tool_results: list[dict]
    ) -> list[LLMMessage]:
        system = COPILOT_SYSTEM.format(tools=tools_prompt_json())
        if session.project_id:
            system += f"\n\nActive project_id: {session.project_id}"
        if page_context:
            system += f"\n\nUser is currently on page: {page_context}"

        messages = [LLMMessage(role=MessageRole.SYSTEM, content=system)]
        for msg in session.messages[-12:]:
            if msg.role in ("user", "assistant"):
                messages.append(LLMMessage(role=MessageRole(msg.role), content=msg.content))

        if tool_results:
            messages.append(LLMMessage(
                role=MessageRole.USER,
                content="Tool results:\n" + json.dumps(tool_results, indent=2, default=str)[:12000],
            ))
        return messages

    def _summarize_tool_results(self, tool_results: list[dict]) -> str:
        lines = ["Here's what I did:"]
        for tr in tool_results:
            name = tr.get("tool", "tool")
            res = tr.get("result", {})
            if res.get("ok"):
                lines.append(f"- **{name}**: succeeded — {json.dumps({k: v for k, v in res.items() if k != 'ok'}, default=str)[:300]}")
            else:
                lines.append(f"- **{name}**: failed — {res.get('error', 'unknown error')}")
        lines.append("\nAsk me to explain results or take the next step.")
        return "\n".join(lines)
