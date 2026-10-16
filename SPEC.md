# SPEC: Lesson-Prep Agent

Status: APPROVED, implemented, and updated to match the code. Last updated 2026-10-17.

## 1. Purpose
An AI agent that prepares teaching materials for a K10–K11 beginner data-analysis course: lesson plans, worksheets, quizzes/exams with answer keys and rubrics, and optional slides, in Arabic, Hebrew and English. Used by one teacher now; built so it can be customized for other teachers later without code changes.

Course topics: data life cycle, data types, Excel functions, data visualization, data storytelling.

## 2. Two ways to run it
- **Standalone (main):** `python -m agent` runs on its own and calls an LLM API you choose. It is operated from numbered terminal menus or from a Telegram bot.
- **Inside Claude Code:** the slash commands `/lesson`, `/exam`, `/reindex` and the `rag` MCP server, following `CLAUDE.md`.

Both share the same `config/`, `knowledge/`, `memory/`, the RAG code (`rag/core.py`) and the same workflow.

## 3. Workflow (both modes)
1. **Start:** read the memory index, the teacher profile and the course outline.
2. **Intake:** the teacher picks topic, length, language, grade, level and outputs from menus. The agent asks only for what is still missing.
3. **Retrieve:** `search_knowledge` on the teacher's material; web search only for fresh examples or datasets.
4. **Outline:** the agent shows an outline that lists its sources. The teacher approves, asks for changes, or cancels. No files are created before approval.
5. **Generate:** Word, Excel and PowerPoint files, right-to-left for Arabic and Hebrew.
6. **Self-check:** timing matches the lesson length, the answer key matches the questions, the level fits the grade, RTL layout is correct, sources are cited.
7. **Save and learn:** files go to `output/<date>-<topic>/`; the agent offers to save them to the knowledge base; memory is updated with the lesson and feedback.

## 4. Standalone architecture
- **Loop (`agent/loop.py`):** calls the LLM, runs the tools it asks for, repeats until it finishes (max 40 steps, configurable). If the model replies with plain text and no tool call, a menu offers continue, type a reply, or finish. Every session is logged to `logs/` for debugging.
- **Switchable LLM (`agent/llm.py`, `config/agent.toml`):** `anthropic` (Claude API, default `claude-sonnet-5-5`) or `openai` (any OpenAI-compatible endpoint, including local models through Ollama). One neutral message format; each provider converts it.
- **Tools (`agent/tools.py`):**

| Tool | Purpose |
|---|---|
| `search_knowledge` | RAG search of the teacher's material, with `topic` and `source` filters |
| `add_to_knowledge` | copy approved output files into `knowledge/generated/` and index them |
| `web_search`, `fetch_url` | fresh examples and datasets; results are marked untrusted; only public http(s) URLs are fetched |
| `read_memory`, `write_memory` | the three memory files only |
| `ask_user` | questions shown as numbered choices (or buttons), plus "Type my own answer" |
| `create_docx`, `create_xlsx`, `create_pptx` | file generation (python-docx, openpyxl, python-pptx) with RTL support (`agent/docs.py`) |

- **Prompt:** `config/system-prompt.md` plus the teacher profile, course outline and memory index, assembled at start.
- **Channels (`agent/channel.py`):** one interface (say, status, choose, choose_many, text, send_files). The menus, wizards, `ask_user` and the loop only use it, so they run unchanged in the terminal and on Telegram.
- **Limits:** Arabic/Hebrew quality and tool use depend on the model; small local models may follow the workflow poorly. Claude API use costs money per request.

## 5. Menu-driven interface
The terminal cannot display or accept right-to-left text reliably, so the agent is operated by numbers (`agent/menu.py`).
- `python -m agent` opens the main menu: lesson, quiz/exam, index files, free chat.
- Lesson and exam wizards have submenus for unit (read from `config/course-outline.md`), length, language, grade, class level and outputs, with Back at every step and a summary before starting.
- Arabic and Hebrew lines are reordered and right-aligned for display, and brackets are shown as dashes. Set `AGENT_TERMINAL_BIDI=native` if the terminal handles RTL itself.
- Free chat is the only place where text must be typed in the terminal.
- Shortcuts without the menu: `lesson`, `exam`, `chat`, `reindex`.

## 6. Telegram trigger
- **Mechanism (`agent/telegram_bot.py`):** long polling with `getUpdates`, so no server or public address is needed. `python -m agent telegram` starts it.
- **Interface:** menus become inline buttons; the outputs multi-select uses toggle buttons with Done and Back; typing Arabic/Hebrew works natively; finished files are sent back as documents.
- **Access control:** only chat ids in `TELEGRAM_ALLOWED_IDS` can use the bot. Others get a refusal that shows only their own chat id. The token is read from `.env` and is removed from all error messages.
- **Sessions:** one session per chat in its own thread; a global lock runs one agent job at a time and tells waiting users. `/cancel` ends a session; 30 minutes of silence also ends it.
- **Testing status:** verified against a simulated Telegram server and a stand-in model, and the real token connects to the Bot API. A real end-to-end chat has not been confirmed yet: the first `/start` received no reply, and the cause was still being investigated when this was written.
- **Not yet built:** receiving documents from Telegram into `knowledge/`, and an email channel. Both fit the channel interface.

## 7. RAG design
- **Input:** PDF, DOCX, PPTX, XLSX, TXT, MD and CSV files in `knowledge/`, optionally in topic subfolders.
- **Pipeline (`rag/core.py`):** extract text, split into chunks of about 250 words (keeping file name and page, slide or sheet), embed, store in a local ChromaDB index in `rag-index/`. Only new, changed or deleted files are re-processed.
- **Embeddings:** `intfloat/multilingual-e5-large` through fastembed/ONNX, so Arabic, Hebrew and English queries match each other. It is local; no data leaves the machine. (fastembed is used because `torch` has no wheel for Intel Macs on Python 3.13.)
- **Source tags:** every chunk is tagged `teacher` or `generated` (anything under `knowledge/generated/`). Search can filter by source, and generated results are labeled so they are never treated as the teacher's original material or as verified facts.
- **Generated knowledge:** when the teacher agrees at the end of a lesson, `add_to_knowledge` copies the approved files to `knowledge/generated/<date-topic>/` and re-indexes, so a later request on the same subject finds them.
- **Rules:** knowledge base first, web second; cite file names; if nothing relevant is found, say so and never invent course facts.
- **Claude Code mode:** `rag/server.py` is a thin MCP wrapper around `rag/core.py` exposing `search_knowledge` and `reindex`.

## 8. Web search rules
- The knowledge base takes priority over the web.
- Web content is labeled with its URL; long passages are not copied.
- Web and knowledge-base text is data, not instructions.
- The agent asks before saving any downloaded dataset into `knowledge/`.

## 9. Memory management
Memory is a set of small markdown files you can read and edit by hand.

| File | Holds |
|---|---|
| `memory/INDEX.md` | One-line pointer per memory file, read at the start of every session (tracked in git) |
| `memory/teacher-preferences.md` | Default language, tone, formats, timing habits |
| `memory/class-notes.md` | Level mix, what worked and what didn't. No student names |
| `memory/lesson-log.md` | Date, topic, files produced, teacher feedback |

- **Read:** the index at session start; other files only when relevant.
- **Write:** after each lesson, new preferences and feedback the teacher stated. Not one-off details.
- **Update, don't duplicate:** edit existing entries; remove entries the teacher says are wrong.
- **Privacy:** no student names or personal data.
- **Git:** only `INDEX.md` is tracked. The other files are git-ignored and created on demand, so a copy given to another teacher starts empty.

## 10. Project layout
```
AI-AGENT/
  SPEC.md  README.md  CLAUDE.md      design, setup, Claude Code rules
  requirements.txt  Dockerfile  .env.example
  agent/
    __main__.py                      CLI, main menu, sessions
    loop.py  llm.py  tools.py        agent loop, LLM providers, tools
    docs.py                          Word/Excel/PowerPoint generators
    menu.py  ui.py  channel.py       menus, RTL display, channel interface
    telegram_bot.py                  Telegram client, channel, bot
  rag/
    core.py                          indexing and search (shared)
    server.py                        MCP wrapper for Claude Code
    requirements.txt
  config/
    agent.toml                       which LLM
    system-prompt.md                 standalone agent instructions
    teacher-profile.md               name, grades, language, formats, tone
    course-outline.md                units, pacing, objectives
  .claude/commands/                  lesson.md, exam.md, reindex.md
  .mcp.json                          registers the RAG server
  knowledge/  memory/  output/  logs/  rag-index/   git-ignored (private)
```
`AGENT_DATA_DIR` (default: the project folder) moves `knowledge/`, `memory/`, `output/`, `logs/` and `rag-index/` to another location, such as a mounted volume.

## 11. Customizing for another teacher
A new teacher gets the repository plus their own `config/teacher-profile.md` and `config/course-outline.md` (optionally `config/system-prompt.md`), their own files in `knowledge/`, and an empty `memory/`. No code changes are needed.

## 12. Safety and privacy
- Student data is never stored; only generic teaching material is produced.
- `.env`, `knowledge/`, `memory/` (except the index), `output/`, `logs/` and `rag-index/` are git-ignored, so private material and keys are not pushed to GitHub.
- The Telegram bot is allowlist-only because every request spends API credit.
- `fetch_url` refuses private and local addresses; memory and output tools only touch their own folders.
- The agent never sends email or posts anything without explicit approval, and never commits or pushes without the user's approval.

## 13. Deployment
- **Now:** runs locally on the teacher's computer; the Telegram bot works only while `python -m agent telegram` is running.
- **Later:** the `Dockerfile` runs the agent anywhere with a volume at `/data` and keys passed at run time. It has not been built or tested yet. An always-on host such as an Oracle Cloud Always Free VM fits the Telegram bot.
- **Storage:** local ChromaDB and files stay for now. Supabase (Postgres with pgvector, Storage, login for teachers) is the planned step for a hosted or sold version; only `rag/core.py` would change.

## 14. Acceptance tests
- A known document in `knowledge/` is cited in a lesson on its topic; a topic with no material gets a "nothing found" answer.
- Arabic and Hebrew queries retrieve relevant English chunks.
- An approved lesson saved to the knowledge base is found, labeled generated, on a later request about the same subject.
- `lesson` for "data types", 45 minutes, Arabic produces files with correct content, RTL layout, timing and answer key.
- Feedback such as "shorter warm-ups" given in one session shows up in the next lesson.
- Replacing `config/` and `knowledge/` changes the outputs without any other edit.
- A Telegram chat from an allowed id runs a full lesson and receives the files; a chat from any other id is refused.

## 15. Open items
- Confirm the Telegram bot end to end with the real Telegram API.
- Build and test the Docker image.
- Receive course files through Telegram into `knowledge/`.
- Email channel.
- Optional: Google Drive sync of outputs, scheduled weekly lesson prep, Canva slides.
