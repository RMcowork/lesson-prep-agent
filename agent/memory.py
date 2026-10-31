"""The teacher's memory: three small markdown files, safe by construction.

The model can only ADD one line at a time (add). It cannot replace a file, so an earlier entry can never be lost
because the model forgot to read first. Every write is atomic: a crash cannot leave a half-written file.
Tickets #31 (append-only), #33 (files created automatically), #32 (given to the model before it plans).
"""
import os
from pathlib import Path

from . import settings

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("AGENT_DATA_DIR", ROOT)).resolve()
MEMORY_DIR = DATA / "memory"

# The three files and how a new, empty one starts.
FILES = {
    "teacher-preferences.md": "# Teacher preferences\n\n",
    "class-notes.md": "# Class notes\n\n",
    "lesson-log.md": "# Lesson log\n\n| Date | Topic | Language | Files | Feedback |\n|---|---|---|---|---|\n",
}
INDEX = (
    "# Memory index\n\n"
    "- [Teacher preferences](teacher-preferences.md): default language, tone, formats, timing habits\n"
    "- [Class notes](class-notes.md): level mix, what worked and what didn't (no student names)\n"
    "- [Lesson log](lesson-log.md): date, topic, files produced, feedback\n"
)
PLACEHOLDER = "(Empty"          # an old template line such as "(Empty. The agent adds preferences here...)"


def _resolve(name: str):
    """(clean file name, its path). Only the file name counts: no folders, no ..; only the three files are allowed."""
    name = Path(str(name)).name
    if name not in FILES:
        raise ValueError(f"Memory file must be one of {sorted(FILES)}")
    return name, MEMORY_DIR / name


def atomic_write(path: Path, text: str) -> None:
    """Write the whole file or nothing: a crash in the middle leaves the old file untouched."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def ensure_files() -> None:
    """Create any missing memory file and the index, so a fresh data folder works from the first run.
    Existing files are never touched."""
    for name, header in {**FILES, "INDEX.md": INDEX}.items():
        path = MEMORY_DIR / name
        if not path.exists():
            atomic_write(path, header)


def index() -> str:
    """The memory index for the model. If the folder cannot be written (read-only volume) the agent still starts."""
    try:
        ensure_files()
        return (MEMORY_DIR / "INDEX.md").read_text(encoding="utf-8")
    except OSError:
        return INDEX                                  # the same text, just not saved to disk


SHOWN = (("teacher-preferences.md", "Teacher preferences"), ("class-notes.md", "Class notes"))


def context() -> str:
    """What the model should remember before it plans: preferences and class notes, newest lines kept if too long.
    Only real entries are shown (no headers or placeholders). The lesson log is not included: it only grows."""
    cap = settings.get().memory_context_chars
    parts = []
    for name, title in SHOWN:
        path = MEMORY_DIR / name
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        entries = [l.strip() for l in text.splitlines() if l.strip().startswith(("- ", "* "))]
        if not entries:
            continue
        kept, size = [], 0
        for line in reversed(entries):                # newest first, so the latest corrections survive the cap
            if size + len(line) + 1 > cap and kept:
                break
            kept.append(line)
            size += len(line) + 1
        kept.reverse()
        note = f"\n(Older entries not shown: {len(entries) - len(kept)}. Use read_memory for the full file.)" if len(kept) < len(entries) else ""
        parts.append(f"## {title}\n" + "\n".join(kept) + note)
    return "\n\n".join(parts) if parts else "(nothing remembered yet)"


def read(name: str) -> str:
    _, path = _resolve(name)
    return path.read_text(encoding="utf-8") if path.exists() else "(empty)"


def add(name: str, entry: str) -> str:
    """Remember ONE new line. Earlier entries are never changed or removed."""
    name, path = _resolve(name)
    entry = " ".join(str(entry).split())             # one line
    if not entry:
        raise ValueError("Nothing to remember: the entry is empty.")
    limit = settings.get().memory_entry_chars
    if len(entry) > limit:
        raise ValueError(f"The entry is {len(entry)} characters; the maximum is {limit}. Shorten it to one short line.")
    if name == "lesson-log.md":
        if not (entry.startswith("|") and entry.endswith("|") and entry.count("|") >= 6):
            raise ValueError("A lesson-log entry must be one table row: | date | topic | language | files | feedback |")
    elif not entry.startswith(("- ", "* ")):
        entry = "- " + entry.lstrip("-* ").strip()

    current = path.read_text(encoding="utf-8") if path.exists() else FILES[name]
    lines = [l for l in current.splitlines() if not l.startswith(PLACEHOLDER)]
    if entry in (l.strip() for l in lines):
        return f"Already remembered in {name}; nothing changed."
    atomic_write(path, "\n".join(lines).rstrip("\n") + "\n" + entry + "\n")
    return f"Added to {name}."


def rewrite(name: str, content: str) -> None:
    """Replace a whole file on purpose (for a person's edit, never offered to the model). The old version is kept."""
    _, path = _resolve(name)
    if path.exists():
        atomic_write(path.with_name(path.name + ".previous"), path.read_text(encoding="utf-8"))
    atomic_write(path, content if content.endswith("\n") else content + "\n")
