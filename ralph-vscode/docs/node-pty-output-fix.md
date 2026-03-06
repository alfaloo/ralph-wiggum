# Fixing CLI Output Streaming in VS Code Extension

## Problem

The `ralph interview` command produced no output in the extension's webview or Output channel, even though running the same command in the VS Code integrated terminal worked correctly.

## Root Cause Chain

### 1. Python stdout buffering (first issue, easy fix)

When a Python process writes to stdout and stdout is connected to a **pipe** (not a real terminal), Python switches from line-buffered to block-buffered mode. Output is held in a 64 KB internal buffer and never flushed until the process exits or the buffer fills.

**Fix:** Set `PYTHONUNBUFFERED=1` in the spawn environment.

```ts
env: { ...process.env, PYTHONUNBUFFERED: '1' }
```

This made the initial log lines (`[ralph] Interview round 1/1`) appear, but the AI-generated questions still didn't stream through.

### 2. TTY detection by subprocesses (root cause, hard fix)

The `ralph interview` command internally spawns child processes (e.g. the `claude` CLI) that call `isatty()` at the OS level to determine whether they are connected to a real terminal. When the answer is "no" (i.e. stdout is a pipe), these tools either suppress output, buffer it, or behave in a completely different (non-interactive) mode.

No environment variable can fake `isatty()` — it is a syscall that checks the file descriptor type at the kernel level.

**Attempted intermediate fix:** `script -q /dev/null ralph ...`

The `script` command allocates a pseudo-terminal and runs a command inside it. This works in a real terminal session but **fails in VS Code's extension host** with:

```
script: tcgetattr/ioctl: Operation not supported on socket
```

This is because `script` itself requires an existing TTY to attach to, which the extension host process does not have (its stdio is connected to IPC sockets, not a terminal).

**Correct fix:** `node-pty`

`node-pty` creates a PTY from scratch via the `openpty()` syscall — it does not need an existing terminal. This is exactly how VS Code's own integrated terminal works internally.

```ts
import * as pty from 'node-pty';

const child = pty.spawn('ralph', fullArgs, {
  name: 'xterm-256color',
  cols: 120,
  rows: 30,
  cwd: this.workspaceRoot,
  env: { ...process.env, PATH: this.shellPath, PYTHONUNBUFFERED: '1' },
});

child.onData((data: string) => {
  const text = stripAnsi(data);
  panel.webview.postMessage({ type: 'stdout', chunk: text });
});

child.onExit(({ exitCode }) => {
  panel.webview.postMessage({ type: 'process_done', exitCode: exitCode ?? null });
});
```

Key differences from `child_process.spawn`:
- All output (stdout + stderr merged) comes through `onData` — PTYs have a single stream
- Stdin is written via `child.write(text)` instead of `child.stdin.write(text)`
- Exit is via `child.onExit()` instead of `child.on('close')`
- PTY output includes ANSI escape codes — must be stripped before display

### 3. ANSI stripping

Because `node-pty` creates a real terminal, the child process emits ANSI escape codes for colors and cursor movement, and the PTY itself converts `\n` to `\r\n`. These must be stripped before displaying in the Output channel or webview.

```ts
function stripAnsi(text: string): string {
  return text
    .replace(/\x1b\[[0-9;?]*[a-zA-Z]/g, '')    // CSI sequences (colors, cursor)
    .replace(/\x1b\][^\x07]*\x07/g, '')          // OSC sequences (window title, etc.)
    .replace(/\x1b[()][AB012]/g, '')             // Character set designations
    .replace(/\x1b[=><MNOPQRSTUVWXYZ\\^_]/g, '') // Single-char escape sequences
    .replace(/\r\n/g, '\n')                       // Normalize CRLF from PTY
    .replace(/\r/g, '\n');                        // Normalize lone CR
}
```

---

## The node-pty/lib/utils.js Bug

### Description

`node-pty` v1.1.0 has a **path construction bug** in `lib/utils.js` that prevents the prebuilt native binary from loading on all platforms.

The relevant code in the original file:

```js
var dirs = ['build/Release', 'build/Debug', "prebuilds/" + process.platform + "-" + process.arch];
var relative = ['..', '.'];

for (var d of dirs) {
  for (var r of relative) {
    var dir = r + "/" + d + "/";          // <-- trailing slash added here
    try {
      return require(dir + "/" + name + ".node");  // <-- another slash added here
    } catch (e) { ... }
  }
}
```

`dir` is built with a trailing `/`, then another `/` is prepended to `name + ".node"`. This results in a **double slash** in the path:

```
./prebuilds/darwin-arm64//pty.node   ← double slash
```

On Unix, `//` in a file path is treated as `/` by the OS, but Node.js `require()` does **not** normalize the path before module lookup. The lookup fails with `Cannot find module` even though the file exists at the correct single-slash path.

### Affected Platforms

All platforms — the bug is in the JavaScript path construction and is not OS-specific. The prebuilt binaries exist for:
- `darwin-arm64` (macOS Apple Silicon)
- `darwin-x64` (macOS Intel)
- `win32-x64` (Windows x64)
- `win32-arm64` (Windows ARM)

### Fix

Remove the trailing slash from the `dir` variable:

```js
// Before (buggy):
var dir = r + "/" + d + "/";

// After (fixed):
var dir = r + "/" + d;
```

This fix is applied via `patches/node-pty+1.1.0.patch` using `patch-package`, which re-applies it automatically after every `npm install`.

### Why the Prebuilt Binary Works Without Rebuilding

The prebuilt `pty.node` is compiled using **N-API** (Node-API), which is ABI-stable across all Node.js versions. Unlike older native modules that used the raw V8 API (and required recompilation per Node.js version), N-API modules work with any Node.js version that supports N-API (Node 6.14.2+). This means the single prebuilt binary works with VS Code's bundled Node.js regardless of which version that is.

---

## macOS App Translocation (Development Only)

During development on macOS, VS Code may run from a randomised App Translocation path:

```
/private/var/folders/.../AppTranslocation/GUID/d/Visual Studio Code.app
```

This occurs when VS Code was downloaded via a browser (quarantine bit set) and not explicitly moved to `/Applications`. In this state, macOS enforces stricter code-signing validation and native modules fail to load with:

```
code signature not valid for use in process: mapping process and mapped file (non-platform) have different Team IDs
```

**Fix (one-time, development only):**

```bash
xattr -dr com.apple.quarantine "/Applications/Visual Studio Code.app"
```

Then fully quit and relaunch VS Code. This does not affect end users installing the extension from the marketplace, as extensions are extracted without quarantine bits.

---

## Summary of All Fixes Applied

| File | Change |
|------|--------|
| `src/processManager.ts` | Added `PYTHONUNBUFFERED: '1'` to spawn env |
| `src/processManager.ts` | Replaced `child_process.spawn` with `node-pty` for PTY support |
| `src/processManager.ts` | Added `stripAnsi()` to clean PTY output |
| `src/processManager.ts` | Windows-aware `resolveShellPath()` (skip Unix shell fixup on win32) |
| `esbuild.js` | Added `'node-pty'` to `external` list (native module, cannot be bundled) |
| `package.json` | Added `postinstall: "patch-package"` to re-apply patches after npm install |
| `patches/node-pty+1.1.0.patch` | Fixes double-slash path bug in `node-pty/lib/utils.js` |
