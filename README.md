# Lesson-Prep Agent

An AI agent that prepares lesson plans, worksheets, quizzes/exams (with answer keys and rubrics) and slides for a K10–K11 data-analysis course in Arabic, Hebrew and English. It uses your own course material (RAG), web search, and file-based memory. Design: see [SPEC.md](SPEC.md) for what is built, and [Architecture.md](Architecture.md) for the full system design (triggers, data flow, database, dashboard, deployment).

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
3. Pick from the numbered menus: lesson or exam, topic, length, language, grade, level, outputs and whether the agent may search the web. Enter `0` to go back.
4. The agent's own questions (outline approval and so on) are numbered choices too, so you never have to type Arabic or Hebrew. You can also add your own instructions in the menu ("Any special instructions?") and, on Telegram, simply type an answer instead of tapping a button.
5. After the files arrive, choose **Request changes or reply to the agent** and write what you want in your own words ("shorter warm-up", "add 3 questions", "use football examples"). The agent applies your notes, rewrites the affected files and sends the updated ones. Repeat as often as you like. Earlier versions are kept in `previous-versions/` inside the output folder.
6. Choose **Looks good, finish** when you are happy. Only then does the agent ask whether to save the files to the knowledge base, and it records your preferences and corrections in memory.
7. Files are written to `output/<date>-<topic>/`; session logs go to `logs/`.

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

## Your own topics
- In the topic menu choose **Add a new topic**, type its name and (optionally) a short outline. The agent builds the lesson on that outline.
- You are asked whether to save it. If you say yes, it appears in the topic list next time, marked as yours.
- **Manage my topics** (main menu) lets you add, remove and list your own topics. They are stored in `topics.json` in your data folder, which is private and not committed. The units in `config/course-outline.md` are always listed too, and their learning objectives are given to the agent.
- Tip: type long outlines on Telegram; the terminal takes one line.

## Web search
Each lesson or exam asks "Search the web for fresh examples if needed?" (default: no, use my files only). If you answer no, the web tools are removed for that session, so the agent cannot search at all. If you answer yes, it searches only for examples your files lack. Search uses the free DuckDuckGo service and can be unreliable for Arabic and Hebrew; the agent continues without results if it fails.

## Email the files
When a lesson or exam is finished, the agent asks "Email these files?" (in the terminal and on Telegram). Nothing is sent unless you say yes, and you choose the recipient: one of your saved addresses or one you type. The model itself has no email tool.

Setup in `.env` (see `.env.example`):
1. For Gmail, turn on 2-step verification, then create an **App Password** at https://myaccount.google.com/apppasswords. Use it as `SMTP_PASSWORD` (never your normal password).
2. Set `SMTP_USER` to your address, and optionally `EMAIL_TO` to the address(es) you want offered in the menu.
3. Other providers: set `SMTP_HOST` and `SMTP_PORT` (465 uses SSL; other ports use STARTTLS).

If `SMTP_USER` and `SMTP_PASSWORD` are empty, the email question is skipped. Files are attached up to about 20 MB in total.

## Generated knowledge
When a lesson is finished, the agent asks whether to save the files to the knowledge base. If you say yes, they are copied to `knowledge/generated/` and indexed, and later requests on the same subject can find and reuse them. Results are labeled as generated, so they are not mistaken for your original material.

## Scanned PDFs
Files that contain only page images (scans) have no text to search. After indexing, the agent lists any such files in a WARNING. Replace them with a text version, or run OCR on them first (for example with `ocrmypdf`), then index again.

## Docker (deploying later)
The image runs the agent anywhere. It holds only code: your `.env`, knowledge files, memory, topics, logs and index are excluded by `.dockerignore`, so you supply them at run time. It runs as a non-root user, and everything private lives in a volume mounted at `/data` (`AGENT_DATA_DIR`).
```bash
docker build -t lesson-prep-agent .
# Menu (interactive):
docker run -it --env-file .env -v agent-data:/data lesson-prep-agent
# Telegram bot (keeps running):
docker run -d --restart unless-stopped --env-file .env -v agent-data:/data lesson-prep-agent telegram
# Index files you put in the volume's knowledge/ folder:
docker run --rm -v agent-data:/data lesson-prep-agent reindex
```
Indexing uses half of the CPU cores by default (set `RAG_THREADS` to change it) and frees the model's memory afterwards; `docker run --cpus=4` also caps the container. The image is about 1 GB. The first index or search downloads the embedding model (about 2 GB) into the volume, once. Pass `--env-file .env` only when you run the container; never copy `.env` into an image.

## Customize for another teacher
Edit `config/teacher-profile.md`, `config/course-outline.md` (and optionally `config/system-prompt.md`), replace the files in `knowledge/`, and start with an empty `memory/` (only `memory/INDEX.md` is tracked; memory files are created on demand). No code changes needed.

## Privacy
`knowledge/`, `memory/`, `output/`, `rag-index/` and `.env` are git-ignored.
