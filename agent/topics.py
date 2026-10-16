"""Topic list: the units in config/course-outline.md plus the teacher's own topics.

Own topics are saved in <data dir>/topics.json (private, not committed), so they
appear in the menus next time. Each topic has a name and an optional outline.
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("AGENT_DATA_DIR", ROOT)).resolve()


class TopicStore:
    def __init__(self, outline_path=None, data_dir=None):
        self.outline_path = Path(outline_path or ROOT / "config" / "course-outline.md")
        self.path = Path(data_dir or DATA) / "topics.json"

    # --- reading ---
    def _units(self) -> dict:
        """name -> objectives, from the markdown table in the course outline."""
        units = {}
        if self.outline_path.exists():
            for line in self.outline_path.read_text(encoding="utf-8").splitlines():
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) >= 2 and cells[0].isdigit():
                    units[cells[1]] = cells[2] if len(cells) > 2 else ""
        return units

    def _custom(self) -> list:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [t for t in data if isinstance(t, dict) and t.get("name")]
        except (OSError, ValueError):
            return []

    def custom_names(self) -> list:
        return [t["name"] for t in self._custom()]

    def names(self) -> list:
        units = list(self._units())
        return units + [n for n in self.custom_names() if n.lower() not in {u.lower() for u in units}]

    def is_custom(self, name: str) -> bool:
        return name.lower() in {n.lower() for n in self.custom_names()}

    def outline(self, name: str) -> str:
        for t in self._custom():
            if t["name"].lower() == name.lower():
                return t.get("outline", "")
        return self._units().get(name, "")

    # --- writing ---
    def _write(self, topics: list):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def add(self, name: str, outline: str = "") -> bool:
        """Save a topic. Returns False if the name is empty or already in the list."""
        name = name.strip()
        if not name or name.lower() in {n.lower() for n in self.names()}:
            return False
        self._write(self._custom() + [{"name": name, "outline": outline.strip()}])
        return True

    def remove(self, name: str) -> bool:
        topics = self._custom()
        kept = [t for t in topics if t["name"].lower() != name.lower()]
        if len(kept) == len(topics):
            return False
        self._write(kept)
        return True
