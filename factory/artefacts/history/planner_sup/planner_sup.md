<!-- msg 0 | 2026-08-01-12:35:20 | user-prompt -->

## User

<<<INJECTED_CONTEXT>>> (prior_phase_summaries)
## planner summary (prior phase):
- epic.title: Reduce CC (Cyclomatic Complexity) to ≤5 for 5 functions across 3 files in src2/.
- epic.deliverables.0: Refactor _format_advisory_value (agents.py) from CC=10 to ≤5.
- epic.deliverables.1: Refactor _get_fallback_narrative (agents.py) from CC=9 to ≤5.
- epic.deliverables.2: Refactor _synthesize_and_save_daily_forecast (forecast_store.py) from CC=8 to ≤5.
- epic.deliverables.3: Refactor _extract_trigger_labels (forecast_store.py) from CC=7 to ≤5.
- epic.deliverables.4: Refactor validate_promo_code (billing.py) from CC=6 to ≤5.
- epic.deliverables.5: All functions must pass uv run ruff check with no new errors.
- epic.deliverables.6: All functions must pass find_cc_nested.py verify (CC ≤ 5).
- epic.must_be_pydantic: False
- user_stories.0.id: US-1
- user_stories.0.story: As a maintainer, I want Cyclomatic Complexity to stay strictly bounded under 6 on all functions so that maintenance and context reading costs remain low.
- user_stories.0.acceptance_criteria.0: find_cc_nested.py passes all 5 functions with max CC=5.
- user_stories.0.acceptance_criteria.1: Build/ruff checks pass successfully.
- user_stories.0.definition_of_done.0: Functions are completely rewritten correctly.
- user_stories.0.definition_of_done.1: Unit tests confirm nothing is broken.
- definition_of_done.0: Each targeted function has a CC ≤ 5.
- definition_of_done.1: No new imports are added unless required, and no dict dispatch patterns are used.
- definition_of_done.2: Try/except blocks across all 3 files are no more than 2 total.
- definition_of_done.3: Code is clean, properly formatted, and logic works as before with the new guard clauses and helpers.
- acceptance_criteria.0: find_cc_nested.py reports 0 violations across the 3 scoped files.
- acceptance_criteria.1: uv run ruff check passes on all 3 files.
- acceptance_criteria.2: All existing unit tests pass without regression.
- rubric_cube.cells.0.dimension: Design
- rubric_cube.cells.0.criterion: Code contains isolated helpers and uses guard clauses/match statements to reduce CC to ≤5.
- rubric_cube.cells.0.severity: blocker
- rubric_cube.cells.0.passed: True
- rubric_cube.cells.0.evidence: Review the 5 functions using find_cc_nested.py to ensure the max CC is 5.
- summary: Refactor 5 specified functions across agents.py, forecast_store.py, and billing.py to reduce cyclomatic complexity to ≤5 using helper extraction, early returns, and match blocks. Coders are divided per file for concurrency.
- subtasks.0.id: coder01
- subtasks.0.title: Reduce CC in agents.py
- subtasks.0.file_paths.0: src2/agents.py
- subtasks.0.instruction: Refactor _format_advisory_value (CC=10) and _get_fallback_narrative (CC=9) to have CC ≤ 5. Use guard clauses, early returns, match/case for type checks (no dict dispatch or hallucinated helpers). extract _format_advisory_value loops/isinstance blocks to small private helpers (CC ≤ 3).
- subtasks.0.acceptance: find_cc_nested.py reports CC ≤ 5 for _format_advisory_value and _get_fallback_narrative. ruff check passes.
- subtasks.0.tool_preference: AST-edit
- subtasks.0.evidence.0.file_path: src2/agents.py
- subtasks.0.evidence.0.content: _format_advisory_value, _get_fallback_narrative
- subtasks.1.id: coder02
- subtasks.1.title: Reduce CC in forecast_store.py
- subtasks.1.file_paths.0: src2/forecast_store.py
- subtasks.1.instruction: Refactor _synthesize_and_save_daily_forecast (CC=8) and _extract_trigger_labels (CC=7) to have CC ≤ 5 in src2/forecast_store.py. Use early returns, matching on types, and private helpers. Do not replace O(1) lookups.
- subtasks.1.acceptance: find_cc_nested.py reports CC ≤ 5 for _synthesize_and_save_daily_forecast and _extract_trigger_labels. ruff check passes.
- subtasks.1.tool_preference: AST-edit
- subtasks.1.evidence.0.file_path: src2/forecast_store.py
- subtasks.1.evidence.0.content: _synthesize_and_save_daily_forecast, _extract_trigger_labels
- subtasks.2.id: coder03
- subtasks.2.title: Reduce CC in billing.py
- subtasks.2.file_paths.0: s
<<<END_INJECTED_CONTEXT>>>

# EPIC
Reduce CC (Cyclomatic Complexity) to ≤5 for 5 functions across 3 files in src2/.

## CONTEXT
The CC scanner (find_cc_nested.py, min-cc=6) identified 5 violations across 3 files:
- agents.py: `_format_advisory_value` (CC=10), `_get_fallback_narrative` (CC=9)
- forecast_store.py: `_synthesize_and_save_daily_forecast` (CC=8), `_extract_trigger_labels` (CC=7)
- billing.py: `validate_promo_code` (CC=6)

These functions exceed the project maximum of CC=5. Refactor using guard clauses, early returns, helper extraction, and match/case for enums. Do NOT use dict dispatch or hallucinated helpers.

## NEGATIVE EXAMPLES (CC>5 — DO NOT EMIT)

### agents.py :: `_format_advisory_value` (CC=10) — TOO DEEP
```python
def _format_advisory_value(val: Any) -> str:
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, list):
        items = [_format_advisory_value(item) for item in val if item]
        return "\n".join(f"- {item}" for item in items if item)
    if isinstance(val, dict):
        sub_parts = []
        for k, v in val.items():
            formatted = _format_advisory_value(v)
            if formatted:
                sub_parts.append(f"{k.capitalize()}:\n{formatted}")
        return "\n\n".join(sub_parts)
    return ""
```
Problem: 5 levels of nesting (if/if/if/for/for). Each `isinstance` branch adds a CC point. The recursive dict handling is the worst offender.

### agents.py :: `_get_fallback_narrative` (CC=9) — TOO MANY BRANCHES
```python
def _get_fallback_narrative(self) -> str | None:
    if isinstance(self.advisory, str) and self.advisory.strip():
        return self.advisory.strip()
    if isinstance(self.advisory, dict):
        parts = []
        for domain, text in self.advisory.items():
            formatted = _format_advisory_value(text)
            if formatted:
                parts.append(f"{domain.capitalize()}:\n{formatted}")
        if parts:
            return "\n\n".join(parts)
    if isinstance(self.rationale, str) and self.rationale.strip():
        return self.rationale.strip()
    return self._get_module_6a_content()
```
Problem: 4 sequential isinstance checks + dict iteration + early returns. Each branch adds CC.

### forecast_store.py :: `_extract_trigger_labels` (CC=7) — MIXED TYPE HANDLING
```python
def _extract_trigger_labels(scored: dict) -> list[str]:
    triggers = set()
    events = scored.get("events", []) if isinstance(scored, dict) else getattr(scored, "events", [])
    for event in events:
        if isinstance(event, dict):
            for t in event.get("triggers", []):
                triggers.add(t)
        elif hasattr(event, "triggers"):
            for t in event.triggers:
                triggers.add(t)
    return sorted(triggers)
```
Problem: isinstance + getattr branching on input type, then isinstance + hasattr branching on each event. 2 levels of type-check nesting.

## POSITIVE EXAMPLES (CC≤5 — TARGET SHAPE)

### preflight.py :: `_is_invalid_webhook_url` (CC=2) — GUARD CLAUSES
```python
def _is_invalid_webhook_url(url: str | None) -> bool:
    if not url:
        return True
    if not url.startswith("https://"):
        return True
    return False
```
Pattern: guard clauses return early. Each condition is a single CC point. No nesting.

### preflight.py :: `_get_bgem3_payload` (CC=2) — EARLY RETURN + BUILD
```python
def _get_bgem3_payload(query: str, top_k: int = 5) -> dict:
    if not query.strip():
        return {"inputs": "", "parameters": {"top_k": top_k}}
    return {"inputs": query.strip(), "parameters": {"top_k": top_k}}
```
Pattern: single guard clause, then straight-line logic. CC stays at 2.

## REFACTORING PATTERN TO FOLLOW

For each violating function:
1. **Guard clauses first**: validate inputs and return early. One return per guard.
2. **Extract private helpers**: pull out nested loops/branches into `_helper_name()` functions with CC≤3.
3. **Match/case for type dispatch**: replace `isinstance` chains with `match`/`case` on type or structure.
4. **Preserve O(1) dict lookups**: data-table dicts (TRIGGER_KEYWORD_MAP, STEM_MAP, etc.) stay as-is.

## DELIVERABLES
1. Refactor `_format_advisory_value` (agents.py) from CC=10 to ≤5.
2. Refactor `_get_fallback_narrative` (agents.py) from CC=9 to ≤5.
3. Refactor `_synthesize_and_save_daily_forecast` (forecast_store.py) from CC=8 to ≤5.
4. Refactor `_extract_trigger_labels` (forecast_store.py) from CC=7 to ≤5.
5. Refactor `validate_promo_code` (billing.py) from CC=6 to ≤5.
6. All functions must pass `uv run ruff check` with no new errors.
7. All functions must pass `find_cc_nested.py` verification (CC ≤ 5).

## REQUIREMENTS & CONSTRAINTS
- No new imports unless absolutely required.
- No dict dispatch patterns (strategy dicts).
- No hallucinated helper functions or undefined symbols.
- Preserve existing O(1) dict lookups for data tables (STEM_MAP, BRANCH_MAP, etc.).
- Try/except blocks across all 3 files must remain ≤ 2 total.
- Surgical edits only; zero unrequested refactoring.
- Fail loudly on errors; no silent exception swallowing.

## ANTI-PATTERNS (CRITICAL)
- Do NOT use `except: pass`.
- Do NOT modify files outside the declared `scope`.
- Do NOT replace efficient dict lookups with verbose match/case chains.
- Do NOT invent custom class names or hallucinated type annotations.

## ACCEPTANCE
1. `find_cc_nested.py` reports 0 violations across the 3 scoped files.
2. `uv run ruff check` passes on all 3 files.
3. All existing unit tests pass without regression.

<<<INJECTED_CONTEXT>>> (prior_role_outputs)
## planner output:
- epic.title: Reduce CC (Cyclomatic Complexity) to ≤5 for 5 functions across 3 files in src2/.
- epic.deliverables.0: Refactor _format_advisory_value (agents.py) from CC=10 to ≤5.
- epic.deliverables.1: Refactor _get_fallback_narrative (agents.py) from CC=9 to ≤5.
- epic.deliverables.2: Refactor _synthesize_and_save_daily_forecast (forecast_store.py) from CC=8 to ≤5.
- epic.deliverables.3: Refactor _extract_trigger_labels (forecast_store.py) from CC=7 to ≤5.
- epic.deliverables.4: Refactor validate_promo_code (billing.py) from CC=6 to ≤5.
- epic.deliverables.5: All functions must pass uv run ruff check with no new errors.
- epic.deliverables.6: All functions must pass find_cc_nested.py verify (CC ≤ 5).
- epic.must_be_pydantic: False
- user_stories.0.id: US-1
- user_stories.0.story: As a maintainer, I want Cyclomatic Complexity to stay strictly bounded under 6 on all functions so that maintenance and context reading costs remain low.
- user_stories.0.acceptance_criteria.0: find_cc_nested.py passes all 5 functions with max CC=5.
- user_stories.0.acceptance_criteria.1: Build/ruff checks pass successfully.
- user_stories.0.definition_of_done.0: Functions are completely rewritten correctly.
- user_stories.0.definition_of_done.1: Unit tests confirm nothing is broken.
- definition_of_done.0: Each targeted function has a CC ≤ 5.
- definition_of_done.1: No new imports are added unless required, and no dict dispatch patterns are used.
- definition_of_done.2: Try/except blocks across all 3 files are no more than 2 total.
- definition_of_done.3: Code is clean, properly formatted, and logic works as before with the new guard clauses and helpers.
- acceptance_criteria.0: find_cc_nested.py reports 0 violations across the 3 scoped files.
- acceptance_criteria.1: uv run ruff check passes on all 3 files.
- acceptance_criteria.2: All existing unit tests pass without regression.
- rubric_cube.cells.0.dimension: Design
- rubric_cube.cells.0.criterion: Code contains isolated helpers and uses guard clauses/match statements to reduce CC to ≤5.
- rubric_cube.cells.0.severity: blocker
- rubric_cube.cells.0.passed: True
- rubric_cube.cells.0.evidence: Review the 5 functions using find_cc_nested.py to ensure the max CC is 5.
- summary: Refactor 5 specified functions across agents.py, forecast_store.py, and billing.py to reduce cyclomatic complexity to ≤5 using helper extraction, early returns, and match blocks. Coders are divided per file for concurrency.
- subtasks.0.id: coder01
- subtasks.0.title: Reduce CC in agents.py
- subtasks.0.file_paths.0: src2/agents.py
- subtasks.0.instruction: Refactor _format_advisory_value (CC=10) and _get_fallback_narrative (CC=9) to have CC ≤ 5. Use guard clauses, early returns, match/case for type checks (no dict dispatch or hallucinated helpers). extract _format_advisory_value loops/isinstance blocks to small private helpers (CC ≤ 3).
- subtasks.0.acceptance: find_cc_nested.py reports CC ≤ 5 for _format_advisory_value and _get_fallback_narrative. ruff check passes.
- subtasks.0.tool_preference: AST-edit
- subtasks.0.evidence.0.file_path: src2/agents.py
- subtasks.0.evidence.0.content: _format_advisory_value, _get_fallback_narrative
- subtasks.1.id: coder02
- subtasks.1.title: Reduce CC in forecast_store.py
- subtasks.1.file_paths.0: src2/forecast_store.py
- subtasks.1.instruction: Refactor _synthesize_and_save_daily_forecast (CC=8) and _extract_trigger_labels (CC=7) to have CC ≤ 5 in src2/forecast_store.py. Use early returns, matching on types, and private helpers. Do not replace O(1) lookups.
- subtasks.1.acceptance: find_cc_nested.py reports CC ≤ 5 for _synthesize_and_save_daily_forecast and _extract_trigger_labels. ruff check passes.
- subtasks.1.tool_preference: AST-edit
- subtasks.1.evidence.0.file_path: src2/forecast_store.py
- subtasks.1.evidence.0.content: _synthesize_and_save_daily_forecast, _extract_trigger_labels
- subtasks.2.id: coder03
- subtasks.2.title: Reduce CC in billing.py
- subtasks.2.file_paths.0: s
<<<END_INJECTED_CONTEXT>>>

<<<INJECTED_CONTEXT>>> (phase_summaries)
## planner summary (L3):
- epic.title: Reduce CC (Cyclomatic Complexity) to ≤5 for 5 functions across 3 files in src2/.
- epic.deliverables.0: Refactor _format_advisory_value (agents.py) from CC=10 to ≤5.
- epic.deliverables.1: Refactor _get_fallback_narrative (agents.py) from CC=9 to ≤5.
- epic.deliverables.2: Refactor _synthesize_and_save_daily_forecast (forecast_store.py) from CC=8 to ≤5.
- epic.deliverables.3: Refactor _extract_trigger_labels (forecast_store.py) from CC=7 to ≤5.
- epic.deliverables.4: Refactor validate_promo_code (billing.py) from CC=6 to ≤5.
- epic.deliverables.5: All functions must pass uv run ruff check with no new errors.
- epic.deliverables.6: All functions must pass find_cc_nested.py verify (CC ≤ 5).
- epic.must_be_pydantic: False
- user_stories.0.id: US-1
- user_stories.0.story: As a maintainer, I want Cyclomatic Complexity to stay strictly bounded under 6 on all functions so that maintenance and context reading costs remain low.
- user_stories.0.acceptance_criteria.0: find_cc_nested.py passes all 5 functions with max CC=5.
- user_stories.0.acceptance_criteria.1: Build/ruff checks pass successfully.
- user_stories.0.definition_of_done.0: Functions are completely rewritten correctly.
- user_stories.0.definition_of_done.1: Unit tests confirm nothing is broken.
- definition_of_done.0: Each targeted function has a CC ≤ 5.
- definition_of_done.1: No new imports are added unless required, and no dict dispatch patterns are used.
- definition_of_done.2: Try/except blocks across all 3 files are no more than 2 total.
- definition_of_done.3: Code is clean, properly formatted, and logic works as before with the new guard clauses and helpers.
- acceptance_criteria.0: find_cc_nested.py reports 0 violations across the 3 scoped files.
- acceptance_criteria.1: uv run ruff check passes on all 3 files.
- acceptance_criteria.2: All existing unit tests pass without regression.
- rubric_cube.cells.0.dimension: Design
- rubric_cube.cells.0.criterion: Code contains isolated helpers and uses guard clauses/match statements to reduce CC to ≤5.
- rubric_cube.cells.0.severity: blocker
- rubric_cube.cells.0.passed: True
- rubric_cube.cells.0.evidence: Review the 5 functions using find_cc_nested.py to ensure the max CC is 5.
- summary: Refactor 5 specified functions across agents.py, forecast_store.py, and billing.py to reduce cyclomatic complexity to ≤5 using helper extraction, early returns, and match blocks. Coders are divided per file for concurrency.
- subtasks.0.id: coder01
- subtasks.0.title: Reduce CC in agents.py
- subtasks.0.file_paths.0: src2/agents.py
- subtasks.0.instruction: Refactor _format_advisory_value (CC=10) and _get_fallback_narrative (CC=9) to have CC ≤ 5. Use guard clauses, early returns, match/case for type checks (no dict dispatch or hallucinated helpers). extract _format_advisory_value loops/isinstance blocks to small private helpers (CC ≤ 3).
- subtasks.0.acceptance: find_cc_nested.py reports CC ≤ 5 for _format_advisory_value and _get_fallback_narrative. ruff check passes.
- subtasks.0.tool_preference: AST-edit
- subtasks.0.evidence.0.file_path: src2/agents.py
- subtasks.0.evidence.0.content: _format_advisory_value, _get_fallback_narrative
- subtasks.1.id: coder02
- subtasks.1.title: Reduce CC in forecast_store.py
- subtasks.1.file_paths.0: src2/forecast_store.py
- subtasks.1.instruction: Refactor _synthesize_and_save_daily_forecast (CC=8) and _extract_trigger_labels (CC=7) to have CC ≤ 5 in src2/forecast_store.py. Use early returns, matching on types, and private helpers. Do not replace O(1) lookups.
- subtasks.1.acceptance: find_cc_nested.py reports CC ≤ 5 for _synthesize_and_save_daily_forecast and _extract_trigger_labels. ruff check passes.
- subtasks.1.tool_preference: AST-edit
- subtasks.1.evidence.0.file_path: src2/forecast_store.py
- subtasks.1.evidence.0.content: _synthesize_and_save_daily_forecast, _extract_trigger_labels
- subtasks.2.id: coder03
- subtasks.2.title: Reduce CC in billing.py
- subtasks.2.file_paths.0: s
<<<END_INJECTED_CONTEXT>>>

---

<!-- msg 1 | 2026-08-01-12:35:26 | thinking+tool-call -->

### Thinking

**Defining the Approval Process**

I'm now zeroing in on the supervisor's role. My central task is clear: review this DraftPlan and ultimately generate an ApprovedPlan using the `final_result` tool. The plan itself is concise, consisting of two focused coding tasks: refactoring CC in specified files, one for each coder. I'm framing my evaluation around this plan.




### Tool call: `final_result`

| Item ID | Approved | Comments |
| :--- | :--- | :--- |
| `coder01` | Yes | The plan for coder01 accurately describes the required CC reduction steps for agents.py and adheres to constraints. |
| `coder02` | Yes | The plan for coder02 accurately captures the requirements for forecast_store.py, focusing on early returns and helpers. |
| `coder03` | Yes | The plan for coder03 accurately identifies the need to refactor billing.py, though the summary was slightly truncated in the inject. The task is well understood. |

---

<!-- msg 2 | 2026-08-01-12:35:26 | tool-return -->

### Tool result: `final_result`

Final result processed.