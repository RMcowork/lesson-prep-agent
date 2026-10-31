from types import SimpleNamespace

from agent.llm import AnthropicProvider, OpenAICompatProvider, make_provider
from agent.settings import Settings
from agent.usage import Meter
import pytest


def test_meter_starts_empty_and_ignores_missing_numbers():
    m = Meter()
    m.add({}); m.add({"input": None, "output": 5})
    assert m.as_dict() == {"calls": 2, "input_tokens": 0, "output_tokens": 5}


def test_anthropic_reply_carries_token_usage():
    block_text = SimpleNamespace(type="text", text="hi")
    block_tool = SimpleNamespace(type="tool_use", id="t1", name="create_docx", input={"filename": "a"})
    resp = SimpleNamespace(content=[block_text, block_tool], usage=SimpleNamespace(input_tokens=1234, output_tokens=56))
    p = AnthropicProvider.__new__(AnthropicProvider)
    p.model, p.max_tokens, p.effort = "m", 10, ""
    p.client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: resp))
    r = p.complete("sys", [{"role": "user", "content": [{"type": "text", "text": "x"}]}], [{"name": "n", "description": "d", "parameters": {}}])
    assert r.usage == {"input": 1234, "output": 56} and r.text == "hi" and r.tool_calls[0]["name"] == "create_docx"


def test_openai_reply_carries_token_usage_and_tolerates_bad_arguments():
    call = SimpleNamespace(id="c1", function=SimpleNamespace(name="t", arguments="{not json"))
    resp = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[call]))],
                           usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3))
    p = OpenAICompatProvider.__new__(OpenAICompatProvider)
    p.model, p.max_tokens = "m", 10
    p.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: resp)))
    r = p.complete("sys", [{"role": "user", "content": [{"type": "text", "text": "x"}]}], [])
    assert r.usage == {"input": 7, "output": 3} and r.tool_calls[0]["input"] == {}


def test_openai_message_conversion_keeps_tool_results():
    msgs = [
        {"role": "user", "content": [{"type": "text", "text": "go"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "ok"}, {"type": "tool_use", "id": "1", "name": "t", "input": {"a": 1}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "1", "content": "done", "is_error": False}]},
    ]
    out = OpenAICompatProvider._convert("SYS", msgs)
    assert [m["role"] for m in out] == ["system", "user", "assistant", "tool"]
    assert out[2]["tool_calls"][0]["function"]["arguments"] == '{"a": 1}' and out[3]["tool_call_id"] == "1"


def test_unknown_provider_stops_with_a_clear_message():
    with pytest.raises(SystemExit):
        make_provider(Settings(provider="nope"))


def test_missing_api_key_stops_with_a_clear_message(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        AnthropicProvider("m", 10)


# --- ticket #39: effort ---------------------------------------------------------------------------
def anthropic_call_args(effort):
    seen = {}
    resp = SimpleNamespace(content=[SimpleNamespace(type="text", text="hi")], usage=SimpleNamespace(input_tokens=1, output_tokens=1))
    p = AnthropicProvider.__new__(AnthropicProvider)
    p.model, p.max_tokens, p.effort = "m", 10, effort
    p.client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: (seen.update(kw), resp)[1]))
    p.complete("sys", [{"role": "user", "content": [{"type": "text", "text": "x"}]}], [])
    return seen


def test_effort_is_sent_to_claude():
    assert anthropic_call_args("high")["output_config"] == {"effort": "high"}
    assert anthropic_call_args("low")["output_config"] == {"effort": "low"}


def test_an_empty_effort_leaves_the_model_default_alone():
    assert "output_config" not in anthropic_call_args("")


def test_effort_comes_from_the_settings_through_make_provider(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    assert make_provider(Settings(effort="medium")).effort == "medium"
    assert make_provider(Settings()).effort == "high"                                  # explicit default, not the model's


def test_the_openai_provider_accepts_and_ignores_effort(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    p = make_provider(Settings(provider="openai", model="local", effort="max"))
    assert not hasattr(p, "effort")
