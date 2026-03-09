# Ralph Wiggum — Interview: Question Generation

You are generating clarifying questions for a project spec. Your output will be parsed by a program — you must output only valid JSON.

## Context

- **Project:** `{{PROJECT_NAME}}`
- **Interview round:** {{ROUND_NUM}} of {{TOTAL_ROUNDS}}

## Steps

### Step 1: Read the current spec and relevant source files

Carefully read `.ralph/{{PROJECT_NAME}}/spec.md` to understand the current state of the project requirements. You should examine other files in the codebase that are referenced by this spec file to gain a better understanding of the problem.

You are also encouraged to browse all other relevant source files, tests, and configuration in the codebase to gain a thorough understanding of the problem domain and existing implementation patterns.

### Step 2: Identify gaps

Identify the **3–5 most important** gaps, ambiguities, or missing details that would block a developer from implementing the project correctly. Good questions to ask:
- What behaviour is undefined or could be interpreted multiple ways?
- What inputs, outputs, or edge cases are not addressed?
- What technical decisions have not been made (e.g. storage format, API design, error handling)?

Prioritise by impact: earlier rounds should address big-picture questions; later rounds should address specifics.

Questions must be **answerable by the user** — do not ask about implementation details the user cannot be expected to know.

### Step 3: Generate answer options

For each question, generate **2–3 concise, mutually exclusive answer options** representing the most common realistic choices for the project. Follow these rules for options:

- Generate 2–3 options per question — no more.
- Options must be concise (≤10 words each), distinct, and non-overlapping.
- Options must represent realistic choices — not obviously wrong answers.
- Cover only the most common choices; do not try to enumerate every possibility.
- Do not include "it depends" or "ask the user" as options — those are not useful.

### Step 4: Output only valid JSON

Output ONLY valid JSON in the format below. No preamble, no markdown fences, no commentary before or after the JSON.

**Required output format:**

```
{"questions": [{"id": 1, "question": "...", "options": ["...", "..."]}, ...]}
```

**Example output:**

{"questions": [{"id": 1, "question": "Under \"Requirements — user authentication\": should the system support OAuth providers, or only email/password login?", "options": ["Email/password login only", "OAuth providers only (Google, GitHub)", "Both email/password and OAuth providers"]}, {"id": 2, "question": "What should happen when a user submits a form with missing required fields?", "options": ["Inline error messages next to each field", "A summary banner at the top of the form"]}]}

## Important Rules

- **Output only the JSON object.** Do not include preamble, commentary, or markdown fences.
- **Do not create or amend any files.**
- **Do not answer your own questions** — the user will answer them.
