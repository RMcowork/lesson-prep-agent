"""Ticket #8: the eval harness itself must work. A stand-in model that follows the rules must pass every case, and one
that breaks a single rule must fail the case that guards it. This proves the graders catch failures; it says nothing
about the real model (that is ticket #17)."""
import csv
import tempfile
from pathlib import Path

import pytest
import yaml

from evals import grader, run
from evals.mock_model import MODES, OracleModel

CASES = {c["id"]: c for c in yaml.safe_load(run.CASES.read_text(encoding="utf-8"))}


def outcome(case_id, mode):
    with tempfile.TemporaryDirectory() as tmp:
        return run.run_case(CASES[case_id], OracleModel(mode), tmp)


# --- the cases file ---------------------------------------------------------------------------------
def test_there_are_thirty_well_formed_cases_across_the_groups():
    assert len(CASES) == 30
    assert not [p for c in CASES.values() for p in grader.validate_case(c)]
    groups = {c["group"] for c in CASES.values()}
    assert {"approval", "retrieve", "honest", "web-off", "web-on", "rtl", "revise", "final", "safety", "scope"} <= groups


def test_validation_catches_typos_that_would_silently_weaken_an_eval():
    base = {"id": "x-1", "group": "x", "task": "t", "expect": {"called": ["search_knowledge"]}}
    assert grader.validate_case(base) == []
    assert any("unknown check" in p for p in grader.validate_case({**base, "expect": {"calld": ["a"]}}))
    assert any("unknown tool" in p for p in grader.validate_case({**base, "expect": {"called": ["search_knowlege"]}}))
    assert any("must start with" in p for p in grader.validate_case({**base, "id": "y-1"}))
    assert any("revise case needs" in p for p in grader.validate_case({**base, "phase": "revise"}))
    assert any("missing" in p for p in grader.validate_case({"id": "x-1", "group": "x"}))


# --- the harness proves itself ----------------------------------------------------------------------
@pytest.mark.parametrize("case_id", sorted(CASES))
def test_a_rule_following_model_passes_every_case(case_id):
    r = outcome(case_id, "good")
    assert r["passed"], r["fails"]


BREAKS = [   # (mode, the case that must catch it)
    ("no_search", "retrieve-first-en"),
    ("skip_approval", "approval-basic-en"),
    ("web_always", "web-off-fresh-examples"),
    ("invent_sources", "honest-nothing-found-en"),
    ("ignore_note", "revise-shorter-warmup"),
    ("ltr_only", "rtl-arabic-docx"),
    ("ltr_only", "revise-arabic-keeps-rtl"),
    ("names_in_memory", "final-no-student-names"),
    ("obeys_injection", "safety-injection-in-file"),
]


@pytest.mark.parametrize("mode,case_id", BREAKS)
def test_a_model_that_breaks_one_rule_fails_the_case_that_guards_it(mode, case_id):
    r = outcome(case_id, mode)
    assert not r["passed"] and r["fails"], f"{mode} was not caught by {case_id}"


def test_every_bad_mode_is_caught_by_at_least_one_case():
    assert {m for m, _ in BREAKS} == set(MODES) - {"good"}


# --- the grader on hand-made traces ---------------------------------------------------------------
def trace(*names, said="", files=(), memory="", asks=()):
    t = grader.Trace(said=said, files=list(files), memory=memory, turns=len(names))
    t.calls = [{"name": n, "input": i, "error": False} for n, i in ((x, {}) if isinstance(x, str) else x for x in names)]
    t.asks = list(asks)
    return t


def test_order_and_approval_checks():
    ok = trace("search_knowledge", "ask_user", "create_docx")
    assert grader.grade({"order": [["search_knowledge", "create_docx"]], "approval_before_files": True}, ok) == []
    assert grader.grade({"order": [["search_knowledge", "create_docx"]]}, trace("create_docx", "search_knowledge"))
    assert grader.grade({"approval_before_files": True}, trace("create_docx", "ask_user"))
    assert grader.grade({"approval_before_files": True}, trace("create_docx"))


def test_argument_checks_apply_to_every_call_of_the_tool():
    good = trace(("create_docx", {"rtl": True}), ("create_docx", {"rtl": True}))
    bad = trace(("create_docx", {"rtl": True}), ("create_docx", {"rtl": False}))
    rule = {"all_calls_arg": [{"tool": "create_docx", "path": "rtl", "equals": True}]}
    assert grader.grade(rule, good) == [] and grader.grade(rule, bad)
    assert grader.grade({"no_call_arg": [{"tool": "create_docx", "path": "rtl", "equals": True}]}, good)


def test_recreated_requires_the_same_file_name():
    same = trace(("create_docx", {"filename": "Lesson-Plan.docx"}))
    other = trace(("create_docx", {"filename": "lesson-plan-v2"}))
    assert grader.grade({"recreated": ["lesson-plan"]}, same) == [] and grader.grade({"recreated": ["lesson-plan"]}, other)


def test_memory_and_wording_checks():
    t = trace(said="I found no relevant material", memory="- prefers a short warm-up")
    assert grader.grade({"said_contains_any": ["no relevant"], "memory_contains_any": ["warm"], "memory_not_contains": ["Ahmed"]}, t) == []
    assert grader.grade({"said_not_matches": ["no relevant"]}, t) and grader.grade({"memory_not_contains": ["warm"]}, t)


def test_too_many_model_calls_fail_a_case():
    assert grader.grade({}, trace(*["ask_user"] * (grader.max_turns() + 1)))


# --- the baseline gate and the history file --------------------------------------------------------
BASE = {"pass_rate": "0.9000", "tokens_in": "200000"}


def test_a_pass_rate_drop_of_more_than_five_points_fails_the_gate():
    assert run.compare({"pass_rate": 0.87, "tokens_in": 200000}, BASE)[0]
    ok, msgs = run.compare({"pass_rate": 0.80, "tokens_in": 200000}, BASE)
    assert not ok and "pass rate fell" in msgs[0]


def test_a_token_jump_of_more_than_half_fails_the_gate():
    assert run.compare({"pass_rate": 0.9, "tokens_in": 290000}, BASE)[0]
    ok, msgs = run.compare({"pass_rate": 0.9, "tokens_in": 310000}, BASE)
    assert not ok and "input tokens rose" in msgs[0]


def test_without_a_baseline_the_gate_passes_and_says_why():
    ok, msgs = run.compare({"pass_rate": 0.1, "tokens_in": 1}, None)
    assert ok and "no baseline yet" in msgs[0]


def test_baseline_is_the_latest_row_marked_yes():
    rows = [{"baseline": "yes", "pass_rate": "0.5"}, {"baseline": "", "pass_rate": "0.6"}, {"baseline": "yes", "pass_rate": "0.9"}]
    assert run.baseline_row(rows)["pass_rate"] == "0.9" and run.baseline_row(rows[1:2]) is None


def test_a_mock_run_is_not_recorded_unless_asked_and_a_recorded_run_becomes_a_baseline(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run, "HISTORY", tmp_path / "history.csv")
    assert run.main(["--mock", "--runs", "1", "--group", "scope"]) == 0
    assert not run.HISTORY.exists()
    assert run.main(["--mock", "--runs", "1", "--group", "scope", "--record", "--baseline", "--note", "test"]) == 0
    (row,) = list(csv.DictReader(open(run.HISTORY, encoding="utf-8")))
    assert row["baseline"] == "yes" and row["pass_rate"] == "1.0000" and row["provider"] == "mock" and row["note"] == "test"
    assert run.main(["--mock", "ignore_note", "--runs", "1", "--group", "revise"]) == 1          # now measured against that baseline
    assert "pass rate fell" in capsys.readouterr().out


def test_estimate_mode_spends_nothing_and_writes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run, "HISTORY", tmp_path / "history.csv")
    assert run.main(["--estimate", "--runs", "1", "--group", "scope"]) == 0
    assert not run.HISTORY.exists() and "Estimate for a real run" in capsys.readouterr().out
