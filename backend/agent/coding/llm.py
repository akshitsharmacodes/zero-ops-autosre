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


class LLMQuotaExhausted(LLMUnavailable):
    """The model's quota is used up for a long time (e.g. a daily token cap); retrying now is pointless."""


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
    prompt_budget: int | None  # max prompt tokens per request (None = unlimited)

    def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn: ...


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    base_url: str
    api_key: str = field(repr=False)  # never printed
    model: str
    timeout: float = 60
    tokens_per_minute: int = 0  # provider cap; 0 = unlimited
    max_output_tokens: int = 1024
    reasoning_effort: str | None = "low"  # for reasoning models (gpt-oss); keeps hidden reasoning short
    rate_limit_retries: int = 3


class OpenAICompatClient:
    """Real LLM over the OpenAI-compatible API, with client-side rate limiting and retries."""

    SAFETY_MARGIN_TOKENS = 400
    MAX_RETRY_WAIT_SECONDS = 60

    def __init__(self, settings: LLMSettings, limiter=None, sleep: Callable[[float], None] | None = None):
        from openai import OpenAI

        from .ratelimit import RollingTokenLimiter, shared_limiter

        if not settings.api_key:
            raise LLMUnavailable(f"no API key configured for provider '{settings.provider}'")
        self.settings = settings
        self.provider = settings.provider
        self.model = settings.model
        self._client = OpenAI(base_url=settings.base_url, api_key=settings.api_key,
                              timeout=settings.timeout, max_retries=1)
        self._limiter = limiter or (shared_limiter(f"{settings.provider}:{settings.model}", settings.tokens_per_minute)
                                    if settings.tokens_per_minute else RollingTokenLimiter(0))
        import time as _time

        self._sleep = sleep or _time.sleep
        self.usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}

    @property
    def prompt_budget(self) -> int | None:
        if not self.settings.tokens_per_minute:
            return None
        return self.settings.tokens_per_minute - self.settings.max_output_tokens - self.SAFETY_MARGIN_TOKENS

    def _request_kwargs(self, messages: list[dict], tools: list[dict]) -> dict:
        kwargs = dict(model=self.model, messages=messages, tools=tools, tool_choice="auto",
                      temperature=0.1, max_tokens=self.settings.max_output_tokens)
        if self.settings.reasoning_effort and "gpt-oss" in self.model:
            kwargs["extra_body"] = {"reasoning_effort": self.settings.reasoning_effort}
        return kwargs

    def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
        import openai

        from .context import TokenEstimator

        estimate = TokenEstimator.messages(messages, tools) + self.settings.max_output_tokens
        for attempt in range(self.settings.rate_limit_retries + 1):
            waited = self._limiter.acquire(estimate)
            if waited > 1:
                logger.info("waited %.0fs to stay under %s's tokens-per-minute limit", waited, self.provider)
            try:
                resp = self._client.chat.completions.create(**self._request_kwargs(messages, tools))
                break
            except openai.RateLimitError as exc:
                hinted = self._retry_after(exc, cap=False)
                if hinted > self.MAX_RETRY_WAIT_SECONDS or "per day" in str(exc).lower():
                    raise LLMQuotaExhausted(
                        f"{self.provider}/{self.model} quota exhausted (retry in ~{hinted / 60:.0f} min)") from exc
                if attempt == self.settings.rate_limit_retries:
                    raise LLMUnavailable(f"{self.provider} rate limit persisted: {exc}") from exc
                wait = self._retry_after(exc)
                logger.warning("%s rate limited; retrying in %.0fs", self.provider, wait)
                self._sleep(wait)
            except openai.APIError as exc:
                raise LLMUnavailable(f"{self.provider} API error: {exc}") from exc
        usage = getattr(resp, "usage", None)
        self.usage["calls"] += 1
        if usage and getattr(usage, "total_tokens", None):
            self._limiter.adjust_last(int(usage.total_tokens))
            self.usage["prompt_tokens"] += int(getattr(usage, "prompt_tokens", 0) or 0)
            self.usage["completion_tokens"] += int(getattr(usage, "completion_tokens", 0) or 0)
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

    def _retry_after(self, exc, cap: bool = True) -> float:
        """Server's wait hint: Retry-After header, or text like 'try again in 7.5s' / '18m36.2s' / '120ms'."""
        headers = getattr(getattr(exc, "response", None), "headers", {}) or {}
        hint = headers.get("retry-after")
        if not hint:
            m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m(?!s))?([\d.]+)?\s*(ms|s)?", str(exc))
            if m and any(m.groups()[:3]):
                h, mins, secs, unit = m.groups()
                seconds = float(secs or 0) / (1000 if unit == "ms" else 1)
                hint = int(h or 0) * 3600 + int(mins or 0) * 60 + seconds
        try:
            wait = max(float(hint), 1.0)
        except (TypeError, ValueError):
            wait = 10.0
        return min(wait, self.MAX_RETRY_WAIT_SECONDS) if cap else wait


class FallbackChatClient:
    """
    Tries models in order. When one runs out of quota (e.g. a free-tier daily cap), it switches
    to the next for the rest of the task. Each model on Groq has its own quota.
    """

    def __init__(self, clients: list, on_switch: Callable[[str, str, str], None] | None = None):
        if not clients:
            raise LLMUnavailable("no LLM models configured")
        self._clients = list(clients)
        self._i = 0
        self.on_switch = on_switch

    @property
    def current(self):
        return self._clients[self._i]

    @property
    def provider(self) -> str:
        return self.current.provider

    @property
    def model(self) -> str:
        return self.current.model

    @property
    def prompt_budget(self) -> int | None:
        return self.current.prompt_budget

    @property
    def usage(self) -> dict:
        total = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
        for c in self._clients:
            for k in total:
                total[k] += getattr(c, "usage", {}).get(k, 0)
        total["models"] = [c.model for c in self._clients[: self._i + 1]]
        return total

    def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
        while True:
            try:
                return self.current.complete(messages, tools)
            except LLMQuotaExhausted as exc:
                if self._i + 1 >= len(self._clients):
                    raise
                old = self.current.model
                self._i += 1
                logger.warning("%s; switching to %s", exc, self.current.model)
                if self.on_switch:
                    self.on_switch(old, self.current.model, str(exc))


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
    prompt_budget = None

    def __init__(self, steps: list[ScriptStep], name: str = "recording"):
        self.usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
        self.steps = list(steps)
        self.model = f"scripted:{name}"
        self._i = 0

    def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
        if self._i >= len(self.steps):
            return AssistantTurn(content="(recording finished)", tool_calls=[])
        thought, name, args = self.steps[self._i]
        self._i += 1
        self.usage["calls"] += 1
        if callable(args):
            last_tool = next((m["content"] for m in reversed(messages) if m.get("role") == "tool"), "")
            args = args(last_tool)
        return AssistantTurn(content=thought, tool_calls=[ToolCall(name=name, arguments=args)])


def build_live_client(provider: str | None = None,
                      on_switch: Callable[[str, str, str], None] | None = None) -> FallbackChatClient:
    """Primary model plus configured fallback models of the same provider (each has its own quota)."""
    from django.conf import settings

    provider = provider or settings.LLM["PROVIDER"]
    cfg = settings.LLM["PROVIDERS"].get(provider)
    if not cfg:
        raise LLMUnavailable(f"unknown LLM provider '{provider}' (use groq or nvidia)")
    models = [cfg["MODEL"], *[m for m in cfg.get("FALLBACK_MODELS", []) if m and m != cfg["MODEL"]]]
    clients = [
        OpenAICompatClient(LLMSettings(
            provider=provider, base_url=cfg["BASE_URL"], api_key=cfg["API_KEY"], model=model,
            timeout=settings.LLM["TIMEOUT_SECONDS"], tokens_per_minute=cfg["TOKENS_PER_MINUTE"],
            max_output_tokens=settings.LLM["MAX_OUTPUT_TOKENS"],
            reasoning_effort=settings.LLM["REASONING_EFFORT"] or None,
        ))
        for model in models
    ]
    return FallbackChatClient(clients, on_switch=on_switch)
