"""The live (Groq / NVIDIA) client: tool-call parsing and error handling, without network."""
from types import SimpleNamespace

import httpx
import openai
import pytest

from agent.coding.llm import LLMUnavailable, OpenAICompatClient


def _response(tool_calls=None, content=""):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def _call(name, arguments, cid="call_1"):
    return SimpleNamespace(id=cid, function=SimpleNamespace(name=name, arguments=arguments))


@pytest.fixture
def client(monkeypatch):
    c = OpenAICompatClient("groq", "https://api.groq.com/openai/v1", "gsk_test_key_not_real_123456", "llama-test")
    sent = {}

    def fake_create(**kwargs):
        sent.update(kwargs)
        return fake_create.reply

    monkeypatch.setattr(c._client.chat.completions, "create", fake_create)
    return c, fake_create, sent


def test_parses_native_tool_calls(client):
    c, create, sent = client
    create.reply = _response([_call("read_file", '{"path": "analytics/views.py"}')], content="look first")
    turn = c.complete([{"role": "user", "content": "hi"}], tools=[{"type": "function"}])
    assert turn.content == "look first"
    assert (turn.tool_calls[0].name, turn.tool_calls[0].arguments, turn.tool_calls[0].id) == \
        ("read_file", {"path": "analytics/views.py"}, "call_1")
    assert sent["model"] == "llama-test" and sent["tool_choice"] == "auto" and sent["temperature"] <= 0.2


def test_invalid_json_arguments_are_flagged_not_crashing(client):
    c, create, _ = client
    create.reply = _response([_call("edit_file", "{not json")])
    turn = c.complete([], tools=[])
    assert "_invalid_json" in turn.tool_calls[0].arguments


def test_tool_call_written_as_text_is_recovered(client):
    c, create, _ = client
    create.reply = _response(None, content='I will call {"name": "run_tests", "arguments": {}}')
    assert c.complete([], tools=[]).tool_calls[0].name == "run_tests"


def test_api_errors_become_llm_unavailable(client):
    c, create, _ = client

    def boom(**kwargs):
        raise openai.APIConnectionError(request=httpx.Request("POST", "https://api.groq.com"))

    c._client.chat.completions.create = boom
    with pytest.raises(LLMUnavailable):
        c.complete([], tools=[])


def test_missing_key_is_reported_before_any_call():
    with pytest.raises(LLMUnavailable, match="no API key"):
        OpenAICompatClient("nvidia", "https://integrate.api.nvidia.com/v1", "", "m")
