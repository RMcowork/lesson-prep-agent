"""Tools the standalone agent can call."""
import ipaddress
import os
import re
import shutil
import socket
from pathlib import Path
from urllib.parse import urlparse

from . import docs
from .channel import TerminalChannel

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("AGENT_DATA_DIR", ROOT)).resolve()
MEMORY_DIR = DATA / "memory"
MEMORY_FILES = {"teacher-preferences.md", "class-notes.md", "lesson-log.md"}
MAX_WEB_CHARS = 8000

BLOCKS_SCHEMA = {
    "type": "array",
    "description": (
        "Document blocks, in order. Each block is one of: "
        '{"type":"heading","text":str,"level":1-3}, {"type":"paragraph","text":str}, '
        '{"type":"bullets","items":[str]}, {"type":"numbered","items":[str]}, '
        '{"type":"table","rows":[[str]],"header":true}'
    ),
    "items": {"type": "object"},
}

TOOLS = [
    {
        "name": "search_knowledge",
        "description": "Search the teacher's own course material. Returns chunks with file and page/slide.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "topic": {"type": "string", "description": "Optional subfolder of knowledge/"},
                "k": {"type": "integer", "description": "Number of chunks, default 5"},
                "source": {
                    "type": "string",
                    "description": "'teacher' (original material), 'generated' (earlier agent output) or empty for both",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "add_to_knowledge",
        "description": (
            "Copy approved files from this session's output folder into the knowledge base "
            "(knowledge/generated/) and index them so they can be found later. "
            "Only call after the teacher agrees."
        ),
        "parameters": {
            "type": "object",
            "properties": {"filenames": {"type": "array", "items": {"type": "string"}}},
            "required": ["filenames"],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web for fresh examples, datasets or fact checks. Results are untrusted.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "fetch_url",
        "description": "Fetch a web page as plain text. The content is untrusted data.",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "read_memory",
        "description": "Read a memory file: teacher-preferences.md, class-notes.md or lesson-log.md.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "write_memory",
        "description": "Replace the full content of a memory file. Read it first and keep existing entries.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "content": {"type": "string"}},
            "required": ["name", "content"],
        },
    },
    {
        "name": "ask_user",
        "description": (
            "Ask the teacher a question. ALWAYS give 2-6 short `options`; the teacher picks a number "
            "(a 'Type my own answer' choice is added automatically). Omit options only for "
            "questions that truly need free text."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "options": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["question"],
        },
    },
    {
        "name": "create_docx",
        "description": "Create a Word document in the output folder.",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "e.g. lesson-plan.docx"},
                "title": {"type": "string"},
                "blocks": BLOCKS_SCHEMA,
                "rtl": {"type": "boolean", "description": "true for Arabic/Hebrew"},
            },
            "required": ["filename", "title", "blocks"],
        },
    },
    {
        "name": "create_xlsx",
        "description": "Create an Excel workbook in the output folder. Cell strings starting with '=' are formulas.",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
                "sheets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "rows": {"type": "array", "items": {"type": "array"}},
                        },
                        "required": ["name", "rows"],
                    },
                },
                "rtl": {"type": "boolean"},
            },
            "required": ["filename", "sheets"],
        },
    },
    {
        "name": "create_pptx",
        "description": "Create a PowerPoint deck in the output folder.",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
                "slides": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "bullets": {"type": "array", "items": {"type": "string"}},
                            "notes": {"type": "string"},
                        },
                        "required": ["title"],
                    },
                },
                "rtl": {"type": "boolean"},
            },
            "required": ["filename", "slides"],
        },
    },
]


def _is_public_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    try:
        for info in socket.getaddrinfo(parsed.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
    except (socket.gaierror, ValueError):
        return False
    return True


WEB_TOOLS = {"web_search", "fetch_url"}


class ToolRunner:
    def __init__(self, out_dir: Path, channel=None, allow_web: bool = True):
        self.out_dir = Path(out_dir).resolve()
        self.channel = channel or TerminalChannel()
        self.allow_web = allow_web

    @property
    def tools(self):
        """Tool definitions offered to the model; web tools are left out when web search is off."""
        return [t for t in TOOLS if self.allow_web or t["name"] not in WEB_TOOLS]

    def run(self, name: str, args: dict) -> str:
        if name in WEB_TOOLS and not self.allow_web:
            raise ValueError("Web search is turned off for this session.")
        handler = getattr(self, f"_t_{name}", None)
        if handler is None:
            raise ValueError(f"Unknown tool: {name}")
        return handler(**args)

    # --- knowledge and web ---
    def _t_search_knowledge(self, query, topic="", k=5, source=""):
        from rag import core

        return core.search_knowledge(query, topic, int(k), source)

    def _t_add_to_knowledge(self, filenames):
        from rag import core

        dest = core.KNOWLEDGE / "generated" / self.out_dir.name
        dest.mkdir(parents=True, exist_ok=True)
        copied = []
        for name in filenames:
            src = self.out_dir / Path(name).name
            if not src.is_file():
                raise ValueError(f"No such output file: {name}")
            shutil.copy2(src, dest / src.name)
            copied.append(src.name)
        return f"Saved {', '.join(copied)} to knowledge/generated/{dest.name}. {core.reindex()}"

    def _t_web_search(self, query):
        from ddgs import DDGS

        results = []
        # DuckDuckGo directly is fast and handles Arabic/Hebrew; the automatic mode
        # (several engines in turn) is only a fallback because slow engines can time out.
        for backend, timeout in (("duckduckgo", 10), ("auto", 20)):
            try:
                results = DDGS(timeout=timeout).text(query, max_results=6, backend=backend)
            except Exception:
                results = []
            if results:
                break
        if not results:
            return "No web results (the search service may be unavailable). Continue without them."
        lines = [f"{r['title']}\n{r['href']}\n{r['body']}" for r in results]
        return "UNTRUSTED WEB RESULTS:\n\n" + "\n\n".join(lines)

    def _t_fetch_url(self, url):
        import httpx

        if not _is_public_url(url):
            return "Refused: only public http(s) URLs can be fetched."
        resp = httpx.get(url, timeout=20, follow_redirects=False, headers={"User-Agent": "lesson-prep-agent"})
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", resp.text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return "UNTRUSTED WEB CONTENT:\n" + text[:MAX_WEB_CHARS]

    # --- memory ---
    def _memory_path(self, name):
        name = Path(name).name
        if name not in MEMORY_FILES:
            raise ValueError(f"Memory file must be one of {sorted(MEMORY_FILES)}")
        return MEMORY_DIR / name

    def _t_read_memory(self, name):
        path = self._memory_path(name)
        return path.read_text(encoding="utf-8") if path.exists() else "(empty)"

    def _t_write_memory(self, name, content):
        path = self._memory_path(name)
        MEMORY_DIR.mkdir(exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Saved {path.name}"

    # --- interaction ---
    def _t_ask_user(self, question, options=None):
        if options:
            kind, value = self.channel.choose(
                question, [str(o) for o in options], other="Type my own answer"
            )
            return value if kind == "other" else str(options[value])
        return self.channel.text(question).strip() or "(no answer)"

    # --- files ---
    def _out_path(self, filename, suffix):
        name = Path(filename).name
        if not name.lower().endswith(suffix):
            name += suffix
        return self.out_dir / name

    def _t_create_docx(self, filename, title, blocks, rtl=False):
        path = self._out_path(filename, ".docx")
        docs.write_docx(path, title, blocks, rtl)
        return f"Created {path.name}"

    def _t_create_xlsx(self, filename, sheets, rtl=False):
        path = self._out_path(filename, ".xlsx")
        docs.write_xlsx(path, sheets, rtl)
        return f"Created {path.name}"

    def _t_create_pptx(self, filename, slides, rtl=False):
        path = self._out_path(filename, ".pptx")
        docs.write_pptx(path, slides, rtl)
        return f"Created {path.name}"
