"""Ticket #31: the model can only ADD one line to memory. An earlier entry can never be lost, and a write is atomic."""
import os

import pytest

from agent import memory, settings
from agent.settings import Settings

ROW = "| 2026-10-31 | Data types | Arabic | plan.docx | none yet |"


@pytest.fixture(autouse=True)
def memory_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_DIR", tmp_path / "memory")
    return tmp_path / "memory"


def test_a_write_without_reading_can_no_longer_destroy_earlier_notes(memory_dir):
    """The scenario that lost 2 of 3 notes before: a model that forgot to read the file first."""
    for note in ("K11 mixed-level class", "K11 plan: week 3 functions", "worksheet split A/B/C"):
        memory.add("class-notes.md", note)
    memory.add("class-notes.md", "prefers short warm-ups")              # written "blind", never read the file
    text = (memory_dir / "class-notes.md").read_text()
    for kept in ("K11 mixed-level class", "week 3 functions", "worksheet split A/B/C", "prefers short warm-ups"):
        assert kept in text


def test_many_additions_keep_every_line_in_order():
    for i in range(25):
        memory.add("teacher-preferences.md", f"preference number {i}")
    lines = [l for l in memory.read("teacher-preferences.md").splitlines() if l.startswith("- ")]
    assert lines == [f"- preference number {i}" for i in range(25)]


def test_the_same_line_is_not_added_twice():
    assert memory.add("teacher-preferences.md", "shorter warm-ups") == "Added to teacher-preferences.md."
    assert "Already remembered" in memory.add("teacher-preferences.md", "shorter warm-ups")
    assert "Already remembered" in memory.add("teacher-preferences.md", "  - shorter   warm-ups ")      # same fact, other spacing
    assert memory.read("teacher-preferences.md").count("shorter warm-ups") == 1


def test_an_entry_is_one_clean_line():
    memory.add("class-notes.md", "line one\nline two\n\n   spaced   out")
    text = memory.read("class-notes.md")
    assert "- line one line two spaced out" in text and text.count("\n- ") + text.startswith("- ") == 1


def test_an_old_placeholder_line_is_dropped_on_the_first_real_entry(memory_dir):
    memory_dir.mkdir()
    (memory_dir / "teacher-preferences.md").write_text("# Teacher preferences\n\n(Empty. The agent adds preferences here.)\n")
    memory.add("teacher-preferences.md", "prefers Arabic")
    text = (memory_dir / "teacher-preferences.md").read_text()
    assert "(Empty" not in text and "- prefers Arabic" in text and text.startswith("# Teacher preferences")


def test_existing_content_and_headers_are_preserved_exactly(memory_dir):
    memory_dir.mkdir()
    original = "# Class notes\n\n- K11 mixed-level class\n- week 3: basic functions\n"
    (memory_dir / "class-notes.md").write_text(original)
    memory.add("class-notes.md", "new observation")
    assert (memory_dir / "class-notes.md").read_text() == original + "- new observation\n"


def test_the_lesson_log_takes_only_a_table_row_and_keeps_its_header():
    memory.add("lesson-log.md", ROW)
    text = memory.read("lesson-log.md")
    assert text.startswith("# Lesson log") and "| Date | Topic |" in text and ROW in text
    for bad in ("just a sentence", "| only | two |", "- a bullet"):
        with pytest.raises(ValueError, match="table row"):
            memory.add("lesson-log.md", bad)


def test_empty_and_oversized_entries_are_refused_with_advice_the_model_can_follow():
    with pytest.raises(ValueError, match="empty"):
        memory.add("class-notes.md", "   \n ")
    settings.use(Settings(memory_entry_chars=20))
    with pytest.raises(ValueError, match="maximum is 20"):
        memory.add("class-notes.md", "x" * 21)
    memory.add("class-notes.md", "x" * 20)                                   # exactly at the limit is fine


@pytest.mark.parametrize("name", ["secrets.md", "INDEX.md", "../class-notes.md.bak", "", "class-notes"])
def test_only_the_three_memory_files_can_be_used(name):
    with pytest.raises(ValueError):
        memory.add(name, "x")


def test_a_path_cannot_leave_the_memory_folder(tmp_path):
    memory.add("../../outside/class-notes.md", "x")                          # reduced to its file name, stays inside
    assert not (tmp_path / "outside").exists() and (memory.MEMORY_DIR / "class-notes.md").exists()


# --- atomic ----------------------------------------------------------------------------------------
def test_a_crash_during_the_write_leaves_the_old_file_untouched_and_no_debris(memory_dir, monkeypatch):
    memory.add("class-notes.md", "important note")
    before = (memory_dir / "class-notes.md").read_text()

    def crash(src, dst):
        raise OSError("disk went away")

    monkeypatch.setattr(os, "replace", crash)
    with pytest.raises(OSError):
        memory.add("class-notes.md", "a second note")
    assert (memory_dir / "class-notes.md").read_text() == before
    assert not list(memory_dir.glob("*.tmp")) and not list(memory_dir.glob(".*.tmp"))


# --- the explicit, human-only rewrite ----------------------------------------------------------------
def test_rewrite_replaces_a_file_but_keeps_the_previous_version(memory_dir):
    memory.add("class-notes.md", "old note")
    memory.rewrite("class-notes.md", "# Class notes\n\n- edited by the teacher")
    assert "edited by the teacher" in (memory_dir / "class-notes.md").read_text()
    assert "old note" in (memory_dir / "class-notes.md.previous").read_text()


def test_the_model_is_never_offered_a_way_to_rewrite():
    from agent.tools import TOOLS

    names = [t["name"] for t in TOOLS]
    assert "add_memory" in names and not [n for n in names if n in ("write_memory", "rewrite_memory", "replace_memory")]


def test_reading_a_file_that_does_not_exist_yet_says_empty():
    assert memory.read("lesson-log.md") == "(empty)"


# --- ticket #33: a fresh data folder works from the first run ----------------------------------------
def test_a_fresh_folder_gets_the_three_files_and_the_index(memory_dir):
    memory.ensure_files()
    assert sorted(p.name for p in memory_dir.iterdir()) == ["INDEX.md", "class-notes.md", "lesson-log.md", "teacher-preferences.md"]
    index = (memory_dir / "INDEX.md").read_text()
    assert all(name in index for name in ("teacher-preferences.md", "class-notes.md", "lesson-log.md"))
    assert (memory_dir / "lesson-log.md").read_text().startswith("# Lesson log") and "| Date |" in (memory_dir / "lesson-log.md").read_text()


def test_existing_files_are_never_overwritten_by_ensure(memory_dir):
    memory_dir.mkdir()
    (memory_dir / "class-notes.md").write_text("# Class notes\n\n- my real notes\n")
    (memory_dir / "INDEX.md").write_text("# My own index\n")
    memory.ensure_files()
    memory.ensure_files()
    assert (memory_dir / "class-notes.md").read_text() == "# Class notes\n\n- my real notes\n"
    assert (memory_dir / "INDEX.md").read_text() == "# My own index\n"


def test_an_unwritable_memory_folder_does_not_stop_the_agent(tmp_path, monkeypatch):
    blocker = tmp_path / "a-file"
    blocker.write_text("x")
    monkeypatch.setattr(memory, "MEMORY_DIR", blocker / "memory")           # cannot be created under a file
    assert "teacher-preferences.md" in memory.index()


def test_the_model_is_told_memory_exists_even_on_a_brand_new_deployment(data_dir):
    """Before: an empty data folder gave the model '(none)'."""
    import agent.__main__ as app

    system = app.build_system()
    block = system.split("# Memory index")[1]
    assert "(none)" not in block.split("Today's date")[0]
    assert all(n in block for n in ("teacher-preferences.md", "class-notes.md", "lesson-log.md"))
    assert (data_dir / "memory" / "INDEX.md").exists()


def test_a_first_add_after_ensure_keeps_the_header(memory_dir):
    memory.ensure_files()
    memory.add("lesson-log.md", ROW)
    text = (memory_dir / "lesson-log.md").read_text()
    assert text.startswith("# Lesson log") and text.rstrip().endswith(ROW)


# --- ticket #32: what the agent remembers is in front of the model before it plans -----------------
def test_preferences_and_class_notes_are_shown_but_not_the_lesson_log():
    memory.add("teacher-preferences.md", "always a 5-minute warm-up")
    memory.add("class-notes.md", "K11 is mixed level")
    memory.add("lesson-log.md", ROW)
    shown = memory.context()
    assert "## Teacher preferences" in shown and "- always a 5-minute warm-up" in shown
    assert "## Class notes" in shown and "- K11 is mixed level" in shown
    assert "Data types" not in shown and "lesson-log" not in shown          # the log only grows; it stays out of the prompt


def test_nothing_remembered_yet_is_said_plainly_without_headers_or_placeholders(memory_dir):
    memory.ensure_files()
    assert memory.context() == "(nothing remembered yet)"
    (memory_dir / "teacher-preferences.md").write_text("# Teacher preferences\n\n(Empty. The agent adds preferences here.)\n")
    assert memory.context() == "(nothing remembered yet)"


def test_a_long_file_is_capped_and_the_newest_lines_survive():
    settings.use(Settings(memory_context_chars=200, memory_entry_chars=600))
    for i in range(40):
        memory.add("teacher-preferences.md", f"preference number {i:02d}")
    shown = memory.context()
    assert "preference number 39" in shown and "preference number 00" not in shown      # the latest correction wins
    assert "Older entries not shown" in shown and "read_memory" in shown
    assert len(shown) < 200 + 150                                                       # cap plus the one-line note


def test_the_cap_applies_to_each_file_separately():
    settings.use(Settings(memory_context_chars=100))
    for i in range(10):
        memory.add("teacher-preferences.md", f"preference number {i}")
        memory.add("class-notes.md", f"class note number {i}")
    shown = memory.context()
    assert "preference number 9" in shown and "class note number 9" in shown


def test_one_line_longer_than_the_cap_is_still_shown_not_dropped():
    settings.use(Settings(memory_context_chars=10, memory_entry_chars=600))
    memory.add("teacher-preferences.md", "a preference that is longer than the tiny cap")
    assert "longer than the tiny cap" in memory.context()


def test_the_model_gets_the_memory_before_its_first_call(data_dir, monkeypatch):
    """The point of #32: not left to the model's initiative. The first model call already carries the preferences."""
    import agent.__main__ as app
    from tests.helpers import FakeProvider, ScriptedChannel, call, docx_call, reply

    for k in ("SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    memory.add("teacher-preferences.md", "always a 5-minute warm-up")
    provider = FakeProvider([reply("", docx_call()), reply("done"),
                             reply("", call("ask_user", question="Save?", options=["Yes", "No"])), reply("bye")])
    app.run_session(provider, Settings(max_turns=10), "Prepare a lesson. Topic: X", "ctx", ScriptedChannel(["back", 1]))
    first_system = provider.calls[0]["system"]
    assert "What you remember about this teacher" in first_system and "- always a 5-minute warm-up" in first_system


def test_memory_added_in_one_session_is_there_for_the_next(data_dir):
    import agent.__main__ as app

    assert "(nothing remembered yet)" in app.build_system()
    memory.add("class-notes.md", "support students need worked examples")
    assert "- support students need worked examples" in app.build_system()
