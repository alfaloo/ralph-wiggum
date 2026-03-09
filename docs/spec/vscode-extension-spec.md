# Ralph Wiggum — VSCode Extension Spec

## Overview

A Visual Studio Code extension that wraps the `ralph` CLI as a GUI application. The extension provides a tab-per-project interface where each tab is a dedicated workspace for a single Ralph project. Users interact with ralph commands through a graphical panel rather than a terminal; all commands are dispatched to the `ralph` CLI as subprocesses and responses are streamed back into the GUI window in real time.

The extension is intentionally a thin wrapper — it does not re-implement any Ralph logic. All state management, file creation, and agent orchestration continues to happen through the existing CLI and its `.ralph/` directory structure.

---

## Goals

1. Remove the need to remember and type `ralph <command> <project-name> [flags]` for every action.
2. Provide a tab-based UI so users can manage multiple projects simultaneously without having to repeatedly specify a project name.
3. Stream rich CLI output (stdout/stderr) into a readable, scrollable GUI panel.
4. Handle the interactive interview flow (where the CLI reads from stdin) natively within the GUI.
5. Provide persistent visual feedback on task progress by reading `.ralph/<project-name>/tasks.json`.

---

## Tech Stack

### Extension Host (TypeScript)

| Concern | Technology |
|---|---|
| Language | TypeScript |
| Runtime | Node.js (Extension Host) |
| Build tool | `esbuild` (fast, simple, VS Code–recommended) |
| VS Code API | `vscode` npm package |
| Process spawning | Node.js `child_process.spawn` (streaming I/O) |
| File watching | `vscode.workspace.createFileSystemWatcher` |
| State persistence | `vscode.ExtensionContext.workspaceState` (project list, open tabs) |

### Webview UI (per project panel)

| Concern | Technology |
|---|---|
| Framework | React (via CDN or bundled with esbuild) |
| Styling | Plain CSS / CSS variables (VSCode theme tokens for native look) |
| Communication | VS Code Webview `postMessage` / `onDidReceiveMessage` |
| Markdown rendering | `marked.js` (lightweight, no server needed) |

**Why React for the webview?** The panel UI has multiple stateful regions (output log, active command, stdin input area, task progress sidebar) that update independently. React's component model handles this cleanly. A CDN-loaded React (in development) or an esbuild-bundled React (in production) avoids heavy tooling setup.

**Why esbuild?** It is the current de-facto standard for VS Code extension bundling — significantly faster than webpack, zero configuration for TypeScript, and produces a single output file that VS Code's extension host can load directly.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  VS Code Window                                                  │
│                                                                  │
│  ┌──────────────┐   ┌────────────────────────────────────────┐  │
│  │  Sidebar     │   │  Webview Panel (one per project tab)   │  │
│  │  (TreeView)  │   │                                        │  │
│  │              │   │  ┌──────────────────────────────────┐  │  │
│  │  ● project-a │   │  │  Command Bar (buttons + options)  │  │  │
│  │  ● project-b │   │  └──────────────────────────────────┘  │  │
│  │  ● project-c │   │                                        │  │
│  │              │   │  ┌──────────────────────────────────┐  │  │
│  │  [+ New]     │   │  │  Output Area (streamed stdout)   │  │  │
│  └──────────────┘   │  │  (scrollable, markdown-rendered) │  │  │
│                     │  └──────────────────────────────────┘  │  │
│                     │                                        │  │
│                     │  ┌──────────────────────────────────┐  │  │
│                     │  │  Task Progress Bar               │  │  │
│                     │  └──────────────────────────────────┘  │  │
│                     │                                        │  │
│                     │  ┌──────────────────────────────────┐  │  │
│                     │  │  Stdin Input (interview mode)    │  │  │
│                     │  └──────────────────────────────────┘  │  │
│                     └────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘

Extension Host (Node.js)
├── extension.ts           — activation, command registration
├── RalphSidebarProvider   — TreeDataProvider for project list
├── RalphPanelManager      — creates/restores WebviewPanels per project
├── RalphProcessManager    — spawns ralph CLI, pipes I/O
└── RalphFileWatcher       — watches tasks.json for live progress updates
```

### Message Flow

```
Webview UI  ──postMessage(command, flags)──►  Extension Host
            ◄─postMessage(stdout chunk)─────  Extension Host ◄── ralph CLI (spawn)
            ◄─postMessage(stdin_ready)──────  Extension Host ◄── ralph CLI (waiting on stdin)
Webview UI  ──postMessage(stdin_input)───►  Extension Host ──► ralph CLI (write to stdin)
            ◄─postMessage(process_done)─────  Extension Host ◄── ralph CLI (exit)
            ◄─postMessage(tasks_update)─────  Extension Host ◄── FileSystemWatcher
```

---

## Project Tab System

### Creating a New Project Tab

1. User clicks **"+ New Project"** in the sidebar (or runs a VS Code command `ralph.newProject`).
2. A VS Code `InputBox` prompts for the project name.
3. The extension validates the name (non-empty, no spaces or special characters, not already initialised).
4. The extension spawns `ralph init <project-name>` and streams output to a temporary panel.
5. On success, the new project is added to the sidebar list and a dedicated WebviewPanel is opened for it.
6. The project list is persisted to `workspaceState` so the sidebar survives VS Code restarts.

### Switching Between Projects

Each project has its own `WebviewPanel`. VS Code natively supports multiple panels; each panel is identified by the project name and can be shown/hidden/focused. Clicking a project in the sidebar brings its panel to the foreground.

Panels preserve their output history within a session. On restart, panels are restored from `workspaceState` with an empty output area (the `.ralph/` files on disk are still intact).

### Removing a Project Tab

A right-click context menu on the sidebar entry offers "Close Tab". This removes the project from the in-memory list and closes the WebviewPanel. It does **not** delete the `.ralph/<project-name>/` directory or any git branches — the user must do that manually. A warning is shown before closing.

---

## Webview Panel Layout

```
┌──────────────────────────────────────────────────────────┐
│  [interview] [comment] [enrich] [execute] [validate]     │  ← Command bar
│  [status]   [retry]   [undo]   [oneshot]  [pr]           │
│  ──────────────────────────────────────────────────────  │
│  Flag panel (appears when a command is selected):        │
│  Execute: [--limit  20 ▲▼] [--base  main] [--resume ☐]  │
│           [--async  ☐]                                   │
│  ──────────────────────────────────────────────────────  │
│  Task progress:  ████████░░░░  5/12 tasks complete       │  ← Progress
│  ──────────────────────────────────────────────────────  │
│                                                          │
│  [ralph] Execute agent has started working on task T1... │  ← Output area
│  [ralph] Agent used 45,320/200,000 tokens (22.7%)        │
│                                                          │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│
│  Interview — type your answers below, then press Submit  │  ← Stdin area
│  ┌────────────────────────────────────────────────────┐  │  (only visible
│  │                                                    │  │   during interview)
│  └────────────────────────────────────────────────────┘  │
│  [Submit Answers]                                        │
└──────────────────────────────────────────────────────────┘
```

### Command Bar

A row of buttons, one per ralph subcommand. Clicking a button:
1. Expands the **Flag Panel** below the command bar with the relevant flags for that command (pre-filled with values from `.ralph/settings.json`).
2. A **Run** button sends the command to the Extension Host.

Commands that require no flags (e.g. `status`, `pr`) run immediately on click without expanding the flag panel.

### Flag Panel

Rendered dynamically based on the selected command. Input types:
- **Number spinner**: `--limit`, `--rounds`
- **Text input**: `--base`, `--provider`
- **Checkbox**: `--resume`, `--asynchronous`, `--force`, `--verbose`
- **Comment textarea**: for `ralph comment <project-name> "<comment>"`

The flag panel reads defaults from `.ralph/settings.json` on panel load and after any command completes.

### Output Area

- Streams stdout and stderr line-by-line as the subprocess runs.
- Prefixes: `[stdout]` lines rendered in normal text; `[stderr]` lines rendered in a muted warning colour.
- Supports basic ANSI escape code stripping (so colour codes from the CLI don't appear as garbage).
- Markdown blocks (e.g. the questions generated during interview, or the validation report) are rendered using `marked.js`.
- A **Clear** button clears the output area.
- Output is not persisted across panel closes/restarts.

### Task Progress Bar

- Reads `.ralph/<project-name>/tasks.json` on panel load and on every file-change event from the FileSystemWatcher.
- Displays a horizontal progress bar: `completed / total` tasks.
- Below the bar, lists each task with its status: `pending`, `in_progress`, `completed`, or `blocked`.
- Updates in real time as `ralph execute` runs (the watcher fires as the CLI mutates `tasks.json`).

### Stdin Input Area (Interview Mode)

The `ralph interview` command generates questions and then blocks waiting for the user to type answers on stdin. The extension handles this as follows:

1. The Extension Host spawns `ralph interview <project-name>` via `child_process.spawn` (not `exec`), keeping stdin open.
2. stdout is streamed to the Output Area. The extension detects the interview prompt string (`"Type your answers below"`) to know stdin is now expected.
3. The Stdin Input Area becomes visible: a multi-line textarea and a **Submit** button.
4. On Submit, the Extension Host writes the text + an EOF (`\n\x04`) to the process's stdin stream.
5. The process continues (Phase 2 amend), and stdout continues to stream into the Output Area.
6. On process exit, the Stdin Input Area is hidden again.

This approach keeps the CLI unmodified — the extension simply acts as a stdin/stdout broker.

---

## Commands and Their GUI Representations

### `ralph init` — New Project Tab

- Triggered only by "New Project" in the sidebar, not a button in the command bar.
- Handled before the project panel is open.

### `ralph interview <project-name> [--rounds N] [--verbose]`

- Flag panel: `--rounds` (number spinner, default from settings), `--verbose` (checkbox).
- Spawns with stdin kept open. Activates Stdin Input Area when prompted.
- Supports multi-round mode: the interview loop runs inside the CLI; the extension just brokers I/O.

### `ralph comment <project-name> "<comment>" [--verbose]`

- Flag panel: large textarea for the comment text, `--verbose` checkbox.
- The comment text is passed as a positional argument: `ralph comment <project-name> "<text>"`.

### `ralph enrich <project-name> [--verbose]`

- Flag panel: `--verbose` checkbox only.
- Runs non-interactively; output streamed to Output Area.

### `ralph execute <project-name> [--limit N] [--base BRANCH] [--verbose] [--resume] [--asynchronous]`

- Flag panel: `--limit` (number spinner), `--base` (text input), `--verbose` (checkbox), `--resume` (checkbox), `--asynchronous` (checkbox).
- Long-running command. A **Stop** button becomes available while it runs (sends SIGTERM to the subprocess).
- Task Progress Bar updates in real time via FileSystemWatcher.

### `ralph status <project-name>`

- No flags. Renders the status output in the Output Area.
- Also available as a quick inline status block at the top of the panel (read directly from JSON files, no CLI call needed).

### `ralph validate <project-name> [--verbose]`

- Flag panel: `--verbose` checkbox.
- After completion, if `validation.md` already exists, the CLI will ask `y/n`. The extension intercepts this prompt from stdout and displays a VS Code confirmation dialog, then writes the response to stdin.

### `ralph undo <project-name> [--force]`

- Flag panel: `--force` checkbox.
- The CLI asks for `y/n` confirmation before deleting the branch. The extension intercepts this and presents a VS Code confirmation dialog (with the destructive action highlighted in red), writing the response to stdin.
- Shown with a warning icon in the command bar to signal destructiveness.

### `ralph retry <project-name> [--force] [--verbose]`

- Flag panel: `--force` checkbox, `--verbose` checkbox.

### `ralph oneshot <project-name> [--limit N] [--base BRANCH] [--verbose] [--resume] [--asynchronous] [--provider]`

- Flag panel: same as `execute` plus `--provider` dropdown.
- Long-running; task progress shown live.

### `ralph pr <project-name> [--provider github|gitlab]`

- Flag panel: `--provider` dropdown (github / gitlab).
- On success, the PR URL returned by the CLI is rendered as a clickable hyperlink in the Output Area.

---

## Interactive Prompt Interception

Several Ralph commands emit `y/n` prompts to stdout and then block on stdin. The extension must intercept these to avoid the process hanging silently. The approach:

1. A regex pattern list is maintained in the Extension Host for known prompts:
   - `"already exists. Overwrite? (y/n):"` — validation.md overwrite (validate command)
   - `"Delete branch '...'. This cannot be undone. (y/n):"` — undo command
   - `"Update base branch to '...'? (y/n):"` — init command
2. When a stdout line matches a pattern, the Extension Host sends a `show_confirm` message to the Webview.
3. The Webview presents a VS Code-style dialog (or an inline confirm button in the Output Area).
4. The user's response is posted back to the Extension Host, which writes `y\n` or `n\n` to stdin.

---

## File Watching and Live State

The Extension Host registers a `FileSystemWatcher` for:
- `.ralph/<project-name>/tasks.json` — task progress updates
- `.ralph/<project-name>/validation.md` — validation status updates
- `.ralph/<project-name>/spec.md` — spec changes (e.g. after interview or comment)

On any change event, the updated file content is read and a `state_update` message is posted to the active WebviewPanel. The Webview re-renders the relevant UI component (task progress bar, validation badge, etc.) without re-running any command.

---

## Extension Activation and Sidebar

### Activation

The extension activates when:
- A workspace is opened that contains a `.ralph/` directory (using `workspaceContains:.ralph` activation event), OR
- The user explicitly opens the Ralph sidebar view.

### Sidebar (TreeDataProvider)

The sidebar shows a flat list of Ralph projects found in `.ralph/`. Each entry:
- Shows the project name.
- Shows a status badge: `pending` / `in_progress` / `completed` / `failed` (derived from the aggregate task status in `tasks.json`).
- Clicking an entry opens (or focuses) its WebviewPanel.

A **"+ New Project"** item is always shown at the top.

The sidebar is refreshed:
- On extension activation.
- When any `.ralph/*/tasks.json` file changes (FileSystemWatcher).
- After a `ralph init` completes.

---

## Process Management

### Spawning

All CLI calls use `child_process.spawn('ralph', [...args], { cwd: workspacePath, shell: false })`.

- `stdout` and `stderr` are attached to `data` event listeners that send chunked output to the Webview in real time.
- The process handle is stored in a `Map<projectName, ChildProcess>` so that the Stop button can send `SIGTERM`.
- Only one process per project tab is allowed at a time. If a command is already running, the Run button is disabled and replaced with a Stop button.

### Error Handling

- Non-zero exit codes are shown as an error banner in the Output Area.
- If `ralph` is not found on PATH, an error is shown once with a link to the installation instructions.
- Process crash (signal termination) is detected via the `close` event and reported in the Output Area.

### Working Directory

The `cwd` for all spawned processes is the VS Code workspace root — the same directory from which the user would run `ralph` in a terminal. This ensures `.ralph/` is created and read in the correct location.

---

## Settings Integration

On panel open, the extension reads `.ralph/settings.json` (if present) and pre-fills the flag panel defaults for the active project. Global flags (`--verbose`, `--rounds`, `--limit`, `--base`, `--provider`, `--asynchronous`) displayed in the flag panel reflect the persisted values but can be overridden per-invocation — identical to the CLI behaviour.

The extension does not write to `settings.json` directly; any flag changes the user makes in the GUI are passed as CLI arguments for that invocation only. To persist them, the user would run the same global flag command via the CLI

---

## Spec File Editor

After a new project tab is created, the extension automatically opens `.ralph/<project-name>/spec.md` in the VS Code editor (via `vscode.workspace.openTextDocument` + `vscode.window.showTextDocument`). This is the fastest path to editing the spec without requiring additional UI.

The `test-instructions.md` file is also opened alongside `spec.md` in a split view, so the user can fill in both files immediately after init.

---

## Development Approach

### Directory Structure

```
ralph-vscode/                    ← extension root (separate repo or sub-folder)
├── package.json                 ← extension manifest + VS Code contribution points
├── tsconfig.json
├── esbuild.js                   ← build script
├── src/
│   ├── extension.ts             ← activate(), registerCommands()
│   ├── sidebarProvider.ts       ← RalphSidebarProvider (TreeDataProvider)
│   ├── panelManager.ts          ← RalphPanelManager (WebviewPanel lifecycle)
│   ├── processManager.ts        ← RalphProcessManager (child_process.spawn)
│   ├── fileWatcher.ts           ← RalphFileWatcher
│   └── messages.ts              ← shared message type definitions (Extension ↔ Webview)
└── webview/
    ├── index.html               ← webview entry point
    ├── app.tsx                  ← React root component
    ├── components/
    │   ├── CommandBar.tsx
    │   ├── FlagPanel.tsx
    │   ├── OutputArea.tsx
    │   ├── TaskProgress.tsx
    │   └── StdinInput.tsx
    └── styles/
        └── main.css             ← VS Code CSS variable tokens for theming
```

### Extension Manifest Contributions (`package.json`)

```json
"contributes": {
  "viewsContainers": {
    "activitybar": [{
      "id": "ralph-sidebar",
      "title": "Ralph Wiggum",
      "icon": "media/ralph-icon.svg"
    }]
  },
  "views": {
    "ralph-sidebar": [{
      "id": "ralph.projectList",
      "name": "Projects"
    }]
  },
  "commands": [
    { "command": "ralph.newProject",  "title": "Ralph: New Project" },
    { "command": "ralph.openProject", "title": "Ralph: Open Project" }
  ]
}
```

### Build

```bash
# Development (watch mode)
node esbuild.js --watch

# Production
node esbuild.js --production
```

esbuild bundles `src/extension.ts` → `dist/extension.js` and `webview/app.tsx` → `dist/webview.js`. The `package.json` `main` field points to `dist/extension.js`.

### Testing

- Unit tests with `vitest` for the process manager and message serialisation logic.
- Integration tests using VS Code's `@vscode/test-electron` runner.
- Manual smoke test checklist:
  - New project tab creation
  - Interview flow with stdin piping
  - Execute with live task progress
  - Undo confirmation dialog
  - Panel restoration after VS Code restart

---

## Phased Rollout

### Phase 1 — Core Shell

- Sidebar with project list.
- WebviewPanel per project with a command bar.
- Process spawning and stdout/stderr streaming to Output Area.
- All commands except interview (no stdin handling yet).
- Task progress bar (polling, not file watching).

### Phase 2 — Interactive Commands

- stdin handling for the interview command.
- Automated `y/n` prompt interception for validate and undo.
- FileSystemWatcher replacing polling.
- Live task progress updates.

### Phase 3 — Polish

- ANSI stripping and markdown rendering in the Output Area.
- Spec file auto-open after init.
- Validation badge in the sidebar.
- Settings read/pre-fill for the flag panel.
- Stop button (SIGTERM) for long-running commands.
- PR URL rendered as a clickable link.
- Extension packaging and README.

---

## Out of Scope

- Re-implementing any Ralph logic inside the extension. All business logic stays in the CLI.
- A custom spec editor UI. The spec is edited in the VS Code text editor.
- Authentication UI for `gh` / `glab`. Users must authenticate those CLIs separately.
- Windows support in Phase 1 (shell differences; to be addressed in Phase 2).
- Multi-root workspaces (single workspace root assumed throughout).
