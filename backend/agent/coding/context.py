"""
Keeping the conversation small enough for the model.

Every request re-sends the whole conversation, and free LLM tiers cap tokens per
minute (Groq free: 8,000). ContextWindow sends the model a *compacted copy*:

  * the system prompt and the task are always kept in full;
  * the most recent messages are kept in full (what the agent is working on now);
  * older tool outputs are shortened to a stub ("call the tool again if you need it").

The full, untrimmed conversation is never lost: every tool result is already in the
audit log and on the dashboard.
"""
from __future__ import annotations

import copy
import json


class TokenEstimator:
    """Cheap, conservative token estimate (no tokenizer dependency): ~3.2 characters per token."""

    CHARS_PER_TOKEN = 3.2

    @classmethod
    def text(cls, text: str) -> int:
        return int(len(text or "") / cls.CHARS_PER_TOKEN) + 1

    @classmethod
    def messages(cls, messages: list[dict], tools: list[dict] | None = None) -> int:
        size = sum(cls.text(json.dumps(m, ensure_ascii=False)) + 4 for m in messages)
        return size + (cls.text(json.dumps(tools)) if tools else 0)


class ContextWindow:
    TRIM_NOTE = "\n… [older output trimmed to save tokens - call the tool again if you need it]"

    def __init__(self, budget_tokens: int | None, keep_recent: int = 4, stub_chars: int = 300,
                 estimator: type[TokenEstimator] = TokenEstimator):
        self.budget = budget_tokens
        self.keep_recent = keep_recent
        self.stub_chars = stub_chars
        self.estimator = estimator

    def fit(self, messages: list[dict], tools: list[dict] | None = None) -> list[dict]:
        """Return a copy of `messages` that fits the budget (the original is not modified)."""
        if not self.budget or self.estimator.messages(messages, tools) <= self.budget:
            return messages
        compact = copy.deepcopy(messages)
        pinned = 2  # system prompt + task
        recent_start = max(pinned, len(compact) - self.keep_recent)

        # Pass 1: shorten old tool outputs and old assistant reasoning, oldest first.
        for msg in compact[pinned:recent_start]:
            self._shorten(msg, self.stub_chars)
            if self.estimator.messages(compact, tools) <= self.budget:
                return compact
        # Pass 2: still too big - shorten recent messages too, but keep more of them.
        for msg in compact[recent_start:-1]:
            self._shorten(msg, 1500)
            if self.estimator.messages(compact, tools) <= self.budget:
                return compact
        # Pass 3: last resort - shrink even the latest output.
        self._shorten(compact[-1], 2500)
        return compact

    def _shorten(self, msg: dict, keep: int) -> None:
        content = msg.get("content") or ""
        if msg.get("role") in ("tool", "assistant") and len(content) > keep:
            msg["content"] = content[:keep] + self.TRIM_NOTE
