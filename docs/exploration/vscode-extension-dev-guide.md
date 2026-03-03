# VSCode Extension — Development, Testing & Publishing Guide

## Local Testing

### Prerequisites

The `.vscode/launch.json` and `.vscode/tasks.json` files must exist inside the `ralph-vscode` folder. These are already committed to the repo.

**`ralph-vscode/.vscode/launch.json`** — tells VS Code how to launch the Extension Development Host:
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Run Extension",
      "type": "extensionHost",
      "request": "launch",
      "args": ["--extensionDevelopmentPath=${workspaceFolder}"],
      "outFiles": ["${workspaceFolder}/dist/**/*.js"],
      "preLaunchTask": "npm: build"
    }
  ]
}
```

**`ralph-vscode/.vscode/tasks.json`** — defines the build task that F5 runs automatically:
```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "type": "npm",
      "script": "build",
      "group": "build",
      "label": "npm: build",
      "detail": "Build the extension with esbuild"
    }
  ]
}
```

---

### Step 1 — Open the Extension Folder in VS Code

The VS Code root **must** be `ralph-vscode` (not the parent `ralph-wiggum` folder) for F5 to work.

Since the `code` CLI may not be on your PATH yet, use one of:
- **File → Open Folder…** → select `ralph-wiggum/ralph-vscode` → Open
- Drag the `ralph-vscode` folder from Finder onto the VS Code Dock icon

To install the `code` CLI permanently: **Cmd+Shift+P** → `Shell Command: Install 'code' command in PATH` → restart your terminal. Then `code ralph-vscode` works from the terminal.

---

### Step 2 — Install Dependencies

Open the integrated terminal (`` Ctrl+` `` or **Terminal → New Terminal**):

```bash
npm install
```

---

### Step 3 — Launch with F5

On Mac:
- **Fn+F5** (if your keyboard has a physical Fn key)
- Or **Run → Start Debugging** from the menu bar
- Or **Cmd+Shift+P** → `Debug: Start Debugging`

What happens:
1. VS Code runs `npm run build` automatically (via `preLaunchTask`)
2. A **second VS Code window** opens — this is the **Extension Development Host**

The dev host is a fresh VS Code instance with your extension loaded live from the `dist/` folder.

---

### Step 4 — See the Extension in the Dev Host

The extension activates when the opened workspace contains a `.ralph/` directory (the `workspaceContains:.ralph` activation event).

In the dev host window:
1. **File → Open Folder…** → select your `ralph-wiggum` Python project (which contains `.ralph/` after running `ralph init`)
2. The Ralph sidebar icon appears in the Activity Bar on the left

If there's no `.ralph/` folder yet, either run `ralph init <name>` in the dev host terminal, or temporarily create an empty `.ralph` directory to trigger activation.

---

### Step 5 — Edit → Rebuild → Reload (Iteration Loop)

You do not need to press F5 again after making changes.

**Manual rebuild:**
1. Edit source files in the first window
2. In the first window terminal: `npm run build`
3. In the **dev host window**: **Cmd+Shift+P** → `Developer: Reload Window`

**Watch mode (faster):**
Start this before pressing F5 and leave it running:
```bash
npm run watch
```
Every file save triggers a rebuild in under a second. Then just reload the dev host window as above.

---

### Troubleshooting

| Problem | Fix |
|---|---|
| F5 does nothing / no second window opens | Confirm `ralph-vscode` is the workspace root — the Explorer sidebar should show `ralph-vscode` at the top level |
| Build error: "Cannot find module 'vscode'" | Not a real error — `vscode` is intentionally excluded from the bundle by esbuild |
| Sidebar icon doesn't appear | Open a workspace with a `.ralph/` folder, or manually create one |
| "preLaunchTask not found" error | Confirm `.vscode/tasks.json` exists and the label matches exactly: `"npm: build"` |
| Build fails with other errors | Run `npm install` first, then check the terminal output for the specific error |

---

## Installing as a `.vsix` (Packaged Artifact Test)

Use this to test the exact package that users will download — good for a final sanity check before publishing.

```bash
cd ralph-vscode

# Build + package into a .vsix file
npm run package
# → creates ralph-wiggum-0.0.1.vsix in the current directory

# Install into your main VS Code
# (replace the version number with whatever was created)
code --install-extension ralph-wiggum-0.0.1.vsix
```

To uninstall: Extensions sidebar → Ralph Wiggum → Uninstall.

> `.vsix` installs persist across restarts. Use F5 dev host for fast iteration; `.vsix` for pre-publish validation.

---

## Publishing to the Marketplace

### One-Time Setup

**1. Create a publisher account**

Go to [marketplace.visualstudio.com/manage](https://marketplace.visualstudio.com/manage) and sign in with a Microsoft account. Choose a publisher ID (e.g. `alfaloo`).

**2. Create a Personal Access Token (PAT)**

- Go to [dev.azure.com](https://dev.azure.com) → top-right avatar → **Personal Access Tokens**
- Click **New Token**
- Set the scope to **Marketplace → Manage**
- Set expiry to 1 year
- Copy and save the token — you only see it once

**3. Add your publisher ID to `package.json`**

```json
{
  "publisher": "your-publisher-id",
  ...
}
```

**4. Add other required marketplace fields to `package.json`**

```json
{
  "publisher": "your-publisher-id",
  "icon": "media/ralph-icon-128.png",
  "repository": {
    "type": "git",
    "url": "https://github.com/you/ralph-wiggum"
  },
  "categories": ["Other"],
  "keywords": ["ralph", "ai", "agents", "claude"]
}
```

The `icon` field requires a **128×128 PNG** file at the specified path. Without it the marketplace listing will have no icon.

**5. Log in with vsce**

```bash
cd ralph-vscode
npx vsce login your-publisher-id
# Paste your PAT when prompted
```

---

### Publishing

```bash
cd ralph-vscode
npx vsce publish
```

This builds, packages, and publishes in one step. The extension appears at `marketplace.visualstudio.com/items?itemName=your-publisher-id.ralph-wiggum` within a few minutes.

---

## Pushing Updates

### The Only Required Change: Bump the Version

The marketplace rejects a publish if `package.json` `"version"` hasn't changed from the previous release. Bump it before every publish:

```bash
# Patch: 0.0.1 → 0.0.2 (bug fixes)
npm version patch

# Minor: 0.0.1 → 0.1.0 (new features, backwards-compatible)
npm version minor

# Major: 0.0.1 → 1.0.0 (breaking changes)
npm version major
```

`npm version` edits `package.json`, creates a git commit, and creates a git tag automatically.

Then publish:
```bash
npx vsce publish
```

Or combine the bump + publish into one command:
```bash
npx vsce publish patch
npx vsce publish minor
npx vsce publish major
```

---

### What to Review Before Each Release

| What | File | When |
|---|---|---|
| Version number | `package.json` → `"version"` | Every release (required) |
| Changelog | `CHANGELOG.md` | Every release — shown on marketplace page |
| VS Code engine minimum | `package.json` → `"engines"."vscode"` | When using new VS Code APIs |
| README | `README.md` | When features change — this is the marketplace homepage |
| Extension icon | `media/ralph-icon-128.png` | Before first publish |

---

## Keeping the Package Small: `.vscodeignore`

Create `ralph-vscode/.vscodeignore` to exclude source and dev files from the `.vsix`. Only `dist/`, `media/`, `package.json`, and `README.md` need to be included.

```
src/
webview/
node_modules/
**/__tests__/
esbuild.js
tsconfig.json
.vscode/
**/*.map
```

Without this file, `vsce package` includes everything, producing a much larger `.vsix` than necessary.
