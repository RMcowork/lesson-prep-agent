# spec.md: what it does, for whom, how many

**Product:** Lesson-Prep Agent. It prepares lesson plans, worksheets, quizzes, exams (with answer keys and rubrics) and slides for a K10–K11 beginner data-analysis course, in Arabic, Hebrew and English, from the teacher's own material.

Every line below is something Claude Code would otherwise guess. Numbers, not adjectives. Ticket numbers (`#n`) point to the GitHub Project board; `[built]` means it already exists in the code.

Related files: [architecture.md](architecture.md) (how, where, why) · [practice.md](practice.md) (how a ticket is worked) · `tests/` and `evals/` (how "Done" is proven). What is built today is described in [docs/implementation.md](docs/implementation.md).

---

## 1. Users

| Question | Answer |
|---|---|
| Who | One teacher today (the owner). Up to **10 people** later, such as a department, each with their own chat. |
| How many at once | Up to **3 people** working at the same time; **1 agent job** runs at a time, the rest wait their turn. |
| From where | **Telegram on a phone** (main), a **terminal menu** on the laptop. Files can also be **emailed** after approval. |
| How often | A few lessons or exams per week per teacher. Peak: before term, **at most 5 jobs per day** per teacher. |
| Languages | Arabic, Hebrew, English. Right-to-left files and chat must be correct. |
| Who may use it | Only chat ids in the allowlist. Anyone else is refused. |
| Shape of the system | **First row of the size ladder: one service, one volume, one allowlist.** More teachers = a copy of the same deployment with its own keys and data, not a rewrite. |

## 2. Jobs

The three things it must do, as sentences.

1. **Lesson.** Prepare a lesson package (plan, worksheet, quiz, slides, Excel task) on a topic, grounded in the teacher's own files, and keep revising it from the teacher's notes until the teacher says it is good.
2. **Exam.** Prepare a quiz or exam with an answer key and a grading rubric, with the same revision loop.
3. **Knowledge.** Index the teacher's files, keep approved lessons searchable for next time, and remember the teacher's preferences between sessions.

## 3. Not in v1

The list that keeps it small.

- Public access, strangers, sign-up.
- Several teachers' data in one deployment (multi-tenant), accounts, payments.
- A web dashboard and a database (designed in [docs/target-system-design.md](docs/target-system-design.md), tickets #23, #24).
- Starting a job by inbound email, a schedule or a webhook (#25, #26, #27).
- OCR for scanned PDFs (#21) and receiving files through Telegram (#20).
- Anything about students: no student names, no grading of student work.
- A mobile app.
- Deployment and operations (pipeline, environments, monitoring, runbook). Out of scope for this phase; [architecture.md](architecture.md) records where the pieces would run.

## 4. Speed

Decided per job, not per app. "Real-time" is only where a person is watching.

| Job step | Mechanism | Target |
|---|---|---|
| Menu step (topic, language, buttons) | Instant, no model | under **1 s** |
| Acknowledge a request | Reply "Working on it" | under **2 s** |
| Generate a lesson or exam | **Background job**; typing indicator; files delivered when done | first files within **5 min** |
| Apply the teacher's change notes | Background job | updated files within **3 min** |
| Search the knowledge base | Direct call | under **10 s** (first call loads the model) |
| Index the knowledge base | **Background batch**; reports progress when done | minutes (first run downloads a 2.2 GB model once) |
| Email the files | Direct call, only after approval | under **30 s** |

Streaming is not used: the output is files, not a chat reply. A scheduled weekly draft (#26) would be the "nobody waits" case.

## 5. Data

| Data | Where | Kept | Sensitive? |
|---|---|---|---|
| Teacher's source files | `knowledge/` on the volume | until the teacher deletes them | Private; may be copyrighted course material |
| Search index (chunks, embeddings) | `rag-index/` | can be rebuilt any time | Derived from the files above |
| Generated files and earlier versions | `output/`, `previous-versions/` | until the teacher deletes them | The teacher's own work |
| Preferences, class notes, lesson log | `memory/` | until edited | Never student names or personal data |
| Topic list | `topics.json` | until removed | No |
| Session logs (full conversations) | `logs/` | **90 days** (#16; today: forever) | Yes: contain lessons and notes |
| Keys and passwords | `.env` locally, host variables later | rotated, never in Git | **Yes**: model key, bot token, SMTP password |

- Student personal data is never requested, stored or logged.
- Parts of the teacher's files are sent to the model provider as context for each job. The provider's retention terms apply; do not index material that may not be shared.
- Private folders and `.env` are git-ignored and excluded from the container image.

## 6. Limits

A limit without a number is a wish. Three layers, three owners (details in [architecture.md](architecture.md#limits)).

| Layer | Limit | Status |
|---|---|---|
| Users → us | Allowlist of chat ids | `[built]` |
| Users → us | **30 messages per hour** per chat id | #12 |
| Users → us | Files **20 MB** in total per email; uploads **20 MB** each | email `[built]`; uploads #20 |
| Us → the model | Up to **3 retries** with waits of 2 s, 8 s, 30 s on 429 / 5xx, then "try again in a minute" | #13 |
| Us → the model | **40 tool steps** per turn; **8,000 output tokens** per call | `[built]` |
| Us → the wallet | **$3 per day**, counted from tokens per call; stop and tell the teacher "back tomorrow" | #11 (token counting #10) |
| Us → the wallet | **150,000 input tokens** per job (measured: median ~78,000, max ~107,000) | #11 |
| Concurrency | **1 agent job** at a time | `[built]` |
| Sessions | A chat session ends after **30 min** of silence | `[built]` |
| Web | Web search is **off by default**; 6 results per search; pages cut at 8,000 characters | `[built]` |

## 7. Done

Twelve checks a stranger could run. Each becomes a test (code) or an eval (agent behaviour).

| # | Check | Proven by | Status |
|---|---|---|---|
| 1 | A message from a chat id that is not allowed is refused, and the model is never called | `tests/test_telegram.py` | automated |
| 2 | Every wizard step has Back; Back on the first step returns to the main menu | `tests/test_menu.py` | automated |
| 3 | With web search off, the model is not offered web tools and a web call is refused | `tests/test_tools.py`, evals `web-off-*` | automated |
| 4 | A change note rewrites the file under the same name, keeps the old version, and the final step runs only after the teacher finishes | `tests/test_session.py`, evals `revise-*` | automated |
| 5 | No file is created before the teacher approves the outline | evals `approval-*` | automated (agent) |
| 6 | When the knowledge base has nothing relevant, the agent says so and invents no source | evals `honest-*` | automated (agent) |
| 7 | Saved lessons are found later, labelled "generated", and the source filter works | `tests/test_rag.py` | automated |
| 8 | A scanned PDF is reported in a WARNING and is not marked as indexed | `tests/test_rag.py` | automated |
| 9 | Email is sent only after a yes, only to the chosen address, and an error never shows the password | `tests/test_email.py` | automated |
| 10 | No key, token or password appears in any file or in any commit | `tests/test_secrets.py` (greps the repo and its history) | automated |
| 11 | Arabic and Hebrew files are right-to-left (Word, Excel, PowerPoint) | `tests/test_docs.py`, evals `rtl-*` | automated |
| 12 | After the daily spend cap, a new job is refused with "back tomorrow" | `tests/test_limits.py` | **skipped until #11** |

A change is Done when its ticket's "done when" lines pass, the gate in [practice.md](practice.md) is green, and the relevant lines above still pass.
