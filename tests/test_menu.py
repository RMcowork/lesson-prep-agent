"""spec.md check 2: every wizard step has Back. Plus numbered input, topics and notes in the wizards."""
import pytest

from agent import menu
from agent.topics import TopicStore
from tests.helpers import ScriptedChannel

OUTLINE = """| Unit | Topic | Objectives | Lessons |
|---|---|---|---|
| 1 | Data life cycle | Name the stages | 2 |
| 2 | Data types | Pick the right type | 2 |
"""


@pytest.fixture
def store(tmp_path):
    (tmp_path / "outline.md").write_text(OUTLINE)
    return TopicStore(outline_path=tmp_path / "outline.md", data_dir=tmp_path)


# --- numbered input -------------------------------------------------------------------------------
def answers(*given):
    it = iter(given)
    return lambda prompt="": next(it)


def test_choose_accepts_a_number_and_rejects_bad_input():
    kind, i = menu.choose("t", ["a", "b", "c"], ask=answers("9", "x", "2"))
    assert (kind, i) == ("option", 1)


def test_choose_back_and_arabic_indic_digits():
    assert menu.choose("t", ["a", "b"], ask=answers("0"), back="Back") == ("back", None)
    assert menu.choose("t", ["a", "b"], ask=answers("٢")) == ("option", 1)


def test_choose_other_returns_typed_text():
    kind, text = menu.choose("t", ["a"], ask=answers("2", "my own"), other="Other")
    assert (kind, text) == ("other", "my own")


def test_choose_many_defaults_toggle_and_invalid():
    opts = ["a", "b", "c"]
    assert menu.choose_many("t", opts, {0, 1}, ask=answers("")) == ("option", [0, 1])
    assert menu.choose_many("t", opts, {0}, ask=answers("2, 3")) == ("option", [1, 2])
    assert menu.choose_many("t", opts, {0}, ask=answers("9", "1")) == ("option", [0])
    assert menu.choose_many("t", opts, {0}, ask=answers("0")) == ("back", None)


# --- wizards ----------------------------------------------------------------------------------------
LESSON = [1, 1, 0, 0, 0, None, 0, 0, 0]   # topic, minutes, language, grade, level, outputs, web, notes, start
EXAM = [1, 1, 0, 0, None, 0, 0, 0]        # topic, kind, language, grade, question types, web, notes, start


def test_lesson_wizard_builds_the_request(store):
    ch = ScriptedChannel(LESSON)
    task, name, opts = menu.lesson_wizard(store, ch)
    assert "Data types" in task and "Arabic" in task and "45 minutes" in task and "K10" in task
    assert "Pick the right type" in task            # objectives from the course outline reach the agent
    assert "do not ask for them again" in task
    assert name == "Data types" and opts == {"allow_web": False}
    assert "Web search is turned off" in task


def test_web_choice_yes_allows_search(store):
    answers_ = LESSON[:6] + [1] + LESSON[7:]
    _, _, opts = menu.lesson_wizard(store, ScriptedChannel(answers_))
    assert opts == {"allow_web": True}


def test_teacher_instructions_reach_the_agent(store):
    answers_ = LESSON[:7] + [("other", "use football examples; max 5 questions")] + [0]
    task, _, _ = menu.lesson_wizard(store, ScriptedChannel(answers_))
    assert "use football examples; max 5 questions" in task and "follow them exactly" in task


def test_exam_wizard_builds_the_request(store):
    task, name, opts = menu.exam_wizard(store, ScriptedChannel(EXAM))
    assert "assessment" in task and "Data types" in task and name == "exam-Data types"


@pytest.mark.parametrize("wizard,forward", [("lesson_wizard", LESSON), ("exam_wizard", EXAM)])
def test_back_works_at_every_step(store, wizard, forward):
    run = getattr(menu, wizard)
    # Back on the first step leaves the wizard
    assert run(store, ScriptedChannel(["back"])) is None
    # Going forward d steps, then Back, repeats the previous question, at every depth
    for d in range(1, len(forward)):
        ch = ScriptedChannel(forward[:d] + ["back"] + forward[d - 1:])
        assert run(store, ch) is not None
        assert ch.titles[d + 1] == ch.titles[d - 1], f"Back at step {d + 1} did not return to step {d}"


def test_new_topic_is_saved_and_listed_next_time(store):
    new = [("other", "Conditional formatting"), "Highlight cells, color scales", 0]   # name, outline, save: yes
    task, name, _ = menu.lesson_wizard(store, ScriptedChannel(new + LESSON[1:]))
    assert name == "Conditional formatting" and "Highlight cells" in task
    assert "Conditional formatting" in store.names()
    ch = ScriptedChannel(LESSON)
    menu.lesson_wizard(store, ch)                                  # next time it is in the topic list
    assert "Conditional formatting" in TopicStore(store.outline_path, store.path.parent).names()


def test_new_topic_can_be_used_once_without_saving(store):
    new = [("other", "One-off topic"), "-", 1]                      # save: no
    menu.lesson_wizard(store, ScriptedChannel(new + LESSON[1:]))
    assert "One-off topic" not in store.names()


def test_manage_topics_add_list_remove(store):
    # Add a topic (name, outline skipped) -> Show all topics -> Remove it (pick the first) -> Back
    ch = ScriptedChannel([0, "My topic", "-", 2, 1, 0, "back"])
    menu.manage_topics(ch, store)
    said = "\n".join(ch.said)
    assert "Added: My topic" in said
    assert "- My topic (mine)" in said and "- Data types" in said     # listing marks the teacher's own topics
    assert "Removed: My topic" in said
    assert store.custom_names() == [] and store.names() == ["Data life cycle", "Data types"]


def test_manage_topics_remove_with_none_saved(store):
    ch = ScriptedChannel([1, "back"])
    menu.manage_topics(ch, store)
    assert any("not added any topics" in t for t in ch.said)
