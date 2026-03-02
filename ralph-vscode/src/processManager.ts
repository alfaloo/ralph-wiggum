import * as vscode from 'vscode';
import { spawn, ChildProcess } from 'child_process';

const YN_PATTERNS = [
  /already exists\. Overwrite\? \(y\/n\):/,
  /Delete branch '.*'\. This cannot be undone\. \(y\/n\):/,
];

export class RalphProcessManager {
  private processes = new Map<string, ChildProcess>();
  private workspaceRoot: string;

  constructor(workspaceRoot: string) {
    this.workspaceRoot = workspaceRoot;
  }

  run(projectName: string, command: string, args: string[], panel: vscode.WebviewPanel): void {
    if (this.isRunning(projectName)) {
      return;
    }

    const child = spawn('ralph', [command, projectName, ...args], {
      cwd: this.workspaceRoot,
      shell: false,
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
