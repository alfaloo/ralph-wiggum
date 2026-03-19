# Ralph Wiggum — VS Code Extension

The Ralph Wiggum VS Code extension wraps the `ralph` CLI as a GUI application inside the editor. Every ralph command is a button click, flags are pre-filled from your project settings, and output streams directly into a panel. Interview Q&A, task progress, and project status are all visible without leaving VS Code.

## What It Does

- **Sidebar**: Lists all Ralph projects in `.ralph/` with live status badges (`pending`, `in_progress`, `completed`, `failed`). Create new projects with **+ New Project**.
- **Project panels**: Each project opens in its own VS Code tab with a command bar, flag configuration dialog, live output area, and task progress list.
- **Interactive interview**: When `ralph interview` is running, a Q&A form appears with pre-generated answer options and a free-text option. Submit all answers at once.
- **Live progress**: The task progress bar and sidebar badge update in real time as `ralph execute` runs.
- **Auto-enabling commands**: Commands that require prerequisite files (e.g. `pr`, `validate`) are disabled until those files exist.
- **Y/N dialogs**: Confirmation prompts (e.g. branch deletion in `ralph undo`) are shown as native VS Code dialogs.

## Prerequisites

The `ralph` CLI must be installed and available on your `PATH`. Verify with:

```bash
ralph --help
```

If `ralph` is not found, install it according to the [ralph documentation](https://github.com/alfaloo/ralph-wiggum) and ensure the install location is on your `PATH`.

## Sidebar

Click the Ralph Wiggum icon in the Activity Bar to open the sidebar. It lists all Ralph projects found in `.ralph/` — any subdirectory that starts with a letter and contains a `spec.md` file.

Each project shows a status badge derived from `tasks.json`:

| Badge | Meaning |
|-------|---------|
| `pending` | No tasks, or tasks not yet started |
| `in_progress` | At least one task is currently in progress |
| `completed` | All tasks are completed |
| `failed` | At least one task is blocked and none are in progress |

The sidebar refreshes automatically when task files change — no manual refresh needed.

**+ New Project**: Prompts for a project name, runs `ralph init <name>`, and opens the generated `spec.md` for editing.

Clicking a project name opens or focuses its panel.

## Project Panels

Each project opens in a dedicated VS Code tab. The panel has two columns.

### Left column — Task Progress

- A list of all tasks with status icons: `✓` completed, `◷` in progress, `✗` blocked, `○` pending.
- A green progress bar showing overall completion percentage.
- A counter: `N completed / M total`.
- Clicking a task name shows its full details (ID, status, attempts, description) in the output area.

### Right column — Output and Controls

- **Command bar**: Buttons for every ralph command. Commands are automatically disabled when their prerequisites are not yet met.
- **Output area**: Streams live stdout/stderr from the running process. Markdown output is rendered. PR URLs are clickable. **Clear** button resets the output.
- **Stop button**: Appears while a command is running. Terminates the process immediately.

## Running Commands

1. Open a project panel by clicking the project in the sidebar.
2. Click a command button in the command bar.
   - **`status`** runs immediately — no dialog.
   - All other commands open a flag configuration dialog.
3. Review or adjust flags in the dialog. Defaults are pre-filled from `.ralph/settings.json`.
4. Click **Run**. Output streams into the output area in real time.
5. To stop a running command, click the **Stop** button.

Commands that require prerequisite files are automatically disabled:

| Command | Requires |
|---------|---------|
| `enrich` | `spec.md` |
| `execute` | `tasks.json` with at least one task |
| `validate` | `pr-description.md` (produced by `ralph execute`) |
| `pr` | `pr-description.md` (produced by `ralph execute`) |
| `undo`, `retry` | `validation.md` (produced by `ralph validate`) |

## Flag Reference

| Command | Flag | Type | Default | Notes |
|---------|------|------|---------|-------|
| `interview` | `--rounds` | integer | 1 | Number of Q&A rounds |
| `interview` | `--verbose` | boolean | false | |
| `comment` | comment text | text | — | Required |
| `comment` | `--verbose` | boolean | false | |
| `enrich` | `--verbose` | boolean | false | |
| `execute` | `--limit` | integer | 20 | Max agent iterations |
| `execute` | `--base` | text | main | Branch to base from |
| `execute` | `--verbose` | boolean | false | |
| `execute` | `--resume` | boolean | false | Resume interrupted run |
| `execute` | `--asynchronous` | boolean | false | Parallel tasks; mutually exclusive with `--single` |
| `execute` | `--single` | boolean | false | Single agent for all tasks; mutually exclusive with `--asynchronous` |
| `oneshot` | `--limit` | integer | 20 | |
| `oneshot` | `--base` | text | main | |
| `oneshot` | `--verbose` | boolean | false | |
| `oneshot` | `--asynchronous` | boolean | false | Mutually exclusive with `--single` |
| `oneshot` | `--single` | boolean | false | Mutually exclusive with `--asynchronous` |
| `oneshot` | `--provider` | github\|gitlab | github | |
| `pr` | `--provider` | github\|gitlab | github | |
| `validate` | `--verbose` | boolean | false | |
| `retry` | `--force` | boolean | false | Bypass rating check |
| `retry` | `--verbose` | boolean | false | |
| `undo` | `--force` | boolean | false | Bypass rating check |

## Interview

When `ralph interview` is running, the output area is replaced by an interactive Q&A form:

1. Each question is shown with a list of pre-generated answer options (radio buttons).
2. Select the option that best fits, or choose **Describe yourself...** to type a custom answer in a text area.
3. All questions are shown at once in a scrollable form.
4. Click **Submit All** to send your answers back to the CLI.

The CLI incorporates the answers into `spec.md` and continues to the next round (if `--rounds` is greater than 1).

## Task Progress

The left column of the project panel shows the current state of all tasks:

- Status icons: `✓` completed, `◷` in progress, `✗` blocked, `○` pending.
- A green progress bar showing overall completion percentage.
- A counter showing `N completed / M total`.
- Clicking a task name shows its full details (ID, status, attempts, description) in the output area.

## Real-Time Updates

The extension watches files in `.ralph/<project>/` for changes:

- `tasks.json` changes → the task progress bar and sidebar badge update immediately.
- `validation.md`, `spec.md`, `pr-description.md`, `summary.md` changes → relevant command buttons enable or disable automatically.

## Keyboard Shortcuts and Command Palette

There are no dedicated keyboard shortcuts for the extension. All ralph commands are accessible via the Command Palette (`Cmd+Shift+P` on macOS, `Ctrl+Shift+P` on Windows/Linux).

| Palette command | Action |
|----------------|--------|
| `Ralph: New Project` | Prompts for a project name, runs `ralph init`, and opens the generated `spec.md` |
| `Ralph: Open Project` | Shows a picker of existing Ralph projects and opens the selected panel |

## Tips

- `status` is the only command that runs immediately without opening a flag dialog.
- `--asynchronous` and `--single` are mutually exclusive. Enabling one in the dialog disables the other automatically.
- Clicking a task in the task list shows its full details in the output area — useful for debugging a blocked or failed task.
- The output area auto-scrolls to the bottom while a command is running. Use the **Clear** button to reset it between runs.
- PR URLs that appear in the output are rendered as clickable links and open in your browser.
- Panels persist across VS Code restarts. If you had a project open when you last closed VS Code, it reopens automatically.
- If `ralph` is not found when you run a command, check that the CLI is installed and the install location is on your `PATH`.
