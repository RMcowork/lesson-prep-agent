# Lesson-Prep Agent

A Claude Code project that prepares lesson plans, worksheets, quizzes/exams (with answer keys and rubrics) and slides for a K10–K11 data-analysis course in Arabic, Hebrew and English. It uses your own course material (RAG), web search, and file-based memory. Design: see [SPEC.md](SPEC.md).

## Setup
```bash
python3 -m venv rag/.venv
rag/.venv/bin/pip install -r rag/requirements.txt
```
Open this folder in Claude Code. The `rag` MCP server is registered in `.mcp.json`. The first search downloads a multilingual embedding model (about 2 GB, once).

## Use
1. Put your course files (PDF, DOCX, PPTX, XLSX, TXT, MD) in `knowledge/`, optionally in topic subfolders.
2. `/reindex` to index them.
3. `/lesson <topic> <minutes> <language>` or `/exam <topic> <language>`.
4. Results are saved in `output/<date>-<topic>/`.

## Customize for another teacher
Edit `config/teacher-profile.md` and `config/course-outline.md`, replace the files in `knowledge/`, and start with an empty `memory/` (only `memory/INDEX.md` is tracked; the agent creates the other memory files on demand). No code changes needed.

## Privacy
`knowledge/`, `memory/`, `output/` and `rag/index/` are git-ignored.
