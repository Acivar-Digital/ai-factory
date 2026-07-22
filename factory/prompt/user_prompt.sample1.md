---
Resume: false
bd: bazi-dm-strength
write_mode: staged
language: python
start_phase: planner
stop_phase: supervisor_plan
scope:
  - temp/
---

# EPIC
Build a self-contained Bazi Day-Master strength CLI script.

## DELIVERABLES
- A python script at `temp/dm_strength.py`
- Prints the Four Pillars, the Day Master (DM), and a Strong / Neutral / Weak estimate with a one-line reason.
- Dependency-light: use the already-installed `lunar-python` library and `pydantic` only.

## REQUIREMENTS & CONSTRAINTS
- Define a Pydantic `BaseModel` to hold the calculated data (pillars, tallies, final strength). Instantiate and print. No loose dicts.
- Hardcode a sample date (Year 2024, Month 5, Day 15, Hour 14, Min 30, Sec 0) — no CLI args.
- Fail loudly: no `except: pass`.

## CORRECT lunar-python API
```python
from lunar_python import Solar
solar = Solar.fromYmdHms(year, month, day, hour, minute, second)
lunar = solar.getLunar()
e = lunar.getEightChar()
year_pillar  = e.getYear()
month_pillar = e.getMonth()
day_pillar   = e.getDay()
hour_pillar  = e.getTime()
day_master   = e.getDayGan()
```

## ACCEPTANCE
1. `python temp/dm_strength.py` runs cleanly
2. Output includes Four Pillars, Day Master, Strong/Neutral/Weak with reason
