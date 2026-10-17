"""Channels: how the agent talks to the teacher (terminal or Telegram).

Every channel offers the same methods, so menus, wizards and the agent loop do not
care where the teacher is:
  say(text)                      show a message
  status(text)                   show progress (terminal prints it, Telegram shows "typing")
  choose(title, options, back, other)        -> ("option", i) | ("back", None) | ("other", text)
  choose_many(title, options, defaults, back) -> ("option", [i, ...]) | ("back", None)
  text(prompt)                   ask for free text
  send_files(paths)              deliver finished files
"""
from pathlib import Path

from . import menu, ui


class Cancelled(Exception):
    """The teacher cancelled, or stopped answering."""


class TerminalChannel:
    def __init__(self, ask=None):
        self._ask = ask or menu._input

    def say(self, text=""):
        ui.show(text)

    def status(self, text=""):
        ui.show(text)

    def choose(self, title, options, back=None, other=None, other_prompt="Type your answer:", free_text=False):
        return menu.choose(title, options, self._ask, back=back, other=other, other_prompt=other_prompt)

    def choose_many(self, title, options, defaults, back="Back"):
        return menu.choose_many(title, options, defaults, self._ask, back=back)

    def text(self, prompt):
        return self._ask(prompt.rstrip() + " ").strip()

    def send_files(self, paths):
        names = ", ".join(Path(p).name for p in paths)
        ui.show("Files: " + (names or "none created"))
