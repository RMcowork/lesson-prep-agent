"""The agent loop: call the LLM, run the tools it asks for, repeat until it finishes."""
import json
from pathlib import Path

from .tools import ToolRunner

def _save_log(log_path, messages):
    if log_path:
        try:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)
            Path(log_path).write_text(json.dumps(messages, ensure_ascii=False, indent=2))
        except OSError:
            pass


def run_agent(
    provider,
    system: str,
    task: str,
    runner: ToolRunner,
    max_turns: int = 40,
    interactive: bool = True,
    log_path=None,
    messages=None,
):
    """Run until the model finishes. Pass `messages` to continue an earlier conversation
    (for example to apply the teacher's requested changes).

    When the model replies with text and no tool call, an interactive session shows a
    menu (continue / type a reply / finish). This covers questions the model asks in plain
    text instead of through `ask_user`.
    """
    ch = runner.channel
    block = {"type": "text", "text": task}
    if messages is None:
        messages = [{"role": "user", "content": [block]}]
    elif messages[-1]["role"] == "user":  # a previous run stopped mid-way: keep roles alternating
        messages[-1]["content"].append(block)
    else:
        messages.append({"role": "user", "content": [block]})
    for _ in range(max_turns):
        reply = provider.complete(system, messages, runner.tools)
        messages.append(reply.to_message())
        _save_log(log_path, messages)
        if reply.text:
            ch.say(reply.text)
        if not reply.tool_calls:
            if not interactive:
                return messages
            kind, value = ch.choose("What next?", ["Yes, continue", "Type a reply"], back="Finish")
            if kind == "back":
                return messages
            answer = "Yes, continue." if value == 0 else ch.text("Your reply:").strip()
            if not answer:
                return messages
            messages.append({"role": "user", "content": [{"type": "text", "text": answer}]})
            continue
        results = []
        for call in reply.tool_calls:
            ch.status(f"  [tool] {call['name']}")
            try:
                output, is_error = runner.run(call["name"], call["input"]), False
            except Exception as exc:  # report the error to the model so it can recover
                output, is_error = f"Error: {exc}", True
                ch.status(f"  [tool error] {call['name']}: {exc}")
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call["id"],
                    "content": str(output),
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": results})
        _save_log(log_path, messages)
    ch.say("Stopped: reached the maximum number of steps.")
    return messages
