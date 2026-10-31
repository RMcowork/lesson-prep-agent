# evals/

Evals judge the agent, tests judge the code (practice.md). An eval is a list of inputs, what a good answer must contain,
and a grader. Run it before and after every change to the prompt, the tools or the model, and keep the score.

| File | What it is |
|---|---|
| `cases.yaml` | 30 cases in 10 groups: approval, retrieve, honest, web-off, web-on, rtl, revise, final, safety, scope. Grow it every time the agent surprises you. |
| `grader.py` | Exact checks on tool calls and fields: which tool, in what order, with which arguments, what was said, what was remembered |
| `run.py` | Runs the cases with stubbed tools and a scripted teacher, grades them, appends to `history.csv`, compares with the baseline |
| `history.csv` | One row per recorded run: pass rate and tokens. The row marked `baseline` is what a change is measured against |
| `mock_model.py` | A scripted stand-in model that proves the harness works. **It is not a measurement of the real model.** |

```bash
python -m evals.run --validate     # is cases.yaml well formed?
python -m evals.run --mock         # free: do the graders pass a good model and catch a bad one?
python -m evals.run --estimate     # free: rough size of a real run
python -m evals.run                # real model; compares with the baseline; exit 1 on a regression
python -m evals.run --baseline --note "first real baseline"    # record the trusted starting point (ticket #17)
```

A regression is a pass rate down by more than 5 points, or input tokens up by more than 50%.
Facts are graded exactly. Wording is only graded where a case has a rubric and a judge model is on (ticket #28).
