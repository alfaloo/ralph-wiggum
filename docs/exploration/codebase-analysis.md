# Ralph Wiggum — Codebase Analysis

This document records findings from a thorough read of the Python orchestration layer
(`ralph/cli.py`, `commands.py`, `run.py`, `dag.py`, `parse.py`, `config.py`, `locks.py`)
cross-referenced against the public-facing README.

Please address all of these issues.

---

## 1. README vs Code Discrepancies

### 1.1 `ralph init` creates an undocumented `test-instructions.md`

**README says** — `ralph init` creates:
> `spec.md`, `tasks.json`, `state.json`, `obstacles.json` — tracking files used by the agents

**Code does** — `InitCommand.execute()` additionally creates `test-instructions.md` from `_TEST_INSTRUCTIONS_TEMPLATE`. This file is not listed in the README at all.

**Recommended solution:** Update the README's `ralph init` section to list `test-instructions.md` alongside the other generated files and briefly describe its purpose (a human-editable file that tells the validation and execute agents how to run the project's tests).

---

### 1.2 `test-instructions.md` is written with `json.dump()` — a bug

`commands.py:300-302`:

```python
test_instructions_path = os.path.join(ralph_dir, "test-instructions.md")
with open(test_instructions_path, "w") as f:
    json.dump(_TEST_INSTRUCTIONS_TEMPLATE, f)
```

`json.dump` on a plain string JSON-encodes it, so the file ends up containing:

```
"# Please define the instructions for how to run tests for this project\n"
```

— i.e. a JSON string literal with surrounding double-quotes and an escaped newline, inside a `.md` file. It should be `f.write(_TEST_INSTRUCTIONS_TEMPLATE)`.

**Recommended solution:** Replace `json.dump(_TEST_INSTRUCTIONS_TEMPLATE, f)` with `f.write(_TEST_INSTRUCTIONS_TEMPLATE)` in `commands.py`.

---

### 1.3 `ralph status` shows individual tasks, not just "task status counts"

**README says:**
> Shows the active branch, execution mode flags, **task status counts** (pending/in_progress/completed), outstanding obstacles, and the validation rating

**Code does** — `StatusCommand.execute()` prints *every individual task* (id, status, title) and then adds a summary count line at the end. The README description implies only aggregate counts are shown.

**Recommended solution:** Update the README to accurately describe the output — e.g. "Lists every task with its id, status, and title, followed by a summary count" — since the per-task view is more useful than aggregate counts and the code behaviour is correct.

---

### 1.4 `--single --resume` does not reset incomplete tasks

**README (Caveats section) says:**
> When using `--single true`, a single Claude agent handles all pending tasks. If that agent is interrupted mid-run, tasks that were not yet started remain `"pending"` and can be resumed with `ralph execute --resume`.

**Code does** — `run_execute_loop` (run.py:616):

```python
def run_execute_loop(self, max_iterations, asynchronous=False, single=False, resume=False):
    if single:
        self.run_execute_single()
        return          # <— returns HERE, never reaches the resume block below

    if resume:
        self._reset_incomplete_tasks()  # never called in single mode
```

When `single=True`, the early return bypasses `_reset_incomplete_tasks`. So `ralph execute myproject --single true --resume` does NOT reset in-progress tasks, contradicting the documented behaviour.

**Recommended solution:** In `run_execute_loop`, call `_reset_incomplete_tasks` before branching on `single`:

```python
def run_execute_loop(self, max_iterations, asynchronous=False, single=False, resume=False):
    if resume:
        self._reset_incomplete_tasks()   # moved up, applies to all modes

    if single:
        self.run_execute_single()
        return
    ...
```

---

### 1.5 `run_execute_loop_async` does not enforce `--limit`

**README says:**
> `--limit N` sets the maximum number of agent iterations (default: 20)

**Code does** — In async mode, `max_iterations` is passed down into the async execute prompt (as a display value) but there is no iteration counter in `run_execute_loop_async`. The loop only exits when all tasks complete or `max_attempts` is exceeded. An upper bound on *wall-clock iterations* is absent.

**Recommended solution:** Add a loop iteration counter to `run_execute_loop_async` and break with an appropriate `exit_reason` when it is reached, mirroring the `for iteration in range(1, max_iterations + 1)` pattern in the synchronous path. Alternatively, update the README to clarify that `--limit` controls per-task `max_attempts` in async mode rather than total loop iterations.

---

### 1.6 Global `--provider` is not validated when used alongside a subcommand

**README says:**
> `--provider github|gitlab` … Validates that the provider's CLI tool is installed and authenticated before saving.

**Code does** — `cli.py:416-419` validates when used at the top level without a subcommand. But `cli.py:423-424`:

```python
if args.global_provider is not None:
    set_provider(args.global_provider)   # <— no _validate_provider_cli call
```

When `--provider` appears alongside any subcommand, it is persisted without CLI validation. The README's guarantee only holds when there is no subcommand.

**Recommended solution:** In `cli.py`, move the provider validation to run in both branches — i.e. call `_validate_provider_cli` before `set_provider` at line 423 just as is done at line 417:

```python
if args.global_provider is not None:
    if not _validate_provider_cli(args.global_provider):
        sys.exit(1)
    set_provider(args.global_provider)
```

---

### 1.7 `_print_validate_summary` checks `"requires_attention"` (underscore) not `"requires attention"` (space)

`commands.py:214`:

```python
if overall_status in ("requires_attention", "failed") and error_description:
```

But the validation agent writes `# Rating: requires attention` (with a space) to `validation.md`, and the upstream JSON result would contain `"requires attention"`. The `"What went wrong"` block in the console summary therefore never renders for `requires attention` results.

**Recommended solution:** Replace `"requires_attention"` with `"requires attention"` (space) in the `_print_validate_summary` check in `commands.py`:

```python
if overall_status in ("requires attention", "failed") and error_description:
```

---

### 1.8 `ralph undo` does not reset `validation.md`, `summary.md`, or `pr-description.md`

After `ralph undo`, `state.json`, `obstacles.json`, and `tasks.json` are reset. The artifact files (`validation.md`, `summary.md`, `pr-description.md`) are left on disk. A subsequent `ralph execute` will re-run but `ralph validate` would prompt "already exists — overwrite?" for a `validation.md` from the prior run. The README does not call this out. Low severity but can be surprising.

**Recommended solution:** In `UndoCommand.execute()`, delete `validation.md`, `summary.md`, and `pr-description.md` if they exist (using `os.path.exists` + `os.unlink`) so the project directory is fully reset to a pre-execute state. Add a note to the README listing all files cleared by `ralph undo`.

---

## 2. Code Quality Issues

### 2.1 `_handle_result` return type annotation is wrong and return value is unused

`run.py:309-315`:

```python
def _handle_result(self, result: subprocess.CompletedProcess) -> None:
    if self.verbose and result.stdout:
        print(result.stdout)
    if result.returncode != 0 and result.stderr:
        print(...)
    return result.stdout          # <— returns a value from a ->None function
```

The return value is never used by any caller. The `-> None` annotation is misleading. Either the return should be removed or the annotation fixed to `-> str | None`.

**Recommended solution:** Remove the `return result.stdout` line. The method's purpose is side-effects only (print on error/verbose); if stdout is ever needed at the call site, callers should read `result.stdout` directly.

---

### 2.2 `run_execute_single` uses a hardcoded path string instead of `self._tasks_path`

`run.py:574` and `run.py:604`:

```python
tasks_path = f".ralph/{self.project_name}/tasks.json"
```

`Runner.__init__` already sets `self._tasks_path`. Every other method uses it. These two occurrences bypass it, creating a subtle inconsistency and a potential maintenance trap.

**Recommended solution:** Replace both `tasks_path = f".ralph/{self.project_name}/tasks.json"` lines in `run_execute_single` with `self._tasks_path`.

---

### 2.3 `run_execute_single` uses `json.loads(f.read())` instead of `json.load(f)`

`run.py:576`:

```python
tasks_data = json.loads(f.read())
```

All other file-reads in the codebase use `json.load(f)`. Minor but inconsistent.

**Recommended solution:** Replace `json.loads(f.read())` with `json.load(f)` in both read sites inside `run_execute_single`.

---

### 2.4 `Runner._all_tasks_complete` and `Runner._any_task_exceeded_max_attempts` duplicate `dag` module logic

`Runner._all_tasks_complete()` re-implements the same logic as `dag.all_tasks_complete()`. Similarly for `_any_task_exceeded_max_attempts`. The Runner methods add only the file-read layer; the predicate logic is duplicated. The sync execute loop even uses the Runner methods while the async loop correctly uses the `dag` functions.

One subtle difference: `dag.all_tasks_complete` uses `t["status"]` (raises `KeyError` if key absent), while `Runner._all_tasks_complete` uses `t.get("status")`. The discrepancy should be resolved.

**Recommended solution:** Simplify both Runner methods to a thin disk-read wrapper that delegates to the `dag` functions:

```python
def _all_tasks_complete(self) -> bool:
    if not os.path.exists(self._tasks_path):
        return False
    tasks = locks.read_json(self._tasks_path).get("tasks", [])
    return bool(tasks) and dag.all_tasks_complete(tasks)

def _any_task_exceeded_max_attempts(self) -> tuple[bool, dict | None]:
    if not os.path.exists(self._tasks_path):
        return False, None
    tasks = locks.read_json(self._tasks_path).get("tasks", [])
    return dag.any_task_exceeded_max_attempts(tasks)
```

Also update `dag.all_tasks_complete` to use `t.get("status")` for defensive access, consistent with the rest of the codebase.

---

### 2.5 `_DEFAULT_LIMIT = 20` is defined in two places

`commands.py:39` defines `_DEFAULT_LIMIT = 20`. `config.py:193` defines `_DEFAULTS = {..., "limit": 20, ...}`. The same constant lives in two modules. If the default ever changes, it must be updated in both.

**Recommended solution:** Remove `_DEFAULT_LIMIT` from `commands.py` and expose the value from `config.py` instead — e.g. add `DEFAULT_LIMIT = _DEFAULTS["limit"]` to `config.py` and import it in `commands.py`.

---

### 2.6 `config.py` getters are inconsistently "self-healing"

Some getters write the default back to disk when the key is absent (`get_rounds`, `get_limit`, `get_base`, `get_provider`), while others simply return the default without persisting (`get_verbose`, `get_asynchronous`, `get_single`). `ensure_defaults()` already handles bulk-initialisation. The self-healing per-getter logic is redundant given `ensure_defaults()` exists, and the inconsistency is confusing.

**Recommended solution:** Remove the self-healing write-back from all individual getters. Each getter should simply read the value and return the default if absent. Rely solely on `ensure_defaults()` (called at `ralph init`) for initialisation. This makes every getter a clean one-liner.

---

### 2.7 `PrCommand` duplicates the GitHub and GitLab branches almost entirely

`commands.py:893-1059` — the `github` and `gitlab` branches share the same six-step pattern:

1. Check CLI installed
2. Verify current branch == project name
3. Check working tree is clean
4. Check `pr-description.md` exists
5. Push branch
6. Create PR/MR

Only the CLI binary name (`gh` / `glab`), one flag (`--head` vs `--source-branch`), and the success message differ. ~80 lines are copy-pasted.

**Recommended solution:** Extract a `_do_create_pr` helper that accepts a provider config dataclass (or named tuple) containing the binary, branch flag, and display name. Both branches then become a short config block + one `_do_create_pr(config, ...)` call. Example shape:

```python
from dataclasses import dataclass

@dataclass
class _ProviderConfig:
    binary: str
    branch_flag: str
    pr_noun: str   # "pull request" or "merge request"

_GITHUB = _ProviderConfig("gh", "--head", "pull request")
_GITLAB = _ProviderConfig("glab", "--source-branch", "merge request")
```

---

### 2.8 `_resolve_asynchronous` vs `_resolve_single` use inconsistent attribute access

`commands.py:97`:
```python
def _resolve_asynchronous(args):
    if args.asynchronous is not None:   # direct attribute access
```

`commands.py:103`:
```python
def _resolve_single(args):
    if getattr(args, "single", None) is not None:   # safe getattr
```

Both functions are only called from `ExecuteCommand`, which has both flags, so neither is wrong. But the inconsistency is distracting. Either both should use `getattr` (defensive) or both should use direct access.

**Recommended solution:** Standardise on `getattr(args, "<flag>", None)` across all three `_resolve_*` helpers (`_resolve_verbose`, `_resolve_asynchronous`, `_resolve_single`) for defensive consistency, especially since these helpers are also imported and used in `cli.py` which creates parsers for many subcommands.

---

### 2.9 `run_execute_loop_async` accepts a `prompts` parameter it never uses

`run.py:428`:

```python
def run_execute_loop_async(self, prompts: list[str], max_iterations: int) -> None:
    """...The ``prompts`` parameter is accepted for API compatibility..."""
```

The `prompts` argument is unused. It is called with `[]` (run.py:626). Dead parameter pollutes the signature.

**Recommended solution:** Remove the `prompts` parameter from `run_execute_loop_async` and update the call site in `run_execute_loop` from `self.run_execute_loop_async([], max_iterations)` to `self.run_execute_loop_async(max_iterations)`.

---

### 2.10 Synchronous execute loop does not use `locks` for its pre-update of `tasks.json`

`run.py:663-664` writes `tasks.json` with plain `open(..., "w")` while `run_execute_loop_async` uses `locked_json_rw`. For the synchronous path this is safe (no concurrency), but the inconsistency could confuse contributors and makes the file-write semantics irregular.

**Recommended solution:** Replace the raw `open(..., "w") + json.dump` in the synchronous execute loop pre-update with `locks.write_json(self._tasks_path, tasks_data)` to align with the locking pattern used everywhere else.

---

### 2.11 `dag.all_tasks_complete` returns `True` for an empty task list

`dag.py:31`:

```python
return all(t["status"] == "completed" for t in tasks)
```

`all([])` returns `True` in Python. An empty task list is thus "complete". In practice `ExecuteCommand` already guards against empty `tasks.json`, but the `dag` function's semantics are surprising and undocumented.

**Recommended solution:** Add an explicit empty-list guard to `dag.all_tasks_complete`:

```python
def all_tasks_complete(tasks: list[dict]) -> bool:
    return bool(tasks) and all(t.get("status") == "completed" for t in tasks)
```

---

### 2.12 `parse_summarise_md` uses a lowercase key `ralph_dir` inconsistent with the uppercase convention

`parse.py:118-125`:

```python
return _render(
    "summarise.md",
    PROJECT_NAME=project_name,
    ralph_dir=ralph_dir,       # <— lowercase, unlike every other key
    EXIT_REASON=exit_reason,
)
```

All other `_render` calls use `UPPER_SNAKE_CASE` keys matching the `{{UPPER_SNAKE_CASE}}` placeholders in templates. The lowercase `ralph_dir` is inconsistent.

**Recommended solution:** Rename the key to `RALPH_DIR` in `parse_summarise_md` and update the corresponding `{{ralph_dir}}` placeholder in `templates/summarise.md` to `{{RALPH_DIR}}`.

---

### 2.13 `cli.py` imports private helpers from `commands.py`

`cli.py:17-24` imports `_DEFAULT_LIMIT`, `_validate_branch_exists`, `_validate_provider_cli`, `_assert_project_exists`, `_resolve_verbose`, `_resolve_asynchronous`, `_resolve_provider`, `_ENRICH_COMMENT` — all prefixed `_` (convention: private). These should either be made public (no leading underscore) or the CLI should not depend on them directly.

**Recommended solution:** Remove the leading underscore from any symbol in `commands.py` that is intentionally part of the module's public API consumed by `cli.py` (e.g. `validate_branch_exists`, `resolve_verbose`, `DEFAULT_LIMIT`, `ENRICH_COMMENT`). Symbols that are truly internal helpers and happen to be imported by `cli.py` for back-compat reasons should instead be re-exported via a small `__all__` list in `commands.py`.

---

### 2.14 Inconsistent `sys.exit(1)` vs `return` at precondition failures

Some guard functions call `sys.exit(1)` (e.g. `_validate_branch_exists`, `_assert_project_exists`), while others return a bool (e.g. `_validate_provider_cli`). The caller of `_validate_provider_cli` then must remember to check the return value and call `sys.exit`. The mixed contract makes error handling harder to follow.

**Recommended solution:** Standardise all guard/precondition helpers to call `sys.exit(1)` directly after printing an error message (matching `_validate_branch_exists` and `_assert_project_exists`). Remove the `if not _validate_provider_cli(...): sys.exit(1)` pattern at every call site — the guard itself handles the exit. This makes all precondition checks self-contained.

---

## 3. Simplification Opportunities

### 3.1 Merge the `_all_tasks_complete` / `_any_task_exceeded_max_attempts` duplication

Both `Runner` and `dag` implement the same predicates. The Runner methods could read from disk then delegate to the `dag` functions for the actual logic:

```python
def _all_tasks_complete(self) -> bool:
    if not os.path.exists(self._tasks_path):
        return False
    data = json.load(open(self._tasks_path))
    tasks = data.get("tasks", [])
    return bool(tasks) and dag.all_tasks_complete(tasks)
```

This removes the duplicate logic and makes `dag.py` the single source of truth for task predicates.

---

### 3.2 Extract a shared `_pr_create` helper to eliminate the GitHub/GitLab copy-paste

The 80-line duplication in `PrCommand` can be collapsed into a single helper that accepts a provider-specific config object (CLI binary, branch flag name, create sub-command, etc.), reducing the two branches to a handful of lines each.

---

### 3.3 Consolidate `_DEFAULT_LIMIT` to `config.py`

`commands.py` should import `_DEFAULTS["limit"]` from `config.py` rather than re-declaring `_DEFAULT_LIMIT = 20`.

---

### 3.4 Standardise bool flag parsing into a shared helper

`_resolve_verbose`, `_resolve_asynchronous`, and `_resolve_single` all follow the same pattern:

```python
if <flag> is not None:
    return <flag> == "true"
return get_<setting>()
```

This can be a single function:

```python
def _resolve_bool_flag(value: str | None, getter: Callable[[], bool]) -> bool:
    return value == "true" if value is not None else getter()
```

---

### 3.5 Unify self-healing config getters

Either all getters should self-heal (write back the default if absent) or none should. Given `ensure_defaults()` already does a one-shot full initialisation at `ralph init`, per-getter self-healing is redundant. Removing it would simplify each getter to a one-liner.

---

### 3.6 `run_execute_single` should use `self._tasks_path`

Replace both `f".ralph/{self.project_name}/tasks.json"` occurrences in `run_execute_single` with `self._tasks_path` to match the rest of the class.

---