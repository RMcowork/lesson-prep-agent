# practice.md: how a ticket is worked

The rules Claude Code (or a person) follows. Every ticket runs through the same eight steps. Numbered, concrete, no adjectives. Skip a step once and the next bug has no trail to follow.

Files that define the work: [spec.md](spec.md) (what), [architecture.md](architecture.md) (how and why), this file (the loop), `tests/` and `evals/` (proof).

## The loop, on every ticket

1. **Read the issue.** Restate it in one line. Stop if it is outside [spec.md](spec.md).
2. **Plan.** 3 to 5 lines, naming the files you will touch. Wait for approval.
3. **Branch.** `git checkout -b 11-daily-spend-cap` (ticket number, then a short name).
4. **Build** the smallest change that meets the ticket's "done when" lines.
5. **Test.** Run `pytest -m "not e2e"`. Add the ticket's test. Run the evals if the prompt, the tools or the model changed (see below).
6. **Docs.** Update [architecture.md](architecture.md) if a decision changed (add a row to Decisions); update [spec.md](spec.md) if a requirement changed.
7. **Commit.** `Add daily spend cap (#11)`. One ticket, one commit.
8. **Pull request** with the three numbers pasted in (see below). A bug found on the way becomes a **new issue**, labelled `bug` and linked back; it is not quietly fixed in the wrong commit.

**Never:** edit `.env`; touch `knowledge/`, `memory/`, `output/` or `logs/` (the teacher's private data); push to `main`; skip step 5; commit a secret; merge on red.

## When to run what (step 5)

| You changed | Run |
|---|---|
| Any code | `pytest -m "not e2e"` (free, fast, model mocked) |
| `config/system-prompt.md`, tool definitions in `agent/tools.py`, `agent/llm.py`, `config/agent.toml` (model, effort) | the tests **and** `python -m evals.run` (real model, costs tokens) |
| `agent/menu.py`, `agent/telegram_bot.py` flows | the tests, plus `pytest -m e2e` before a release |
| Only documents | the tests (they check that the documents agree with the code) |

Change the prompt: run the evals. Change the code: run the tests. Change both and you will, often: run both.

## The three numbers in every pull request

1. **Tests passed:** for example `71 passed, 0 failed, 1 skipped`.
2. **Eval pass rate against the baseline:** for example `27/30 (baseline 27/30)`. If the evals were not needed, write `evals not needed: <why>`.
3. **Tokens per eval run:** for example `212k in / 14k out (baseline 205k / 14k)`. A jump is a regression too.

When the numbers are in the PR, the review takes five minutes.

## Board

GitHub Project **Lesson-Prep Agent**, three columns: **To do**, **In progress**, **Done**. Every card is an issue. Milestones group them:

| Milestone | Meaning |
|---|---|
| v1 Foundation | The agent is safe to rely on: guard-rails, limits, tests, evals |
| v2 Data and dashboard | Database, dashboard, more input types |
| v3 More triggers | Email in, schedule, webhook |

A ticket has: **Title**, **Milestone**, **Label** (`enhancement`, `bug`, `documentation`, `test`, `eval`, `ci`, `process`, `cost`, `privacy`), **Why** (a spec.md section), **Done when** (lines a stranger can check), **Test** (a file or eval ids), **Out of scope**. A ticket is one change small enough to review in five minutes and to revert. If a "done when" line cannot become a test, the ticket is not specific enough yet.

## Branches, pull requests and review (even solo)

- **`main` is what runs.** No direct pushes; a change reaches it only through a pull request. If `main` is broken, the product is broken.
- **One branch per ticket**, named for it: `11-daily-spend-cap`, `18-fix-web-search`. Delete the branch after it merges; history keeps everything.
- **The pull request carries** the diff, the three numbers, the issue link (`Closes #n`) and the reason. Review it yourself on a different day, or ask Claude Code to review it against this checklist.
- **Merge only when the gate is green** (`.github/workflows/ci.yml`: tests, secret scan, evals when needed). Red means not merged, never "merge and fix later".

**Review checklist:** does it meet every "done when" line? Is the ticket's test there, and would it fail without the change? Do the three numbers hold? Is a secret, a private path or student data anywhere in the diff? Is `architecture.md` still true? Did a bug appear that deserves its own issue?

## The gate

| If this goes red | Do this |
|---|---|
| Tests fail | Fix the code in the same branch. Never skip a test to get green. |
| Eval score drops (for example 27 of 30 became 22) | Open the failing cases: which tool, which wording. Usually one prompt sentence. If unsure, revert the prompt and keep the code. |
| Tokens per eval run jump | Check effort, model, and whether history is still capped. Cost is a regression too. |
| Secret scan finds anything | Rotate the key first, then clean history, then fix the cause. |

## Definition of Done

The ticket's "done when" lines pass, its test exists, the gate is green, the docs agree with the code, and the PR is merged with its issue closed.
