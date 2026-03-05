import * as vscode from 'vscode';
import { execSync } from 'child_process';
import * as pty from 'node-pty';

const YN_PATTERNS = [
  /already exists\. Overwrite\? \(y\/n\):/,
  /Delete branch '.*'\. This cannot be undone\. \(y\/n\):/,
];

/**
 * VS Code on macOS/Linux launches without a login shell, so PATH is minimal
 * and tools installed via Homebrew, pip, etc. are not found. This runs the
 * user's shell as a login shell once to capture the full PATH.
 * On Windows, the inherited PATH is already complete — no fixup needed.
 */
function resolveShellPath(): string {
  if (process.platform === 'win32') {
    return process.env.PATH || '';
  }

  const home = process.env.HOME || '';
  // These are always prepended so that tools in non-standard locations
  // (e.g. ~/.local/bin for claude, /opt/homebrew/bin for Homebrew) are
  // always reachable regardless of whether shell resolution succeeds.
  const commonPaths = [
    `${home}/.local/bin`,
    '/opt/homebrew/bin',
    '/opt/homebrew/sbin',
    '/usr/local/bin',
  ];

  let shellPath = process.env.PATH || '';
  try {
    const shell = process.env.SHELL || '/bin/zsh';
    // -l loads .zprofile; source .zshrc explicitly since -i can fail in non-TTY contexts
    shellPath = execSync(
      `${shell} -l -c 'source ~/.zshrc 2>/dev/null; echo $PATH'`,
      { encoding: 'utf8', timeout: 5000 }
    ).trim();
  } catch {
    // fall through to commonPaths + process.env.PATH
  }

  return [...commonPaths, shellPath].join(':');
}

/**
 * Strip ANSI escape codes and normalize line endings from PTY output.
 */
function stripAnsi(text: string): string {
  return text
    .replace(/\x1b\[[0-9;?]*[a-zA-Z]/g, '')    // CSI sequences (colors, cursor)
    .replace(/\x1b\][^\x07]*\x07/g, '')          // OSC sequences (window title, etc.)
    .replace(/\x1b[()][AB012]/g, '')             // Character set designations
    .replace(/\x1b[=><MNOPQRSTUVWXYZ\\^_]/g, '') // Single-char escape sequences
    .replace(/\r\n/g, '\n')                       // Normalize CRLF
    .replace(/\r/g, '\n');                        // Normalize lone CR
}

export class RalphProcessManager {
  private processes = new Map<string, pty.IPty>();
  private suppressEcho = new Map<string, string>();
  private workspaceRoot: string;
  private shellPath: string;
  private outputChannel: vscode.OutputChannel;

  constructor(workspaceRoot: string) {
    this.workspaceRoot = workspaceRoot;
    this.shellPath = resolveShellPath();
    this.outputChannel = vscode.window.createOutputChannel('Ralph');
  }

  run(projectName: string, command: string, args: string[], panel: vscode.WebviewPanel): void {
    if (this.isRunning(projectName)) {
      return;
    }

    const fullArgs = [command, projectName, ...args];
    this.outputChannel.appendLine(`\n[ralph ${fullArgs.join(' ')}]`);
    this.outputChannel.show(true); // true = don't steal focus

    let child: pty.IPty;
    try {
      child = pty.spawn('ralph', fullArgs, {
        name: 'xterm-256color',
        cols: 120,
        rows: 30,
        cwd: this.workspaceRoot,
        env: { ...process.env, PATH: this.shellPath, PYTHONUNBUFFERED: '1' } as Record<string, string>,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      this.outputChannel.appendLine(`[error spawning: ${msg}]`);
      panel.webview.postMessage({ type: 'ralph_not_found' });
      return;
    }

    this.processes.set(projectName, child);
    this.outputChannel.appendLine(`[pid: ${child.pid}]`);
    panel.webview.postMessage({ type: 'process_started' });

    child.onData((data: string) => {
      const text = stripAnsi(data);
      this.outputChannel.append(text);

      // Suppress PTY echo of text submitted via writeToStdin
      const pending = this.suppressEcho.get(projectName);
      if (pending !== undefined && text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trimEnd() === pending) {
        this.suppressEcho.delete(projectName);
        return;
      }

      panel.webview.postMessage({ type: 'stdout', chunk: text });

      if (text.includes('Type your answers below')) {
        panel.webview.postMessage({ type: 'stdin_ready' });
      }

      for (const line of text.split('\n')) {
        this.handleYNPrompt(line, projectName);
      }
    });

    child.onExit(({ exitCode }) => {
      this.outputChannel.appendLine(`[exit code: ${exitCode}]`);
      panel.webview.postMessage({ type: 'process_done', exitCode: exitCode ?? null });
      this.processes.delete(projectName);
      this.suppressEcho.delete(projectName);
    });
  }

  stop(projectName: string): void {
    const child = this.processes.get(projectName);
    if (child) {
      child.kill('SIGTERM');
    }
  }

  isRunning(projectName: string): boolean {
    return this.processes.has(projectName);
  }

  writeToStdin(projectName: string, text: string): void {
    const child = this.processes.get(projectName);
    if (child) {
      // Record what we're writing so the PTY echo can be suppressed in onData
      this.suppressEcho.set(projectName, text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trimEnd());
      child.write(text);
    }
  }

  handleYNPrompt(line: string, projectName: string): void {
    for (const pattern of YN_PATTERNS) {
      if (pattern.test(line)) {
        vscode.window.showInformationMessage(line, 'Yes', 'No').then((choice) => {
          if (choice !== undefined) {
            this.writeToStdin(projectName, choice === 'Yes' ? 'y\n' : 'n\n');
          }
        });
        return;
      }
    }
  }
}
