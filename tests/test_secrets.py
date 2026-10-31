"""spec.md check 10 and architecture.md Secrets: grep the repo, and every commit, for keys. It must come back empty.
If this fails: rotate the key first, then clean the history, then fix the cause."""
import re
import subprocess

import pytest

from tests.conftest import ROOT

PATTERNS = {
    "Anthropic key": r"sk-ant-[A-Za-z0-9_-]{10,}",
    "OpenAI-style key": r"\bsk-[A-Za-z0-9]{32,}\b",
    "Telegram bot token": r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b",
    "key assigned in a file": r"(ANTHROPIC_API_KEY|OPENAI_API_KEY|TELEGRAM_BOT_TOKEN|SMTP_PASSWORD)[ \t]*=[ \t]*[\"']?[A-Za-z0-9_:\-]{12,}",
}
COMBINED = re.compile("|".join(f"(?:{p})" for p in PATTERNS.values()))


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, errors="replace")


def in_git_repo():
    return git("rev-parse", "--is-inside-work-tree").stdout.strip() == "true"


def test_the_scanner_itself_catches_each_kind_of_secret():
    fakes = ["sk-ant-api03-" + "a" * 40, "sk-" + "A1" * 20, "123456789:" + "x" * 35, "SMTP_PASSWORD=abcdefghijklmnop"]
    assert all(COMBINED.search(f) for f in fakes)
    assert not COMBINED.search("ANTHROPIC_API_KEY=") and not COMBINED.search("TELEGRAM_BOT_TOKEN=\n")   # .env.example style
    assert not COMBINED.search("OPENAI_API_KEY=\n TELEGRAM_BOT_TOKEN=\n")     # a name on the next line is not a value


@pytest.mark.skipif(not in_git_repo(), reason="not a git checkout")
def test_no_secret_in_any_tracked_file():
    hits = []
    for name in git("ls-files").stdout.splitlines():
        path = ROOT / name
        if path.is_file() and path.stat().st_size < 2_000_000:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            hits += [f"{name}: {m.group(0)[:12]}..." for m in COMBINED.finditer(text)]
    assert not hits, f"secrets in tracked files: {hits}"


@pytest.mark.skipif(not in_git_repo(), reason="not a git checkout")
def test_no_secret_in_any_commit():
    history = git("log", "--all", "-p", "--no-color", "--format=commit %h")
    assert history.returncode == 0
    hits = sorted({m.group(0)[:12] + "..." for m in COMBINED.finditer(history.stdout)})
    assert not hits, f"secrets in git history: {hits}"


@pytest.mark.skipif(not in_git_repo(), reason="not a git checkout")
def test_private_paths_are_never_tracked():
    tracked = git("ls-files").stdout.splitlines()
    bad = [f for f in tracked if not f.endswith(".gitkeep") and (f == ".env" or f == "topics.json" or f.startswith(("logs/", "output/", "rag-index/")))
           or (f.startswith("knowledge/") and not f.endswith(".gitkeep"))
           or (f.startswith("memory/") and f != "memory/INDEX.md")]
    assert not bad, f"private files tracked by git: {bad}"


def test_git_and_docker_ignore_the_private_paths():
    for ignore in (".gitignore", ".dockerignore"):
        lines = (ROOT / ignore).read_text().splitlines()
        for needed in (".env", "knowledge/*", "output/*", "logs/", "topics.json", "rag-index/"):
            assert needed in lines, f"{ignore} does not exclude {needed}"
