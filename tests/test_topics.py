import json

from agent.topics import TopicStore

OUTLINE = "| Unit | Topic | Objectives | Lessons |\n|---|---|---|---|\n| 1 | Data types | Pick the right type | 2 |\n"


def make(tmp_path):
    (tmp_path / "o.md").write_text(OUTLINE)
    return TopicStore(outline_path=tmp_path / "o.md", data_dir=tmp_path)


def test_units_come_from_the_outline_with_objectives(tmp_path):
    s = make(tmp_path)
    assert s.names() == ["Data types"] and s.outline("Data types") == "Pick the right type"


def test_add_remove_and_duplicates(tmp_path):
    s = make(tmp_path)
    assert s.add("SQL basics", "SELECT, WHERE")
    assert not s.add("sql BASICS")                    # duplicate ignoring case
    assert not s.add("data types")                    # clashes with a course unit
    assert not s.add("   ")
    assert s.names() == ["Data types", "SQL basics"] and s.is_custom("SQL basics")
    assert s.outline("sql basics") == "SELECT, WHERE"
    assert s.remove("SQL basics") and not s.remove("SQL basics")
    assert s.names() == ["Data types"]


def test_saved_topics_survive_a_new_store_object(tmp_path):
    make(tmp_path).add("Pivot tables")
    assert "Pivot tables" in make(tmp_path).names()


def test_a_damaged_topics_file_is_ignored(tmp_path):
    s = make(tmp_path)
    s.path.write_text("{not json")
    assert s.names() == ["Data types"]
    s.path.write_text(json.dumps([{"nope": 1}, {"name": "Ok"}]))
    assert s.custom_names() == ["Ok"]


def test_unicode_names_are_kept(tmp_path):
    s = make(tmp_path)
    s.add("أنواع البيانات", "الرقمية والفئوية")
    assert "أنواع البيانات" in json.loads(s.path.read_text(encoding="utf-8"))[0]["name"]
