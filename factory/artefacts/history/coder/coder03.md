<!-- msg 0 | 2026-08-01-12:04:16 | user-prompt -->

## User

You are implementing EXACTLY ONE task. Do not implement others.

TASK ID: coder03
TITLE: Refactor billing.py CC Violations
FILE TO EDIT: src2/billing.py

INSTRUCTION:
Refactor validate_promo_code to have CC <= 5. Apply early returns and simple guard clauses instead of nested if-else structures.

ACCEPTANCE CRITERIA:
CC of validate_promo_code <= 5, tests pass, ruff passes.

LIVE FILES (read-only reference — DO NOT write here):
['src2/billing.py']

STAGING PATHS (WRITE your proposed files ONLY here, under factory/temp/):
['/home/yapilwsl/arthityap/ai-factory/factory/temp/src2/billing.py']

=== EDIT MODE (per file — follow exactly) ===
The harness pre-staged a copy of every target file and determined its edit mode:
  - src2/billing.py  →  FULL WRITE  (new/empty file; use write_file on the STAGING copy /home/yapilwsl/arthityap/ai-factory/factory/temp/src2/billing.py)
Rule: NEVER rewrite a file marked SURGICAL in full. NEVER write src/ or src2/. Read the STAGING copy (eviction-exempt, full content present) — do NOT read the live tree. A human applies your staged file.

=== FULL FILE CONTENT (edit directly; NO read tool needed) ===
--- FILE TO EDIT: src2/billing.py (staging: /home/yapilwsl/arthityap/ai-factory/factory/temp/src2/billing.py) ---
1: <unreadable staging mirror: /home/yapilwsl/arthityap/ai-factory/factory/temp/src2/billing.py>
--- END FILE ---
<<<INJECTED_CONTEXT>>> (global_alignment)
GLOBAL ALIGNMENT:
This workplan resolves 5 non-compliant Cyclomatic Complexity (CC) violations across agents.py, forecast_store.py, and billing.py within the src2/ codebase. 3 subtasks have been outlined to execute concurrency, leveraging AST-edit tools. The refactoring strategy utilises guard clauses, helper extraction, and structural pattern matching to flatten nesting while retaining functionality without raising Try/Except limits.
<<<END_INJECTED_CONTEXT>>>

=== EXPECTED CODER BEHAVIOUR (frozen contract) ===
- Implement ONLY this task; do not touch other tasks' files.
- Satisfy EVERY acceptance_criteria line below verbatim; if a criterion is unachievable, return status 'blocked' with the reason — never fake it.
- Use STRICT Pydantic models / typed fields only; no bare dicts for domain logic; no dict access on Pydantic models.
- Code MUST pass `uv run ruff check`. Write output under factory/temp/ (PROPOSE-ONLY); never write src/ or src2/.
- Return a TaskResult (task_id, status, files_changed, diff_summary, notes) with NO file content inside it.
- ACCEPTANCE (verbatim):
CC of validate_promo_code <= 5, tests pass, ruff passes.

=== FROZEN DISCIPLINE (load-bearing rules — DO NOT VIOLATE) ===
- ZERO-DICTS: No bare dict access on Pydantic models. All domain data uses strict Pydantic models/Enums/Literals.
- PYDANTIC-ONLY: All domain lookups/tables = Pydantic registry models with typed fields. Enums ONLY as field types.
- FAIL LOUDLY: Full tracebacks on errors. No silent except:pass, no hidden fallbacks.
- FAIL CHEAPLY: Cheap assertions before expensive LLM calls.
- NO src/ or src2/ edits: Write output under factory/temp/ only.
- Code MUST pass `uv run ruff check` before being considered done.


---

<!-- msg 1 | 2026-08-01-12:04:18 | tool-call -->

### Tool call: `read_file`

- **relative_path**: `src2/billing.py`

---

<!-- msg 2 | 2026-08-01-12:04:18 | tool-return -->

### Tool result: `read_file`

SYSTEM ERROR: You MUST call the 'remember' tool to record your step-by-step plan BEFORE using any search or edit tools. You are blocked until you plan.

---

<!-- msg 3 | 2026-08-01-12:04:22 | tool-call -->

### Tool call: `remember`

- **note**: Plan:
1. Read src2/billing.py
2. Refactor validate_promo_code helper in billing.py by applying early returns and guard clauses.
3. Write the refactored code to the staging path /home/yapilwsl/arthityap/ai-factory/factory/temp/src2/billing.py.
4. Report final result.

---

<!-- msg 4 | 2026-08-01-12:04:22 | tool-return -->

### Tool result: `remember`

remember: note recorded to role 'coder' history (persists across turns).

[TOOL CALL 1/75]

---

<!-- msg 5 | 2026-08-01-12:04:24 | tool-call -->

### Tool call: `read_file`

- **relative_path**: `src2/billing.py`

---

<!-- msg 6 | 2026-08-01-12:04:24 | tool-return -->

### Tool result: `read_file`


---
Since you are stateless across turns, you may call `remember("<note>")` to record anything you need to execute correctly on your next turn (e.g. a focused slice, an edit decision, or a collision to avoid). Use `remember`, not `bd`.ERROR: File not found: src2/billing.py
---
Tip: Use batch_read for broad discovery; read_file is for targeted line reads only.
batch_read format: line_ranges is ONE contiguous 'start-end' range per file (e.g. {"src/foo.py": "400-500"}). NEVER use comma-joined multi-segments like '400, 600-650, 760-800' — that is a malformed range and the call fails. For non-contiguous slices, make separate batch_read calls (one range each).

[TOOL CALL 2/75]

---

<!-- msg 7 | 2026-08-01-12:04:30 | thinking+tool-call -->

### Thinking

**Considering Filepaths**

I'm currently focused on determining the correct file path for a write operation, and now I have narrowed it down to `factory/temp/src2/billing.py`. I'm going to look at that file.




### Tool call: `batch_read`

- **line_ranges**: _(empty)_
- **paths**: - `src2/billing.py`
- `factory/temp/src2/billing.py`
- `/home/yapilwsl/arthityap/ai-factory/factory/temp/src2/billing.py`

---

<!-- msg 8 | 2026-08-01-12:04:30 | tool-return -->

### Tool result: `batch_read`


---
Since you are stateless across turns, you may call `remember("<note>")` to record anything you need to execute correctly on your next turn (e.g. a focused slice, an edit decision, or a collision to avoid). Use `remember`, not `bd`.ERROR: File not found: src2/billing.py

ERROR: File not found: factory/temp/src2/billing.py

ERROR: Path escape detected: /home/yapilwsl/arthityap/ai-factory/factory/temp/src2/billing.py
---
Note: no line_ranges given for ['src2/billing.py', 'factory/temp/src2/billing.py', '/home/yapilwsl/arthityap/ai-factory/factory/temp/src2/billing.py']; returned the first 250 lines of each. Next time pass line_ranges={path: "start-end"} for a tighter slice.
---
batch_read line_ranges format: ONE contiguous 'start-end' range per file ({"src/foo.py": "400-500"}). Do NOT use comma-joined multi-segments ('400, 600-650, 760-800') — that fails. For non-contiguous slices, make separate batch_read calls.

[TOOL CALL 3/75]

---

<!-- msg 9 | 2026-08-01-12:04:33 | tool-call -->

### Tool call: `batch_read`

- **paths**: - `src2/billing.py`
- `src2/test_billing.py`
- `tests/test_billing.py`
- **line_ranges**: _(empty)_

---

<!-- msg 10 | 2026-08-01-12:04:33 | tool-return -->

### Tool result: `batch_read`


---
Since you are stateless across turns, you may call `remember("<note>")` to record anything you need to execute correctly on your next turn (e.g. a focused slice, an edit decision, or a collision to avoid). Use `remember`, not `bd`.ERROR: File not found: src2/billing.py

ERROR: File not found: src2/test_billing.py

ERROR: File not found: tests/test_billing.py
---
Note: no line_ranges given for ['src2/billing.py', 'src2/test_billing.py', 'tests/test_billing.py']; returned the first 250 lines of each. Next time pass line_ranges={path: "start-end"} for a tighter slice.
---
batch_read line_ranges format: ONE contiguous 'start-end' range per file ({"src/foo.py": "400-500"}). Do NOT use comma-joined multi-segments ('400, 600-650, 760-800') — that fails. For non-contiguous slices, make separate batch_read calls.

[TOOL CALL 4/75]

---

<!-- msg 11 | 2026-08-01-12:04:40 | thinking+tool-call -->

### Thinking

**Analyzing the Target**

I'm now focusing on a specific target file, `src2/billing.py`, and its edit mode, which is FULL WRITE, indicating a new or empty file. This raises a key question: how do I access existing code if the file is new? I'm now exploring the provided context, specifically `/home/yapilwsl`.


**Clarifying File Access**

I've realized the target file, `src2/billing.py`, is new and requires a full write to the staging area. The path escape detection made me question the workspace root's relevance, but the instructions clarify using the staging copy directly. I was initially trying to read the non-existent file, so I'll now focus on writing to the staging location specified. I'll utilize `write_file` to populate the `temp/src2/billing.py` file.




### Tool call: `batch_read`

- **paths**: - `admin/orchestrator/temp/src2/billing.py`
- `admin/orchestrator/temp/billing.py`
- **line_ranges**: _(empty)_

---

<!-- msg 12 | 2026-08-01-12:04:40 | tool-return -->

### Tool result: `batch_read`


---
Since you are stateless across turns, you may call `remember("<note>")` to record anything you need to execute correctly on your next turn (e.g. a focused slice, an edit decision, or a collision to avoid). Use `remember`, not `bd`.ERROR: File not found: admin/orchestrator/temp/src2/billing.py

ERROR: File not found: admin/orchestrator/temp/billing.py
---
Note: no line_ranges given for ['admin/orchestrator/temp/src2/billing.py', 'admin/orchestrator/temp/billing.py']; returned the first 250 lines of each. Next time pass line_ranges={path: "start-end"} for a tighter slice.
---
batch_read line_ranges format: ONE contiguous 'start-end' range per file ({"src/foo.py": "400-500"}). Do NOT use comma-joined multi-segments ('400, 600-650, 760-800') — that fails. For non-contiguous slices, make separate batch_read calls.

[TOOL CALL 5/75]

---

<!-- msg 13 | 2026-08-01-12:04:48 | thinking+tool-call -->

### Thinking

**Clarifying the Task's Core**

I'm now focusing on what "FULL WRITE" implies in this context. It's not clear if I'm creating a new file from scratch, so I'll re-read the injected context to understand the scope and intent. "GLOBAL ALIGNMENT" seems relevant, so I will prioritize this aspect.


**Analyzing Codebase Structure**

I'm now identifying 5 CC violations across `agents.py`, `forecast_store.py`, and `billing.py`. I've outlined 3 subtasks to implement concurrency using AST-edit tools, with a refactoring approach involving guard clauses and helper extractions to reduce nesting while preserving functionality. I'm focusing on the file's presence in `src2/`. I'm unsure of the directory, and trying alternative file paths.




### Tool call: `batch_read`

- **line_ranges**: _(empty)_
- **paths**: - `billing.py`
- `src/billing.py`
- `src2/billing.py`

---

<!-- msg 14 | 2026-08-01-12:04:48 | tool-return -->

### Tool result: `batch_read`


---
Since you are stateless across turns, you may call `remember("<note>")` to record anything you need to execute correctly on your next turn (e.g. a focused slice, an edit decision, or a collision to avoid). Use `remember`, not `bd`.ERROR: File not found: billing.py

ERROR: File not found: src/billing.py

ERROR: File not found: src2/billing.py
---
Note: no line_ranges given for ['billing.py', 'src/billing.py', 'src2/billing.py']; returned the first 250 lines of each. Next time pass line_ranges={path: "start-end"} for a tighter slice.
---
batch_read line_ranges format: ONE contiguous 'start-end' range per file ({"src/foo.py": "400-500"}). Do NOT use comma-joined multi-segments ('400, 600-650, 760-800') — that fails. For non-contiguous slices, make separate batch_read calls.

[TOOL CALL 6/75]

---

<!-- msg 15 | 2026-08-01-12:04:54 | thinking+tool-call -->

### Thinking

**Analyzing Failed Paths**

I've hit a wall. Every path explored has failed. However, I now understand that I'm replacing the entirety of `factory/temp/src2/billing.py`. It seems I'm in "FULL" edit mode for that specific file, based on the harness's pre-staging. Time to consider this reset as an opportunity.




### Tool call: `read_file`

- **relative_path**: docs/PM/GRAVEYARD.md

---

<!-- msg 16 | 2026-08-01-12:04:54 | tool-return -->

### Tool result: `read_file`


---
Since you are stateless across turns, you may call `remember("<note>")` to record anything you need to execute correctly on your next turn (e.g. a focused slice, an edit decision, or a collision to avoid). Use `remember`, not `bd`.ERROR: File not found: docs/PM/GRAVEYARD.md
---
Tip: Use batch_read for broad discovery; read_file is for targeted line reads only.
batch_read format: line_ranges is ONE contiguous 'start-end' range per file (e.g. {"src/foo.py": "400-500"}). NEVER use comma-joined multi-segments like '400, 600-650, 760-800' — that is a malformed range and the call fails. For non-contiguous slices, make separate batch_read calls (one range each).

[TOOL CALL 7/75]

---

<!-- msg 17 | 2026-08-01-12:04:56 | tool-call -->

### Tool call: `read_file`

- **relative_path**: _docs/PM/GRAVEYARD.md

---

<!-- msg 18 | 2026-08-01-12:04:56 | tool-return -->

### Tool result: `read_file`

File read: _docs/PM/GRAVEYARD.md

---

<!-- msg 19 | 2026-08-01-12:05:05 | thinking+tool-call -->

### Thinking

**Locating Source Code**

I've pinpointed a file and method with a high Cyclomatic Complexity score: `/home/yapilwsl/arthityap/ai-factory/factory/temp/src2/billing.py`, specifically `validate_promo_code`. The CC score is greater than 5. I think this indicates an area needing significant review or refactoring.


**Clarifying File Access**

I've realized a critical detail: I shouldn't be attempting to read the target file initially. It's marked for full write, meaning it's a new or empty file staged in the `/home/yapilwsl/arthityap/ai-factory/factory/temp/src2/billing.py` location. The "FULL WRITE" designation explains why my earlier read attempts failed. I now understand the staging process.




### Tool call: `batch_read`

- **paths**: - `admin/orchestrator/temp/factory/temp/src2/billing.py`
- `src2/billing.py`
- **line_ranges**: _(empty)_

---

<!-- msg 20 | 2026-08-01-12:05:05 | tool-return -->

### Tool result: `batch_read`


---
Since you are stateless across turns, you may call `remember("<note>")` to record anything you need to execute correctly on your next turn (e.g. a focused slice, an edit decision, or a collision to avoid). Use `remember`, not `bd`.ERROR: File not found: admin/orchestrator/temp/factory/temp/src2/billing.py

ERROR: File not found: src2/billing.py
---
Note: no line_ranges given for ['admin/orchestrator/temp/factory/temp/src2/billing.py', 'src2/billing.py']; returned the first 250 lines of each. Next time pass line_ranges={path: "start-end"} for a tighter slice.
---
batch_read line_ranges format: ONE contiguous 'start-end' range per file ({"src/foo.py": "400-500"}). Do NOT use comma-joined multi-segments ('400, 600-650, 760-800') — that fails. For non-contiguous slices, make separate batch_read calls.

[TOOL CALL 9/75]

---

<!-- msg 21 | 2026-08-01-12:05:11 | thinking+tool-call -->

### Thinking

**Clarifying Staging Path**

I've just confirmed the staging path. It's `/home/yapilwsl/arthityap/ai-factory/factory/temp/src2/billing.py`. This resolves the initial confusion, and it is in agreement with what the instructions suggested about the harness.



**Interpreting Unreadable Mirror**

I've realized the `<unreadable staging mirror...>` isn't a typical file content display. Instead, it signals the content injection failed, making the staging file inaccessible. My objective is to edit `src2/billing.py`, modifying `validate_promo_code`, but since I can't read the content, I must infer its initial state. The instruction clearly states this is a "FULL WRITE" of an empty file on the staging path, meaning I can start fresh.




### Tool call: `batch_read`

- **line_ranges**: _(empty)_
- **paths**: - `src2/agents.py`
- `src2/forecast_store.py`

---

<!-- msg 22 | 2026-08-01-12:05:11 | tool-return -->

### Tool result: `batch_read`


---
Since you are stateless across turns, you may call `remember("<note>")` to record anything you need to execute correctly on your next turn (e.g. a focused slice, an edit decision, or a collision to avoid). Use `remember`, not `bd`.ERROR: File not found: src2/agents.py

ERROR: File not found: src2/forecast_store.py
---
Note: no line_ranges given for ['src2/agents.py', 'src2/forecast_store.py']; returned the first 250 lines of each. Next time pass line_ranges={path: "start-end"} for a tighter slice.
---
batch_read line_ranges format: ONE contiguous 'start-end' range per file ({"src/foo.py": "400-500"}). Do NOT use comma-joined multi-segments ('400, 600-650, 760-800') — that fails. For non-contiguous slices, make separate batch_read calls.

[TOOL CALL 10/75]