# Ralph Wiggum — VS Code Extension

A Visual Studio Code extension that wraps the `ralph` CLI as a GUI application. Instead of typing `ralph <command> <project-name> [flags]` in a terminal, you interact with Ralph projects through a sidebar and per-project webview panels that stream CLI output in real time.

## What It Does

- **Sidebar**: Lists all Ralph projects found in `.ralph/` in your workspace, with live status badges (`pending`, `in_progress`, `completed`, `failed`).
- **Project panels**: Each project gets its own tab with a command bar, flag inputs, a scrollable output area, and a live task progress bar.
- **Interactive interview**: The stdin input area appears automatically when `ralph interview` is waiting for answers — type and submit without leaving VS Code.
- **Live progress**: The task progress bar updates in real time as `ralph execute` runs.

## Prerequisites

The `ralph` CLI must be installed and available on your `PATH`. Verify with:

```bash
ralph --help
```

If `ralph` is not found, install it according to the [ralph documentation](https://github.com/anthropics/ralph-wiggum) and ensure the install location is on your `PATH`.

## Installation

### From VSIX (recommended)

1. Build the VSIX package:
   ```bash
   cd ralph-vscode
   npm install
   npm run package
   ```
2. In VS Code, open the Extensions view (`Ctrl+Shift+X` / `Cmd+Shift+X`).
3. Click the `...` menu → **Install from VSIX...** and select the generated `.vsix` file.

### Development mode (F5)

1. Open the `ralph-vscode/` folder in VS Code.
2. Run `npm install` to install dependencies.
3. Press **F5** to launch a new VS Code window with the extension loaded.

## Basic Usage

1. Open a workspace folder that contains a `.ralph/` directory (or any workspace — you can create a new project from the sidebar).
2. The **Ralph Wiggum** icon appears in the Activity Bar. Click it to open the sidebar.
3. The sidebar lists all Ralph projects. Click **+ New Project** to initialise a new one.
4. Click a project to open its panel.
5. Select a command from the command bar, adjust any flags, and click **Run**.
