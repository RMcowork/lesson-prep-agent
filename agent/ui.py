"""Terminal output that stays readable for Arabic and Hebrew.

Terminals do not do right-to-left layout, so Arabic/Hebrew lines are wrapped,
letter-joined (Arabic), reordered visually and right-aligned before printing.
Only the display changes; the underlying text is untouched.
"""
import os
import re
import shutil
import textwrap

RTL_CHARS = re.compile(r"[֐-ࣿיִ-﷿ﹰ-﻿]")
BRACKETS = re.compile(r"\s*[()\[\]]\s*")
ARABIC_CHARS = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")


def format_text(text: str) -> str:
    if os.environ.get("AGENT_TERMINAL_BIDI") == "native":  # terminal already handles RTL
        return text
    try:
        import arabic_reshaper
        from bidi import get_display
    except ImportError:
        return text

    width = max(shutil.get_terminal_size((100, 20)).columns - 1, 40)
    out = []
    for line in text.splitlines():
        if not RTL_CHARS.search(line):
            out.append(line)
            continue
        # brackets flip direction unpredictably in terminals; show them as dashes
        line = BRACKETS.sub(" - ", line) if BRACKETS.search(line) else line
        line = re.sub(r"\s*-\s*([.!?،؟:;])", r"\1", line).strip(" -")
        for part in textwrap.wrap(line, width - 2) or [""]:
            if ARABIC_CHARS.search(part):
                part = arabic_reshaper.reshape(part)
            out.append(get_display(part).rjust(width))
    return "\n".join(out)


def show(text: str = "") -> None:
    print(format_text(str(text)))
