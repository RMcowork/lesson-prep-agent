"""Telegram front end: long polling (no server or public address needed).

  TelegramAPI      thin client for the Bot API (token never appears in errors)
  TelegramChannel  one chat's conversation: buttons for menus, files sent back as documents
  Bot              polls for updates, enforces the allowlist, runs one session per chat
"""
import queue
import threading
import time
import traceback
import uuid
from pathlib import Path

import httpx

from .channel import Cancelled

MAX_TEXT = 4000
BUTTON_TEXT = 60


class TelegramAPI:
    def __init__(self, token: str):
        self._base = f"https://api.telegram.org/bot{token}"
        self._client = httpx.Client(timeout=70)

    def call(self, method: str, **params):
        try:
            resp = self._client.post(f"{self._base}/{method}", json=params)
            data = resp.json()
        except Exception as exc:  # never include the URL: it contains the token
            raise RuntimeError(f"Telegram {method} failed ({type(exc).__name__})") from None
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method}: {data.get('description', 'error')}")
        return data["result"]

    def send_document(self, chat_id, path: Path):
        try:
            with open(path, "rb") as f:
                resp = self._client.post(
                    f"{self._base}/sendDocument",
                    data={"chat_id": chat_id},
                    files={"document": (Path(path).name, f)},
                )
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(f"Telegram sendDocument failed ({type(exc).__name__})") from None
        if not data.get("ok"):
            raise RuntimeError(f"Telegram sendDocument: {data.get('description', 'error')}")


def _split(text: str):
    text = str(text)
    while len(text) > MAX_TEXT:
        cut = text.rfind("\n", 0, MAX_TEXT)
        cut = cut if cut > MAX_TEXT // 2 else MAX_TEXT
        yield text[:cut]
        text = text[cut:].lstrip("\n")
    if text.strip():
        yield text


def _label(text: str) -> str:
    text = str(text)
    return text if len(text) <= BUTTON_TEXT else text[: BUTTON_TEXT - 1] + "…"


class TelegramChannel:
    def __init__(self, api, chat_id, inbox: queue.Queue, timeout=1800):
        self.api, self.chat_id, self.inbox, self.timeout = api, chat_id, inbox, timeout

    # --- output ---
    def say(self, text=""):
        for part in _split(text):
            self.api.call("sendMessage", chat_id=self.chat_id, text=part)

    def status(self, text=""):
        try:
            self.api.call("sendChatAction", chat_id=self.chat_id, action="typing")
        except RuntimeError:
            pass

    def send_files(self, paths):
        if not paths:
            self.say("No files were created.")
        for path in paths:
            self.api.send_document(self.chat_id, Path(path))

    # --- input ---
    def _wait(self):
        try:
            item = self.inbox.get(timeout=self.timeout)
        except queue.Empty:
            raise Cancelled("timed out") from None
        if item["type"] == "message" and item["text"].strip().lower() == "/cancel":
            raise Cancelled("cancelled")
        return item

    def _answer(self, item):
        try:
            self.api.call("answerCallbackQuery", callback_query_id=item["id"])
        except RuntimeError:
            pass

    def _finish_prompt(self, message_id, title, chosen):
        try:
            self.api.call(
                "editMessageText",
                chat_id=self.chat_id,
                message_id=message_id,
                text=f"{title}\n→ {chosen}",
            )
        except RuntimeError:
            pass

    def choose(self, title, options, back=None, other=None):
        token = uuid.uuid4().hex[:6]
        rows = [[{"text": _label(o), "callback_data": f"{token}:o{i}"}] for i, o in enumerate(options)]
        if other:
            rows.append([{"text": _label(other), "callback_data": f"{token}:x"}])
        if back:
            rows.append([{"text": "⬅ " + _label(back), "callback_data": f"{token}:b"}])
        sent = self.api.call(
            "sendMessage",
            chat_id=self.chat_id,
            text=title,
            reply_markup={"inline_keyboard": rows},
        )
        while True:
            item = self._wait()
            if item["type"] == "callback" and item["data"].startswith(token + ":"):
                self._answer(item)
                action = item["data"].split(":", 1)[1]
                if action == "b":
                    self._finish_prompt(sent["message_id"], title, "Back")
                    return "back", None
                if action == "x":
                    self._finish_prompt(sent["message_id"], title, other)
                    return "other", self.text("Type your answer:")
                index = int(action[1:])
                self._finish_prompt(sent["message_id"], title, options[index])
                return "option", index
            if item["type"] == "callback":
                self._answer(item)  # stale button from an earlier question
            else:
                self.say("Please tap one of the buttons above (or send /cancel).")

    def choose_many(self, title, options, defaults, back="Back"):
        token = uuid.uuid4().hex[:6]
        selected = set(defaults)

        def keyboard():
            rows = [
                [{"text": ("☑ " if i in selected else "☐ ") + _label(o), "callback_data": f"{token}:t{i}"}]
                for i, o in enumerate(options)
            ]
            rows.append(
                [
                    {"text": "⬅ " + _label(back), "callback_data": f"{token}:b"},
                    {"text": "✅ Done", "callback_data": f"{token}:d"},
                ]
            )
            return {"inline_keyboard": rows}

        sent = self.api.call(
            "sendMessage", chat_id=self.chat_id, text=title, reply_markup=keyboard()
        )
        while True:
            item = self._wait()
            if item["type"] == "callback" and item["data"].startswith(token + ":"):
                self._answer(item)
                action = item["data"].split(":", 1)[1]
                if action == "b":
                    self._finish_prompt(sent["message_id"], title, "Back")
                    return "back", None
                if action == "d":
                    chosen = ", ".join(options[i] for i in sorted(selected)) or "nothing"
                    self._finish_prompt(sent["message_id"], title, chosen)
                    return "option", sorted(selected)
                i = int(action[1:])
                selected.symmetric_difference_update({i})
                try:
                    self.api.call(
                        "editMessageReplyMarkup",
                        chat_id=self.chat_id,
                        message_id=sent["message_id"],
                        reply_markup=keyboard(),
                    )
                except RuntimeError:
                    pass
            elif item["type"] == "callback":
                self._answer(item)
            else:
                self.say("Please tap the buttons above (or send /cancel).")

    def text(self, prompt):
        self.say(prompt)
        while True:
            item = self._wait()
            if item["type"] == "callback":
                self._answer(item)
                continue
            if item["text"].strip():
                return item["text"].strip()


class Bot:
    def __init__(self, api, session_fn, allowed_ids, timeout=1800):
        self.api, self.session_fn, self.timeout = api, session_fn, timeout
        self.allowed = {int(i) for i in allowed_ids}
        self.sessions = {}  # chat_id -> (thread, inbox)
        self.offset = None

    def _send(self, chat_id, text):
        try:
            self.api.call("sendMessage", chat_id=chat_id, text=text)
        except RuntimeError:
            pass

    def handle(self, update):
        if "message" in update:
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            item = {"type": "message", "text": msg.get("text") or ""}
            if msg.get("document") or msg.get("photo"):
                item["text"] = item["text"] or ""
        elif "callback_query" in update:
            cq = update["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            item = {"type": "callback", "data": cq.get("data", ""), "id": cq["id"]}
        else:
            return

        if chat_id not in self.allowed:
            print(f"[telegram] blocked chat {chat_id}")
            if item["type"] == "message":
                self._send(
                    chat_id,
                    f"This bot is private. Your chat id is {chat_id}. "
                    "The owner can add it to TELEGRAM_ALLOWED_IDS to give you access.",
                )
            return

        session = self.sessions.get(chat_id)
        if session and session[0].is_alive():
            session[1].put(item)
            return
        if item["type"] == "callback":
            try:
                self.api.call(
                    "answerCallbackQuery",
                    callback_query_id=item["id"],
                    text="That session ended. Send /start.",
                )
            except RuntimeError:
                pass
            return
        self._start_session(chat_id)

    def _start_session(self, chat_id):
        inbox = queue.Queue()
        channel = TelegramChannel(self.api, chat_id, inbox, self.timeout)

        def run():
            try:
                self.session_fn(channel)
                channel.say("Session finished. Send /start to begin again.")
            except Cancelled as exc:
                self._send(chat_id, f"Stopped ({exc}). Send /start to begin again.")
            except Exception as exc:
                traceback.print_exc()
                self._send(
                    chat_id,
                    f"Something went wrong ({type(exc).__name__}). Send /start to try again.",
                )

        thread = threading.Thread(target=run, daemon=True)
        self.sessions[chat_id] = (thread, inbox)
        thread.start()

    def poll_once(self, long_poll=30):
        params = {"timeout": long_poll, "allowed_updates": ["message", "callback_query"]}
        if self.offset is not None:
            params["offset"] = self.offset
        for update in self.api.call("getUpdates", **params):
            self.offset = update["update_id"] + 1
            try:
                self.handle(update)
            except Exception:
                traceback.print_exc()

    def run(self):
        print("Telegram bot running. Press Ctrl+C to stop.")
        delay = 1
        while True:
            try:
                self.poll_once()
                delay = 1
            except KeyboardInterrupt:
                print("\nStopped.")
                return
            except RuntimeError as exc:
                print(f"[telegram] {exc}; retrying in {delay}s")
                time.sleep(delay)
                delay = min(delay * 2, 60)
