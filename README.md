# Lesson-Prep Agent

An AI agent that prepares lesson plans, worksheets, quizzes/exams (with answer keys and rubrics) and slides for a K10–K11 data-analysis course in Arabic, Hebrew and English. It uses your own course material (RAG), web search, and file-based memory. Design: see [SPEC.md](SPEC.md).

It works in two ways:
- **Standalone program** (`python -m agent ...`): runs on its own, calls an LLM API you choose.
- **Inside Claude Code**: the `/lesson`, `/exam`, `/reindex` commands and the `rag` MCP server.

## Setup
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # then add your API key
```
Choose the model in `config/agent.toml`:
- `provider = "anthropic"` (default): Claude API, needs `ANTHROPIC_API_KEY`.
- `provider = "openai"`: any OpenAI-compatible API (OpenAI, OpenRouter, or a local model via Ollama with `base_url = "http://localhost:11434/v1"`), needs `OPENAI_API_KEY` (any value for Ollama).

The first search/reindex downloads a multilingual embedding model (about 2 GB, once).

## Use (standalone)
1. Put your course files (PDF, DOCX, PPTX, XLSX, TXT, MD) in `knowledge/`, optionally in topic subfolders.
2. Start the menu: `.venv/bin/python -m agent`
3. Pick from the numbered menus: lesson or exam, unit, length, language, grade, level and outputs. Enter `0` to go back.
4. The agent's own questions (outline approval and so on) are numbered choices too, so you never have to type Arabic or Hebrew.
5. Files are written to `output/<date>-<topic>/`; session logs go to `logs/`.

Shortcuts without the menu: `python -m agent lesson "data types" 45 arabic`, `exam`, `chat`, `reindex`.

Arabic and Hebrew lines are reordered for terminals that lack right-to-left support, and brackets in those lines are shown as dashes. If your terminal supports right-to-left itself, set `AGENT_TERMINAL_BIDI=native` in `.env`.

## Telegram
Run the agent as a Telegram bot on your own computer (no server or public address needed):
1. In Telegram, talk to **@BotFather**, send `/newbot`, and copy the token it gives you.
2. Put it in `.env` as `TELEGRAM_BOT_TOKEN=...`. Keep it secret and never commit it.
3. Start the bot: `.venv/bin/python -m agent telegram`
4. Send `/start` to your bot. It replies with your chat id because you are not allowed yet. Put that number in `.env` as `TELEGRAM_ALLOWED_IDS=123456789` (comma-separated for more people) and restart the bot.
5. Send `/start` again. You get the same menus as buttons, you can type Arabic or Hebrew freely, and finished files arrive as documents in the chat.

Only chat ids in `TELEGRAM_ALLOWED_IDS` can use the bot, because every request spends API credit. `/cancel` stops the current conversation. One job runs at a time; others wait. The bot works only while the program is running on your computer.

## Generated knowledge
When a lesson is finished, the agent asks whether to save the files to the knowledge base. If you say yes, they are copied to `knowledge/generated/` and indexed, and later requests on the same subject can find and reuse them. Results are labeled as generated, so they are not mistaken for your original material.

## Deploying later
Set `AGENT_DATA_DIR` to a persistent folder (for example a mounted volume). A `Dockerfile` is included (untested):
```bash
docker build -t lesson-prep-agent .
docker run -it --env-file .env -v agent-data:/data lesson-prep-agent lesson "data types" 45 english
```

## Customize for another teacher
Edit `config/teacher-profile.md`, `config/course-outline.md` (and optionally `config/system-prompt.md`), replace the files in `knowledge/`, and start with an empty `memory/` (only `memory/INDEX.md` is tracked; memory files are created on demand). No code changes needed.

## Privacy
`knowledge/`, `memory/`, `output/`, `rag-index/` and `.env` are git-ignored.
