"""Staying under free-tier token limits: context compaction, pacing and rate-limit retries."""
from types import SimpleNamespace

import httpx
import openai

from agent.coding.context import ContextWindow, TokenEstimator
from agent.coding.llm import LLMSettings, OpenAICompatClient
from agent.coding.ratelimit import RollingTokenLimiter


def conversation(n_tools=8, size=4000):
    msgs = [{"role": "system", "content": "rules"}, {"role": "user", "content": "task " * 50}]
    for i in range(n_tools):
        msgs.append({"role": "assistant", "content": f"thinking {i}", "tool_calls": [
            {"id": f"c{i}", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": f"output {i} " + "x" * size})
    return msgs


def test_context_window_trims_old_outputs_first_and_keeps_original():
    msgs = conversation()
    before = TokenEstimator.messages(msgs)
    fitted = ContextWindow(budget_tokens=4000).fit(msgs)
    assert TokenEstimator.messages(fitted) <= 4000 < before
    assert fitted[0] == msgs[0] and fitted[1] == msgs[1]                       # system + task intact
    assert fitted[-1]["content"] == msgs[-1]["content"]                       # latest output intact
    assert ContextWindow.TRIM_NOTE in fitted[3]["content"]                   # oldest output trimmed
    assert all(f.get("tool_call_id") == m.get("tool_call_id") for f, m in zip(fitted, msgs))  # pairs preserved
    assert ContextWindow.TRIM_NOTE not in msgs[3]["content"]                 # full history untouched


def test_context_window_noop_when_unlimited_or_small():
    msgs = conversation(1, 10)
    assert ContextWindow(None).fit(msgs) is msgs
    assert ContextWindow(100_000).fit(msgs) is msgs


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def test_limiter_waits_for_the_window_instead_of_failing():
    clock = FakeClock()
    limiter = RollingTokenLimiter(8000, clock=clock, sleep=clock.sleep)
    assert limiter.acquire(5000) == 0
    waited = limiter.acquire(5000)  # would exceed 8000 in the same minute
    assert 59 < waited < 61 and limiter.used() == 5000
    limiter.adjust_last(1200)  # real usage was smaller
    assert limiter.used() == 1200


def test_client_retries_after_rate_limit_using_server_hint():
    waits = []
    client = OpenAICompatClient(LLMSettings("groq", "https://x", "gsk_test_key_not_real_123456", "openai/gpt-oss-120b",
                                            tokens_per_minute=8000), sleep=waits.append)
    calls = {"n": 0}
    sent = {}
    ok = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[]))],
                         usage=SimpleNamespace(total_tokens=900))

    def create(**kwargs):
        sent.update(kwargs)
        calls["n"] += 1
        if calls["n"] == 1:
            resp = httpx.Response(429, request=httpx.Request("POST", "https://x"), headers={"retry-after": "7"})
            raise openai.RateLimitError("Rate limit reached. Please try again in 7s", response=resp, body=None)
        return ok

    client._client.chat.completions.create = create
    client.complete([{"role": "user", "content": "hi"}], tools=[])
    assert calls["n"] == 2 and waits == [7.0]
    assert sent["extra_body"] == {"reasoning_effort": "low"}  # gpt-oss keeps hidden reasoning short
    assert client.prompt_budget == 8000 - 1024 - OpenAICompatClient.SAFETY_MARGIN_TOKENS
