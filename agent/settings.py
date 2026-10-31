"""Every tunable value has ONE home: config/agent.toml. The default of each value is defined here, once.

Secrets and paths are not settings: they stay in .env and AGENT_DATA_DIR (architecture.md, Secrets).
All settings are documented in config/README.md; tests fail if the file, this class and that document disagree.
"""
import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "agent.toml"
PROVIDERS = ("anthropic", "openai")
EFFORTS = ("", "low", "medium", "high", "xhigh", "max")   # "" = leave the provider default


@dataclass(frozen=True)
class Settings:
    # --- which model ---
    provider: str = "anthropic"
    model: str = "claude-sonnet-5-5"
    base_url: str = ""
    max_tokens: int = 8000
    effort: str = "high"
    max_turns: int = 40
    # --- memory ---
    memory_entry_chars: int = 600
    memory_context_chars: int = 4000
    # --- web tools ---
    web_results: int = 6
    web_search_timeout_s: int = 10
    web_search_fallback_timeout_s: int = 20
    web_fetch_timeout_s: int = 20
    web_fetch_chars: int = 8000
    # --- email ---
    email_max_mb: int = 20
    smtp_timeout_s: int = 60
    # --- telegram ---
    session_timeout_s: int = 1800
    message_chars: int = 4000
    button_chars: int = 60
    telegram_http_timeout_s: int = 70
    # --- search index ---
    embedding_model: str = "intfloat/multilingual-e5-large"
    chunk_words: int = 250
    overlap_words: int = 40
    embed_batch_size: int = 16
    embed_threads: int = 0
    # --- evals ---
    eval_max_turns: int = 15
    eval_pass_drop_allowed: float = 0.05
    eval_token_rise_allowed: float = 0.5


FIELD_NAMES = [f.name for f in fields(Settings)]


def _problems(values: dict) -> list:
    """Everything wrong with the values, as readable sentences. Empty means valid."""
    out = []
    for f in fields(Settings):
        v = values[f.name]
        want = type(f.default)
        if want is float:
            ok = isinstance(v, (int, float)) and not isinstance(v, bool)
        else:
            ok = isinstance(v, want) and not (want is int and isinstance(v, bool))
        if not ok:
            out.append(f"{f.name} must be {want.__name__}, got {v!r}")
        elif want is int and f.name != "embed_threads" and v < 1:
            out.append(f"{f.name} must be at least 1, got {v}")
    if not out:
        if values["provider"] not in PROVIDERS:
            out.append(f"provider must be one of {list(PROVIDERS)}, got {values['provider']!r}")
        if values["effort"] not in EFFORTS:
            out.append(f"effort must be one of {[e for e in EFFORTS if e]} or empty, got {values['effort']!r}")
        if not values["model"]:
            out.append("model must not be empty")
        if values["overlap_words"] >= values["chunk_words"]:
            out.append("overlap_words must be smaller than chunk_words")
        if values["embed_threads"] < 0:
            out.append("embed_threads must be 0 (automatic) or more")
        if not 0 <= values["eval_pass_drop_allowed"] <= 1:
            out.append("eval_pass_drop_allowed must be between 0 and 1")
    return out


def load(path: Path = CONFIG, env=None) -> Settings:
    """Read config/agent.toml, fill in defaults, check everything, and stop with a clear message if it is wrong."""
    env = os.environ if env is None else env
    raw = tomllib.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else {}
    unknown = sorted(set(raw) - set(FIELD_NAMES))
    if unknown:
        raise SystemExit(f"Unknown setting(s) in {Path(path).name}: {', '.join(unknown)}. See config/README.md for the list.")
    values = {f.name: raw.get(f.name, f.default) for f in fields(Settings)}
    if env.get("RAG_THREADS"):                       # a deployment can still tune threads without editing the file
        try:
            values["embed_threads"] = int(env["RAG_THREADS"])
        except ValueError:
            raise SystemExit(f"RAG_THREADS must be a whole number, got {env['RAG_THREADS']!r}") from None
    problems = _problems(values)
    if problems:
        raise SystemExit("Invalid settings in " + Path(path).name + ":\n  " + "\n  ".join(problems))
    return Settings(**values)


_current = None


def get() -> Settings:
    """The settings for this process, loaded once. Modules read values from here at call time."""
    global _current
    if _current is None:
        _current = load()
    return _current


def use(settings: Settings) -> None:
    """Replace the process-wide settings (used by the CLI after loading, and by tests)."""
    global _current
    _current = settings
