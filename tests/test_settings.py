"""Ticket #38: every tunable value has one home (config/agent.toml), is checked at start, is documented in
config/README.md, and really changes behaviour. Tests fail if the file, the class and the document drift apart."""
import queue
import re
import tomllib

import pytest

from agent import settings
from agent.settings import FIELD_NAMES, Settings
from tests.conftest import ROOT


def write(tmp_path, text):
    p = tmp_path / "agent.toml"
    p.write_text(text)
    return p


# --- one home, checked at start -------------------------------------------------------------------
def test_the_real_config_file_loads_and_lists_every_setting():
    raw = tomllib.loads((ROOT / "config" / "agent.toml").read_text())
    assert set(raw) == set(FIELD_NAMES), f"agent.toml and Settings differ: {set(raw) ^ set(FIELD_NAMES)}"
    assert isinstance(settings.load(), Settings)


def test_a_missing_or_partial_file_falls_back_to_the_defaults(tmp_path):
    assert settings.load(tmp_path / "nope.toml") == Settings()
    s = settings.load(write(tmp_path, 'model = "x-model"\nmax_turns = 7\n'))
    assert s.model == "x-model" and s.max_turns == 7 and s.max_tokens == Settings().max_tokens


def test_an_unknown_key_stops_the_program_and_names_the_key(tmp_path):
    with pytest.raises(SystemExit, match="max_turnz"):
        settings.load(write(tmp_path, "max_turnz = 5\n"))


@pytest.mark.parametrize("text,words", [
    ('max_turns = "forty"', "max_turns must be int"),
    ("max_turns = true", "max_turns must be int"),
    ("max_turns = 0", "at least 1"),
    ("web_results = -3", "at least 1"),
    ('provider = "gemini"', "provider must be one of"),
    ('model = ""', "model must not be empty"),
    ("chunk_words = 50\noverlap_words = 50", "overlap_words must be smaller"),
    ("embed_threads = -1", "embed_threads must be"),
    ("eval_pass_drop_allowed = 2", "between 0 and 1"),
    ("eval_token_rise_allowed = 'lots'", "eval_token_rise_allowed must be float"),
])
def test_invalid_values_are_refused_with_a_clear_message(tmp_path, text, words):
    with pytest.raises(SystemExit, match=words):
        settings.load(write(tmp_path, text + "\n"))


def test_integers_are_accepted_where_a_float_is_expected(tmp_path):
    assert settings.load(write(tmp_path, "eval_pass_drop_allowed = 1\n")).eval_pass_drop_allowed == 1


def test_the_rag_threads_variable_overrides_the_file(tmp_path):
    p = write(tmp_path, "embed_threads = 2\n")
    assert settings.load(p, env={"RAG_THREADS": "6"}).embed_threads == 6
    assert settings.load(p, env={}).embed_threads == 2
    with pytest.raises(SystemExit, match="RAG_THREADS"):
        settings.load(p, env={"RAG_THREADS": "many"})


# --- documented ------------------------------------------------------------------------------------
def documented_keys():
    text = (ROOT / "config" / "README.md").read_text().split("## Settings in `agent.toml`")[1].split("## Variables")[0]
    return re.findall(r"^\| `(\w+)` \|", text, flags=re.M)


def test_every_setting_is_documented_exactly_once_in_config_readme():
    keys = documented_keys()
    assert sorted(keys) == sorted(FIELD_NAMES), f"README and Settings differ: {set(keys) ^ set(FIELD_NAMES)}"


def test_the_readme_defaults_are_the_real_defaults():
    rows = re.findall(r"^\| `(\w+)` \| (`[^`]*`|empty) \|", (ROOT / "config" / "README.md").read_text(), flags=re.M)
    for key, shown in rows:
        if key not in FIELD_NAMES:
            continue
        default = getattr(Settings(), key)
        assert shown == ("empty" if default == "" else f"`{default}`"), f"{key}: README says {shown}, code says {default!r}"


def test_no_known_tunable_is_hard_coded_again():
    gone = ["MAX_WEB_CHARS", "MAX_TOTAL_BYTES", "MAX_TEXT", "BUTTON_TEXT", "CHUNK_WORDS", "OVERLAP_WORDS", "BATCH_SIZE",
            "MODEL_NAME", "PASS_DROP_ALLOWED", "TOKEN_RISE_ALLOWED", "MAX_TURNS"]
    for path in [*(ROOT / "agent").glob("*.py"), *(ROOT / "rag").glob("*.py"), *(ROOT / "evals").glob("*.py")]:
        for name in gone:
            assert not re.search(rf"^{name}\s*=", path.read_text(), flags=re.M), f"{path.name} defines {name} again"


# --- each setting really changes behaviour -----------------------------------------------------------
def test_web_settings_reach_the_search_and_fetch_tools(tmp_path, monkeypatch):
    import ddgs
    import httpx

    from agent.channel import TerminalChannel
    from agent.tools import ToolRunner

    seen = {}

    class FakeDDGS:
        def __init__(self, timeout=None): seen["timeout"] = timeout
        def text(self, query, max_results, backend): seen["max"] = max_results; return [{"title": "T", "href": "h", "body": "b"}]

    monkeypatch.setattr(ddgs, "DDGS", FakeDDGS)
    settings.use(Settings(web_results=2, web_search_timeout_s=3, web_fetch_chars=40, web_fetch_timeout_s=9))
    runner = ToolRunner(tmp_path, TerminalChannel(ask=lambda p="": ""))
    runner.run("web_search", {"query": "q"})
    assert seen == {"timeout": 3, "max": 2}

    import socket

    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", ("93.184.216.34", 0))])
    got = {}

    class Resp: text = "<p>" + "word " * 100 + "</p>"

    monkeypatch.setattr(httpx, "get", lambda url, **kw: (got.update(kw), Resp())[1])
    out = runner.run("fetch_url", {"url": "https://example.com"})
    assert got["timeout"] == 9 and len(out.split("\n", 1)[1]) == 40


def test_email_size_cap_comes_from_the_settings():
    from agent import emailer

    settings.use(Settings(email_max_mb=3))
    assert emailer.max_total_bytes() == 3 * 1024 * 1024


def test_telegram_limits_come_from_the_settings():
    from agent.telegram_bot import Bot, TelegramChannel, _label, _split

    settings.use(Settings(message_chars=100, button_chars=10, session_timeout_s=5))
    parts = list(_split("x" * 250))
    assert all(len(p) <= 100 for p in parts) and "".join(parts) == "x" * 250
    assert len(_label("y" * 50)) == 10
    assert TelegramChannel(object(), 1, queue.Queue()).timeout == 5 and Bot(object(), lambda c: None, [1]).timeout == 5
    assert TelegramChannel(object(), 1, queue.Queue(), timeout=9).timeout == 9      # an explicit value still wins


def test_search_index_settings_come_from_the_settings():
    from rag import core

    settings.use(Settings(chunk_words=10, overlap_words=2, embed_threads=3))
    chunks = list(core.chunk(" ".join(f"w{i}" for i in range(30))))
    assert all(len(c.split()) <= 10 for c in chunks) and chunks[0].split()[-2:] == chunks[1].split()[:2]
    assert core._threads() == 3
    settings.use(Settings(embed_threads=0))
    assert core._threads() >= 2


def test_max_turns_limits_one_turn_of_work(data_dir, monkeypatch):
    import agent.__main__ as app
    from tests.helpers import FakeProvider, ScriptedChannel, docx_call, reply

    for k in ("SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    provider = FakeProvider([reply("", docx_call(filename=f"f{i}")) for i in range(10)])    # a model that never stops
    ch = ScriptedChannel(["back"])                                                           # the teacher finishes at once
    app.run_session(provider, Settings(max_turns=2), "Prepare a lesson. Topic: X", "limit", ch)
    # two turns of work (the task, then the final step), each cut off after max_turns model calls
    assert len(provider.calls) == 4
    assert sum("maximum number of steps" in t for t in ch.said) == 2


def test_the_eval_thresholds_come_from_the_settings():
    from evals import grader, run

    settings.use(Settings(eval_max_turns=3, eval_pass_drop_allowed=0.5, eval_token_rise_allowed=2.0))
    assert grader.max_turns() == 3
    base = {"pass_rate": "0.9", "tokens_in": "100"}
    assert run.compare({"pass_rate": 0.5, "tokens_in": 250}, base)[0]            # within the looser limits
    assert not run.compare({"pass_rate": 0.3, "tokens_in": 250}, base)[0]


@pytest.mark.parametrize("value", ["", "low", "medium", "high", "xhigh", "max"])
def test_every_documented_effort_level_is_accepted(tmp_path, value):
    assert settings.load(write(tmp_path, f'effort = "{value}"\n')).effort == value


@pytest.mark.parametrize("value", ["HIGH", "extreme", "none", "5"])
def test_an_unknown_effort_is_refused_naming_the_valid_ones(tmp_path, value):
    with pytest.raises(SystemExit, match="effort must be one of"):
        settings.load(write(tmp_path, f'effort = "{value}"\n'))


def test_the_default_effort_is_explicitly_high():
    assert Settings().effort == "high" and tomllib.loads((ROOT / "config" / "agent.toml").read_text())["effort"] == "high"
