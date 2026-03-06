import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import { RalphPanelManager } from './panelManager';
import { RalphSidebarProvider } from './sidebarProvider';

type FileType = 'tasks' | 'validation' | 'spec' | 'pr_description' | 'summary';

function extractProjectName(uri: vscode.Uri, workspaceRoot: string): string | undefined {
  const ralphDir = path.join(workspaceRoot, '.ralph');
  const filePath = uri.fsPath;
  if (!filePath.startsWith(ralphDir + path.sep)) {
    return undefined;
  }
  const relative = filePath.slice(ralphDir.length + 1);
  const parts = relative.split(path.sep);
  if (parts.length < 2) {
    return undefined;
  }
  return parts[0];
}

function readFileContent(uri: vscode.Uri): string {
  try {
    return fs.readFileSync(uri.fsPath, 'utf8');
  } catch {
    return '';
  }
}

export class RalphFileWatcher implements vscode.Disposable {
  private readonly watchers: vscode.FileSystemWatcher[] = [];

  constructor(
    private readonly panelManager: RalphPanelManager,
    private readonly sidebarProvider: RalphSidebarProvider,
    private readonly workspaceRoot: string
  ) {
    const patterns: [string, FileType][] = [
      ['.ralph/*/tasks.json', 'tasks'],
      ['.ralph/*/validation.md', 'validation'],
      ['.ralph/*/spec.md', 'spec'],
      ['.ralph/*/pr-description.md', 'pr_description'],
      ['.ralph/*/summary.md', 'summary'],
    ];

    for (const [pattern, fileType] of patterns) {
      const watcher = vscode.workspace.createFileSystemWatcher(
        new vscode.RelativePattern(workspaceRoot, pattern)
      );

      const handler = (uri: vscode.Uri, deleted = false) => {
        this.handleChange(uri, fileType, deleted);
      };

      watcher.onDidChange(uri => handler(uri));
      watcher.onDidCreate(uri => handler(uri));
      watcher.onDidDelete(uri => handler(uri, true));

      this.watchers.push(watcher);
    }
  }

  private handleChange(uri: vscode.Uri, fileType: FileType, deleted: boolean): void {
    const projectName = extractProjectName(uri, this.workspaceRoot);
    if (!projectName) {
      return;
    }

    const content = deleted ? '' : readFileContent(uri);

    const panel = this.panelManager.getPanel(projectName);
    if (panel) {
      panel.webview.postMessage({
        type: 'state_update',
        file: fileType,
        projectName,
        content,
      });
    }

    if (fileType === 'tasks') {
      this.sidebarProvider.refresh();
    }
  }

  dispose(): void {
    for (const watcher of this.watchers) {
      watcher.dispose();
    }
    this.watchers.length = 0;
  }
}
