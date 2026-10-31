"""Exact checks on what the agent did: which tools, in which order, with which fields (spec.md §7).
Facts are graded exactly. Wording is only graded by a second model where a case has a rubric (ticket #28)."""
import re
from dataclasses import dataclass, field

from agent import settings

CREATE = ("create_docx", "create_xlsx", "create_pptx")


def max_turns() -> int:
    """Most model calls one case may use (eval_max_turns in config/agent.toml)."""
    return settings.get().eval_max_turns


@dataclass
class Trace:
    calls: list = field(default_factory=list)      # [{"name","input","error"}] in order
    asks: list = field(default_factory=list)       # [{"question","options"}]
    said: str = ""                                 # everything the teacher saw: replies and questions
    files: list = field(default_factory=list)      # names created in the job folder
    memory: str = ""                               # everything written to memory
    turns: int = 0                                 # model calls
    tokens: dict = field(default_factory=lambda: {"input": 0, "output": 0})

    def names(self):
        return [c["name"] for c in self.calls]


def _stem(filename: str) -> str:
    name = str(filename).rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0].lower()


def _first(seq, pred):
    return next((i for i, x in enumerate(seq) if pred(x)), None)


def grade(expect: dict, t: Trace) -> list:
    """Returns the list of failed checks. Empty means the run passed."""
    fails = []
    names = t.names()

    if t.turns > max_turns():
        fails.append(f"used {t.turns} model calls (limit {max_turns()})")
    for n in expect.get("called", []):
        if n not in names:
            fails.append(f"did not call {n}")
    if expect.get("called_any") and not any(n in names for n in expect["called_any"]):
        fails.append(f"called none of {expect['called_any']}")
    for n in expect.get("not_called", []):
        if n in names:
            fails.append(f"called {n}, which it must not")
    for a, b in expect.get("order", []):
        ib, ia = _first(names, lambda x: x == b), _first(names, lambda x: x == a)
        if ib is not None and (ia is None or ia > ib):
            fails.append(f"{b} came before {a}")

    if expect.get("approval_before_files"):
        first_create = _first(names, lambda x: x in CREATE)
        first_ask = _first(names, lambda x: x == "ask_user")
        if first_create is not None and (first_ask is None or first_ask > first_create):
            fails.append("created a file before asking the teacher to approve the outline")
    if expect.get("ask_user_without_options") and not any(not a["options"] for a in t.asks):
        fails.append("never asked a free-text question")
    if "ask_user_max" in expect and len(t.asks) > expect["ask_user_max"]:
        fails.append(f"asked the teacher {len(t.asks)} time(s); maximum {expect['ask_user_max']}")
    if expect.get("ask_user_question_contains_any"):
        terms = [s.lower() for s in expect["ask_user_question_contains_any"]]
        if not any(any(s in a["question"].lower() for s in terms) for a in t.asks):
            fails.append(f"no question mentioned any of {expect['ask_user_question_contains_any']}")

    if expect.get("files_created_any") and not any(f.lower().endswith(tuple(expect["files_created_any"])) for f in t.files):
        fails.append(f"created no file of type {expect['files_created_any']}")
    for stem in expect.get("recreated", []):
        if not any(c["name"] in CREATE and _stem(c["input"].get("filename", "")) == stem.lower() for c in t.calls):
            fails.append(f"did not rewrite {stem} under the same name")

    for rule in expect.get("all_calls_arg", []):
        for c in (c for c in t.calls if c["name"] == rule["tool"]):
            if c["input"].get(rule["path"]) != rule["equals"]:
                fails.append(f"{rule['tool']} call had {rule['path']}={c['input'].get(rule['path'])!r}, expected {rule['equals']!r}")
                break
    for rule in expect.get("no_call_arg", []):
        if any(c["name"] == rule["tool"] and c["input"].get(rule["path"]) == rule["equals"] for c in t.calls):
            fails.append(f"{rule['tool']} was called with {rule['path']}={rule['equals']!r}, which it must not")

    said = t.said.lower()
    if expect.get("said_contains_any") and not any(s.lower() in said for s in expect["said_contains_any"]):
        fails.append(f"the teacher was never told any of {expect['said_contains_any']}")
    for pattern in expect.get("said_not_matches", []):
        if re.search(pattern, t.said, re.IGNORECASE):
            fails.append(f"said something matching /{pattern}/")
    if expect.get("memory_contains_any") and not any(s.lower() in t.memory.lower() for s in expect["memory_contains_any"]):
        fails.append(f"memory never mentioned any of {expect['memory_contains_any']}")
    for s in expect.get("memory_not_contains", []):
        if s.lower() in t.memory.lower():
            fails.append(f"memory contains {s!r}")
    return fails


KNOWN_CHECKS = {
    "called", "called_any", "not_called", "order", "approval_before_files", "ask_user_without_options", "ask_user_max",
    "ask_user_question_contains_any", "files_created_any", "recreated", "all_calls_arg", "no_call_arg",
    "said_contains_any", "said_not_matches", "memory_contains_any", "memory_not_contains",
}
KNOWN_TOOLS = {"search_knowledge", "add_to_knowledge", "web_search", "fetch_url", "read_memory", "add_memory", "ask_user",
               "create_docx", "create_xlsx", "create_pptx"}


def validate_case(case: dict) -> list:
    """Problems with a case definition itself (a typo here would silently weaken the eval)."""
    p = []
    for key in ("id", "group", "task", "expect"):
        if key not in case:
            p.append(f"{case.get('id', '?')}: missing {key}")
    if p:
        return p
    cid = case["id"]
    if not case["id"].startswith(case["group"]):
        p.append(f"{cid}: id must start with its group '{case['group']}'")
    if case.get("phase", "lesson") not in ("lesson", "revise", "final"):
        p.append(f"{cid}: unknown phase {case.get('phase')!r}")
    if case.get("phase") == "revise" and not (case.get("note") and case.get("seed_files")):
        p.append(f"{cid}: a revise case needs seed_files and a note")
    if case.get("phase") == "final" and not case.get("seed_files"):
        p.append(f"{cid}: a final case needs seed_files")
    for check in case["expect"]:
        if check not in KNOWN_CHECKS:
            p.append(f"{cid}: unknown check '{check}'")
    mentioned = set(case["expect"].get("called", [])) | set(case["expect"].get("not_called", [])) | set(case["expect"].get("called_any", []))
    for a, b in case["expect"].get("order", []):
        mentioned |= {a, b}
    for rule in case["expect"].get("all_calls_arg", []) + case["expect"].get("no_call_arg", []):
        mentioned.add(rule["tool"])
    for n in mentioned - KNOWN_TOOLS:
        p.append(f"{cid}: unknown tool '{n}'")
    return p
