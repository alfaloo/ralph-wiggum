import * as vscode from 'vscode';
import { spawn, execSync, ChildProcess } from 'child_process';

const YN_PATTERNS = [
  /already exists\. Overwrite\? \(y\/n\):/,
  /Delete branch '.*'\. This cannot be undone\. \(y\/n\):/,
];

/**
 * VS Code on macOS launches without a login shell, so PATH is minimal and
 * tools installed via Homebrew, npm, pip, etc. are not found. This runs the
 * user's shell as a login shell once to capture the full PATH.
 */
function resolveShellPath(): string {
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

export class RalphProcessManager {
  private processes = new Map<string, ChildProcess>();
  private workspaceRoot: string;
  private shellPath: string;

  constructor(workspaceRoot: string) {
    this.workspaceRoot = workspaceRoot;
    this.shellPath = resolveShellPath();
  }

  run(projectName: string, command: string, args: string[], panel: vscode.WebviewPanel): void {
    if (this.isRunning(projectName)) {
      return;
    }

    const child = spawn('ralph', [command, projectName, ...args], {
      cwd: this.workspaceRoot,
      shell: false,
      env: { ...process.env, PATH: this.shellPath },
    });

    this.processes.set(projectName, child);
    panel.webview.postMessage({ type: 'process_started' });

    child.stdout!.on('data', (chunk: Buffer) => {
      const text = chunk.toString();
      panel.webview.postMessage({ type: 'stdout', chunk: text });

      if (text.includes('Type your answers below')) {
        panel.webview.postMessage({ type: 'stdin_ready' });
      }

      for (const line of text.split('\n')) {
        this.handleYNPrompt(line, projectName);
      }
    });

    child.stderr!.on('data', (chunk: Buffer) => {
      panel.webview.postMessage({ type: 'stderr', chunk: chunk.toString() });
    });

    child.on('close', (exitCode: number | null) => {
      panel.webview.postMessage({ type: 'process_done', exitCode });
      this.processes.delete(projectName);
    });

    child.on('error', (err: NodeJS.ErrnoException) => {
      if (err.code === 'ENOENT') {
        panel.webview.postMessage({ type: 'ralph_not_found' });
      }
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
    if (child && child.stdin) {
      child.stdin.write(text);
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
