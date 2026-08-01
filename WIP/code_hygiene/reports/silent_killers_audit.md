# 🕵️ Silent Killers & Fallback Audit Report

Scanned `6` files in `src2/`.

## 📂 `admin/code_hygiene/scanners/find_dead_code.py`

### ✅ Line 296: `Exception` (swallowed_exception)
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The exception is not swallowed silently; it is printed to stderr as a warning. Since the whitelist is optional (the file may not even exist), failing to load it is a non-critical error that allows the tool to proceed with a default empty set, which is a safe fallback.

### ✅ Line 329: `Exception` (swallowed_exception)
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The exception is not swallowed silently; it is printed to stderr, providing visibility into parsing errors for individual files while allowing the remaining files in a batch process to continue.

### ✅ Line 391: `Exception` (swallowed_exception)
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The exception is caught and logged as a warning to stderr. The code continues with an empty `existing_results` dictionary, which is effectively a safe fallback to re-running the audit for all candidates. Since this is a tool for finding dead code (an offline analysis tool) and not a critical system component, failing to load a cache file is a non-critical failure that should not crash the process.

### ✅ Line 419: `Exception` (swallowed_exception)
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The exception is not swallowed; it is logged to stderr and recorded in a 'failed_audits' list within the report, ensuring the failure is tracked and visible to the user.

### ✅ Line 435: `Exception` (swallowed_exception)
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The exception is caught and printed to stderr, which prevents the silent failure of the final reporting step (markdown generation) from crashing the entire script. Since the JSON report is already saved on line 429, the primary data is preserved. This is a safe fallback to ensure the script completes its final output summaries.

---

## 📂 `admin/code_hygiene/scanners/find_silent_killers.py`

### ✅ Line 250: `Exception` (swallowed_exception)
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The exception is not swallowed silently; it is logged to stderr. Since this is a scanner tool designed to iterate through many files, skipping a single unparseable file while reporting the error is the intended and correct behavior to prevent the entire scan from crashing.

### ✅ Line 268: `Exception` (swallowed_exception)
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The exception is not swallowed silently; it is printed to stderr as a WARNING. Furthermore, loading existing results is an optimization to avoid re-auditing; failure to load it simply means starting the audit from scratch, which is a safe fallback.

### ✅ Line 296: `Exception` (swallowed_exception)
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The exception is not swallowed; it is logged to stderr and recorded in a failed_audits list within the report, ensuring the failure is visible and persists in the output.

### ✅ Line 311: `Exception` (swallowed_exception)
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The exception is caught and printed to stderr, which is not a 'silent' failure. The error is not suppressed; it is reported to the user.

---

## 📂 `src2/interfaces/telegram/conductor.py`

### ✅ Line 301: `ValueError` (swallowed_exception)
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The exception is not swallowed; it's used as a control flow mechanism to try a secondary parsing strategy (splitting by whitespace) before finally logging a warning if both fail. This is a robust parsing pattern.

### ✅ Line 310: `Exception` (swallowed_exception)
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The exception is caught and logged as a warning. This is a safe fallback pattern for parsing user input from an external interface (Telegram), where invalid input should not crash the entire session/bot interaction.

---

## 📂 `src2/interfaces/telegram/ier_parser.py`

### ✅ Line 147: `Exception` (swallowed_exception)
- **Verdict**: `FALSE_POSITIVE`
- **Severity**: `LOW`
- **Reasoning**: The exception handling for datetime.strptime is a safe, expected pattern for parsing a list of dates provided by an LLM, ensuring that one malformed date doesn't crash the entire extraction process.

---

