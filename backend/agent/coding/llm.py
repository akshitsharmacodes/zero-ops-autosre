"""
The agent's "brain": something that, given the conversation so far, decides the next
tool call(s).

  * OpenAICompatClient — a real LLM over the OpenAI-compatible chat API. Groq and
    NVIDIA (Nemotron) both speak it, so one client covers both (NFR-M2: swappable).
  * ScriptedClient — plays back pre-recorded decisions (cached mode, FR-9.1). The
    tools still run for real; only the *decisions* are recorded.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Callable, Protocol

logger = logging.getLogger("autosre.llm")


class LLMUnavailable(Exception):
    """The model could not be reached (network, auth, rate limit, timeout)."""


@dataclass
class ToolCall:
    name: str
    arguments: dict
    id: str = field(default_factory=lambda: f"call_{uuid.uuid4().hex[:12]}")


@dataclass
class AssistantTurn:
    content: str
    tool_calls: list[ToolCall]


class ChatClient(Protocol):
    provider: str
    model: str

    def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn: ...


class OpenAICompatClient:
    def __init__(self, provider: str, base_url: str, api_key: str, model: str, timeout: float = 60):
        from openai import OpenAI

        if not api_key:
            raise LLMUnavailable(f"no API key configured for provider '{provider}'")
        self.provider = provider
        self.model = model
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=2)

    def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
        import openai

        try:
            resp = self._client.chat.completions.create(
                model=self.model, messages=messages, tools=tools, tool_choice="auto",
                temperature=0.1, max_tokens=2048,
            )
        except openai.APIError as exc:
            raise LLMUnavailable(f"{self.provider} API error: {exc}") from exc
        msg = resp.choices[0].message
        calls = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_invalid_json": tc.function.arguments}
            calls.append(ToolCall(name=tc.function.name, arguments=args, id=tc.id))
        if not calls and msg.content:
            calls = _tool_calls_from_text(msg.content)  # some models write the call as JSON text
        return AssistantTurn(content=msg.content or "", tool_calls=calls)


def _tool_calls_from_text(text: str) -> list[ToolCall]:
    m = re.search(r"\{[\s\S]*\"name\"\s*:\s*\"(\w+)\"[\s\S]*\}", text)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    args = data.get("arguments") or data.get("parameters") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return []
    return [ToolCall(name=data["name"], arguments=args)]


# A scripted step: (thought, tool name, arguments). Arguments may be a function of the
# previous tool result, so a recording can react to what actually happened.
ScriptStep = tuple[str, str, "dict | Callable[[str], dict]"]


class ScriptedClient:
    provider = "cached"
    model = "scripted-recording"

    def __init__(self, steps: list[ScriptStep], name: str = "recording"):
        self.steps = list(steps)
        self.model = f"scripted:{name}"
        self._i = 0

    def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
        if self._i >= len(self.steps):
            return AssistantTurn(content="(recording finished)", tool_calls=[])
        thought, name, args = self.steps[self._i]
        self._i += 1
        if callable(args):
            last_tool = next((m["content"] for m in reversed(messages) if m.get("role") == "tool"), "")
            args = args(last_tool)
        return AssistantTurn(content=thought, tool_calls=[ToolCall(name=name, arguments=args)])


def build_live_client(provider: str | None = None) -> OpenAICompatClient:
    from django.conf import settings

    provider = provider or settings.LLM["PROVIDER"]
    cfg = settings.LLM["PROVIDERS"].get(provider)
    if not cfg:
        raise LLMUnavailable(f"unknown LLM provider '{provider}' (use groq or nvidia)")
    return OpenAICompatClient(provider, cfg["BASE_URL"], cfg["API_KEY"], cfg["MODEL"], settings.LLM["TIMEOUT_SECONDS"])
