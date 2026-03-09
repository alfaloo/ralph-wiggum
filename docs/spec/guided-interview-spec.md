# Guided Interview UX — Specification

## Overview

Revamp `ralph interview` to replace the current "dump all questions at once, type a free-form essay" interaction with a guided, one-question-at-a-time flow with pre-generated answer suggestions — similar to the clarifying question UI in Cursor IDE and Claude Code.

---

## Current Behaviour (Baseline)

### Flow

```
ralph interview <project>
  └─ Round 1..N
       ├─ Phase 1: Claude reads spec.md → outputs numbered list of 3–5 plain-text questions
       ├─ All questions printed to terminal at once
       ├─ User types free-form multi-line answer covering all questions (Ctrl+D to submit)
       └─ Phase 2: Claude takes (questions, answers) → amends spec.md + tasks.json
```

### Pain Points

1. **Cognitive overload**: User must hold 5 questions in their head while composing a single free-form response.
2. **Incomplete answers**: Users frequently skip questions or give shallow answers because the open-ended format offers no scaffolding.
3. **Speed**: Composing a thoughtful multi-line response for 5 distinct questions is slow.
4. **No guidance**: Users don't know what a "good" answer looks like for each question.

---

## Proposed Behaviour

### Core Idea

The first Claude agent (question generation) now outputs **structured JSON** containing each question and 2–3 suggested answers. The CLI then presents one question at a time in a numbered-selection menu. The user picks a suggestion or selects a "Describe yourself..." option to type a custom answer.

### New Flow

```
ralph interview <project>
  └─ Round 1..N
       ├─ Phase 1: Claude reads spec.md → outputs JSON: [{question, options[]}]
       ├─ For each question (one at a time):
       │     ├─ Print "Question M of N: <question text>"
       │     ├─ List options 1..K + final option "Describe yourself..."
       │     ├─ Prompt: "Select an option (1–K+1): "
       │     └─ If "Describe yourself..." → open inline text prompt for custom answer
       └─ Phase 2: Claude takes (questions, answers) → amends spec.md + tasks.json
```

### Sample Terminal Session

```
[ralph] Interview round 1/1
[ralph] Interview agent has started working — generating questions...

Question 1 of 4:
Under "Requirements — user authentication": should the system support OAuth providers,
or only email/password login?

  > Email/password login only
    OAuth providers only (Google, GitHub)
    Both email/password and OAuth providers
    Describe yourself...

↑↓ to move  Enter to select

─────────────────────────────────────────────────────────────

Question 2 of 4:
What should happen when a user submits a form with missing required fields?

  > Inline error messages next to each field
    A summary banner at the top of the form
    Describe yourself...

↑↓ to move  Enter to select

[Describe yourself selected — rich text area opens]
Type your answer. Press Ctrl+D when done, or Ctrl+C to stop:

Show inline errors but also scroll to the first error automatically.
Also highlight the first invalid field with a red border.

─────────────────────────────────────────────────────────────

... (questions 3 and 4) ...

[ralph] Interview agent has started working — updating spec with your answers...
[ralph] Round 1 complete.
```

---

## Technical Specification

### 1. New Prompt Template: `templates/questions_with_options.md`

A new template replacing `templates/questions.md` for the guided interview flow.

**Key instructions to the agent:**

- Read `spec.md` and relevant source files (same as current).
- Identify 3–5 most important gaps/ambiguities (same criteria as current).
- For each question, generate **2–3 concise, mutually exclusive answer options** that represent the most common realistic choices for the project. Do not try to cover every possibility — focus on the most likely ones only.
- Output **only valid JSON** — no preamble, no markdown fences, no commentary.

**Output format the agent must produce:**

```json
{
  "questions": [
    {
      "id": 1,
      "question": "Under 'Requirements — user authentication': should the system support OAuth providers, or only email/password login?",
      "options": [
        "Email/password login only",
        "OAuth providers only (Google, GitHub)",
        "Both email/password and OAuth providers"
      ]
    },
    {
      "id": 2,
      "question": "What should happen when a user submits a form with missing required fields?",
      "options": [
        "Inline error messages next to each field",
        "A summary banner at the top of the form"
      ]
    }
  ]
}
```

**Guidelines for option quality (to include in the template):**

- Generate 2–3 options per question — no more.
- Options must be concise (≤10 words each), distinct, and non-overlapping.
- Options must represent realistic choices — not obviously wrong answers.
- Cover only the most common choices; do not try to enumerate every possibility.
- Do not include "it depends" or "ask the user" as options — those are not useful.

### 2. Template Variable Substitution

Same variables as `questions.md`:

| Variable | Value |
|---|---|
| `{{PROJECT_NAME}}` | project name |
| `{{ROUND_NUM}}` | current round (1-indexed) |
| `{{TOTAL_ROUNDS}}` | total rounds |

### 3. New Parse Function: `parse_questions_with_options_md()`

In `ralph/parse.py`, add:

```python
def parse_questions_with_options_md(project_name: str, round_num: int, total_rounds: int) -> str:
    """Render the guided question-generation prompt (outputs JSON with options)."""
    return _render(
        "questions_with_options.md",
        PROJECT_NAME=project_name,
        ROUND_NUM=str(round_num),
        TOTAL_ROUNDS=str(total_rounds),
    )
```

### 4. Structured Output Parsing

After `run_noninteractive()` returns the agent's stdout:

1. Attempt `json.loads(stdout.strip())`.
2. If parsing fails (the model occasionally wraps JSON in a markdown fence), strip `` ```json `` / `` ``` `` delimiters and retry.
3. If parsing still fails after stripping, fall back to the **legacy plain-text flow** (print all text, collect one free-form answer). Log a warning: `[ralph] Could not parse structured questions — falling back to free-form input.`

```python
def _parse_questions_json(raw: str) -> list[dict] | None:
    """Parse Claude's JSON output into a list of question dicts.

    Returns None on parse failure so the caller can fall back gracefully.
    """
    text = raw.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data.get("questions", [])
    except (json.JSONDecodeError, AttributeError):
        return None
```

### 5. New Input Collection: `_collect_guided_answers()`

In `ralph/run.py`, add a new function that drives the one-at-a-time selection UX:

```python
def _collect_guided_answers(questions: list[dict]) -> str:
    """Present questions one at a time with arrow-key or numbered selection.

    Returns a formatted string of Q&A pairs suitable for passing to the
    generate_tasks template (same format as free-form _collect_user_answers).
    """
```

**Two-tier approach** — mirrors the existing `isatty()` pattern in `_collect_user_answers()`:

#### TTY mode (normal terminal): arrow-key navigation via `prompt_toolkit`

`prompt_toolkit` is already an installed dependency. Use a custom inline `Application` with a `RadioList`-style control rendered directly in the terminal (no full-screen takeover):

- Up/Down arrows move a `>` cursor between options.
- Enter confirms the selection.
- Up/Down arrows move a `>` cursor between options.
- Enter confirms the selection.
- "Describe yourself..." is always the last option.
- Selecting "Describe yourself..." closes the selection widget and opens the **same rich multiline text area used by `_collect_user_answers()`** — full `prompt_toolkit` multiline editor with arrow key navigation, mouse-click cursor positioning, and Ctrl+D to submit.
- Ctrl+C at any point exits cleanly.

Example TTY rendering:

```
Question 1 of 4:
Under "Requirements — user authentication": should the system support OAuth
providers, or only email/password login?

  > Email/password login only           ← highlighted with arrow keys
    OAuth providers only (Google, GitHub)
    Both email/password and OAuth providers
    Describe yourself...

↑↓ to move  Enter to select
```

`prompt_toolkit` provides `prompt_toolkit.application.Application` and `prompt_toolkit.layout` primitives to build this inline widget. The implementation will use a `FormattedTextControl` with a stateful cursor index, bound to `up`, `down`, and `enter` key handlers.

#### Non-TTY mode (VSCode extension / piped stdin): numbered fallback

When `sys.stdin.isatty()` is `False`, render the same options as a numbered list and read a single line via `sys.stdin.readline()`:

```
Question 1 of 4:
Under "Requirements — user authentication": should the system support OAuth
providers, or only email/password login?

  1. Email/password login only
  2. OAuth providers only (Google, GitHub)
  3. Both email/password and OAuth providers
  4. SSO/SAML enterprise login
  5. Describe yourself...

Select an option (1–5):
```

Validate the input is an integer in range; re-prompt on invalid input. If "Describe yourself..." is selected, read the next line as the custom answer.

#### Shared behaviour

- For each question dict `{id, question, options}`:
  1. Print `Question {i} of {total}:\n{question text}`.
  2. Display options via the appropriate mode above.
  3. If the user selects "Describe yourself...", open the **full `prompt_toolkit` multiline editor** (identical to the existing `_collect_user_answers()` implementation — arrow key navigation, mouse-click cursor positioning, Ctrl+D to submit, Ctrl+C to abort).
  4. Print a horizontal rule separator between questions.
- Ctrl+C at any point: `print("\n[ralph] Ok, stopping the interview."); sys.exit(0)`.

**Output format** returned by the function (passed to `generate_tasks.md` as `ANSWERS`):

```
1. Under "Requirements — user authentication": should the system support OAuth providers?
   Answer: Both email/password and OAuth providers

2. What should happen when missing required fields?
   Answer: Show inline errors but also scroll to the first error automatically
```

### 6. Updated `run_interview_loop()` in `run.py`

The existing `run_interview_loop()` method needs a new code path for structured questions:

```python
def run_interview_loop(self, question_prompts, make_amend_prompts):
    for i, q_prompt in enumerate(question_prompts):
        round_num = i + 1
        print(f"\n[ralph] Interview round {round_num}/{total}")

        print("[ralph] Interview agent has started working — generating questions...\n")
        result = run_noninteractive(q_prompt)
        raw_output = result.stdout.strip()

        # Try structured (guided) path first
        questions_data = _parse_questions_json(raw_output)
        if questions_data:
            answers = _collect_guided_answers(questions_data)
            # Reconstruct a plain-text questions string for the generate_tasks template
            questions_text = _format_questions_as_text(questions_data)
        else:
            # Fallback: legacy free-form path
            print("[ralph] Could not parse structured questions — falling back to free-form input.")
            print(raw_output)
            print()
            answers = _collect_user_answers()
            questions_text = raw_output

        print("\n[ralph] Interview agent has started working — updating spec with your answers...")
        result2 = run_noninteractive(make_amend_prompts[i](questions_text, answers))
        ...
```

**Helper: `_format_questions_as_text()`** — converts structured question dicts back to a numbered list string, so the `generate_tasks.md` template receives the same `QUESTIONS` format it always has.

### 7. `InterviewCommand` Changes in `commands.py`

`InterviewCommand.execute()` currently calls `parse_questions_md()` to build the phase-1 prompt. Change it to call `parse_questions_with_options_md()` instead.

No other changes needed in `commands.py`.

### 8. Dependency: No New Library Required

- Arrow-key navigation uses `prompt_toolkit`, which is **already an installed dependency** (used in `_collect_user_answers()`).
- `questionary` and `InquirerPy` are intentionally avoided — they would add a new dependency for functionality already covered by `prompt_toolkit`.
- The numbered fallback path uses only `sys.stdin.readline()` — no imports needed.

---

## Files to Create / Modify

| File | Change |
|---|---|
| `templates/questions_with_options.md` | **Create** — new agent prompt that outputs JSON |
| `ralph/parse.py` | **Modify** — add `parse_questions_with_options_md()` |
| `ralph/run.py` | **Modify** — add `_parse_questions_json()`, `_collect_guided_answers()`, `_format_questions_as_text()`; update `run_interview_loop()` |
| `ralph/commands.py` | **Modify** — swap `parse_questions_md` → `parse_questions_with_options_md` in `InterviewCommand` |
| `tests/test_cmd_interview.py` | **Modify** — update mock targets; add tests for guided path and fallback |
| `tests/test_run_interview.py` | **Create** — unit tests for `_parse_questions_json`, `_collect_guided_answers`, `_format_questions_as_text` |

---

## Edge Cases and Fallbacks

| Scenario | Behaviour |
|---|---|
| Claude outputs malformed JSON | Fall back to legacy free-form flow; warn user |
| Claude outputs JSON with 0 questions | Fall back to legacy free-form flow; warn user |
| User enters out-of-range number | Re-prompt: `Invalid selection. Please enter a number between 1 and {K+1}.` |
| User enters non-integer | Re-prompt with same message |
| User presses Ctrl+C during selection | Exit cleanly: `[ralph] Ok, stopping the interview.` |
| stdin is not a TTY (VSCode extension) | Numbered list + `sys.stdin.readline()` for selection; "Describe yourself" falls back to `sys.stdin.read()` (same as current free-form fallback) |
| A question has no options (empty list) | Skip option display; fall back to free-form text prompt for that question only |

---

## generate_tasks.md Compatibility

No changes required to `templates/generate_tasks.md` or `parse_generate_tasks_md()`. The guided flow produces the same `QUESTIONS` and `ANSWERS` string format that the template has always received.

---

## Testing Strategy

### Unit Tests

- `_parse_questions_json()`: valid JSON, JSON in markdown fence, malformed JSON, empty questions array.
- `_format_questions_as_text()`: correct numbered list output.
- `_collect_guided_answers()`: mock stdin with valid selection, out-of-range input (re-prompt), "Describe yourself" selection, Ctrl+C.

### Integration / Smoke Test

- Run `ralph interview` against a minimal `.ralph/<project>/spec.md` and verify:
  1. Questions are presented one at a time.
  2. Selecting a pre-built option produces correct Q&A text.
  3. Selecting "Describe yourself..." prompts for custom text.
  4. `spec.md` and `tasks.json` are updated correctly after the round.
  5. Fallback activates when the mock agent returns invalid JSON.

---

## Out of Scope

- Multi-select (choosing more than one option per question) — not needed for this feature.
- Persistent answer history across sessions.
- Changes to `ralph comment`, `ralph enrich`, `ralph execute`, or any other command.
- Changes to `templates/generate_tasks.md`.
