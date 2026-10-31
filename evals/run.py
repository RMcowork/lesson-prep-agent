"""Run the evals: the same input, a good-enough output (practice.md, spec.md §7).

  python -m evals.run                   real model from config/agent.toml (costs tokens; needs the API key)
  python -m evals.run --baseline        the same, and mark the result as the new baseline in evals/history.csv
  python -m evals.run --mock            scripted stand-in model: proves the harness works, costs nothing
  python -m evals.run --validate        only check that cases.yaml is well formed
  python -m evals.run --estimate        what a real run would roughly cost, without spending anything

Exit code 1 means a regression against the baseline (pass rate down more than 5 points, or tokens up more than 50%).
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import agent.__main__ as app  # noqa: E402
from agent import settings  # noqa: E402
from agent.loop import run_agent  # noqa: E402
from agent.tools import ToolRunner  # noqa: E402
from agent.usage import Meter  # noqa: E402
from evals import grader  # noqa: E402

CASES = ROOT / "evals" / "cases.yaml"
HISTORY = ROOT / "evals" / "history.csv"
COLUMNS = ["date", "git_sha", "provider", "model", "cases", "runs_per_case", "runs_passed", "runs_total", "pass_rate",
           "tokens_in", "tokens_out", "baseline", "note"]


class EvalChannel:
    """The scripted teacher: answers ask_user from the case, otherwise approves and says no to saving."""

    def __init__(self, script):
        self.script, self.asks, self.said = list(script), [], []

    def say(self, text=""):
        self.said.append(str(text))

    def status(self, text=""):
        pass

    def send_files(self, paths):
        pass

    def text(self, prompt):
        self.asks.append({"question": prompt, "options": []})
        return self.script.pop(0) if self.script else "ok"

    def choose(self, title, options, back=None, other=None, other_prompt="", free_text=False):
        self.asks.append({"question": title, "options": list(options)})
        if self.script:
            item = self.script.pop(0)
            for i, o in enumerate(options):
                if o.lower().startswith(item.lower()) or item.lower() in o.lower():
                    return "option", i
            return "other", item
        wanted = ("no",) if "knowledge" in title.lower() else ("approve", "yes", "ok", "continue", "looks good", "go ahead")
        for i, o in enumerate(options):
            if o.lower().startswith(wanted):
                return "option", i
        return "option", 0


class StubRunner(ToolRunner):
    """Real file and memory tools; canned knowledge and web results; every call recorded."""

    def __init__(self, out_dir, channel, case):
        super().__init__(out_dir, channel, allow_web=bool(case.get("web")) or "web search is allowed" in case["task"].lower())
        self.case, self.log = case, []

    def run(self, name, args):
        entry = {"name": name, "input": args, "error": False}
        self.log.append(entry)
        try:
            return super().run(name, args)
        except Exception:
            entry["error"] = True
            raise

    def _t_search_knowledge(self, query, topic="", k=5, source=""):
        kb = self.case.get("knowledge", "No relevant material found.")
        if isinstance(kb, str):
            return kb
        return "\n\n---\n\n".join(f"[{c['file']} | {c['location']} | teacher material | score 0.9]\n{c['text']}" for c in kb)

    def _t_web_search(self, query):
        return "UNTRUSTED WEB RESULTS:\n\n" + self.case.get("web_results", "No results.")

    def _t_fetch_url(self, url):
        return "UNTRUSTED WEB CONTENT:\n" + self.case.get("web_results", "")

    def _t_add_to_knowledge(self, filenames):
        return "Saved (stub)."


def seed_conversation(case, runner):
    """Earlier turns for revise and final cases: the files already exist and the teacher has spoken."""
    messages = [{"role": "user", "content": [{"type": "text", "text": case["task"]}]}]
    blocks = []
    for i, f in enumerate(case["seed_files"]):
        args = {"filename": f["name"], "title": f["title"], "rtl": bool(f.get("rtl")),
                "blocks": [{"type": "paragraph", "text": f["text"]}]}
        runner.run("create_docx", args)
        blocks.append({"type": "tool_use", "id": f"seed{i}", "name": "create_docx", "input": args})
    runner.log.clear()                                                   # seeding is not the agent's work
    messages.append({"role": "assistant", "content": blocks})
    messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": b["id"], "content": f"Created {b['input']['filename']}.docx", "is_error": False} for b in blocks]})
    messages.append({"role": "assistant", "content": [{"type": "text", "text": "Created the files."}]})
    for note in case.get("history_notes", []):
        messages.append({"role": "user", "content": [{"type": "text", "text": note}]})
        messages.append({"role": "assistant", "content": [{"type": "text", "text": "Changed as you asked."}]})
    return messages


def run_case(case, provider, workdir):
    out_dir = Path(workdir) / "output"
    channel = EvalChannel(case.get("teacher", []))
    runner = StubRunner(out_dir, channel, case)
    app.DATA = Path(workdir)
    from agent import memory
    memory.MEMORY_DIR = Path(workdir) / "memory"
    for fname, text in (case.get("memory") or {}).items():          # what the agent already remembers in this case
        memory.MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        (memory.MEMORY_DIR / fname).write_text(text, encoding="utf-8")
    system = app.build_system()
    phase = case.get("phase", "lesson")
    meter, messages, task = Meter(), None, case["task"]
    if phase in ("revise", "final"):
        messages = seed_conversation(case, runner)
        task = case["note"] if phase == "revise" else app.FINAL_PHASE
    try:
        out = run_agent(provider, system, task, runner, max_turns=grader.max_turns() + 1, interactive=False, messages=messages, meter=meter)
    except Exception as exc:                                              # a provider failure is a failed run, not a crash
        return {"passed": False, "fails": [f"the run crashed: {type(exc).__name__}: {str(exc)[:120]}"], "tokens": {"input": meter.input_tokens, "output": meter.output_tokens}, "calls": meter.calls}

    trace = grader.Trace(turns=meter.calls, tokens={"input": meter.input_tokens, "output": meter.output_tokens})
    trace.calls = [c for c in runner.log]
    trace.asks = channel.asks
    texts = [b["text"] for m in out if m["role"] == "assistant" for b in m["content"] if b["type"] == "text"]
    trace.said = "\n".join(texts + [a["question"] for a in channel.asks])
    trace.files = [p.name for p in out_dir.glob("*") if p.is_file()]
    mem = Path(workdir) / "memory"
    trace.memory = "\n".join(c["input"].get("entry", "") for c in runner.log if c["name"] == "add_memory" and not c["error"])
    fails = grader.grade(case["expect"], trace)
    return {"passed": not fails, "fails": fails, "tokens": {"input": meter.input_tokens, "output": meter.output_tokens}, "calls": meter.calls}


def load_cases(select=None, group=None):
    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    if select:
        cases = [c for c in cases if c["id"] in select]
    if group:
        cases = [c for c in cases if c["group"] == group]
    return cases


def git_sha():
    out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return out.stdout.strip() or "unknown"


def read_history():
    if not HISTORY.exists():
        return []
    with open(HISTORY, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def baseline_row(rows):
    marked = [r for r in rows if r.get("baseline") == "yes"]
    return marked[-1] if marked else None


def compare(result, base):
    """Returns (ok, messages) against the baseline row."""
    if base is None:
        return True, ["no baseline yet: run with --baseline once the prompt is in a state you trust (ticket #17)"]
    s = settings.get()
    msgs, ok = [], True
    base_rate = float(base["pass_rate"])
    if result["pass_rate"] < base_rate - s.eval_pass_drop_allowed:
        ok = False
        msgs.append(f"pass rate fell: {result['pass_rate']:.1%} against a baseline of {base_rate:.1%}")
    base_tokens = int(base["tokens_in"])
    if base_tokens and result["tokens_in"] > base_tokens * (1 + s.eval_token_rise_allowed):
        ok = False
        msgs.append(f"input tokens rose from {base_tokens} to {result['tokens_in']} (more than {s.eval_token_rise_allowed:.0%})")
    return ok, msgs or ["within the baseline"]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m evals.run", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=3, help="runs per case (default 3)")
    ap.add_argument("--cases", help="comma separated case ids")
    ap.add_argument("--group", help="only this group")
    ap.add_argument("--baseline", action="store_true", help="record this run as the baseline")
    ap.add_argument("--note", default="", help="a note for history.csv")
    ap.add_argument("--mock", help="use the scripted stand-in model; value is its mode (good, no_search, ...)", nargs="?", const="good")
    ap.add_argument("--record", action="store_true", help="write the run to history.csv (default for real runs)")
    ap.add_argument("--no-record", action="store_true", help="do not write history.csv")
    ap.add_argument("--validate", action="store_true", help="only validate cases.yaml")
    ap.add_argument("--estimate", action="store_true", help="estimate the cost of a real run using the stand-in model")
    args = ap.parse_args(argv)

    cases = load_cases(args.cases.split(",") if args.cases else None, args.group)
    problems = [p for c in cases for p in grader.validate_case(c)]
    if problems:
        print("cases.yaml has problems:\n  " + "\n  ".join(problems))
        return 2
    if args.validate:
        print(f"cases.yaml is well formed: {len(cases)} cases in {len({c['group'] for c in cases})} groups")
        return 0
    if not cases:
        print("no cases selected")
        return 2

    mode = args.mock or ("good" if args.estimate else None)
    if mode:
        from evals.mock_model import OracleModel

        provider, label = OracleModel(mode), ("mock", f"oracle-{mode}")
    else:
        os.environ.setdefault("AGENT_DATA_DIR", tempfile.mkdtemp(prefix="evals-"))
        app.load_env()
        cfg = settings.load()
        settings.use(cfg)
        provider, label = app.make_provider(cfg), (cfg.provider, cfg.model)

    per_case, totals = {}, {"input": 0, "output": 0}
    passed_runs = total_runs = 0
    for case in cases:
        results = []
        for _ in range(args.runs):
            with tempfile.TemporaryDirectory() as tmp:
                r = run_case(case, provider, tmp)
            results.append(r)
            total_runs += 1
            passed_runs += r["passed"]
            totals["input"] += r["tokens"]["input"]
            totals["output"] += r["tokens"]["output"]
        per_case[case["id"]] = results

    print(f"\n{'case':34s} runs passed")
    for case in cases:
        rs = per_case[case["id"]]
        ok = sum(r["passed"] for r in rs)
        print(f"{'OK ' if ok == len(rs) else '.. ' if ok else 'XX '}{case['id']:31s} {len(rs)}    {ok}")
        for why in sorted({f for r in rs for f in r["fails"]})[:3]:
            print(f"      - {why}")
    cases_ok = sum(all(r["passed"] for r in rs) for rs in per_case.values())
    rate = passed_runs / total_runs
    result = {"pass_rate": rate, "tokens_in": totals["input"], "tokens_out": totals["output"]}
    print(f"\nTests of the agent: {cases_ok}/{len(cases)} cases pass every run; {passed_runs}/{total_runs} runs passed ({rate:.1%})")
    print(f"Tokens for this eval run: {totals['input']:,} in / {totals['output']:,} out"
          f" ({'stand-in model, an estimate only' if mode else 'measured'})")
    print("Wording checks (rubrics) were skipped: no judge model yet (ticket #28).")

    if args.estimate:
        print("\nEstimate for a real run: the stand-in writes far less than the real model, so expect the input above to be about"
              " 1x to 2x and the output about 2x to 4x. Prices are not guessed here: multiply by the current price of the model.")
        return 0

    rows = read_history()
    ok, msgs = compare(result, baseline_row(rows))
    print("Against the baseline: " + "; ".join(msgs))

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### Evals\n- **Eval pass rate:** {passed_runs}/{total_runs} ({rate:.1%}); {'; '.join(msgs)}\n"
                    f"- **Tokens per eval run:** {totals['input']:,} in / {totals['output']:,} out\n")

    record = (args.record or not mode) and not args.no_record
    if record:
        new = not HISTORY.exists()
        with open(HISTORY, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            if new:
                w.writeheader()
            w.writerow({"date": date.today().isoformat(), "git_sha": git_sha(), "provider": label[0], "model": label[1],
                        "cases": len(cases), "runs_per_case": args.runs, "runs_passed": passed_runs, "runs_total": total_runs,
                        "pass_rate": f"{rate:.4f}", "tokens_in": totals["input"], "tokens_out": totals["output"],
                        "baseline": "yes" if args.baseline else "", "note": args.note})
        try:
            shown = HISTORY.relative_to(ROOT)
        except ValueError:                      # the history file can live elsewhere (tests)
            shown = HISTORY
        print(f"Recorded in {shown}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
