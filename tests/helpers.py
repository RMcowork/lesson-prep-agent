"""Test doubles shared by the tests. The model, Telegram and the mail server are always faked,
so tests are free, fast and identical on every run (practice.md, step 5)."""
import copy
import itertools
import pathlib
import queue
import time

from agent.llm import Reply


class ScriptedChannel:
    """A teacher who answers from a script. Anything unexpected fails the test."""

    def __init__(self, answers=()):
        self.answers = list(answers)
        self.said, self.titles, self.sent = [], [], []

    def _next(self, kind, title):
        self.titles.append(title)
        if not self.answers:
            raise AssertionError(f"unexpected {kind}: {title!r}")
        return self.answers.pop(0)

    def say(self, text=""):
        self.said.append(str(text))

    def status(self, text=""):
        pass

    def choose(self, title, options, back=None, other=None, other_prompt="", free_text=False):
        a = self._next("question", title)
        if isinstance(a, int):
            return "option", a
        if a == "back":
            return "back", None
        if isinstance(a, tuple):
            return a
        return "other", a

    def choose_many(self, title, options, defaults, back="Back"):
        a = self._next("multi-choice", title)
        if a is None:
            return "option", sorted(defaults)
        if a == "back":
            return "back", None
        return "option", list(a)

    def text(self, prompt):
        return self._next("text prompt", prompt)

    def send_files(self, paths):
        self.sent.append(sorted(pathlib.Path(p).name for p in paths))


class FakeProvider:
    """A model that replies from a script and records what it was asked."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, system, messages, tools):
        self.calls.append(
            {"system": system, "messages": copy.deepcopy(messages), "tools": [t["name"] for t in tools]}
        )
        if not self.replies:
            raise AssertionError("the model was called more times than scripted")
        return self.replies.pop(0)


def call(_tool, **args):
    return {"id": f"c{next(_ids)}", "name": _tool, "input": args}


_ids = itertools.count(1)


def reply(text="", *calls, usage=None):
    return Reply(text=text, tool_calls=list(calls), usage=usage or {"input": 100, "output": 20})


def docx_call(filename="plan", title="T", text="x", rtl=False):
    return call("create_docx", filename=filename, title=title, rtl=rtl, blocks=[{"type": "paragraph", "text": text}])


class FakeTelegramAPI:
    """Stands in for the Telegram Bot API. `taps` are callback suffixes tapped for each keyboard sent."""

    def __init__(self, taps=()):
        self.taps = list(taps)
        self.pending, self.sent, self.docs, self.methods = [], [], [], []
        self._uid, self._mid = itertools.count(1), itertools.count(100)

    def push_text(self, chat, text):
        self.pending.append({"update_id": next(self._uid), "message": {"chat": {"id": chat}, "text": text}})

    def push_callback(self, chat, data, message_id=1):
        self.pending.append({"update_id": next(self._uid), "callback_query": {
            "id": f"cb{next(self._uid)}", "data": data, "message": {"chat": {"id": chat}, "message_id": message_id}}})

    def call(self, method, **p):
        self.methods.append(method)
        if method == "getUpdates":
            if not self.pending:
                time.sleep(0.02)
                return []
            out, self.pending = self.pending, []
            return out
        if method == "sendMessage":
            mid = next(self._mid)
            self.sent.append((p["chat_id"], p["text"]))
            kb = p.get("reply_markup", {}).get("inline_keyboard")
            if kb and self.taps:
                for want in self.taps.pop(0).split(","):
                    data = next(b["callback_data"] for row in kb for b in row if b["callback_data"].endswith(":" + want))
                    self.push_callback(p["chat_id"], data, mid)
            return {"message_id": mid}
        return True

    def send_document(self, chat, path):
        self.docs.append(pathlib.Path(path).name)

    def texts_to(self, chat):
        return [t for c, t in self.sent if c == chat]


def run_bot_until_done(bot, chat, seconds=10):
    """Poll the fake server until the chat's session thread has finished."""
    end = time.time() + seconds
    while time.time() < end:
        bot.poll_once(long_poll=0)
        s = bot.sessions.get(chat)
        if s and not s[0].is_alive():
            return True
    return False


class FakeSMTP:
    """Records messages instead of sending them."""

    sent = []
    login_fails = False
    last_login = None

    def __init__(self, host, port, **kw):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, **kw):
        pass

    def login(self, user, password):
        import smtplib

        FakeSMTP.last_login = (user, password)
        if FakeSMTP.login_fails:
            raise smtplib.SMTPAuthenticationError(535, b"rejected " + password.encode())

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)
