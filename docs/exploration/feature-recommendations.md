# Feature Recommendations

A review of the current Ralph Wiggum command set and suggested additions to extend the workflow.

## Current Commands (as of v2.6)

| Command | Purpose |
|---|---|
| `ralph init` | Initialise a project |
| `ralph interview` | Refine the spec through Q&A rounds |
| `ralph comment` | Push a quick spec amendment without Q&A |
| `ralph enrich` | Improve spec and regenerate tasks |
| `ralph execute` | Spawn agents to implement tasks |
| `ralph validate` | Assess implementation against spec |
| `ralph retry` | Fix "requires attention" validation results |
| `ralph undo` | Roll back a failed branch |
| `ralph pr` | Push branch and open a pull/merge request |
| `ralph oneshot` | Run the full pipeline in one command |

---

## Recommended Additions

### High Value, Low Complexity

#### `ralph status <project-name>`
The most glaring usability gap. Users currently have to manually inspect `tasks.json` and `state.json` to understand where a project stands. A single command should surface:
- Current branch and base branch
- Task counts (complete / pending / failed / total)
- Last obstacle or error (if any)
- Validation rating (if `validation.md` exists)

This would be the most frequently used command after `execute` and is almost essential for managing long-running or async executions.

#### `ralph list`
Lists all Ralph projects in the current repo (scanning `.ralph/` subdirectories) with enriched info — project name, branch, task progress, and validation rating. Makes it easy to manage multiple concurrent projects without manually inspecting the filesystem.

#### `ralph tasks <project-name>`
Pretty-prints the task plan from `tasks.json` in a readable table or tree format, including task IDs, descriptions, dependencies, status, and attempt counts. Currently reviewing the task plan requires manually opening and reading a JSON file.

---

### Workflow Additions

#### `ralph refine <project-name> "<feedback>"`
A surgical post-execution alternative to `retry`. Rather than letting the agent decide what to fix from `validation.md`, the user passes explicit feedback directly. Analogous to how `ralph comment` relates to `ralph interview` — same outcome, more direct control. Useful when you know exactly what needs fixing but don't want to roll back entirely with `undo`.

#### `ralph scope <project-name>`
A dry-run estimation step that runs a lightweight agent to read the spec and report:
- Expected task count and complexity
- Files likely to be touched
- Estimated number of execute iterations
- Any ambiguities that should be resolved before execution

Run before `ralph execute` on complex projects to avoid surprises mid-run.

#### `ralph checkpoint <project-name> [--name <label>]`
Saves a named snapshot of `tasks.json` and `state.json` mid-execution. Currently `undo` rolls all the way back to the initial state. A checkpoint system would allow rolling back to a known-good mid-execution point, which is valuable for long runs with many tasks.

---

### Quality-of-Life

#### `--dry-run` flag on `execute`
Prints what tasks *would* be dispatched (and in what order / parallelism for async mode) without actually running any agents. Useful for reviewing the DAG before committing to a full run, especially with `--asynchronous true`.

#### `ralph clean <project-name>`
Fully removes the `.ralph/<project-name>/` artifact directory. `ralph undo` resets code changes and task state, but there is no first-class way to tear down a project's metadata short of `rm -rf`. A `clean` command should prompt for confirmation and optionally also delete the project branch.

#### `ralph watch <project-name>`
Live tail of execution progress during an async run — polling `tasks.json` and printing status updates as tasks complete or fail. Since async mode dispatches multiple agents concurrently, visibility into what is happening is currently limited to reading log files manually.

---

## Priority Order

| Priority | Command / Feature | Rationale |
|---|---|---|
| 1 | `ralph status` | Used constantly; essential for usability |
| 2 | `ralph refine` | Fills the gap between `retry` (automatic) and `undo` (nuclear) |
| 3 | `ralph list` | Low effort, high convenience for multi-project use |
| 4 | `ralph tasks` | Eliminates the need to read raw JSON |
| 5 | `--dry-run` on `execute` | Safety net before long async runs |
| 6 | `ralph scope` | Useful pre-flight check for complex specs |
| 7 | `ralph watch` | Improves async execution observability |
| 8 | `ralph checkpoint` | Advanced; only needed for very long runs |
| 9 | `ralph clean` | Convenience; workaround is just `rm -rf` |
