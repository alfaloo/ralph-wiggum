# Ralph Wiggum — Interview: Question Generation

You are generating clarifying questions for a project spec. Your output will be shown to the user, who will answer the questions before the spec is updated.

## Context

- **Project:** `{{PROJECT_NAME}}`
- **Interview round:** {{ROUND_NUM}} of {{TOTAL_ROUNDS}}

## Steps

### Step 1: Read the current spec

Read `.ralph/{{PROJECT_NAME}}/spec.md` to understand the current state of the project requirements.

### Step 2: Identify gaps

Identify the **3–5 most important** gaps, ambiguities, or missing details that would block a developer from implementing the project correctly. Good questions to ask:
- What behaviour is undefined or could be interpreted multiple ways?
- What inputs, outputs, or edge cases are not addressed?
- What technical decisions have not been made (e.g. storage format, API design, error handling)?

Prioritise by impact: earlier rounds should address big-picture questions; later rounds should address specifics.

Questions must be **answerable by the user** — do not ask about implementation details the user cannot be expected to know.

### Step 3: Output only your questions

Output a numbered list of focused, specific questions. Where helpful, reference the exact part of the spec that is unclear.

**Example format:**
1. Under "Requirements — user authentication": should the system support OAuth providers, or only email/password login?
2. What should happen when a user submits a form with missing required fields — inline error messages or a summary at the top?

## Important Rules

- **Output only the numbered list.** Do not include preamble, commentary, or a summary.
- **Do not create or amend any files.**
- **Do not answer your own questions** — the user will answer them.
