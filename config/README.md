# config/: everything you can change, in one place

| File | What it is |
|---|---|
| [`agent.toml`](agent.toml) | **Every tunable value** (the table below). Defaults are defined once, in `agent/settings.py`. |
| [`system-prompt.md`](system-prompt.md) | The agent's instructions: workflow, rules for notes, sources and memory. |
| [`teacher-profile.md`](teacher-profile.md) | Who the teacher is: grades, default language, formats, tone. Given to the model on every run. |
| [`course-outline.md`](course-outline.md) | The units, with objectives and pacing. Also fills the topic menu. |
| `.env` (not in git) | **Secrets and deployment variables**: keys, tokens, passwords, `AGENT_DATA_DIR`. Names are listed in [`../.env.example`](../.env.example) and in `architecture.md` under Secrets. |
| the tools | Defined once, in code: [`../agent/tools.py`](../agent/tools.py). `architecture.md` lists them and a test keeps that list honest. |

If a value is not in `agent.toml`, it is not a setting. If it is a secret, it does not belong in `agent.toml`.

## Settings in `agent.toml`

An unknown key, a wrong type or an invalid value stops the program at start with a message naming it. A missing key uses the default below. A test fails if this table, `agent.toml` and `agent/settings.py` disagree.

| Key | Default | Meaning | Used by |
|---|---|---|---|
| `provider` | `anthropic` | `anthropic` (Claude API) or `openai` (any OpenAI-compatible API, including local models) | `agent/llm.py` |
| `model` | `claude-sonnet-5-5` | Model name for that provider | `agent/llm.py` |
| `base_url` | empty | Endpoint for `openai`-style providers such as Ollama | `agent/llm.py` |
| `max_tokens` | `8000` | Most the model may write in one reply | `agent/llm.py` |
| `effort` | `high` | How hard Claude thinks: `low`, `medium`, `high`, `xhigh`, `max`, or empty for the model's own default. Sent only to Claude; the `openai` provider ignores it. A lower value is cheaper and faster, but change it only after the evals (#17) show quality holds. | `agent/llm.py` |
| `max_turns` | `40` | Most model calls in one turn of work before the agent stops | `agent/loop.py` |
| `web_results` | `6` | Results returned by one web search | `agent/tools.py` |
| `web_search_timeout_s` | `10` | Seconds for the first search attempt | `agent/tools.py` |
| `web_search_fallback_timeout_s` | `20` | Seconds for the second search attempt | `agent/tools.py` |
| `web_fetch_timeout_s` | `20` | Seconds to fetch one page | `agent/tools.py` |
| `web_fetch_chars` | `8000` | Characters of a fetched page given to the model | `agent/tools.py` |
| `email_max_mb` | `20` | Total attachment size per email | `agent/emailer.py` |
| `smtp_timeout_s` | `60` | Seconds to wait for the mail server | `agent/emailer.py` |
| `session_timeout_s` | `1800` | A Telegram session ends after this many seconds of silence | `agent/telegram_bot.py` |
| `message_chars` | `4000` | Telegram messages longer than this are split | `agent/telegram_bot.py` |
| `button_chars` | `60` | Telegram button labels are shortened to this | `agent/telegram_bot.py` |
| `telegram_http_timeout_s` | `70` | HTTP timeout for Telegram calls (longer than the 30 s long poll) | `agent/telegram_bot.py` |
| `embedding_model` | `intfloat/multilingual-e5-large` | Local model that turns text into vectors for search | `rag/core.py` |
| `chunk_words` | `250` | Words per searchable chunk | `rag/core.py` |
| `overlap_words` | `40` | Words shared by neighbouring chunks (must be smaller than `chunk_words`) | `rag/core.py` |
| `embed_batch_size` | `16` | Chunks embedded at once; small keeps memory bounded | `rag/core.py` |
| `embed_threads` | `0` | CPU threads for embedding; `0` means half the cores. The `RAG_THREADS` variable overrides it. | `rag/core.py` |
| `eval_max_turns` | `15` | An eval case that needs more model calls fails | `evals/grader.py` |
| `eval_pass_drop_allowed` | `0.05` | A pass rate this far below the baseline is a regression | `evals/run.py` |
| `eval_token_rise_allowed` | `0.5` | Input tokens this far above the baseline (50 percent) is a regression | `evals/run.py` |

## Variables in `.env` (not settings)

| Name | Why it is not in `agent.toml` |
|---|---|
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `SMTP_PASSWORD` | Secrets never go in files that are committed |
| `TELEGRAM_ALLOWED_IDS`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `EMAIL_FROM`, `EMAIL_TO` | Belong to one person's accounts |
| `AGENT_DATA_DIR` | Where the volume is mounted: a deployment decision |
| `AGENT_TERMINAL_BIDI` | Depends on the terminal in use |
| `RAG_THREADS` | Lets a host override `embed_threads` without editing the file |
