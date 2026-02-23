```
██████╗  █████╗ ██╗     ██████╗ ██╗  ██╗
██╔══██╗██╔══██╗██║     ██╔══██╗██║  ██║
██████╔╝███████║██║     ██████╔╝███████║
██╔══██╗██╔══██║██║     ██╔═══╝ ██╔══██║
██║  ██║██║  ██║███████╗██║     ██║  ██║
╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝  ╚═╝

    ── R A L P H   W I G G U M ──
"Me fail English? That's unpossible"
```

# Ralph Wiggum

A CLI-driven agentic coding framework that manages context and prompt quality to get better results from AI coding agents.

## What is Ralphing?

Agentic coding tools are powerful, but two problems routinely limit their effectiveness:

1. **Poor prompts.** Most users miss important details when specifying a task. Vague or incomplete requirements lead to agents that implement the wrong thing. Ralph addresses this by running an *interview* phase: before any code is written, an agent reads your spec and asks targeted clarifying questions. You answer them, and the spec is updated to be precise enough to drive accurate implementation.

2. **Context window degradation.** Agentic models have a limited context window. Long-running sessions trigger automatic context compression, and since the model has no principled way to decide what matters, performance degrades significantly. Ralph avoids this entirely: instead of one long-running agent, it spawns a fresh agent for each task with only the essential context — the project spec, the task list, and the history of completed work. Each iteration starts clean.

## Installation

Clone this repository and install the Ralph CLI using pip:

```bash
pip install -e .
```

If the `pip install` fails, a possible solution would be to use `pipx install` instead.

[pipx](https://pipx.pypa.io/) installs the tool into an isolated virtual environment while making the `ralph` command available globally, so it does not interfere with your system Python or project dependencies.

## Caveats

- Ralph currently invokes Claude Code with `--dangerously-skip-permissions`, which means the execute agents run without confirmation prompts. All file writes, shell commands, and git operations happen automatically. Run it on code you have committed or backed up.
- The `ralph pr` command requires the [GitHub CLI (`gh`)](https://cli.github.com/) to be installed and authenticated.
- GitLab support requires the [GitLab CLI (`glab`)](https://gitlab.com/gitlab-org/cli) to be installed and authenticated (`glab auth login`) before use. Ralph validates this when you set `--provider gitlab`.
- When using `--asynchronous true`, concurrent Claude agents have no hard file locking on source-code files. It is theoretically possible for two agents to race and corrupt a source file if they both attempt to edit it at the same time. File locking is only guaranteed for `.json` artefact files. The probability is low — task generation mitigates this by encoding dependencies — but users should be aware of the risk.

## Commands

### `ralph init <project-name>`

Initialises a new project. Creates `.ralph/<project-name>/` containing:
- `spec.md` — a template spec file for you to fill in
- `tasks.json`, `state.json`, `obstacles.json` — tracking files used by the agents

Also creates `.ralph/settings.json` with default values for global flags if it does not already exist.

---

### `ralph interview <project-name> [--rounds N] [--verbose BOOL]`

Runs one or more interview rounds to refine the spec. Each round has two phases:
1. An agent reads `spec.md` and outputs 3–5 clarifying questions.
2. You type your answers; a second agent incorporates them into `spec.md` and writes/refreshes `tasks.json`.

`--rounds N` (alias `-r`) controls how many rounds to run. Defaults to the persisted `rounds` setting (default: 1).

---

### `ralph comment <project-name> "<comment>" [--verbose BOOL]`

A lightweight alternative to `ralph interview` for quick spec amendments. Passes your comment directly to an agent, which updates `spec.md` and refreshes `tasks.json` without an interactive Q&A round.

---

### `ralph enrich <project-name> [--verbose BOOL]`

Improves the `spec.md` file and regenerates `tasks.json` from it. A Claude agent reads the current spec and all relevant source files, then enhances `spec.md` in-place — filling in missing context, clarifying ambiguities, and adding technical details — before regenerating `tasks.json`.

- Preconditions: project must exist; `spec.md` must exist.

---

### `ralph execute <project-name> [--limit N] [--base BRANCH] [--verbose BOOL] [--resume] [--asynchronous BOOL]`

Implements the project by spawning execute agents iteratively. Each agent picks up the next pending task from `tasks.json`, implements it, commits the changes, and updates the task status.

- Creates a new branch named `<project-name>` branched from `<base>` (default: `main`). Aborts if the branch already exists.
- Stops when all tasks are complete, a task exceeds its `max_attempts`, the iteration limit is reached, or the Claude Code usage limit is hit.
- At the end, spawns a summary agent that writes `summary.md` and `pr-description.md` to the artifact directory.
- `--limit N` (alias `-l`) sets the maximum number of agent iterations (default: 20).
- `--base BRANCH` (alias `-b`) sets the branch to branch from (default: `main`).
- `--resume` (alias `-r`) resumes execution on an existing project branch instead of creating a new one.
- `--asynchronous BOOL` (alias `-a`) enables parallel agent execution. When `true`, tasks with no unsatisfied dependencies are dispatched concurrently using the DAG in `tasks.json`. Overrides the global setting for this invocation (default: `false`).

---

### `ralph oneshot <project-name> [--limit N] [--base BRANCH] [--verbose BOOL]`

Runs the full pipeline in one command: enriches the spec, executes agents, validates the result, and creates a PR. Requires a clean working tree. Useful for straightforward tasks where interactive interview rounds are not needed.

- A `"failed"` validation rating aborts PR creation.
- A `"requires attention"` validation rating prints a warning but continues to create the PR.

---

### `ralph pr <project-name> [--provider github|gitlab]`

Pushes the project branch to `origin` and opens a pull request (or merge request for GitLab) using the `pr-description.md` generated by the execute step.

- Requires the `gh` CLI for GitHub (default) or the `glab` CLI for GitLab.
- `--provider github|gitlab` (alias `-p`) selects the VCS platform for this invocation. Overrides the global setting.

---

### `ralph validate <project-name> [--verbose BOOL]`

Spawns a Claude agent to assess whether the code changes produced by `ralph execute` correctly address the requirements in `spec.md`. The agent reads spec/task/state files, runs available tests, and produces a `validation.md` report in `.ralph/<project-name>/`.

- Preconditions: project must exist; `pr-description.md` must be present (indicating `ralph execute` has completed); all tasks in `tasks.json` must have `status: "completed"`; the project branch must exist.
- Output: `.ralph/<project-name>/validation.md` — a report whose first line is one of: `# Rating: passed`, `# Rating: failed`, or `# Rating: requires attention`.
- If `validation.md` already exists, you are prompted (`y/n`) before it is overwritten.
- No code changes are made by this command.

---

### `ralph undo <project-name> [--force]`

Rolls back code changes from a previous `ralph execute` run. All logic runs in the Python layer — no Claude agent is spawned.

- Preconditions: project must exist; `validation.md` must exist; validation rating must be `"failed"` (unless `--force` is provided).
- `--force` (alias `-f`) bypasses the rating check, allowing `undo` to run even when the rating is not `"failed"`.
- Steps performed:
  1. Checks out the base branch (from `settings.json`; defaults to `"main"`).
  2. Force-deletes the project branch (after `y/n` confirmation).
  3. Resets `state.json`, `obstacles.json`, and all tasks in `tasks.json` back to their initial state.

---

### `ralph retry <project-name> [--force] [--verbose BOOL]`

Spawns a single Claude agent to fix small insufficiencies identified by `ralph validate`. After `ralph retry` finishes, run `ralph validate` again to re-assess.

- Preconditions: project must exist; `validation.md` must exist; validation rating must be `"requires attention"` (unless `--force` is provided); working tree must be clean; project branch must exist.
- `--force` (alias `-f`) bypasses the rating check, allowing `retry` to run even when the rating is not `"requires attention"`.
- The agent may only modify source code and tests — artifact files (`summary.md`, `pr-description.md`, `validation.md`, `tasks.json`) must not be changed.
- The agent commits its changes upon completion.

---

### Global flags

When used at the top level (before or without a subcommand), these flags persist their values to `.ralph/settings.json`:

| Flag | Alias | Default | Description |
|------|-------|---------|-------------|
| `--verbose true\|false` | `-v` | `false` | Print agent stdout during runs |
| `--rounds N` | `-r` | `1` | Default number of interview rounds |
| `--limit N` | `-l` | `20` | Default max execute iterations |
| `--base BRANCH` | `-b` | `main` | Default base branch for execute |
| `--provider github\|gitlab` | `-p` | `github` | VCS platform for PR/MR creation. Validates that the provider's CLI tool is installed and authenticated before saving. |
| `--asynchronous true\|false` | `-a` | `false` | Enable parallel agent execution in `ralph execute`. |

Per-command flags (e.g. `ralph interview my-project --rounds 3`) override the persisted setting for that invocation only.

## Workflow

### 1. Initialise the project

```bash
ralph init my-feature
```

This creates `.ralph/my-feature/spec.md`. Open it and fill in the Overview, Goals, Requirements, and any technical constraints. The more detail you provide here, the better the agent output.

### 2. Run the interview (optional but recommended)

```bash
ralph interview my-feature --rounds 2
```

For each round, the agent asks clarifying questions. Answer them in the terminal; the spec and task list are updated automatically. Run multiple rounds for complex projects.

Alternatively, use `ralph comment` to push a specific amendment without the Q&A loop:

```bash
ralph comment my-feature "Add rate limiting to all API endpoints"
```

### 3. Enrich the spec (optional)

```bash
ralph enrich my-feature
```

A Claude agent reads the current spec and relevant source files, enhances `spec.md` in-place with missing context and technical details, then regenerates `tasks.json`. Useful before executing on complex projects where the spec may be underspecified.

### 4. Execute

```bash
ralph execute my-feature
```

Ralph creates a branch `my-feature` from `main`, then spawns agents one at a time. Each agent picks up one task, implements it, commits the changes, and marks the task complete. Progress is tracked in `tasks.json` and `state.json`.

When done (or on early exit), a summary is written to `.ralph/my-feature/summary.md`.

To run tasks in parallel (for independent tasks with no shared files):

```bash
ralph execute my-feature --asynchronous true
```

### 5. Validate

```bash
ralph validate my-feature
```

Spawns a Claude agent that checks whether the implementation satisfies `spec.md`. The result is written to `.ralph/my-feature/validation.md` with a rating of `passed`, `requires attention`, or `failed`.

### 6. Act on the validation result

**If the rating is `passed`** — proceed to create the PR.

**If the rating is `requires attention`** — run `ralph retry` to spawn a single agent that fixes the identified issues, then validate again:

```bash
ralph retry my-feature
ralph validate my-feature
```

**If the rating is `failed`** — roll back the branch entirely and start over:

```bash
ralph undo my-feature
```

This deletes the project branch and resets all task state, ready for a fresh `ralph execute`.

### 7. Create the PR

```bash
ralph pr my-feature
```

Pushes the branch and opens a pull request using the auto-generated `pr-description.md`. For GitLab:

```bash
ralph pr my-feature --provider gitlab
```

---

### Resuming a partial execution

If `ralph execute` was interrupted, resume from where it left off:

```bash
ralph execute my-feature --resume
```

### Fully automated (oneshot)

For simpler tasks where you want to skip the interview:

```bash
ralph oneshot my-feature
```

This runs enrich → execute → validate → PR in sequence. A `"failed"` validation rating aborts PR creation; a `"requires attention"` rating prints a warning but continues.

---

## Changelog

### Version 1

Initial release. Introduced the core agentic development workflow: `ralph init` to set up a project, `ralph interview` and `ralph comment` to refine the spec through clarifying questions, `ralph execute` to spawn fresh Claude Code agents per task (avoiding context window degradation), `ralph pr` to push the project branch and create a GitHub pull request, and `ralph oneshot` to run the full pipeline in a single command.

### Version 2

Added GitLab support and a `--provider / -p` flag for selecting the VCS platform. Introduced parallel task execution via `--asynchronous / -a`, dispatching independent tasks concurrently using a DAG-based orchestrator with `filelock`-protected JSON writes. Added four new commands: `ralph enrich` (enriches `spec.md` and regenerates `tasks.json`), `ralph validate` (produces a rated `validation.md` report via a Claude agent), `ralph undo` (rolls back a failed branch), and `ralph retry` (fixes a "requires attention" result with a single agent). `ralph oneshot` was updated to include enrich and validate steps. Synchronous task delegation moved to the Python/DAG layer; context window usage is logged after each agent run.
