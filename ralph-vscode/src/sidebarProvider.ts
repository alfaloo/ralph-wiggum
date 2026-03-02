import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';

type StatusBadge = 'pending' | 'in_progress' | 'completed' | 'failed';

export class ProjectItem extends vscode.TreeItem {
  constructor(
    public readonly label: string,
    public readonly description: string,
    public readonly command?: vscode.Command,
    public readonly iconPath?: vscode.ThemeIcon
  ) {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.description = description;
    this.command = command;
    this.iconPath = iconPath;
  }
}

export class RalphSidebarProvider implements vscode.TreeDataProvider<ProjectItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<ProjectItem | undefined | null | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  constructor(
    private readonly workspaceRoot: string,
    context: vscode.ExtensionContext
  ) {
    // Watcher 1: .ralph/*/tasks.json — refresh on any change
    const tasksWatcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(workspaceRoot, '.ralph/*/tasks.json')
    );
    tasksWatcher.onDidChange(() => this.refresh());
    tasksWatcher.onDidCreate(() => this.refresh());
    tasksWatcher.onDidDelete(() => this.refresh());
    context.subscriptions.push(tasksWatcher);

    // Watcher 2: .ralph/ directory — refresh when sub-folders are created or deleted
    const dirWatcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(workspaceRoot, '.ralph/*')
    );
    dirWatcher.onDidCreate(() => this.refresh());
    dirWatcher.onDidDelete(() => this.refresh());
    context.subscriptions.push(dirWatcher);
  }

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: ProjectItem): vscode.TreeItem {
    return element;
  }

  getChildren(): ProjectItem[] {
    const items: ProjectItem[] = [];

    // Special 'New Project' item at the top
    const newProjectItem = new ProjectItem(
      'New Project',
      '',
      {
        command: 'ralph.newProject',
        title: 'New Project',
      },
      new vscode.ThemeIcon('add')
    );
    items.push(newProjectItem);

    const ralphDir = path.join(this.workspaceRoot, '.ralph');

    if (!fs.existsSync(ralphDir)) {
      return items;
    }

    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(ralphDir, { withFileTypes: true });
    } catch {
      return items;
    }

    for (const entry of entries) {
      if (!entry.isDirectory()) {
        continue;
      }

      // Criterion 1: name must not begin with a symbol character (first char must be letter or digit)
      const firstChar = entry.name[0];
      if (!firstChar || !/[a-zA-Z0-9]/.test(firstChar)) {
        continue;
      }

      // Criterion 2: must contain a spec.md file
      const specPath = path.join(ralphDir, entry.name, 'spec.md');
      if (!fs.existsSync(specPath)) {
        continue;
      }

      const projectName = entry.name;
      const status = this.computeStatus(ralphDir, projectName);

      const projectItem = new ProjectItem(
        projectName,
        status,
        {
          command: 'ralph.openProject',
          title: 'Open',
          arguments: [projectName],
        }
      );
      items.push(projectItem);
    }

    return items;
  }

  private computeStatus(ralphDir: string, projectName: string): StatusBadge {
    const tasksPath = path.join(ralphDir, projectName, 'tasks.json');

    if (!fs.existsSync(tasksPath)) {
      return 'pending';
    }

    let content: string;
    try {
      content = fs.readFileSync(tasksPath, 'utf8');
    } catch {
      return 'pending';
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(content);
    } catch {
      return 'pending';
    }

    if (!parsed || typeof parsed !== 'object') {
      return 'pending';
    }

    const obj = parsed as Record<string, unknown>;

    // Empty object or no tasks array
    if (!Array.isArray(obj['tasks']) || obj['tasks'].length === 0) {
      return 'pending';
    }

    const tasks = obj['tasks'] as Array<{ status: string }>;

    if (tasks.some(t => t.status === 'in_progress')) {
      return 'in_progress';
    }

    if (tasks.every(t => t.status === 'completed')) {
      return 'completed';
    }

    if (tasks.some(t => t.status === 'blocked') && !tasks.some(t => t.status === 'in_progress')) {
      return 'failed';
    }

    return 'pending';
  }
}
