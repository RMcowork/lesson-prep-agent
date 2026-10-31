"""spec.md check 1: a chat that is not allowed is refused and the model is never called."""
import queue
import threading
import time

import httpx
import pytest

from agent.channel import Cancelled
from agent.telegram_bot import Bot, TelegramAPI, TelegramChannel, _label, _split
from tests.helpers import FakeTelegramAPI, run_bot_until_done

TOKEN = "123456789:AAH-secretSECRETsecretSECRETsecret_1234"


def test_a_chat_that_is_not_allowed_is_refused_and_nothing_runs():
    api, started = FakeTelegramAPI(), []
    bot = Bot(api, lambda ch: started.append(ch), allowed_ids=[111])
    api.push_text(222, "/start")
    api.push_callback(222, "abc:o0")
    bot.poll_once(long_poll=0)
    assert started == [] and 222 not in bot.sessions
    refusal = api.texts_to(222)
    assert len(refusal) == 1 and "Your chat id is 222" in refusal[0]       # only its own id; no callback gets a reply


def test_an_allowed_chat_gets_a_session_buttons_and_a_goodbye():
    api, chosen = FakeTelegramAPI(taps=["o1"]), []

    def session(ch):
        chosen.append(ch.choose("Pick", ["A", "B"], back="Back"))

    bot = Bot(api, session, allowed_ids=[111])
    api.push_text(111, "/start")
    assert run_bot_until_done(bot, 111)
    assert chosen == [("option", 1)] and any("Session finished" in t for t in api.texts_to(111))
    assert "editMessageText" in api.methods and "answerCallbackQuery" in api.methods


def test_a_crash_in_a_session_is_reported_without_details():
    api = FakeTelegramAPI()

    def session(ch):
        raise ValueError("internal detail with " + TOKEN)

    bot = Bot(api, session, allowed_ids=[111])
    api.push_text(111, "/start")
    assert run_bot_until_done(bot, 111)
    last = api.texts_to(111)[-1]
    assert "Something went wrong (ValueError)" in last and TOKEN not in last and "internal detail" not in last


def test_cancel_stops_the_session():
    api = FakeTelegramAPI()
    bot = Bot(api, lambda ch: ch.text("Your name?"), allowed_ids=[111])
    api.push_text(111, "/start")
    bot.poll_once(long_poll=0)
    time.sleep(0.1)
    api.push_text(111, "/cancel")
    assert run_bot_until_done(bot, 111)
    assert any("Stopped (cancelled)" in t for t in api.texts_to(111))


def test_a_second_message_goes_to_the_running_session():
    api, got = FakeTelegramAPI(), []
    bot = Bot(api, lambda ch: got.append(ch.text("Name?")), allowed_ids=[111])
    api.push_text(111, "/start")
    bot.poll_once(long_poll=0)
    time.sleep(0.1)
    api.push_text(111, "Dana")
    assert run_bot_until_done(bot, 111) and got == ["Dana"]


def test_a_stale_button_when_no_session_is_answered_politely():
    api = FakeTelegramAPI()
    bot = Bot(api, lambda ch: None, allowed_ids=[111])
    api.push_callback(111, "old:o0")
    bot.poll_once(long_poll=0)
    assert "answerCallbackQuery" in api.methods and 111 not in bot.sessions


# --- the channel on its own -----------------------------------------------------------------------
class KeyboardAPI:
    """Remembers the last keyboard so a test can press its buttons."""

    def __init__(self):
        self.kb, self.calls, self.n = None, [], 100

    def call(self, method, **p):
        self.calls.append(method)
        if method == "sendMessage":
            self.n += 1
            self.kb = p.get("reply_markup", {}).get("inline_keyboard", self.kb)
            return {"message_id": self.n}
        return True

    def data(self, suffix):
        return next(b["callback_data"] for row in self.kb for b in row if b["callback_data"].endswith(":" + suffix))


def in_thread(fn):
    out = {}

    def run():
        try:
            out["r"] = fn()
        except Cancelled as exc:          # the channel gave up waiting: record it instead of a thread crash
            out["cancelled"] = str(exc)

    t = threading.Thread(target=run)
    t.start()
    return t, out


def wait_for_keyboard(api):
    end = time.time() + 3
    while api.kb is None and time.time() < end:
        time.sleep(0.01)


def test_a_stale_button_is_ignored_and_the_right_one_is_used():
    api, q = KeyboardAPI(), queue.Queue()
    ch = TelegramChannel(api, 1, q, timeout=5)
    t, out = in_thread(lambda: ch.choose("Pick", ["A", "B"]))
    wait_for_keyboard(api)
    q.put({"type": "callback", "data": "zzzzzz:o0", "id": "1"})        # from an earlier question
    q.put({"type": "callback", "data": api.data("o1"), "id": "2"})
    t.join(5)
    assert out["r"] == ("option", 1)


def test_typing_is_accepted_only_where_free_text_is_allowed():
    api, q = KeyboardAPI(), queue.Queue()
    ch = TelegramChannel(api, 1, q, timeout=5)
    t, out = in_thread(lambda: ch.choose("Approve?", ["Yes"], other="Type my own", free_text=True))
    wait_for_keyboard(api)
    q.put({"type": "message", "text": "add a chart section"})
    t.join(5)
    assert out["r"] == ("other", "add a chart section")

    api2, q2 = KeyboardAPI(), queue.Queue()
    ch2 = TelegramChannel(api2, 1, q2, timeout=0.5)
    t2, out2 = in_thread(lambda: ch2.choose("Which unit?", ["A"], other="Add a new topic"))
    wait_for_keyboard(api2)
    q2.put({"type": "message", "text": "random chatter"})
    t2.join(5)
    assert "r" not in out2 and out2["cancelled"] == "timed out"        # typing was ignored; the menu timed out instead


def test_multi_select_toggles_then_done():
    api, q = KeyboardAPI(), queue.Queue()
    ch = TelegramChannel(api, 1, q, timeout=5)
    t, out = in_thread(lambda: ch.choose_many("Create?", ["a", "b", "c"], {0}))
    wait_for_keyboard(api)
    q.put({"type": "callback", "data": api.data("t2"), "id": "1"})     # add c
    q.put({"type": "callback", "data": api.data("t0"), "id": "2"})     # remove a
    q.put({"type": "callback", "data": api.data("d"), "id": "3"})
    t.join(5)
    assert out["r"] == ("option", [2]) and "editMessageReplyMarkup" in api.calls


def test_silence_ends_the_session_with_a_timeout():
    ch = TelegramChannel(KeyboardAPI(), 1, queue.Queue(), timeout=0.1)
    with pytest.raises(Cancelled, match="timed out"):
        ch.text("Name?")


def test_no_files_says_so():
    api = FakeTelegramAPI()
    TelegramChannel(api, 7, queue.Queue()).send_files([])
    assert api.texts_to(7) == ["No files were created."]


def test_long_messages_are_split_under_the_telegram_limit():
    text = "\n".join(f"line {i}" for i in range(2000))
    parts = list(_split(text))
    assert len(parts) > 1 and all(len(p) <= 4000 for p in parts)
    assert "".join(parts).replace("\n", "") == text.replace("\n", "")


def test_button_labels_are_shortened():
    assert len(_label("x" * 200)) <= 60 and _label("short") == "short"


# --- the token never leaks ------------------------------------------------------------------------
def test_the_token_never_appears_in_errors(monkeypatch):
    api = TelegramAPI(TOKEN)

    def boom(url, **kw):
        raise httpx.ConnectError(f"cannot reach {url}")

    monkeypatch.setattr(api._client, "post", boom)
    with pytest.raises(RuntimeError) as e:
        api.call("getMe")
    assert TOKEN not in str(e.value) and e.value.__cause__ is None and "ConnectError" in str(e.value)


def test_a_rejected_request_reports_the_reason_not_the_url(monkeypatch):
    api = TelegramAPI(TOKEN)

    class R:
        def json(self): return {"ok": False, "description": "Bad Request: chat not found"}

    monkeypatch.setattr(api._client, "post", lambda url, **kw: R())
    with pytest.raises(RuntimeError, match="chat not found") as e:
        api.call("sendMessage", chat_id=1, text="x")
    assert TOKEN not in str(e.value)
