# Intake Flow Report — gemma-4-31b-it

**Generated:** 2026-05-21 17:15:54 UTC
**Model:** gemma-4-31b-it (preset: intake)
**Results:** 4/4 passed, 0 failed

---

## Scenario 1: Alias + Gender (minimal) [PASS]

**User Input:**
```
Hi, I'm Francis, male.
```

**Raw LLM Response:**
```
REPLY: Nice to meet you, Francis. To create your Bazi chart, please provide your birth date (YYYY-MM-DD), birth time, and birth place.

---
JSON:
{
  "extracted": {
    "alias": "Francis",
    "gender": "male"
  },
  "next_prompt": "Please provide your birth date (YYYY-MM-DD), birth time, and birth place.",
  "all_collected": false
}
```

**Parsed JSON:**
```json
{
  "reply": "Nice to meet you, Francis. To create your Bazi chart, please provide your birth date (YYYY-MM-DD), birth time, and birth place.",
  "extracted": {
    "alias": "Francis",
    "gender": "male"
  },
  "all_collected": false
}
```

---

## Scenario 2: DOB extraction [PASS]

**User Input:**
```
I was born on April 28, 1977 at 11:51am.
```

**Raw LLM Response:**
```
REPLY: Thank you for providing your birth date and time. To complete your Bazi chart and accurately calculate your Luck Pillars and solar time, could you please tell me your gender and your birth city/country?

---
JSON:
{
  "extracted": {
    "dob": "1977-04-28 11:51"
  },
  "next_prompt": "Could you please provide your gender and your birth city/country?",
  "all_collected": false
}
```

**Parsed JSON:**
```json
{
  "reply": "Thank you for providing your birth date and time. To complete your Bazi chart and accurately calculate your Luck Pillars and solar time, could you please tell me your gender and your birth city/country?",
  "extracted": {
    "dob": "1977-04-28 11:51"
  },
  "all_collected": false
}
```

---

## Scenario 3: Chinese characters [PASS]

**User Input:**
```
男，出生地：新加坡
```

**Raw LLM Response:**
```
REPLY: 收到。请提供您的出生日期（年、月、日）以及具体的出生时间。
---
JSON:
{
  "extracted": {
    "gender": "M",
    "location": "新加坡"
  },
  "next_prompt": "请提供您的出生日期（年、月、日）以及具体的出生时间。",
  "all_collected": false
}
```

**Parsed JSON:**
```json
{
  "reply": "收到。请提供您的出生日期（年、月、日）以及具体的出生时间。",
  "extracted": {
    "gender": "M",
    "location": "新加坡"
  },
  "all_collected": false
}
```

---

## Scenario 4: All fields (power user) [PASS]

**User Input:**
```
My name is Francis Yap, alias FYCL, male. Born 28 April 1977 at 11:51am in Singapore.
```

**Raw LLM Response:**
```
REPLY: Thank you, Francis. I have collected all your birth details.

---
JSON:
{
  "extracted": {
    "alias": "FYCL",
    "gender": "male",
    "dob": "1977-04-28 11:51",
    "location": "Singapore"
  },
  "next_prompt": null,
  "all_collected": true
}
```

**Parsed JSON:**
```json
{
  "reply": "Thank you, Francis. I have collected all your birth details.",
  "extracted": {
    "alias": "FYCL",
    "gender": "male",
    "dob": "1977-04-28 11:51",
    "location": "Singapore"
  },
  "all_collected": true
}
```

---
