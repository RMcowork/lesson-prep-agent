"""The repo is the plan (practice.md). If a decision is not in a file, it was not made.
These checks keep the documents and the code from drifting apart."""
import re

import pytest

from tests.conftest import ROOT

SPEC = (ROOT / "spec.md").read_text()
ARCH = (ROOT / "architecture.md").read_text()
PRACTICE = (ROOT / "practice.md").read_text()


def headings(text):
    return [re.sub(r"^\d+\.\s*", "", h).strip() for h in re.findall(r"^##\s+(.+)$", text, flags=re.M)]


def test_the_plan_files_exist():
    for name in ("spec.md", "architecture.md", "practice.md", "CLAUDE.md", ".github/workflows/ci.yml",
                 ".github/pull_request_template.md", "evals/cases.yaml", "evals/grader.py", "evals/history.csv"):
        assert (ROOT / name).exists(), f"{name} is missing"
    assert (ROOT / "tests").is_dir()


def test_deployment_files_are_not_part_of_this_phase():
    assert not (ROOT / "runbook.md").exists()
    workflow = (ROOT / ".github/workflows/ci.yml").read_text().lower()
    assert "railway" not in workflow and "deploy" not in workflow.replace("no deploy", "")


def test_claude_md_is_one_line_pointing_at_the_three_files():
    lines = [l for l in (ROOT / "CLAUDE.md").read_text().splitlines() if l.strip()]
    assert len(lines) == 1 and all(f in lines[0] for f in ("practice.md", "spec.md", "architecture.md"))


def test_spec_has_the_lesson_9_headings_in_order():
    assert headings(SPEC) == ["Users", "Jobs", "Not in v1", "Speed", "Data", "Limits", "Done"]


def test_architecture_has_the_lesson_9_headings():
    assert headings(ARCH) == ["Components", "Flows", "Storage", "Model", "Limits", "Hosting", "Secrets", "Decisions"]


def test_every_spec_limit_has_a_number():
    section = SPEC.split("## 6. Limits")[1].split("## 7. Done")[0]
    rows = [r for r in section.splitlines() if r.startswith("|") and not r.startswith("|---") and "Layer" not in r]
    assert rows and all(re.search(r"\d", r.split("|")[2]) or "allowlist" in r.lower() or "off by default" in r.lower() for r in rows)


def done_rows():
    section = SPEC.split("## 7. Done")[1]
    return [r.split("|") for r in section.splitlines() if re.match(r"\|\s*\d+\s*\|", r)]


def test_done_lists_twelve_checks_and_each_is_proven_by_something_real():
    rows = done_rows()
    assert [int(r[1]) for r in rows] == list(range(1, 13))
    for r in rows:
        proof = r[3]
        files = re.findall(r"`(tests/[\w./]+?\.py)", proof)
        assert files or "evals" in proof, f"check {r[1].strip()} names no test or eval"
        for f in files:
            assert (ROOT / f).exists(), f"check {r[1].strip()} points at {f}, which does not exist"


def test_eval_prefixes_named_in_the_spec_exist_in_the_cases():
    cases = (ROOT / "evals/cases.yaml").read_text()
    for prefix in re.findall(r"`([a-z-]+)-\*`", SPEC):
        assert re.search(rf"id:\s*{prefix}-", cases), f"spec.md names evals {prefix}-* but cases.yaml has none"


def test_practice_has_the_eight_steps_the_never_list_and_the_three_numbers():
    steps = re.findall(r"^\d\.\s+\*\*", PRACTICE.split("## When to run what")[0], flags=re.M)
    assert len(steps) == 8
    assert "**Never:**" in PRACTICE and "Tests passed" in PRACTICE and "Tokens per eval run" in PRACTICE


def test_every_environment_variable_the_code_reads_is_documented():
    used = set()
    for path in list((ROOT / "agent").glob("*.py")) + list((ROOT / "rag").glob("*.py")):
        used |= set(re.findall(r"os\.environ(?:\.get)?[\[(]\s*[\"'](\w+)[\"']", path.read_text()))
    example = (ROOT / ".env.example").read_text()
    secrets_section = ARCH.split("## Secrets")[1].split("## Decisions")[0]
    for name in used:
        assert name in secrets_section, f"{name} is read by the code but not listed in architecture.md Secrets"
        assert name in example, f"{name} is missing from .env.example"


def test_decisions_have_all_four_columns():
    rows = [r.split("|") for r in ARCH.split("## Decisions")[1].splitlines() if re.match(r"\|\s*20\d\d-", r)]
    assert len(rows) >= 10
    for r in rows:
        assert len(r) == 6 and all(c.strip() for c in r[1:5]), f"incomplete decision row: {r}"


def test_markdown_links_between_the_documents_resolve():
    for doc in ("spec.md", "architecture.md", "practice.md", "README.md"):
        text = (ROOT / doc).read_text()
        for target in re.findall(r"\]\(([^)#\s]+\.md)(?:#[^)]*)?\)", text):
            assert (ROOT / target).exists(), f"{doc} links to {target}, which does not exist"


def test_the_component_drawing_names_the_real_tools():
    from agent.tools import TOOLS

    section = ARCH.split("## Components")[1].split("## Flows")[0]
    for t in TOOLS:
        assert t["name"] in section, f"tool {t['name']} is missing from the architecture drawing"
