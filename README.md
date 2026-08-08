# Community Test-Kit

This is a curated, runnable library of test patterns — the kind of code you'd
want to show someone who asks, *"what does a real Python test suite look like
when the code under test is messy, non-deterministic, or talks to third-party
APIs?"*

**It is NOT a product, app, or service you install and run.** It is a
**reference collection of patterns**, each one small enough to read in 60
seconds but complete enough to run with a single command.

---

## The 30-second version

You clone this folder, then run one command:

```bash
cd kit-tests
uv run pytest examples -q
```

That executes **8 small stub files** in `examples/`. Each file demonstrates
**one** testing technique (frozen clock, golden snapshot, mutation target,
etc.) and runs **fully offline** — no API keys, no database, no network.
You can read any of them in a minute and understand exactly how the technique
works.

## Why this exists

This kit was extracted from `baziforecaster`, a large codebase. In its original
home, the tests were tightly coupled to source code, databases, and live LLM
calls — great for CI, impossible for a newcomer to run on a laptop. This kit
takes the **interesting patterns** out of that suite and makes each one
self-contained. You get the *shape* of a production-grade test without needing
to understand 50k lines of application code.

## What "patterns" do you see here?

| File | Pattern | Real-world analog |
|---|---|---|
| `examples/01_frozen_clock.py` | Freeze time + stub the LLM | Deterministic CI runs despite clocks and API drift |
| `examples/02_snapshot_regression.py` | Golden-file comparison with readable diff | Catch unintended output changes in reports/exports |
| `examples/03_mutation_target.py` | Tests designed to be "killed" by mutation tools | Verify your test suite actually covers edge cases |
| `examples/04_silent_swallow_scanner.py` | AST scanner that lints tests for `except: pass` | Enforce "fail loudly" discipline across your own codebase |
| `examples/05_hypothesis_fuzz.py` | Property-based testing that finds NaN/Inf bugs | Automatically discover inputs that break numeric code |
| `examples/06_kit_mem0_model.py` | Config wiring test (env vars → model selection) | Prove config knobs are independent and observable |
| `examples/test_kit_live_smoke.py` | Fail-fast attestation for `KIT_LIVE=true` | Tests the test-infrastructure itself boots correctly |

## Folder map

```
kit-tests/
├── examples/          ← START HERE. 8 self-contained, offline demos (no upstream code).
├── 01_gold_snapshots/  … 09_tech_debt_audit/
│                      ← Full layers from baziforecaster. Need the original source tree
│                        + a PostgreSQL DB to run. These are NOT cloner-runnable unless
│                        you already work on baziforecaster. They're here as reference.
├── math_chapters/     ← Chapter-level engine math tests (ch01-ch12). Needs src2.
├── param_flows/       ← Parameterized flow tests. Needs src2 + SQLAlchemy.
├── infra/             ← conftest, pytest.ini, config.py, bazirag/ (rag demo)
├── tools/             ← Audit/dev tooling (find_bad_style, evaluate_*)
├── .env.example       ← Template for KIT_LIVE=true runs (copy → .env)
├── pyproject.toml     ← Only pins pytest + hypothesis. That's it.
├── README.md          ← This file.
├── QUICKSTART.md      ← Faster version of this guide.
├── GUIDE.md           ← Your personal setup playbook (how to configure for your env).
├── STRUCTURE.md       ← Exact layout + curation rules applied during build.
└── orchestrator.md    ← How this kit was built (reproducible recipe).
```

## The two run modes

This kit has two faces:

### Offline (default) — `KIT_LIVE=false`

```bash
cd kit-tests
uv run pytest examples -q
```

Runs the 8 stubs. Pure Python + pytest + hypothesis. **Zero configuration.**

### Live (opt-in) — `KIT_LIVE=true`

For the 2 example files that talk to a real LLM API or kit server:

```bash
cp .env.example .env
# Edit .env: set KIT_LIVE=true, KIT_PATH, KIT_BASE_URL, KIT_MODEL, KIT_API_KEY
KIT_LIVE=true uv run pytest examples -q
```

If you set `KIT_LIVE=true` but forget a variable, the kit **refuses to run**
with a loud error naming the missing var. Nothing silently breaks.

## Is this "AI-generated slop"?

No. Every `.py` file here is **hand-curated** from a real, working test suite.
Each example is a distilled slice — stripped of its upstream dependencies so
it stands alone. The narrative comments inside each file explain the lesson.
If you want the full, coupled versions, they're in the `01_`–`09_` layers
(need the baziforecaster source tree).

## Want to go deeper?

- **Start immediately**: See [QUICKSTART.md](QUICKSTART.md) — 5 lines, done.
- **Set up your own environment**: See [GUIDE.md](GUIDE.md) — full playbook.
- **Understand every folder**: See [STRUCTURE.md](STRUCTURE.md) — exact layout.
- **Rebuild this kit from source**: See [orchestrator.md](orchestrator.md) —
  reproducible build recipe.
