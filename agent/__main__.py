"""Command line entry point.

  python -m agent lesson "data types" 45 arabic
  python -m agent exam "data types" hebrew
  python -m agent chat
  python -m agent reindex
"""
import argparse
import json
import os
import re
import threading
from datetime import date
from pathlib import Path

from . import emailer, menu, settings
from .topics import TopicStore
from .usage import Meter
from .channel import TerminalChannel
from .llm import make_provider
from .loop import run_agent
from .tools import ToolRunner

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("AGENT_DATA_DIR", ROOT)).resolve()


def load_env():
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else "(none)"


def build_system() -> str:
    return "\n\n".join(
        [
            read(ROOT / "config" / "system-prompt.md"),
            "# Teacher profile\n" + read(ROOT / "config" / "teacher-profile.md"),
            "# Course outline\n" + read(ROOT / "config" / "course-outline.md"),
            "# Memory index\n" + read(DATA / "memory" / "INDEX.md"),
            f"Today's date: {date.today().isoformat()}",
        ]
    )


def slug(text: str) -> str:
    return re.sub(r"[^\w]+", "-", text.strip().lower(), flags=re.UNICODE).strip("-")[:40] or "session"


FINAL_PHASE = (
    "The teacher is satisfied with the files. Now finish up: ask the teacher with ask_user whether "
    "to save the final files to the knowledge base (call add_to_knowledge if yes), then update memory "
    "with write_memory: add the lesson to the lesson log, and save any preferences or corrections the "
    "teacher asked for during this session. Then say a one-line goodbye."
)


def run_session(provider, cfg, task: str, name: str, ch, lock=None, allow_web: bool = True):
    """One working session: generate, then keep taking the teacher's notes until they are happy."""
    folder = f"{date.today().isoformat()}-{slug(name)}"
    out_dir = DATA / "output" / folder
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = DATA / "logs" / f"{folder}.json"
    runner = ToolRunner(out_dir, ch, allow_web)
    system, max_turns = build_system(), cfg.max_turns
    state = {"messages": None}
    meter = Meter()
    delivered = {}

    def turn(text):
        if lock is not None:  # hold the lock only while the agent works, not while waiting for the teacher
            if lock.locked():
                ch.say("Another job is running. Yours will start when it finishes.")
            lock.acquire()
        try:
            ch.say("Working on it. This can take a few minutes.")
            state["messages"] = run_agent(
                provider, system, text, runner, max_turns,
                interactive=False, log_path=log_path, messages=state["messages"], meter=meter,
            )
        finally:
            if lock is not None:
                lock.release()

    def deliver():
        files = [p for p in sorted(out_dir.iterdir()) if p.is_file()]
        changed = [p for p in files if delivered.get(p.name) != p.stat().st_mtime_ns]
        for p in changed:
            delivered[p.name] = p.stat().st_mtime_ns
        if changed:
            ch.send_files(changed)
        else:
            ch.say("No files were created or changed.")
        return files

    turn(task)
    if isinstance(ch, TerminalChannel):
        ch.say(f"Output folder: {out_dir}")
    deliver()
    while True:
        kind, _ = ch.choose(
            "What next?", ["Request changes or reply to the agent"], back="Looks good, finish"
        )
        if kind == "back":
            break
        message = ch.text("Type your message to the agent:")
        if message:
            turn(message)
            deliver()
    turn(FINAL_PHASE)
    files = [p for p in sorted(out_dir.iterdir()) if p.is_file()]
    try:  # token totals for this job, kept next to the log (spec.md §6)
        (log_path.parent / f"{folder}.usage.json").write_text(json.dumps(meter.as_dict()))
    except OSError:
        pass
    if isinstance(ch, TerminalChannel):
        ch.say(f"Session log: {log_path}. Model use: {meter.calls} calls, "
               f"{meter.input_tokens} tokens in, {meter.output_tokens} out.")
    offer_email(ch, files, name)


def offer_email(ch, files, name: str):
    """Ask whether to email the files. Nothing is sent unless the teacher says yes."""
    if not files or not emailer.configured():
        return
    defaults = emailer.default_recipients()
    options = [f"Yes, send to {a}" for a in defaults]
    kind, value = ch.choose(
        "Email these files?", options, back="No, thanks", other="Send to another address"
    )
    if kind == "back":
        return
    if kind == "other":
        to = value
    else:
        to = defaults[value]
    if not emailer.is_address(to):
        ch.say("That does not look like an email address, so nothing was sent.")
        return
    names = "\n".join(f"- {p.name}" for p in files)
    try:
        ch.say(emailer.send_files(
            to, f"Lesson materials: {name}", f"Files prepared by the lesson-prep agent:\n{names}\n", files
        ))
    except (RuntimeError, ValueError) as exc:
        ch.say(f"Email not sent: {exc}")


def main_menu(cfg, ch, provider=None, lock=None, store=None):
    store = store or TopicStore()
    while True:
        kind, choice = ch.choose(
            "Lesson-prep agent: what would you like to do?",
            [
                "Prepare a lesson",
                "Prepare a quiz or exam",
                "Manage my topics",
                "Index my knowledge files",
                "Free chat (type a request)",
            ],
            back="Exit",
        )
        if kind == "back":
            return
        if choice == 2:
            menu.manage_topics(ch, store)
            continue
        if choice == 3:
            from rag import core

            ch.say("Indexing... the first run downloads the embedding model and can take a while.")
            ch.say(core.reindex())
            continue
        if provider is None:
            provider = make_provider(cfg)
        if choice == 0:
            result = menu.lesson_wizard(store, ch)
        elif choice == 1:
            result = menu.exam_wizard(store, ch)
        else:
            text = ch.text("What do you need?")
            if text:
                _, web = ch.choose("Search the web if needed?", menu.WEB_CHOICES)
                result = (text, "chat", {"allow_web": web == 1})
            else:
                result = None
        if result:
            task, name, options = result
            run_session(provider, cfg, task, name, ch, lock, **options)


def telegram_main(cfg):
    from .telegram_bot import Bot, TelegramAPI

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env (create a bot with @BotFather).")
    allowed = [i for i in os.environ.get("TELEGRAM_ALLOWED_IDS", "").replace(" ", "").split(",") if i]
    if not all(i.lstrip("-").isdigit() for i in allowed):
        raise SystemExit("TELEGRAM_ALLOWED_IDS must be numeric chat ids separated by commas.")
    api = TelegramAPI(token)
    me = api.call("getMe")
    print(f"Connected as @{me.get('username')}")
    if not allowed:
        print("TELEGRAM_ALLOWED_IDS is empty: message the bot to see your chat id, then add it to .env.")
    provider = make_provider(cfg)  # fail early if the LLM key is missing
    lock = threading.Lock()
    Bot(api, lambda ch: main_menu(cfg, ch, provider, lock), allowed).run()


def main():
    parser = argparse.ArgumentParser(prog="agent", description="Lesson-prep agent")
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("lesson", help="prepare a lesson package (no menu)")
    p.add_argument("topic")
    p.add_argument("minutes", nargs="?", default="")
    p.add_argument("language", nargs="?", default="")
    p = sub.add_parser("exam", help="prepare a quiz or exam (no menu)")
    p.add_argument("topic")
    p.add_argument("language", nargs="?", default="")
    sub.add_parser("chat", help="free conversation with the agent")
    sub.add_parser("reindex", help="index the knowledge/ folder")
    sub.add_parser("menu", help="interactive menu (default)")
    sub.add_parser("telegram", help="run the Telegram bot")
    args = parser.parse_args()

    load_env()

    if args.cmd == "reindex":
        from rag import core

        print(core.reindex())
        return

    cfg = settings.load()
    settings.use(cfg)
    ch = TerminalChannel()

    if args.cmd in (None, "menu"):
        main_menu(cfg, ch)
        return
    if args.cmd == "telegram":
        telegram_main(cfg)
        return

    provider = make_provider(cfg)
    if args.cmd == "lesson":
        task = f"Prepare a lesson. Topic: {args.topic}. Minutes: {args.minutes or 'default'}. Language: {args.language or 'default'}."
        name = args.topic
    elif args.cmd == "exam":
        task = f"Prepare a quiz or exam with answer key and grading rubric. Topic: {args.topic}. Language: {args.language or 'default'}."
        name = "exam-" + args.topic
    else:
        task, name = ch.text("What do you need?"), "chat"
    run_session(provider, cfg, task, name, ch)


if __name__ == "__main__":
    main()
