"""Switchable LLM providers.

Internal message format (provider-neutral, Anthropic-style blocks):
  {"role": "user" | "assistant", "content": [block, ...]}
  block = {"type": "text", "text": str}
        | {"type": "tool_use", "id": str, "name": str, "input": dict}
        | {"type": "tool_result", "tool_use_id": str, "content": str, "is_error": bool}
"""
import json
import os
from dataclasses import dataclass, field


@dataclass
class Reply:
    text: str = ""
    tool_calls: list = field(default_factory=list)  # [{"id","name","input"}]
    usage: dict = field(default_factory=dict)  # {"input": tokens, "output": tokens} for this call

    def to_message(self):
        blocks = []
        if self.text:
            blocks.append({"type": "text", "text": self.text})
        for call in self.tool_calls:
            blocks.append({"type": "tool_use", **call})
        return {"role": "assistant", "content": blocks}


class AnthropicProvider:
    def __init__(self, model, max_tokens, base_url="", effort=""):
        import anthropic

        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("Set ANTHROPIC_API_KEY in .env (see .env.example).")
        kwargs = {"base_url": base_url} if base_url else {}
        self.client = anthropic.Anthropic(**kwargs)
        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort

    def complete(self, system, messages, tools):
        extra = {"output_config": {"effort": self.effort}} if self.effort else {}   # GA on the Messages API, no beta header
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=messages,
            tools=[
                {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
                for t in tools
            ],
            **extra,
        )
        reply = Reply(usage={
            "input": getattr(resp.usage, "input_tokens", 0),
            "output": getattr(resp.usage, "output_tokens", 0),
        })
        for block in resp.content:
            if block.type == "text":
                reply.text += block.text
            elif block.type == "tool_use":
                reply.tool_calls.append(
                    {"id": block.id, "name": block.name, "input": dict(block.input)}
                )
        return reply


class OpenAICompatProvider:
    def __init__(self, model, max_tokens, base_url="", effort=""):   # effort is Claude-only and ignored here
        from openai import OpenAI

        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise SystemExit("Set OPENAI_API_KEY in .env (any value works for Ollama).")
        self.client = OpenAI(api_key=key, base_url=base_url or None)
        self.model = model
        self.max_tokens = max_tokens

    @staticmethod
    def _convert(system, messages):
        out = [{"role": "system", "content": system}]
        for msg in messages:
            if msg["role"] == "assistant":
                text = "".join(b["text"] for b in msg["content"] if b["type"] == "text")
                calls = [
                    {
                        "id": b["id"],
                        "type": "function",
                        "function": {"name": b["name"], "arguments": json.dumps(b["input"])},
                    }
                    for b in msg["content"]
                    if b["type"] == "tool_use"
                ]
                item = {"role": "assistant", "content": text or None}
                if calls:
                    item["tool_calls"] = calls
                out.append(item)
            else:
                texts = []
                for b in msg["content"]:
                    if b["type"] == "tool_result":
                        out.append(
                            {"role": "tool", "tool_call_id": b["tool_use_id"], "content": b["content"]}
                        )
                    elif b["type"] == "text":
                        texts.append(b["text"])
                if texts:
                    out.append({"role": "user", "content": "\n".join(texts)})
        return out

    def complete(self, system, messages, tools):
        resp = self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=self._convert(system, messages),
            tools=[{"type": "function", "function": t} for t in tools],
        )
        msg = resp.choices[0].message
        usage = getattr(resp, "usage", None)
        reply = Reply(
            text=msg.content or "",
            usage={
                "input": getattr(usage, "prompt_tokens", 0),
                "output": getattr(usage, "completion_tokens", 0),
            },
        )
        for call in msg.tool_calls or []:
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            reply.tool_calls.append({"id": call.id, "name": call.function.name, "input": args})
        return reply


def make_provider(cfg):
    """cfg is a Settings object (agent/settings.py)."""
    kind = cfg.provider
    args = (cfg.model, cfg.max_tokens, cfg.base_url, cfg.effort)
    if kind == "anthropic":
        return AnthropicProvider(*args)
    if kind == "openai":
        return OpenAICompatProvider(*args)
    raise SystemExit(f"Unknown provider '{kind}' in config/agent.toml")
