# Ralph Wiggum — Code Audit & Improvement Findings

**Scope:** Full audit of Python source (`ralph/`), CLI entry point (`ralph/cli.py`), and cross-reference against `README.md`.
**Date:** 2026-03-20
**Methodology:** Manual code review of all `.py` source files plus README comparison.

---

## Table of Contents

1. [README vs. Source Discrepancies](#1-readme-vs-source-discrepancies)
2. [Code Repetition / DRY Violations](#2-code-repetition--dry-violations)
3. [Inconsistencies Across the Codebase](#3-inconsistencies-across-the-codebase)
4. [Code Clarity & Naming Issues](#4-code-clarity--naming-issues)
5. [Minor Bug Risks / Edge Cases](#5-minor-bug-risks--edge-cases)
6. [Style & Standards](#6-style--standards)

---

## 1. README vs. Source Discrepancies

### 1.1 `ralph oneshot` undocumented `--resume` flag

**Location:** `ralph/cli.py:315–320`
**Issue:** The `oneshot_parser` accepts a `--resume / -r` flag, but the README synopsis for `ralph oneshot` only lists:
```
ralph oneshot <project-name> [--limit N] [--base BRANCH] [--verbose BOOL] [--asynchronous BOOL] [--single BOOL]
```
`--resume` (and `--provider`) are absent from the README signature.

**Suggested fix:** Add `[--resume] [--provider github|gitlab]` to the `ralph oneshot` synopsis in the README.

---

### 1.2 `pyproject.toml` version vs `RALPH_VERSION` mismatch

**Location:** `pyproject.toml:7` (`version = "0.1.0"`) vs `ralph/cli.py:50` (`RALPH_VERSION = "4.0.0"`)
**Issue:** The installable package version and the banner version are out of sync. A user who inspects the installed package metadata (e.g. `pip show ralph-wiggum`) will see `0.1.0`, while `ralph` (no args) prints `4.0.0`.

**Suggested fix:** Use a single source of truth. Either read `importlib.metadata.version("ralph-wiggum")` in `cli.py`, or keep `RALPH_VERSION` and set `pyproject.toml` to match it (e.g. via a dynamic version field).

---

### 1.3 `ralph validate` — overwrite prompt not mentioned in README

**Location:** `ralph/commands.py:487–493`
**Issue:** The README states: _"If `validation.md` already exists, you are prompted (`y/n`) before it is overwritten."_
This is correct. However, when `ralph oneshot` calls `ValidateCommand.execute()` internally, this interactive prompt fires if `validation.md` already exists (e.g. on a second `oneshot` run), which can stall an otherwise fully-automated pipeline unexpectedly. This behaviour is not noted in the `ralph oneshot` documentation.

**Suggested fix:** Add a note in the `ralph oneshot` section that re-running it when `validation.md` already exists will trigger an interactive prompt.

---

### 1.4 `ralph pr` — authentication not validated upfront

**Location:** `ralph/commands.py:1018–1032` (`PrCommand.execute()`) and `ralph/commands.py:930–1015` (`_do_create_pr`)
**Issue:** The README caveats say the `ralph pr` command requires the relevant CLI tool to be installed and authenticated. However, `PrCommand.execute()` never calls `validate_provider_cli()`. `_do_create_pr` only checks if the binary is installed via `--version`; it does not check authentication. If the user is not authenticated, the command will fail mid-execution during `git push` or the create step with a raw stderr dump.

The global `--provider` setter *does* call `validate_provider_cli()`, but that's a different code path.

**Suggested fix:** Call `validate_provider_cli(provider)` at the start of `PrCommand.execute()` before `_do_create_pr()`, consistent with the global-flag path.

---

## 2. Code Repetition / DRY Violations

### 2.1 `validation.md` rating parsing duplicated three times

**Location:**
- `UndoCommand.execute()` — `ralph/commands.py:533–539`
- `RetryCommand.execute()` — `ralph/commands.py:655–661`
- `OneshotCommand.execute()` — `ralph/commands.py:728–737`

**Issue:** All three commands open `validation.md`, iterate lines, and extract the rating with a `re.match`. The regex patterns are slightly inconsistent too:
- `UndoCommand` and `RetryCommand` use `r"#\s*[Rr]ating:\s*(.+)"` with `re.IGNORECASE` (the `[Rr]` is redundant due to the flag)
- `OneshotCommand` uses `r"#\s*Rating:\s*(.+)"` with `re.IGNORECASE`

**Suggested fix:** Extract a shared helper:
```python
def _read_validation_rating(validation_path: str) -> str | None:
    """Return the rating string from validation.md, or None if not found."""
    try:
        with open(validation_path) as f:
            for line in f:
                m = re.match(r"#\s*rating:\s*(.+)", line.strip(), re.IGNORECASE)
                if m:
                    return m.group(1).strip().lower()
    except OSError:
        pass
    return None
```

---

### 2.2 Git subprocess patterns repeated throughout `commands.py`

**Location:** `ralph/commands.py` — multiple commands
**Issue:** The same boilerplate git subprocess calls appear across several commands with nearly identical error-handling:

```python
# Pattern A — branch existence check (appears 4× across Execute, Retry, Validate, PrCommand)
result = subprocess.run(["git", "branch", "--list", name], capture_output=True, text=True)
if not result.stdout.strip():
    print(f"[ralph] I can't find branch '{name}'.", file=sys.stderr)
    sys.exit(1)

# Pattern B — checkout (appears 4× across Execute, Validate, Undo, Retry)
result = subprocess.run(["git", "checkout", branch], capture_output=True, text=True)
if result.returncode != 0:
    print(f"[ralph] I couldn't get to branch '{branch}': {result.stderr.strip()}", file=sys.stderr)
    sys.exit(1)
```

**Suggested fix:** Add two small helpers (already consistent with the existing `validate_branch_exists` pattern):
```python
def _git_checkout(branch: str) -> None:
    result = subprocess.run(["git", "checkout", branch], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ralph] I couldn't get to branch '{branch}': {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

def _git_branch_exists(branch: str) -> bool:
    result = subprocess.run(["git", "branch", "--list", branch], capture_output=True, text=True)
    return bool(result.stdout.strip())
```

---

### 2.3 `validate_provider_cli` has near-identical blocks for GitHub and GitLab

**Location:** `ralph/commands.py:114–155`
**Issue:** The function contains two near-identical `if/elif` blocks — one for `"github"` and one for `"gitlab"` — that perform the same operations with only the binary name and URL differing:

```python
if provider == "github":
    try:
        result = subprocess.run(["gh", "auth", "status"], capture_output=True)
    except FileNotFoundError:
        print("[ralph] I can't find the 'gh' thingy! ...")
        sys.exit(1)
    if result.returncode != 0:
        print("[ralph] The 'gh' thingy doesn't know who you are! ...")
        sys.exit(1)
elif provider == "gitlab":
    # identical structure with "glab" and a different URL
```

The `_ProviderConfig` dataclass already captures `binary` and `cli_url`, but is only used in `_do_create_pr`, not in `validate_provider_cli`.

**Suggested fix:** Refactor `validate_provider_cli` to use `_GITHUB`/`_GITLAB` configs:
```python
def validate_provider_cli(provider: str) -> None:
    configs = {"github": _GITHUB, "gitlab": _GITLAB}
    if provider not in configs:
        print(f"[ralph] I don't know what '{provider}' is! Try 'github' or 'gitlab'.", file=sys.stderr)
        sys.exit(1)
    cfg = configs[provider]
    try:
        result = subprocess.run([cfg.binary, "auth", "status"], capture_output=True)
    except FileNotFoundError:
        print(f"[ralph] I can't find the '{cfg.binary}' thingy! Get it from {cfg.cli_url}", file=sys.stderr)
        sys.exit(1)
    if result.returncode != 0:
        print(f"[ralph] The '{cfg.binary}' thingy doesn't know who you are! Do '{cfg.binary} auth login'.", file=sys.stderr)
        sys.exit(1)
```

---

### 2.4 `tasks.json` existence/emptiness check repeated in `ExecuteCommand`

**Location:** `ralph/commands.py:424–441`
**Issue:** `ExecuteCommand.execute()` manually opens `tasks.json` with `open()` + `json.load()` for its pre-check, while `run_execute_loop()` re-reads it later via `locks.read_json()`. The manual read bypasses the `locks` module and introduces an inconsistency.

**Suggested fix:** Use `locks.read_json(tasks_path)` for the pre-check to stay consistent with the rest of the codebase's JSON access pattern.

---

### 2.5 Global `--provider` persistence logic duplicated in `main()`

**Location:** `ralph/cli.py:407–424`
**Issue:** The provider validation and persist block appears twice:
```python
# Block 1 (no-subcommand path, line 416–418)
if args.global_provider is not None:
    validate_provider_cli(args.global_provider)
    set_provider(args.global_provider)

# Block 2 (with-subcommand path, line 422–424)
if args.global_provider is not None:
    validate_provider_cli(args.global_provider)
    set_provider(args.global_provider)
```

**Suggested fix:** Move both into a single call site after all the other globals are processed:
```python
# After processing all other global flags:
if args.global_provider is not None:
    validate_provider_cli(args.global_provider)
    set_provider(args.global_provider)

if args.command is None:
    if all_globals_none:
        print_banner_and_exit()
    return

args.func(args).execute()
```

---

### 2.6 `_reset_incomplete_tasks` uses raw `open()` instead of `locks` module

**Location:** `ralph/run.py:552–564`
**Issue:** `_reset_incomplete_tasks()` reads and writes `tasks.json` with plain `open()` and `json.dump()` rather than using `locks.write_json()`. While the method is only called before agents are spawned (so no real concurrency risk), it is inconsistent with the rest of the codebase and means the write is not atomic.

**Suggested fix:** Replace with `locks.locked_json_rw()` or at minimum `locks.write_json()` for the write step.

---

### 2.7 `".ralph"` root path string is scattered across multiple modules

**Location:** `ralph/commands.py` (~15 occurrences), `ralph/run.py` (~3 occurrences)
**Issue:** The string `".ralph"` is used as a raw literal in `os.path.join(".ralph", project_name)` throughout the codebase without a named constant.

**Suggested fix:** Define a module-level constant in `commands.py` or a shared `constants.py`:
```python
_RALPH_ROOT = ".ralph"
```
Then replace all `os.path.join(".ralph", ...)` with `os.path.join(_RALPH_ROOT, ...)`.

---

## 3. Inconsistencies Across the Codebase

### 3.1 `_resolve_single` is private; `resolve_verbose` and `resolve_asynchronous` are public

**Location:** `ralph/commands.py:92–104`
**Issue:** `resolve_verbose` and `resolve_asynchronous` are public functions (used in `cli.py` and tests), while `_resolve_single` has a leading underscore indicating it's private. All three perform the same role (resolve a CLI flag with settings fallback) and all three are only used within `commands.py`. The naming is inconsistent.

**Suggested fix:** Either make all three public (remove the underscore from `_resolve_single`), or make all three private. Since they're not imported outside the module, making them all private is more accurate.

---

### 3.2 `set_asynchronous` and `set_single` accept `str | bool`; other setters accept only `bool`

**Location:** `ralph/config.py:54–73` and `139–158`
**Issue:** `set_asynchronous` and `set_single` contain logic to parse string values `"true"` / `"false"` before the boolean conversion. However, their callers in `cli.py` already convert to bool before calling:
```python
set_asynchronous(args.global_asynchronous == "true")  # already a bool
set_single(args.global_single == "true")              # already a bool
```
The string-parsing branches in both functions are dead code. Meanwhile `set_verbose`, `set_rounds`, `set_limit`, `set_base`, and `set_provider` all have simple typed signatures.

**Suggested fix:** Remove the string-parsing branches from `set_asynchronous` and `set_single`, and update their type signatures to `value: bool` to match the other setters.

---

### 3.3 Obstacle entries in async mode are missing the `iteration` field

**Location:** `ralph/run.py:473–486` (`run_execute_loop_async`)
**Issue:** When an async agent fails, the obstacle appended to `obstacles.json` does not include an `"iteration"` field:
```python
obs_list.append({
    "id": next_id,
    "task_id": task_id,
    "message": f"Agent for task {task_id} failed ...",
    "resolved": False,
})
```
But `StatusCommand.execute()` (commands.py:885) displays `obs.get('iteration', '?')`, so async-mode obstacles always render as `[iter ?]`.

By contrast, sequential-mode agents are expected to write obstacles themselves (including the iteration number) per the execute prompt template.

**Suggested fix:** Add the current orchestrator iteration to the obstacle entry in async mode:
```python
obs_list.append({
    "id": next_id,
    "task_id": task_id,
    "iteration": iteration,   # add this
    "message": f"...",
    "resolved": False,
})
```

---

### 3.5 `run_execute_loop_async` hardcodes `iteration_num=1` for all tasks

**Location:** `ralph/run.py:532–539`
**Issue:** `parse_execute_async_md` is called with `iteration_num=1` hardcoded for every task dispatch, regardless of the actual polling iteration count. The async execute template likely uses this value to give the agent context ("you're on iteration X of Y"). All async agents always see `iteration_num=1`.

**Suggested fix:** Pass the actual `iteration` counter, or document that async agents are always given `1` (since each task is effectively its own first-and-only iteration).

---

## 4. Code Clarity & Naming Issues

### 4.1 `run_noninteractive` and `run_noninteractive_json` are module-level functions, not methods

**Location:** `ralph/run.py:19–35`
**Issue:** These are module-level functions but are only used inside `Runner` methods and `run_interview_loop`. They are not imported by any other module. The asymmetry between module-level functions (no `self`) and the `Runner` class makes the code slightly harder to navigate.

**Suggested fix:** Move them to be static/private methods of `Runner`, or keep them as module-level but document clearly that they are implementation details of this module.

---

### 4.2 `_collect_user_answers` is a thin wrapper that adds no value

**Location:** `ralph/run.py:93–101`
**Issue:** `_collect_user_answers` simply calls `_open_multiline_editor` with a hardcoded preamble. It is only called once (in the fallback path of `run_interview_loop`). The wrapper adds an extra indirection layer without any additional logic.

**Suggested fix:** Inline the call to `_open_multiline_editor` at its single call site, or keep the wrapper but rename it more descriptively (e.g. `_prompt_freeform_answers`).

---

### 4.3 `DESCRIBE_YOURSELF = _DESCRIBE_YOURSELF` redundant local alias

**Location:** `ralph/run.py:186`
**Issue:** Inside `_collect_guided_answers`, a local variable `DESCRIBE_YOURSELF` is assigned from the module-level `_DESCRIBE_YOURSELF`. This creates a redundant alias that serves no purpose — the module constant could be used directly throughout the function.

**Suggested fix:** Remove the local alias and use `_DESCRIBE_YOURSELF` directly.

---

### 4.4 `make_amend_prompt` factory could use `functools.partial`

**Location:** `ralph/commands.py:340–350`
**Issue:** `InterviewCommand.execute()` uses a nested factory function `make_amend_prompt(round_num)` that returns another function `build(qa_json)`. This is the correct pattern to avoid the Python closure-in-loop variable capture bug, but it could be simplified:
```python
# Current (verbose)
def make_amend_prompt(round_num: int) -> Callable[[str], str]:
    def build(qa_json: str) -> str:
        return parse_generate_tasks_md(args.project_name, round_num=round_num, ...)
    return build

# Simpler alternative using functools.partial
from functools import partial
amend_fns = [
    partial(parse_generate_tasks_md, args.project_name, round_num=i+1, total_rounds=rounds)
    for i in range(rounds)
]
```

---

### 4.5 `OneshotCommand.execute()` doesn't call `assert_project_exists` directly

**Location:** `ralph/commands.py:716–761`
**Issue:** `OneshotCommand` relies on `EnrichCommand(args).execute()` being called first, which itself calls `assert_project_exists()`. If the sub-command call order ever changes, `oneshot` could proceed further than intended before detecting a missing project. The implicit dependency is not obvious from reading `OneshotCommand.execute()` alone.

**Suggested fix:** Add `assert_project_exists(args.project_name)` at the top of `OneshotCommand.execute()` to make the precondition explicit.

---

## 5. Minor Bug Risks / Edge Cases

### 5.1 Bare `except Exception: pass` silences errors in `run_execute_single`

**Location:** `ralph/run.py:570–581` and `599–608`
**Issue:** Two catch-all exception handlers silently swallow errors:
```python
# Block 1 — pre-check to skip agent spawn
try:
    with open(self._tasks_path) as f:
        tasks_data = json.load(f)
    ...
except Exception:
    pass   # <-- silently ignores IOError, JSONDecodeError, etc.

# Block 2 — post-agent tasks.json read to determine exit reason
try:
    with open(self._tasks_path) as f:
        tasks_data = json.load(f)
    ...
except Exception:
    exit_reason = "Some tasks did not complete successfully"
```
Block 1 silently drops any file read error, potentially causing the agent to be spawned unnecessarily. Block 2 swallows JSON decode errors, which could indicate a corrupt file.

**Suggested fix:** Narrow the exception types (`OSError`, `json.JSONDecodeError`) and log a warning rather than silently passing.

---

### 5.2 `UndoCommand` falls through when `base_branch` is empty string

**Location:** `ralph/commands.py:563–565`
**Issue:**
```python
base_branch = get_base()
if not base_branch:
    set_base("main")
    base_branch = "main"
```
`get_base()` returns `str(_read_settings().get("base", "main"))` — the default is `"main"`, so the empty-string branch can never be reached through normal usage. The dead fallback adds confusion and suggests uncertainty about `get_base()`'s behaviour.

**Suggested fix:** Remove the dead branch since `get_base()` guarantees a non-empty string.

---

### 5.3 `ValidateCommand` opens `tasks.json` without the `locks` module

**Location:** `ralph/commands.py:471–473`
**Issue:**
```python
with open(tasks_path) as f:
    tasks_data = json.load(f)
```
This is a read-only check for incomplete tasks, so it's safe from a concurrency standpoint (no agent is running during validate). However, it is inconsistent with `locks.read_json()` used elsewhere for the same purpose.

**Suggested fix:** Use `locks.read_json(tasks_path)` for consistency.

---

### 5.4 `_do_create_pr` checks `git merge-base` only for GitHub

**Location:** `ralph/commands.py:965–975`
**Issue:** The `_ProviderConfig.check_merge_base` flag causes `git merge-base HEAD <base>` to run for GitHub but not GitLab. The comment-free `check_merge_base=False` on `_GITLAB` gives no indication of *why* GitLab skips this check. If the reason is just a historical omission, GitLab users could create MRs from branches with no shared history and get confusing errors from `glab mr create`.

**Suggested fix:** Set `check_merge_base=True` for GitLab if the check is equally valid.

---

## 6. Style & Standards

### 6.1 Long line in `main()` exceeds PEP 8 limit

**Location:** `ralph/cli.py:407`
**Issue:** This line is 172+ characters:
```python
if args.global_verbose is None and args.global_rounds is None and args.global_limit is None and args.global_base is None and args.global_provider is None and args.global_asynchronous is None and args.global_single is None:
```

**Suggested fix:**
```python
no_globals_set = all(
    getattr(args, f"global_{flag}") is None
    for flag in ("verbose", "rounds", "limit", "base", "provider", "asynchronous", "single")
)
if no_globals_set:
    ...
```

---

### 6.2 `config.py` setters each perform a separate read-write cycle

**Location:** `ralph/config.py` — all setters
**Issue:** Every setter calls `_read_settings()` then `_write_settings()` without any locking. While concurrent writes are unlikely (settings are only changed by user commands), the pattern is technically a TOCTOU race. More practically, it means each setter makes two file I/O calls; if multiple settings need updating, it's unnecessarily chatty.

**Suggested fix:** This is low priority since the race is theoretical. If needed, a `locked_json_rw` pattern identical to `locks.py` could be applied here. For now, a comment acknowledging the limitation would suffice.

---

### 6.3 `run_execute_loop_async` assigns `exit_reason` before the loop but it can be overwritten

**Location:** `ralph/run.py:435`
**Issue:**
```python
exit_reason = f"Reached maximum iteration limit ({max_iterations})."
```
This is set before the loop, then potentially overwritten inside it. While this matches the sequential loop pattern, it can be confusing because `exit_reason` still holds the iteration limit message if the loop exits via `return` (not `break`) — those paths call `self._run_summarise(...)` with their own string rather than using this variable. The variable's usage is therefore split: it's used by the iteration-limit path but never by the other exit paths.

**Suggested fix:** Pass the exit reason strings directly to `_run_summarise()` at each exit point, and remove the pre-loop variable. This matches what the sequential loop does at its own `break` points.

---

### 6.4 `InterviewCommand` pre-generates all question prompts before running any rounds

**Location:** `ralph/commands.py:335–350`
**Issue:** All `question_prompts` for all rounds are rendered upfront via a list comprehension before any round runs. Since later rounds might ask questions tailored to an already-updated spec, generating them all upfront could theoretically cause the later round's questions to be based on the *original* spec content rather than the spec as amended by the previous round's answers.

In practice the question prompt template embeds the `PROJECT_NAME` and round numbers (not the spec content itself — the agent reads spec.md at runtime), so this is not a bug today. But the pattern looks like premature optimisation and could become a subtle issue if the template ever embeds the spec content directly.

**Suggested fix:** Generate each round's question prompt inside the loop, just before it is needed, to make the intent clearer and eliminate latent risk:
```python
for i in range(rounds):
    q_prompt = parse_questions_md(args.project_name, round_num=i+1, total_rounds=rounds)
    amend_fn = partial(parse_generate_tasks_md, ...)
    ...
```

---

## Summary Table

| # | Category | Severity | File(s) |
|---|----------|----------|---------|
| 1.1 | README discrepancy | Low | README.md, cli.py |
| 1.2 | Version mismatch | Medium | pyproject.toml, cli.py |
| 1.3 | README discrepancy | Low | README.md |
| 1.4 | Missing auth check | Medium | commands.py |
| 2.1 | Code repetition | Medium | commands.py |
| 2.2 | Code repetition | Medium | commands.py |
| 2.3 | Code repetition | Medium | commands.py |
| 2.4 | Inconsistent JSON access | Low | commands.py |
| 2.5 | Logic duplication | Low | cli.py |
| 2.6 | Inconsistent file I/O | Low | run.py |
| 2.7 | Magic string repeated | Low | commands.py, run.py |
| 3.1 | Naming inconsistency | Low | commands.py |
| 3.2 | Dead code / type inconsistency | Low | config.py |
| 3.3 | Missing field in async obstacles | Medium | run.py |
| 3.4 | Async vs sequential asymmetry | Medium | run.py |
| 3.5 | Hardcoded iteration_num | Low | run.py |
| 4.1 | Clarity | Low | run.py |
| 4.2 | Clarity | Low | run.py |
| 4.3 | Redundant alias | Low | run.py |
| 4.4 | Clarity | Low | commands.py |
| 4.5 | Implicit precondition | Low | commands.py |
| 5.1 | Bug risk | Medium | run.py |
| 5.2 | Dead code | Low | commands.py |
| 5.3 | Inconsistency | Low | commands.py |
| 5.4 | Undocumented asymmetry | Low | commands.py |
| 6.1 | PEP 8 violation | Low | cli.py |
| 6.2 | Style note | Low | config.py |
| 6.3 | Clarity | Low | run.py |
| 6.4 | Latent risk | Low | commands.py |
