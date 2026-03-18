# Single-Agent Execute Mode — Specification

## Overview

Add a `--single` / `-s` boolean flag to `ralph execute` and `ralph oneshot` that, when `true`, replaces the iterative multi-agent execution loop with a single Claude agent invocation. The single agent reads the full project context (`spec.md`, `tasks.json`, `obstacles.json`, `state.json`) and implements all pending tasks in one pass. This significantly reduces per-agent startup overhead and token consumption for projects with many small tasks.

---

## Current Behaviour (Baseline)

### Synchronous execute loop (`run_execute_loop`)

```
ralph execute <project>
  └─ for iteration in range(1, limit+1):
       ├─ Load tasks.json, pick one ready task via dag.get_ready_tasks()
       ├─ Render templates/execute.md with task-specific context
       ├─ Invoke: claude --dangerously-skip-permissions --print --output-format json <prompt>
       ├─ Update tasks.json / state.json / obstacles.json
       └─ Loop until all tasks complete or max_attempts exceeded
  └─ Spawn summarise agent
```

Each iteration spawns a **fresh Claude process** for a **single task**. For a project with N tasks, N separate agents are launched. Each agent carries Claude's per-invocation startup cost and a context window sized for one task, but repeated across N invocations the cumulative token usage is significant.

---

## Proposed Behaviour

### Core Idea

When `--single true` is active, bypass the iteration loop entirely. Spawn **one agent** with instructions to read the project context and implement **all pending tasks** sequentially, committing after each one.

```
ralph execute <project> --single true
  └─ Runner.run_execute_single()
       ├─ Render templates/execute_single.md with full project context
       ├─ Invoke: claude --dangerously-skip-permissions --print --output-format json <prompt>
       └─ Spawn summarise agent
```

### Trade-offs

| | Multi-agent (default) | Single-agent (`--single true`) |
|---|---|---|
| Token usage | Higher (N × startup cost) | Lower (one startup cost) |
| Context window | Fresh per task | Accumulates across all tasks |
| Fault isolation | One task failure doesn't block agent | Single agent failure aborts all remaining tasks |
| Suitable for | Complex, large projects | Simpler projects with many small tasks |

---

## Flag Design

`--single` follows the same pattern as `--asynchronous`:

- **Global persistence:** `ralph --single true` saves to `.ralph/settings.json`; applies to all future `ralph execute` / `ralph oneshot` invocations until changed.
- **Per-invocation override:** `ralph execute <project> --single true` (or `false`) overrides the persisted setting for that run only.
- **Mutual exclusivity:** `--single true` and `--asynchronous true` are mutually exclusive. If both resolve to `true`, ralph should exit with an error: `[ralph] Error: --single and --asynchronous cannot both be true.`

### Default

`single: false` — existing multi-agent behaviour is unchanged.

---

## Technical Specification

### 1. `ralph/config.py` — New getter and setter

Add `get_single()` and `set_single()` following the exact pattern of `get_asynchronous()` / `set_asynchronous()`:

```python
def get_single() -> bool:
    return bool(_read_settings().get("single", False))

def set_single(value) -> None:
    if isinstance(value, str):
        if value.lower() == "true":
            value = True
        elif value.lower() == "false":
            value = False
        else:
            print(f"[ralph] Oops! '{value}' is not valid for single.")
            return
    elif not isinstance(value, bool):
        print(f"[ralph] Oops! '{value}' is not valid for single.")
        return
    data = _read_settings()
    data["single"] = value
    _write_settings(data)
```

Add `"single": False` to `_DEFAULTS`:

```python
_DEFAULTS = {
    "verbose": False,
    "rounds": 1,
    "limit": 20,
    "base": "main",
    "provider": "github",
    "asynchronous": False,
    "single": False,          # ← new
}
```

### 2. `ralph/cli.py` — Argument registration

**Global parser** (before subcommands):

```python
parser.add_argument(
    "--single", "-s",
    choices=["true", "false"],
    default=None,
    dest="global_single",
    metavar="BOOL",
    help="Persist single-agent execute setting to .ralph/settings.json (true/false)",
)
```

**Global flag handler** in `main()` (alongside existing `set_asynchronous` call):

```python
if args.global_single is not None:
    set_single(args.global_single == "true")
```

**`execute` subcommand** (alongside existing `--asynchronous` argument):

```python
execute_parser.add_argument(
    "--single", "-s",
    choices=["true", "false"],
    default=None,
    metavar="BOOL",
    help="Use a single agent to implement all tasks (true/false). Overrides persisted setting.",
)
```

**`oneshot` subcommand** (same addition):

```python
oneshot_parser.add_argument(
    "--single", "-s",
    choices=["true", "false"],
    default=None,
    metavar="BOOL",
    help="Use a single agent to implement all tasks (true/false). Overrides persisted setting.",
)
```

### 3. `ralph/commands.py` — Resolver and validation

**Add `_resolve_single()` helper** (alongside `_resolve_asynchronous()`):

```python
def _resolve_single(args: argparse.Namespace) -> bool:
    """Return effective single: per-command CLI flag > persisted setting."""
    if args.single is not None:
        return args.single == "true"
    return get_single()
```

**Update `ExecuteCommand.execute()`** to resolve the flag and validate mutual exclusivity, then pass it to the runner:

```python
class ExecuteCommand(Command):
    def execute(self) -> None:
        # ... existing setup ...
        asynchronous = _resolve_asynchronous(args)
        single = _resolve_single(args)

        if single and asynchronous:
            print("[ralph] Error: --single and --asynchronous cannot both be true.")
            sys.exit(1)

        Runner(project_name, verbose=verbose).run_execute_loop(
            limit,
            asynchronous=asynchronous,
            single=single,
            resume=args.resume,
        )
```

`OneshotCommand` delegates to `ExecuteCommand`, so no additional changes are needed there — the resolved flag flows through automatically.

### 4. `ralph/run.py` — New execution path

**Update `run_execute_loop()` signature** to accept `single`:

```python
def run_execute_loop(
    self,
    max_iterations: int,
    asynchronous: bool = False,
    single: bool = False,
    resume: bool = False,
) -> None:
    if single:
        self.run_execute_single()
    elif asynchronous:
        self.run_execute_loop_async([], max_iterations)
    else:
        # existing synchronous loop
        ...
```

**Add `run_execute_single()` method:**

```python
def run_execute_single(self) -> None:
    """Spawn one agent to implement all pending tasks in sequence."""
    from ralph.parse import parse_execute_single_md

    print("[ralph] Single-agent mode: spawning one agent for all tasks.")
    prompt = parse_execute_single_md(self.project_name)
    result = run_noninteractive_json(prompt)

    if self.verbose:
        print(result.stdout)

    try:
        data = json.loads(result.stdout)
        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        print(f"[ralph] Agent complete. Tokens used — input: {input_tokens}, output: {output_tokens}")
    except (json.JSONDecodeError, KeyError):
        pass

    print("[ralph] Running summarise agent...")
    self._run_summarise()
```

### 5. `ralph/parse.py` — New render function

```python
def parse_execute_single_md(project_name: str) -> str:
    """Render the single-agent execution prompt."""
    return _render(
        "execute_single.md",
        PROJECT_NAME=project_name,
    )
```

### 6. `templates/execute_single.md` — New prompt template

This template gives a single agent full authority over all pending tasks. Key differences from `execute.md`:

- No `ITERATION_NUM` / `MAX_ITERATIONS` / `TASK_ID` / `TASK_TITLE` / `TASK_DESCRIPTION` placeholders — the agent discovers tasks itself.
- The agent loops over all pending tasks internally, committing after each one.
- Artifact update instructions cover the full task list rather than a single task.

**Template content:**

```markdown
# Ralph Wiggum — Single-Agent Execute

You are an **execution agent** for Ralph Wiggum operating in **single-agent mode**.
Your job is to implement ALL pending tasks for this project in one session,
committing each task's changes as you go.

## Context

- **Project:** `{{PROJECT_NAME}}`
- **Artifact directory:** `.ralph/{{PROJECT_NAME}}/`

## Your Task

### Step 1: Orient yourself

Read the following files in full before doing anything else:

1. `.ralph/{{PROJECT_NAME}}/spec.md` — the project requirements
2. `.ralph/{{PROJECT_NAME}}/tasks.json` — the task list and statuses
3. `.ralph/{{PROJECT_NAME}}/state.json` — history of previous agent runs
4. `.ralph/{{PROJECT_NAME}}/obstacles.json` — known blockers and errors

Also run `git diff HEAD` (or `git diff` if no commits yet) to understand what has already been implemented.

### Step 2: Verify you are on the correct branch

Before touching any files:

1. Run `git branch --show-current`.
2. Confirm you are on `{{PROJECT_NAME}}`.
3. If you are not on the correct branch, **stop immediately** and report the discrepancy. Do not create or switch branches.

### Step 3: Implement all pending tasks in order

Work through `tasks.json` sequentially. For each task with `status: "pending"`, `blocked: false`, and all dependencies completed:

1. **Claim the task** — set its `status` to `"in_progress"` and increment `attempts` by 1 in `tasks.json` before starting.
2. **Check `obstacles.json`** for any known issues related to this task. Do not repeat past mistakes.
3. **Implement the task** — make the necessary code changes in the repository. Refer to `spec.md` for requirements context.
4. **Run tests** — if the project has test infrastructure, run the relevant tests and fix any failures caused by your changes.
5. **Commit** — once the implementation is complete and tests pass, commit:
   ```
   git add -A
   git commit -m "ralph: <task title> [{{PROJECT_NAME}} T<id>]"
   ```
6. **Update artifact files** (on success):
   - In `tasks.json`: set `status` to `"completed"`.
   - Append to `state.json`:
     ```json
     {
       "task_id": "<id>",
       "status": "completed",
       "summary": "<brief description of what was done>",
       "files_modified": ["<list of files changed>"],
       "obstacles": []
     }
     ```
7. **On failure** — if you cannot complete a task:
   - Set its `status` back to `"pending"` (or `"blocked": true` if it cannot proceed without external input).
   - Append a failure entry to `state.json` and an entry to `obstacles.json`.
   - Continue to the next task.

Repeat until all pending tasks have been attempted.

### Step 4: Exit

You are done once all tasks are either `completed` or `blocked`. Do not create a summary — the orchestrator handles that separately.

## Important Rules

- **Never create or switch branches.** All changes must be committed to `{{PROJECT_NAME}}`.
- **Do not skip artifact updates.** The orchestrator relies on `tasks.json` and `state.json` being accurate.
- **One commit per task.** Do not batch multiple tasks into a single commit.
- **Do not falsely mark tasks complete.** Only set `status: "completed"` when the implementation is actually done.
- All artifact file paths are relative to the current working directory.
```

---

## Files to Create / Modify

### CLI / Python

| File | Change |
|---|---|
| `templates/execute_single.md` | **Create** — single-agent prompt template |
| `ralph/config.py` | **Modify** — add `get_single()`, `set_single()`; add `"single": False` to `_DEFAULTS` |
| `ralph/cli.py` | **Modify** — add `--single / -s` to global parser and `execute` / `oneshot` subparsers; handle global flag in `main()` |
| `ralph/commands.py` | **Modify** — add `_resolve_single()`; update `ExecuteCommand.execute()` to resolve flag, validate mutual exclusivity with `--asynchronous`, and pass `single` to runner |
| `ralph/parse.py` | **Modify** — add `parse_execute_single_md()` |
| `ralph/run.py` | **Modify** — add `single` param to `run_execute_loop()`; add `run_execute_single()` method |
| `tests/test_cmd_execute.py` | **Modify** — add tests for `--single` flag resolution and mutual exclusivity check |
| `tests/test_run_execute.py` | **Modify** — add test for `run_execute_single()` invocation path |

### VSCode Extension

| File | Change |
|---|---|
| `ralph-vscode/webview/components/CommandDialog.tsx` | **Modify** — add `single` state, read from settings, render checkbox in execute/oneshot dialogs, push `--single` to args |
| `ralph-vscode/src/__tests__/messages.test.ts` | **Modify** — add assertions covering `single` flag in run_command payloads |

---

## VSCode Extension Changes

The extension exposes ralph flags through `CommandDialog.tsx`, which renders a modal of inputs when a command button is clicked. `--single` follows the same pattern as `--asynchronous`.

### `ralph-vscode/webview/components/CommandDialog.tsx`

#### 1. Add `single` to `initState()`

In the `initState()` function (alongside `asynchronous`), read the flag from `settings.json`:

```typescript
single: settingBool(settings, '--single'),
```

`settingBool()` already handles missing keys by returning `false`, so no default fallback is needed.

#### 2. Add `single` to local state

In the component state declaration (alongside `asynchronous`):

```typescript
const [single, setSingle] = useState(false);
```

The `useEffect` that calls `initState()` on settings change should also set this:

```typescript
setSingle(s.single);
```

#### 3. Add `--single` to args in `handleRun()` for `execute`

In the `execute` case of `handleRun()` (alongside the existing `--asynchronous` push):

```typescript
args.push('--single', String(single));
```

#### 4. Add `--single` to args in `handleRun()` for `oneshot`

Same addition in the `oneshot` case:

```typescript
args.push('--single', String(single));
```

#### 5. Render checkbox in the Execute dialog section

In the JSX for the `execute` command (alongside the `--asynchronous` checkbox):

```tsx
<label>
  <input
    type="checkbox"
    checked={single}
    onChange={e => setSingle(e.target.checked)}
  />
  Single-agent mode
</label>
<p className="flag-description">
  Spawn one agent to implement all tasks in sequence. Reduces token usage.
  Cannot be combined with asynchronous mode.
</p>
```

**Mutual exclusivity UI note:** When `single` is checked, the asynchronous checkbox should be disabled (and vice versa). Add `disabled={single}` to the asynchronous checkbox and `disabled={asynchronous}` to the single checkbox.

#### 6. Render checkbox in the Oneshot dialog section

Identical addition in the `oneshot` JSX section.

#### 7. Client-side validation in `handleRun()`

Before building args, guard against both flags being enabled simultaneously:

```typescript
if (single && asynchronous) {
  vscode.postMessage({ type: 'show_error', message: '--single and --asynchronous cannot both be true.' });
  return;
}
```

This mirrors the CLI-level guard and prevents a visually confusing error from appearing in the output panel after the process has started.

---

## README / Docs Updates

### `ralph execute` entry

Add `--single BOOL` to the flag table:

```
- `--single BOOL` (alias `-s`) runs all tasks with a single agent instead of one agent per task. Reduces token usage for projects with many small tasks. Cannot be combined with `--asynchronous true` (default: `false`).
```

### Global flags table

Add row:

| `--single true\|false` | `-s` | `false` | Use a single agent for all tasks in `ralph execute`. Cannot be combined with `--asynchronous`. |

### Caveats section

Add:

> - When using `--single true`, a single Claude agent handles all pending tasks. If that agent is interrupted mid-run, tasks that were not yet started remain `"pending"` and can be resumed with `ralph execute --resume`. Tasks that were in-progress at interruption time may be left in `"in_progress"` status and will need manual reset or a fresh `ralph undo`.

---

## Edge Cases

| Scenario | Behaviour |
|---|---|
| `--single true` and `--asynchronous true` both resolve to `true` | Exit with error: `[ralph] Error: --single and --asynchronous cannot both be true.` |
| All tasks already completed when `--single` is invoked | Agent reads `tasks.json`, finds nothing pending, logs `no_tasks_available` in `state.json`, exits cleanly. Summarise agent still runs. |
| Agent interrupted mid-run | Tasks completed before interruption remain `"completed"`. Remaining `"pending"` tasks can be resumed with `ralph execute --resume` (using normal multi-agent or single-agent mode). |
| Agent marks a task `"blocked"` | Continues to next task; blocked task is skipped for the remainder of the run. |
| Project has no `tasks.json` | Same precondition check as the existing execute loop — abort with existing error message before spawning the agent. |

---

## Testing Strategy

### VSCode Extension Tests (`ralph-vscode/src/__tests__/`)

- `single_checkbox_present_in_execute_dialog`: render `CommandDialog` for `execute`; assert a checkbox labelled "Single-agent mode" is present.
- `single_checkbox_present_in_oneshot_dialog`: same for `oneshot`.
- `single_flag_included_in_run_command_args`: simulate checking `single`, clicking Run; assert `run_command` message contains `'--single', 'true'`.
- `single_and_async_checkboxes_mutually_disabled`: when `single` is checked, assert `asynchronous` checkbox has `disabled` attribute; and vice versa.
- `client_validation_blocks_both_flags`: programmatically set both `single=true` and `asynchronous=true`; click Run; assert `show_error` message is posted and `run_command` is not posted.

### Unit Tests (`tests/test_cmd_execute.py`)

- `test_single_true_forwarded_to_run_execute_loop`: assert `run_execute_loop` called with `single=True` when `--single true` passed.
- `test_single_false_forwarded_to_run_execute_loop`: assert `run_execute_loop` called with `single=False` when `--single false` passed.
- `test_single_defaults_from_settings`: mock `get_single()` to return `True`; assert `run_execute_loop` called with `single=True` when flag is absent.
- `test_single_and_async_mutual_exclusivity`: pass both `--single true` and `--asynchronous true`; assert `sys.exit(1)` called.

### Unit Tests (`tests/test_run_execute.py`)

- `test_run_execute_loop_dispatches_to_single_when_single_true`: mock `run_execute_single`; call `run_execute_loop(limit, single=True)`; assert `run_execute_single` called, async loop not called.
- `test_run_execute_single_invokes_agent`: mock `run_noninteractive_json` and `_run_summarise`; assert correct prompt rendered and summarise agent called after.

### Integration / Smoke Test

1. Set up a minimal project with 3 tasks.
2. Run `ralph execute <project> --single true`.
3. Verify all 3 tasks are marked `"completed"` in `tasks.json`.
4. Verify `state.json` contains one entry per task.
5. Verify `summary.md` and `pr-description.md` are generated.

---

### Integration / Smoke Test (VSCode Extension)

1. Open a project panel; verify `single` checkbox is unchecked by default.
2. Open `settings.json`, set `"single": true`; reload the panel; verify checkbox is pre-checked.
3. Check `single`, click Run on execute; verify the spawned process receives `--single true`.
4. Check both `single` and `asynchronous`; verify the `asynchronous` checkbox becomes disabled once `single` is checked (and vice versa).

---

## Out of Scope

- Changing the behaviour of `--single false` (identical to the existing default).
- Applying `--single` to `ralph retry` (retry is already a single-agent command by design).
- Streaming output from the single agent (output is captured as with all other agent invocations).
- Automatic selection of `--single` based on task count heuristics.
