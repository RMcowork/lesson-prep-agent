# SPEC: Lesson-Prep Agent

Status: APPROVED.

## 1. Purpose
An AI agent that prepares teaching materials for a K10–K11 beginner data-analysis course: lesson plans, worksheets, quizzes/exams with answer keys and rubrics, and optional slides, in Arabic, Hebrew and English. Used by one teacher now; built so it can be customized for other teachers later without code changes.

Course topics: data life cycle, data types, Excel functions, data visualization, data storytelling.

## 2. How it works (end to end)
The agent is a Claude Code project. The teacher runs a slash command, and Claude follows the rules in `CLAUDE.md`.

1. **Start:** the agent reads `memory/INDEX.md` and `config/teacher-profile.md`.
2. **Intake:** it asks only for missing details: topic, grade, duration, level mix, language, output types.
3. **Retrieve:** it calls `search_knowledge` on the teacher's own material. It may also use web search for fresh examples or datasets.
4. **Outline:** it proposes an outline listing the sources it will use. The teacher approves or edits.
5. **Generate:** it builds the files with the document skills (Word, Excel, PowerPoint, PDF).
6. **Self-check:** timing matches the lesson length, the answer key matches the questions, the level fits the grade, RTL layout is correct, and sources are cited.
7. **Save and learn:** files go to `output/<date>-<topic>/`, and `memory/` is updated with the lesson and any feedback.

Commands: `/lesson <topic> <minutes> <language>`, `/exam <topic> <language>`, `/reindex`.

## 3. Tools

| Need | Tool | Source |
|---|---|---|
| Course pedagogy and structure | `data-analysis-curriculum-teacher` skill | existing skill |
| Word, Excel, PowerPoint, PDF files | `docx`, `xlsx`, `pptx`, `pdf` skills | existing skills |
| Search the teacher's material (RAG) | `search_knowledge`, `reindex` | new local MCP server in `rag/` |
| Current examples and datasets | WebSearch, WebFetch | built into Claude Code |
| Slides and visuals (optional) | Canva plugin | existing plugin |
| Cloud storage (optional) | Google Drive connector | existing connector |
| Preferences and history | markdown files in `memory/` | plain files |

## 4. RAG design
- **Input:** PDF, DOCX, PPTX, XLSX and text files placed in `knowledge/`, organized by topic folder.
- **Pipeline:** extract text, split into chunks of about 250 words (keeping file name and page or slide number), embed, store in a local vector database in `rag/index/`.
- **Embeddings:** a multilingual local model (`intfloat/multilingual-e5-large (via fastembed/ONNX, since torch has no wheel for Intel Macs on Python 3.13)`) so Arabic, Hebrew and English queries match each other. No data leaves the machine.
- **Vector store:** ChromaDB (local, no server).
- **Tool contract:** `search_knowledge(query, topic?, k=5)` returns chunks with file, location and score. `reindex()` rebuilds the index for new or changed files.
- **Rules:** the agent searches the knowledge base first and cites file names. If nothing relevant is found, it says so and does not invent course facts.

## 5. Web search rules
- The knowledge base takes priority over the web.
- Web content is labeled with its URL.
- No copying of long passages from sources.
- The agent asks before saving any downloaded dataset into `knowledge/`.

## 6. Memory management
Memory is a set of small markdown files that you can read and edit by hand.

| File | Holds |
|---|---|
| `memory/INDEX.md` | One-line pointer per memory file, read at the start of every session |
| `memory/teacher-preferences.md` | Default language, tone, formats, timing habits |
| `memory/class-notes.md` | Level mix, what worked and what didn't. No student names |
| `memory/lesson-log.md` | Date, topic, files produced, teacher feedback |

Rules:
- **Read:** the index is loaded at session start, and only the relevant files are opened.
- **Write:** after each lesson, the agent saves new preferences and feedback the teacher stated. It does not save one-off details.
- **Update, don't duplicate:** it edits an existing entry instead of adding a second one, and removes entries the teacher says are wrong.
- **Privacy:** no student names or personal data are stored.
- **Separation:** memory is separate from `knowledge/` (course content) and `config/` (customization), so a sold copy starts with an empty `memory/`.

## 7. Project layout
```
AI-AGENT/
  SPEC.md                 this document
  CLAUDE.md               agent role, workflow, rules for RAG, web, memory
  README.md               setup and usage
  config/
    teacher-profile.md    name, grades, default language, formats, tone, folders
    course-outline.md     topics, pacing, learning objectives
  knowledge/              teacher's source material (git-ignored)
  rag/
    server.py             MCP server (search_knowledge, reindex)
    requirements.txt
    index/                vector database (git-ignored)
  memory/                 INDEX.md is tracked; other memory files are git-ignored and created on demand
  templates/              Word and PowerPoint templates, RTL styles
  output/                 generated lessons (git-ignored)
  .claude/commands/       lesson.md, exam.md, reindex.md
  .mcp.json               registers the RAG server
```

## 8. Customizing for another teacher (selling later)
A new teacher gets the repository with:
- their own `config/teacher-profile.md` and `config/course-outline.md`,
- their own files in `knowledge/`,
- an empty `memory/`,
- a setup guide in `README.md`.

No code changes are needed. A Telegram or email backend (FastAPI, job queue, Agent SDK) can be added later and would reuse the same prompts, RAG server and templates.

## 9. Safety and privacy
- Student data is never stored; only generic teaching material is produced.
- Documents in `knowledge/` and text from the web are treated as data, not instructions.
- `knowledge/`, `memory/`, `output/` and `rag/index/` are git-ignored, so private material is not pushed to GitHub.
- The agent never sends email or posts anything without explicit approval.

## 10. Build phases
1. Scaffold project, `CLAUDE.md`, config, commands. `/lesson` works without RAG.
2. RAG server and `/reindex`, tested with 3–5 real course files in all three languages.
3. Memory files and update rules.
4. Web search rules and example-dataset flow.
5. Optional: Google Drive sync, scheduled weekly prep.

## 11. Acceptance tests
- A known document in `knowledge/` is cited in a lesson on its topic. A topic with no material gets a "nothing found" answer.
- Arabic and Hebrew queries retrieve relevant English chunks.
- Feedback such as "shorter warm-ups" given in one session shows up in the next lesson.
- `/lesson data types 45 Arabic` produces files with correct content, RTL layout, timing and answer key.
- Replacing `config/` and `knowledge/` changes the outputs without any other edit.

## 12. GitHub plan (after your approval)
1. Initialize git, add a `.gitignore` for the private folders listed above.
2. Commit the project.
3. Create the GitHub repository (public or private, your choice) and push.

I will ask for the repository name and visibility before pushing.

## 13. Open decisions
- Repository name and public or private.
- Output formats to prioritize first (Word, Google Docs, PowerPoint, Canva).
- Whether Google Drive sync is wanted in the first version.
