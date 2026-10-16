"""Numbered menus, so the teacher never has to type Arabic/Hebrew in the terminal.

Every menu returns quickly from a typed number. Arabic-Indic digits are accepted.
"""
import re
from pathlib import Path

from . import ui

BACK = "back"
OTHER = "other"
def _input(prompt=""):
    return input(prompt)  # looked up at call time


_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _read(ask, prompt="Choose a number: "):
    try:
        return ask(prompt).strip().translate(_DIGITS)
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("\nStopped.")


def choose(title, options, ask=_input, back=None, other=None):
    """Show a numbered menu. Returns ("option", index) | ("back", None) | ("other", text)."""
    while True:
        ui.show(f"\n{title}")
        for i, label in enumerate(options, 1):
            ui.show(f"  {i}. {label}")
        other_no = len(options) + 1 if other else None
        if other:
            ui.show(f"  {other_no}. {other}")
        if back:
            ui.show(f"  0. {back}")
        answer = _read(ask)
        if back and answer == "0":
            return BACK, None
        if answer.isdigit():
            n = int(answer)
            if 1 <= n <= len(options):
                return "option", n - 1
            if other and n == other_no:
                typed = ask("Type your answer: ").strip()
                if typed:
                    return OTHER, typed
        ui.show("Please enter one of the numbers shown.")


def choose_many(title, options, defaults, ask=_input, back="Back"):
    """Multi-select. Enter numbers separated by commas, or press Enter for the defaults."""
    while True:
        ui.show(f"\n{title}")
        for i, label in enumerate(options, 1):
            mark = "*" if i - 1 in defaults else " "
            ui.show(f"  {i}. [{mark}] {label}")
        ui.show(f"  0. {back}")
        answer = _read(ask, "Numbers separated by commas (Enter = keep the marked ones): ")
        if answer == "0":
            return BACK, None
        if answer == "":
            return "option", sorted(defaults)
        parts = [p for p in re.split(r"[,\s]+", answer) if p]
        if parts and all(p.isdigit() and 1 <= int(p) <= len(options) for p in parts):
            return "option", sorted({int(p) - 1 for p in parts})
        ui.show("Please enter numbers from the list, for example: 1,3")


def load_units(outline_path: Path):
    """Read the unit names from the markdown table in config/course-outline.md."""
    units = []
    if outline_path.exists():
        for line in outline_path.read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and cells[0].isdigit():
                units.append(cells[1])
    return units


def run_steps(steps):
    """Run wizard steps with Back support. Each step is f(state) -> BACK | None."""
    state, i = {}, 0
    while i < len(steps):
        result = steps[i](state)
        if result == BACK:
            if i == 0:
                return None
            i -= 1
        else:
            i += 1
    return state


def _single(key, title, options, ch, labels=None, other=None):
    def step(state):
        kind, value = ch.choose(title, options, back="Back", other=other)
        if kind == BACK:
            return BACK
        state[key] = value if kind == OTHER else (labels or options)[value]
        return None

    return step


def _multi(key, title, options, defaults, ch, labels=None):
    def step(state):
        kind, value = ch.choose_many(title, options, defaults)
        if kind == BACK:
            return BACK
        state[key] = [(labels or options)[i] for i in value]
        return None

    return step


def _confirm(summary, ch):
    def step(state):
        ch.say("Summary:\n" + "\n".join(f"  {k}: {v}" for k, v in summary(state)))
        kind, value = ch.choose("Ready?", ["Start"], back="Back")
        return BACK if kind == BACK else None

    return step


LANGS = ["Arabic (right-to-left)", "Hebrew (right-to-left)", "English"]
LANG_NAMES = ["Arabic", "Hebrew", "English"]
GRADES = ["K10", "K11", "Both"]
LEVELS = ["Mixed class", "Support (easier)", "Core", "Extension (harder)"]
MINUTES = ["30", "45", "60", "90"]


def lesson_wizard(units, ch):
    outputs = [
        "Lesson plan (.docx)",
        "Student worksheet (.docx)",
        "Quiz with answer key (.docx)",
        "Slides (.pptx)",
        "Excel exercise file (.xlsx)",
    ]
    steps = [
        _single("topic", "Which unit?", units, ch, other="Another topic (type it)"),
        _single("minutes", "Lesson length (minutes)?", MINUTES, ch),
        _single("language", "Language of the materials?", LANGS, ch, labels=LANG_NAMES),
        _single("grade", "Grade?", GRADES, ch),
        _single("level", "Level of the class?", LEVELS, ch),
        _multi("outputs", "What should I create?", outputs, {0, 1, 2}, ch),
        _confirm(
            lambda s: [
                ("Topic", s["topic"]),
                ("Length", s["minutes"] + " min"),
                ("Language", s["language"]),
                ("Grade", s["grade"]),
                ("Level", s["level"]),
                ("Create", ", ".join(s["outputs"])),
            ],
            ch,
        ),
    ]
    state = run_steps(steps)
    if state is None:
        return None
    task = (
        f"Prepare a lesson. Topic: {state['topic']}. Grade: {state['grade']}. "
        f"Length: {state['minutes']} minutes. Language: {state['language']}. "
        f"Class level: {state['level']}. Create: {', '.join(state['outputs'])}. "
        "The teacher chose these options from a menu, so do not ask for them again."
    )
    return task, state["topic"]


def exam_wizard(units, ch):
    kinds = ["Short quiz (10-15 min)", "Test (30-45 min)", "Full exam (60-90 min)"]
    qtypes = [
        "Multiple choice",
        "Short answer",
        "Excel practical task",
        "Read a chart or table",
        "True / false",
    ]
    steps = [
        _single("topic", "Which unit?", units, ch, other="Another topic (type it)"),
        _single("kind", "Type of assessment?", kinds, ch),
        _single("language", "Language?", LANGS, ch, labels=LANG_NAMES),
        _single("grade", "Grade?", GRADES, ch),
        _multi("qtypes", "Question types?", qtypes, {0, 1}, ch),
        _confirm(
            lambda s: [
                ("Topic", s["topic"]),
                ("Type", s["kind"]),
                ("Language", s["language"]),
                ("Grade", s["grade"]),
                ("Questions", ", ".join(s["qtypes"])),
            ],
            ch,
        ),
    ]
    state = run_steps(steps)
    if state is None:
        return None
    task = (
        f"Prepare an assessment with answer key and grading rubric. Topic: {state['topic']}. "
        f"Type: {state['kind']}. Grade: {state['grade']}. Language: {state['language']}. "
        f"Question types: {', '.join(state['qtypes'])}. "
        "The teacher chose these options from a menu, so do not ask for them again."
    )
    return task, "exam-" + state["topic"]
