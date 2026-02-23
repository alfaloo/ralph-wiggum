# Ralph Wiggum — Claude Code Optimisation: Findings & Spec

## Context

Ralph Wiggum is a Python-orchestrated AI development loop that spawns fresh `claude --print` subprocess agents for each task to avoid context-window degradation. Token usage is high and the user wants to know whether Claude Code's built-in features — subagents, `--worktree`, skills — can (a) reduce token consumption, and (b) simplify the Python orchestration code (particularly the async file-locking system).

---

## Findings

### 1. Claude Code Subagents — Not a Drop-In Replacement

**What subagents are:**
Subagents are Claude Code instances spawned *from within* a Claude Code session via the `Task` tool. A parent Claude Code agent writes `Task(...)` tool calls; the subagent runs, and only a summary comes back to the parent's context window. The key benefit is **keeping large verbose outputs (test logs, doc fetches) out of the parent's context window**.

**Why Ralph can't use them as-is:**
Ralph already spawns isolated `claude --print` processes from Python — these are not subagents. They are fully independent Claude Code sessions. To use true subagents, the Python orchestrator would have to be replaced by a *Claude Code agent* that itself dispatches subtasks via the `Task` tool. This is a fundamentally different architecture (Claude-driven orchestration vs Python-driven orchestration).

**Assessment for Ralph:**
- Ralph's Python orchestrator is *more deterministic* than a Claude-driven one. It owns DAG resolution, retry counters, task state, and branch management.
- Delegating orchestration to a Claude parent agent introduces non-determinism and a long-running parent context that itself degrades for large task lists.
- Known upstream issue: Claude loses context tracking when dispatching async sub-agents beyond the top level (GitHub issue #5483).
- **Recommendation: Do not migrate to a subagent architecture. Keep Python as the orchestrator.**

The one place subagents *could* help: if a single task involves a large amount of tool output (e.g., running a large test suite), a future enhancement could have the execute agent internally spawn sub-agents for the verbose parts and summarise the results. This is an optional future improvement, not a structural change.

---

### 2. `--worktree` for Async Parallel Execution — High Value for Code Safety

**What `--worktree` does:**
`claude --worktree` creates a git worktree on a new branch and runs Claude inside it. Each agent gets an isolated copy of the working tree, so concurrent agents cannot overwrite each other's source file changes.

**Current async mode risk:**
In `run_execute_loop_async()`, multiple `claude --print` processes run concurrently on the *same* branch. If two tasks touch the same source file (uncommon but possible), git commits from parallel agents can corrupt each other's work. The `locks.py` system only protects *artifact files* (`.ralph/*.json`) — it does NOT protect source code files.

**Proposed approach: manual git worktree management (not `--worktree` flag):**
Rather than the `--worktree` flag (which is designed for interactive sessions and may leave orphaned worktrees in headless mode), Ralph should manage worktrees directly:

```
Before spawning each async agent:
  git worktree add .ralph/.worktrees/<project>-<task-id> -b <project>-<task-id> HEAD

Invoke claude in the worktree directory (subprocess cwd=worktree_path).

After agent succeeds:
  git -C <main_repo> merge --no-ff <project>-<task-id>
  git worktree remove .ralph/.worktrees/<project>-<task-id>
  git branch -d <project>-<task-id>
```

**Effect on `locks.py`:**
In async mode, agents are already instructed NOT to modify artifact files (`execute_async.md` is explicit on this). The Python master thread updates artifact files sequentially in the polling loop. The `locked_json_rw` calls in the main thread protect against the case where multiple futures complete simultaneously and both try to update state. This protection should be **kept** — it is lightweight and correct.

**Net complexity change:**
- Removes: Source file conflict risk between parallel agents
- Adds: ~30 lines of worktree setup + merge + cleanup in `run_execute_loop_async()`
- Roughly neutral on code complexity; meaningfully improves correctness

**Files affected:** `ralph/run.py` (`run_execute_loop_async`)

---

### 3. Skills — Architecture Improvement, Modest Token Benefit

**What skills are:**
Skills are YAML frontmatter + markdown files that Claude Code loads *progressively*. Only metadata (~30–50 tokens) loads initially; the full body loads only when Claude determines the skill is relevant. The token benefit ("progressive disclosure") only applies when *multiple skills exist* and Claude can filter which ones are needed.

**Honest assessment for Ralph:**
Ralph currently spawns a fresh agent with the *entire* template as the `--print` prompt. The full template is always needed — there is no opportunity for progressive filtering. Converting templates to skills does NOT save input tokens in this invocation pattern. The prompt token count would be identical.

**Where skills DO offer value for Ralph:**
1. **Portability:** Skills follow the Agent Skills open standard and can be reused across projects and shared publicly.
2. **Linked files:** Skills can bundle secondary resources (e.g., spec.md format reference, example tasks.json) that load on-demand rather than being inlined.
3. **Cleaner architecture:** Templates become first-class Claude Code entities rather than raw markdown files with `{{PLACEHOLDER}}` substitution.
4. **Self-documentation:** The YAML frontmatter provides human-readable metadata for each agent type.

**Token savings: Zero for standalone invocations. Marginal for bundled resource files.**

**Recommendation:** Convert templates to skills as an optional polish step. Do not expect token savings from this alone.

---

### 4. Model Selection — High-Value Cost Optimisation

**Current situation:**
All agents (`run_noninteractive`, `run_noninteractive_json`) use Claude's default model. Simpler agents (question generation, summarise) use the same model as complex execute agents.

**Opportunity:**
```
Agent                 | Complexity | Recommended model
----------------------|------------|------------------
execute               | High       | claude-sonnet-4-6 (current default — keep)
validate              | High       | claude-sonnet-4-6
questions (interview) | Low        | claude-haiku-4-5 (~5x cheaper)
summarise             | Low        | claude-haiku-4-5
retry                 | Medium     | claude-sonnet-4-6
comment/enrich        | Medium     | claude-sonnet-4-6
```

**Implementation:** Add an optional `model` parameter to `run_noninteractive()` and `run_noninteractive_json()`:
```python
cmd = ["claude", "--dangerously-skip-permissions", "--print"]
if model:
    cmd += ["--model", model]
cmd += [prompt]
```

Then pass `model="claude-haiku-4-5-20251001"` from `_run_summarise()` and the questions phase of `run_interview_loop()`.

**Files affected:** `ralph/run.py`, potentially `ralph/commands.py`

---

### 5. Context Slimming for Execute Agents — Medium-Value Token Reduction

**Current situation:**
Every execute agent prompt instructs the agent to read `state.json`, `obstacles.json`, `tasks.json`, and `spec.md` in full. As the project progresses, `state.json` grows linearly (one entry per completed task). For a 20-task project, the last execute agent reads 19 completed entries it doesn't need.

**Opportunity:**
Pre-filter state and obstacles in `parse_execute_md()` / `parse_execute_async_md()` before passing them to agents. Options:
1. Inject a pre-filtered summary of state into the prompt: "N tasks completed, current task T7 has N previous attempts: ..."
2. Instruct agents to only read state entries relevant to their task ID (prompt change)

The prompt already reads the files from disk, so the agent incurs the token cost of full files. Option 1 (injecting a pre-filtered snippet) is more impactful.

**Estimated savings:** 100–500 tokens per agent on mid-to-large projects.

**Files affected:** `ralph/parse.py`, `templates/execute.md`, `templates/execute_async.md`

---

### 6. Claude Code Hooks — Optional Defensive Safeguard

**What hooks are:**
Hooks are shell commands that run at specific points in Claude Code's lifecycle (e.g., before/after file writes, before bash commands). They execute deterministically — unlike agent instructions, they cannot be accidentally skipped.

**Potential use in Ralph:**
A `PreToolUse` hook on `git checkout / git switch` could enforce the branch-locking rules that Ralph currently encodes only in prompt instructions. This would prevent an execute agent from accidentally switching branches even if it misunderstands its instructions.

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [{
        "type": "command",
        "command": "if echo \"$CLAUDE_TOOL_INPUT\" | grep -qE 'git (checkout|switch)'; then echo 'Branch switching is forbidden in ralph execute agents' >&2; exit 1; fi"
      }]
    }]
  }
}
```

**Assessment:** Low-priority hardening, not a token-efficiency change. Can be added to a CLAUDE.md in the ralph project directory or user-level config.

---

### 7. What NOT to Change

| Feature | Verdict | Reason |
|---------|---------|--------|
| Migrate to Agent SDK | No | Current subprocess approach is simpler, transparent, and works. SDK adds a Python dependency for no token savings |
| Subagent-driven orchestration | No | Claude parent context degrades; Python DAG logic is more deterministic |
| Remove `locks.py` | No | Lightweight, correct defensive code. Keep it |
| Reduce template detail | No | Template detail is what makes agents reliable. Don't cut |

---

## Recommended Changes (Prioritised)

### Priority 1 — Cost Reduction (Quick Win)
**Add model selection to cheap agents**
- `run_noninteractive()` accepts optional `model` param
- `_run_summarise()` → `claude-haiku-4-5-20251001`
- Interview question-generation phase → `claude-haiku-4-5-20251001`
- **Impact:** ~5x cost reduction for simple agent calls. No behaviour change.
- **Files:** `ralph/run.py`

### Priority 2 — Async Correctness (Medium Effort)
**git worktree isolation for async execute agents**
- Before spawning each async task agent, create a git worktree on a task-specific branch
- Pass the worktree directory as `cwd` to the subprocess
- After agent success, merge the task branch back to the project branch and remove the worktree
- **Impact:** Eliminates source file conflicts in async mode. Correctness improvement.
- **Files:** `ralph/run.py` (`run_execute_loop_async`)

### Priority 3 — Token Reduction (Medium Effort)
**Pre-filter context passed to execute agents**
- Inject a compact state summary ("Tasks completed: T1, T2, T3. Previous attempts at T7: 0.") into the prompt rather than having agents read full growing JSON files
- **Impact:** 100–500 token savings per agent on mid-to-large projects.
- **Files:** `ralph/parse.py`, `templates/execute.md`, `templates/execute_async.md`

### Priority 4 — Architecture Polish (Low Effort)
**Convert templates to Claude Code skills (optional)**
- Create `.claude/skills/` directory in the project
- Convert each template to a skill YAML+MD file
- No change to invocation logic; primarily for portability and standards alignment
- **Impact:** Zero token savings, better architecture, reusability
- **Files:** New `.claude/skills/` files

---

## Files That Will Change

| File | Change |
|------|--------|
| `ralph/run.py` | Add `model` param to `run_noninteractive()`; add worktree setup/merge/cleanup in `run_execute_loop_async()` |
| `ralph/parse.py` | Add state/obstacle filtering logic for execute prompts |
| `templates/execute.md` | Update to accept pre-filtered context snippet |
| `templates/execute_async.md` | Update to accept pre-filtered context snippet |

---

## Verification

1. **Model selection:** Run `ralph interview` + `ralph execute` with `--verbose true` and confirm haiku is used for question generation and summarise steps; confirm sonnet is used for execute/validate.
2. **Worktree isolation:** Run `ralph execute --asynchronous true` and confirm worktrees are created, task code changes are isolated per task, merge succeeds, and worktrees are cleaned up.
3. **Context slimming:** Compare token counts in the `--output-format json` output before and after the context slimming change on a project with 10+ completed tasks.
4. **Skills:** Run a fresh agent and confirm skills are loaded from `.claude/skills/` as expected.
