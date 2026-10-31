import json

from agent.loop import run_agent
from agent.tools import ToolRunner
from agent.usage import Meter
from tests.helpers import FakeProvider, ScriptedChannel, call, docx_call, reply


def runner(tmp_path):
    ch = ScriptedChannel()
    return ToolRunner(tmp_path, ch), ch


def test_runs_tools_then_stops_when_the_model_answers_in_text(tmp_path):
    r, ch = runner(tmp_path)
    p = FakeProvider([reply("", docx_call()), reply("Done.")])
    msgs = run_agent(p, "sys", "make a plan", r, interactive=False)
    assert (tmp_path / "plan.docx").exists() and ch.said == ["Done."]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[2]["content"][0]["type"] == "tool_result" and not msgs[2]["content"][0]["is_error"]


def test_a_tool_error_is_given_to_the_model_so_it_can_recover(tmp_path):
    r, _ = runner(tmp_path)
    p = FakeProvider([reply("", call("read_memory", name="nope.md")), reply("recovered")])
    msgs = run_agent(p, "sys", "go", r, interactive=False)
    result = msgs[2]["content"][0]
    assert result["is_error"] and result["content"].startswith("Error:")
    assert p.calls[1]["messages"][-1]["content"][0]["is_error"]      # the model saw the error


def test_stops_after_max_turns(tmp_path):
    r, ch = runner(tmp_path)
    p = FakeProvider([reply("", docx_call(filename=f"f{i}")) for i in range(5)])
    run_agent(p, "sys", "go", r, max_turns=3, interactive=False)
    assert len(p.calls) == 3 and "maximum number of steps" in ch.said[-1]


def test_continuing_a_conversation_keeps_roles_alternating(tmp_path):
    r, _ = runner(tmp_path)
    p = FakeProvider([reply("first"), reply("second")])
    msgs = run_agent(p, "sys", "task", r, interactive=False)
    msgs = run_agent(p, "sys", "a change note", r, interactive=False, messages=msgs)
    roles = [m["role"] for m in msgs]
    assert roles == ["user", "assistant", "user", "assistant"]
    assert msgs[2]["content"][0]["text"] == "a change note"
    assert [m["role"] for m in p.calls[1]["messages"]][-1] == "user"   # the model saw the whole history


def test_a_note_after_a_run_that_stopped_mid_way_is_merged_not_duplicated(tmp_path):
    r, _ = runner(tmp_path)
    p = FakeProvider([reply("", docx_call(filename=f"f{i}")) for i in range(2)] + [reply("ok")])
    msgs = run_agent(p, "sys", "go", r, max_turns=2, interactive=False)
    assert msgs[-1]["role"] == "user"                                   # ended on a tool result
    msgs = run_agent(p, "sys", "continue please", r, interactive=False, messages=msgs)
    roles = [m["role"] for m in msgs]
    assert all(roles[i] != roles[i + 1] for i in range(len(roles) - 1))


def test_token_meter_adds_up_every_call(tmp_path):
    r, _ = runner(tmp_path)
    p = FakeProvider([reply("", docx_call(), usage={"input": 1000, "output": 50}), reply("x", usage={"input": 1500, "output": 30})])
    meter = Meter()
    run_agent(p, "sys", "go", r, interactive=False, meter=meter)
    assert meter.as_dict() == {"calls": 2, "input_tokens": 2500, "output_tokens": 80}


def test_the_conversation_is_logged_after_every_step(tmp_path):
    r, _ = runner(tmp_path)
    log = tmp_path / "logs" / "s.json"
    run_agent(FakeProvider([reply("hi")]), "sys", "go", r, interactive=False, log_path=log)
    assert json.loads(log.read_text())[-1]["role"] == "assistant"


def test_plain_text_reply_in_an_interactive_session_asks_what_next(tmp_path):
    ch = ScriptedChannel([1, "my reply", "back"])      # Type a reply -> text -> Finish
    r = ToolRunner(tmp_path, ch)
    p = FakeProvider([reply("a question?"), reply("thanks")])
    msgs = run_agent(p, "sys", "go", r, interactive=True)
    assert msgs[2]["content"][0]["text"] == "my reply" and len(p.calls) == 2
