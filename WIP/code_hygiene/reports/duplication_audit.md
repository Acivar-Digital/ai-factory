# 🕵️ Code Duplication & Copypasta Report

Scanned `118` files in `src2/`.

### 🛑 `STEM_MAP and BRANCH_MAP constants`
- **File A**: `src2/core/calendar/populate_calendar.py` (Line 9)
- **Verdict**: `DUPLICATION`
- **Severity**: `LOW`
- **Reasoning**: These are static mapping constants used for Bazi/Calendar translations. Having them duplicated across core and engine modules suggests they should be moved to a shared constants or utility file to ensure consistency.

---

### 🛑 `Heavenly Stems list`
- **File A**: `src2/engine/daily_pillar.py` (Line 33)
- **Verdict**: `DUPLICATION`
- **Severity**: `LOW`
- **Reasoning**: This is a static list of the Ten Heavenly Stems used in Chinese astrology/calendar calculations. Since it is a fundamental constant used across multiple engine modules, it should be defined once in a shared constants file.

---

### 🛑 `RAG context concatenation logic`
- **File A**: `src2/engine/monthly_generator.py` (Line 113)
- **Verdict**: `DUPLICATION`
- **Severity**: `LOW`
- **Reasoning**: The code implements a specific business logic for filtering and joining RAG context strings based on a sentinel value ('No specific references found.'). This logic is repeated across two different engine files and should be refactored into a shared utility function.

---

### 🛑 `find_best_month_logic`
- **File A**: `src2/interfaces/telegram/chronomancer/agents.py` (Line 119)
- **Verdict**: `DUPLICATION`
- **Severity**: `HIGH`
- **Reasoning**: The code implements a specific business logic for finding the latest month entry that is less than or equal to a target date. This logic is repeated across two different files in the the same module, indicating a copy-paste violation that should be refactored into a shared utility function.

---

### 🛑 `Person profile mapping logic`
- **File A**: `src2/interfaces/telegram/chronomancer/agents.py` (Line 142)
- **Verdict**: `DUPLICATION`
- **Severity**: `LOW`
- **Reasoning**: The code block is a data mapping function that transforms a person object (p) into a dictionary. This logic is repeated across two different files, which is a clear violation of DRY principles and should be refactored into a shared utility or a method on the person model.

---

### 🛑 `calculate_end_date_logic`
- **File A**: `src2/engine/monthly_generator.py` (Line 186)
- **Verdict**: `DUPLICATION`
- **Severity**: `HIGH`
- **Reasoning**: The code block contains specific business logic for calculating the end date of a month, including a fallback for 2027 solar months and a hardcoded 29-day offset. This logic is repeated across two different engine files and should be refactored into a shared utility.

---

### 🛑 `branch_mapping_logic`
- **File A**: `src2/engine/module12_compatibility.py` (Line 304)
- **Verdict**: `DUPLICATION`
- **Severity**: `HIGH`
- **Reasoning**: The code implements a specific business logic mapping for branches (Yin, Wu, Xu -> Mao, etc.). This identical logic is repeated across two different engine modules, indicating a clear violation of DRY principles and should be refactored into a shared utility function.

---

