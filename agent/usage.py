"""Token counting: how much each job asks of the model (spec.md §6, tickets #7 and #8)."""
from dataclasses import dataclass


@dataclass
class Meter:
    """Adds up the tokens of every model call in a job."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, usage: dict) -> None:
        self.calls += 1
        self.input_tokens += int(usage.get("input", 0) or 0)
        self.output_tokens += int(usage.get("output", 0) or 0)

    def as_dict(self) -> dict:
        return {"calls": self.calls, "input_tokens": self.input_tokens, "output_tokens": self.output_tokens}
