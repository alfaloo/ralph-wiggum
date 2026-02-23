# Ralph Wiggum — Subagent Patterns: Findings & Implementation Guide

## Context

This document covers two proposed subagent patterns for Ralph:

1. **Testing subagent** — offload test execution to a cheap subagent so that large pytest output never enters the execute agent's context window. Only a compact failure summary returns.
2. **Codebase exploration subagents** — for commands like `ralph interview` and `ralph enrich`, spawn parallel subagents to explore the codebase and return summaries rather than having the main agent read every file itself.

---

## How Subagents Work in Ralph's Context

Ralph spawns agents as `claude --dangerously-skip-permissions --print <prompt>` subprocesses. These are full Claude Code sessions that have access to all of Claude Code's built-in tools — including the `Task` tool. This means Ralph's existing agents **can already spawn subagents** without any changes to the Python orchestration layer. The only changes needed are to the **prompt templates**.

### Key mechanism
When an agent calls the Task tool:
- The subagent runs in its own isolated context window
- **All verbose output (test logs, file contents, etc.) stays inside the subagent's context**
- Only the subagent's final return value comes back to the parent agent's context
- The parent context receives a compact summary, not the full output

This is the core token saving: a 20,000-token pytest run becomes a ~300-token failure summary in the parent's context.

---

## Part 1: Testing Subagent

### Why this is high value

Pytest output for even modest test suites can be 5,000–50,000 tokens. Without a subagent, all of this enters the execute agent's context window every time tests are run — consuming a large fraction of its budget and pushing earlier context (spec.md, task context, code it just wrote) out of the window.

With a testing subagent:
- The test output stays inside the subagent
- Only the result summary (~200–500 tokens) returns to the parent
- The execute agent can run tests multiple times (e.g. fix → retest → fix → retest) without compounding context bloat

### The `test-instructions.md` convention

Users should optionally create a test instructions file for their project:

```
.ralph/<project-name>/test-instructions.md
```

This file explains how to run the tests for the project — the test framework, commands to use, environment setup, what a passing run looks like, etc. Example content:

```markdown
## How to run tests for this project

This project uses pytest. To run all tests:

    python -m pytest tests/ -v

To run only unit tests:

    python -m pytest tests/unit/ -v

The test suite requires the following to be set up first:
- A running local Postgres instance (docker compose up -d)
- DJANGO_SETTINGS_MODULE=myapp.settings.test

A passing run looks like: "X passed, Y warnings in Zs"
```

If this file does not exist, the testing subagent is instructed to explore the repository and figure out how to run tests itself.

### Critical implementation note: use foreground, not background

There is an active Claude Code bug (GitHub issue #17011) where `run_in_background: true` subagents silently discard all output. **Do not use background execution for the testing subagent.** The subagent must run in the foreground so its result is returned inline to the parent.

As a secondary output channel, the subagent should also write the full raw test output to `.ralph/<project-name>/test-results.md` so that it is available for human inspection or debugging without entering the parent's context.

### What the testing subagent returns

The subagent should return **only**:
- Overall pass/fail status
- Number of tests that passed / failed / errored
- For each failure: test name + error type + truncated error message (≤300 chars)
- A one-line suggested fix for each failure if the cause is obvious

It should NOT return: full stack traces, passing test details, warnings, coverage output.

### Template change: add to `templates/execute.md`

After **Step 5 (Implement the task)** and before **Step 6 (Commit changes)**, insert the following section:

```markdown
### Step 5b: Verify via testing subagent

If this project has tests relevant to the task you just implemented, spawn a testing subagent using the Task tool. Use the cheapest available model (claude-haiku-4-5-20251001):

**Subagent instructions:**
> Check whether `.ralph/{{PROJECT_NAME}}/test-instructions.md` exists.
> - If YES: read it and follow those instructions exactly to run the relevant tests.
> - If NO: explore the repository for test infrastructure — look for `pytest.ini`, `setup.cfg`, `pyproject.toml [tool.pytest]`, a `tests/` directory, or any `*_test.py` / `test_*.py` files. Determine how to run the tests and run them.
>
> Write the complete raw test output to `.ralph/{{PROJECT_NAME}}/test-results.md` (overwrite if it exists).
>
> Return ONLY a compact summary:
> - Overall: PASSED or FAILED
> - X passed, Y failed, Z errors
> - For each failure: [test name] — [error type]: [first 300 chars of the error message]
>
> Do not return the full output inline. Do not describe passing tests. Do not include warnings or coverage data.

If the subagent reports failures related to the task you just implemented, fix them before committing. You may re-run the testing subagent after fixing.

If no test infrastructure exists in the repository, skip this step.
```

The same section should be added to `templates/execute_async.md`.

### Model and permission notes

- Specify `model: claude-haiku-4-5-20251001` in the Task tool call — test running is straightforward and does not need a powerful model
- The subagent inherits `--dangerously-skip-permissions` from the parent (this is the current behaviour for all Ralph agents; no change needed)
- The subagent has access to the same working directory as the parent; it can run shell commands, read files, and write to `.ralph/`

---

## Part 2: Codebase Exploration Subagents

### The problem

For `ralph interview` and `ralph enrich`, the agent needs to understand the existing codebase before it can ask good questions or enrich the spec. Currently the agent reads source files, tests, and config directly — all of that content enters its context window.

For large codebases this can consume 10,000–30,000+ tokens just for orientation, before the agent has done any useful work. This also means the agent has less budget left for reasoning, outputting questions, and amending the spec.

### The subagent approach

Instead of the main agent reading all files itself, it can spawn 2–3 parallel exploration subagents, each responsible for a different part of the codebase. Each returns a compact summary (~200–400 words). The main agent synthesises the summaries and proceeds.

Token comparison:
| Approach | Tokens consumed by main agent |
|----------|------------------------------|
| Agent reads files directly | 10,000–30,000 (raw file content) |
| Exploration subagents | 600–1,200 (3 × ~300-word summaries) |

### Important quality tradeoff

**Summaries are lossy.** The exploration subagent distils the codebase into a summary, and nuance can be lost. This is acceptable for **question generation** (where you need a broad picture to identify gaps) but risky for **task generation** (where you need precise detail to write non-conflicting, correctly-scoped tasks).

Recommendation:
- **`questions.md` (interview phase):** Use exploration subagents. Broad understanding is sufficient for gap identification.
- **`generate_tasks.md` (task generation phase):** Do NOT use exploration subagents by default. This agent needs full detail to write correct task descriptions and dependency relationships. Let it read files directly.
- **`enrich` command:** Borderline — exploration subagents acceptable for the initial orientation pass; the agent still reads specific files in full when refining the spec.

### Sub-sub-agent limitation

There is a known Claude Code crash (GitHub issue #19077) if a subagent tries to create its own subagents. The exploration subagents spawned from `questions.md` must NOT be given instructions to further delegate. They must read files directly themselves. This is not a problem — exploration subagents are doing simple file reading, not complex reasoning.

Depth rule: Ralph agents may spawn subagents (1 level deep). Subagents must NOT spawn further subagents.

### Template change: modify `templates/questions.md` Step 1

Replace the current Step 1 (which asks the agent to read files directly) with:

```markdown
### Step 1: Understand the codebase via parallel exploration subagents

Before generating questions, build a picture of the codebase without filling your own context window with raw file contents. Spawn 2–3 parallel exploration subagents using the Task tool (use claude-haiku-4-5-20251001 for all of them):

**Subagent A — Spec and docs:**
> Read `.ralph/{{PROJECT_NAME}}/spec.md` in full. Also look for any README, CHANGELOG, or docs/ directory at the repository root.
> Return a 250-word summary covering: project goals, stated requirements, known constraints, and any gaps or ambiguities you notice in the spec itself.

**Subagent B — Source code:**
> Explore the repository source code (ignore .ralph/, node_modules/, .venv/, __pycache__). Identify the main modules, entry points, and key data structures. Skim 3–5 of the most central files.
> Return a 300-word summary covering: what the code currently does, the key components and their relationships, the technology stack, and any patterns or conventions visible in the code.

**Subagent C — Tests and config (optional):**
> Look for test files, CI config (.github/workflows/, .circleci/), and project config (pyproject.toml, package.json, Makefile). Skim them briefly.
> Return a 200-word summary covering: what is currently tested, the testing framework, and any build/run constraints.

Synthesise the summaries from all subagents into your working understanding of the project. Then proceed to Step 2.

Note: Do NOT spawn subagents from within your subagents.
```

### Template change: add exploration hint to `templates/generate_tasks.md`

The generate_tasks agent should still read files directly (for accuracy), but can be guided to be selective:

```markdown
### Step 1: Read existing .ralph and orient yourself

1. Read `.ralph/{{PROJECT_NAME}}/spec.md` in full.
2. Check whether `.ralph/{{PROJECT_NAME}}/tasks.json` exists. If it does, read it in full.
3. For codebase orientation: read the files most directly relevant to the spec requirements. You do not need to read every file — focus on entry points, the modules that the tasks will touch, and any existing tests. Use Glob and Grep to navigate efficiently rather than reading entire directories sequentially.
```

This is a prompt-level optimisation (more targeted reading) rather than a subagent pattern, and it's appropriate here given the accuracy requirement.

---

## Summary: What to Change

### High priority

| Change | Token impact | Effort |
|--------|-------------|--------|
| Add testing subagent instructions to `execute.md` and `execute_async.md` | 5,000–50,000 tokens saved per test run in execute agent | Low — template edit only |
| Create `.ralph/<project>/test-instructions.md` convention and document it | N/A (user-facing convention) | Low |

### Medium priority

| Change | Token impact | Effort |
|--------|-------------|--------|
| Add exploration subagent instructions to `questions.md` | 5,000–25,000 tokens saved per interview round | Low — template edit only |

### Not recommended

| Change | Reason |
|--------|--------|
| Exploration subagents in `generate_tasks.md` | Too lossy — task generation needs full codebase detail to be accurate |
| Background subagents (`run_in_background: true`) | Active bug causes output to be silently discarded (GitHub #17011) |
| Sub-sub-agents (subagent spawning another subagent) | Known crash / OOM (GitHub #19077) |

---

## Implementation Notes

### No Python changes required

Both patterns are **template-only changes**. The Python orchestration layer (`run.py`, `commands.py`) does not need modification. The agent receives a prompt that instructs it to use the Task tool, and Claude Code handles the rest.

### Subagent model specification

In the Task tool call, specify: `model: "claude-haiku-4-5-20251001"`. This uses the cheapest capable model for the subagent. The parent execute agent continues to use the default (sonnet).

Alternatively, set the environment variable `CLAUDE_CODE_SUBAGENT_MODEL=claude-haiku-4-5-20251001` globally. This overrides ALL subagent model choices, which is simpler but less flexible.

### Output file for test results

The testing subagent writes its full output to `.ralph/<project>/test-results.md`. This file:
- Is NOT read by the parent agent (it would defeat the purpose)
- Is available for human inspection after the run
- Can be referenced by the retry agent (`templates/retry.md`) if the retry agent needs context on what failed
- Should be added to `.gitignore` or the `.ralph/` directory's gitignore to avoid committing test noise

### Verifying token savings

Use `ralph execute` with `--output-format json` (already supported via `run_noninteractive_json`). Compare the `input_tokens` count before and after adding the testing subagent pattern on a project with a real test suite. The reduction should be visible from the first iteration where tests are run.
