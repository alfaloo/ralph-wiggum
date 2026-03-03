import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import { spawn } from 'child_process';
import { RalphSidebarProvider } from './sidebarProvider';
import { RalphPanelManager } from './panelManager';
import { RalphProcessManager } from './processManager';
import { RalphFileWatcher } from './fileWatcher';

const OPEN_PANELS_KEY = 'ralph.openPanels';

export function activate(context: vscode.ExtensionContext) {
  const workspaceRoot = vscode.workspace.workspaceFolders![0].uri.fsPath;

  const sidebar = new RalphSidebarProvider(workspaceRoot, context);
  const panelManager = new RalphPanelManager(context, context.extensionUri, workspaceRoot);
  const processManager = new RalphProcessManager(workspaceRoot);
  const fileWatcher = new RalphFileWatcher(panelManager, sidebar, workspaceRoot);

  // Register sidebar
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider('ralph.projectList', sidebar)
  );

  // Push fileWatcher disposable
  context.subscriptions.push(fileWatcher);

  // Track wired panels to avoid duplicate listeners
  const wiredPanels = new Set<string>();

  function wirePanel(projectName: string, panel: vscode.WebviewPanel): void {
    if (wiredPanels.has(projectName)) {
      return;
    }
    wiredPanels.add(projectName);

    panel.onDidDispose(() => {
      wiredPanels.delete(projectName);
    }, undefined, context.subscriptions);

    panel.webview.onDidReceiveMessage(
      msg => {
        switch (msg.type) {
          case 'run_command':
            processManager.run(projectName, msg.command, msg.args, panel);
            break;
          case 'stdin_input':
            processManager.writeToStdin(projectName, msg.text + '\n\x04');
            break;
          case 'stop_command':
            processManager.stop(projectName);
            break;
          case 'open_url':
            vscode.env.openExternal(vscode.Uri.parse(msg.url));
            break;
        }
      },
      undefined,
      context.subscriptions
    );
  }

  // Register ralph.newProject command
  context.subscriptions.push(
    vscode.commands.registerCommand('ralph.newProject', async () => {
      const name = await vscode.window.showInputBox({
        prompt: 'Enter project name',
        placeHolder: 'my-project',
        validateInput(v) {
          if (!v || v.trim() === '') {
            return 'Project name cannot be empty';
          }
          if (!/^[a-zA-Z]/.test(v)) {
            return 'Project name must begin with a letter';
          }
          if (/[/\\:*?"<>|\x00]/.test(v)) {
            return 'Project name cannot contain /, \\, :, *, ?, ", <, >, or |';
          }
          const projectPath = path.join(workspaceRoot, '.ralph', v);
          if (fs.existsSync(projectPath)) {
            return `Project '${v}' already exists`;
          }
          return undefined;
        },
      });

      if (!name) {
        return;
      }

      const channel = vscode.window.createOutputChannel('Ralph Init');
      channel.show();

      const child = spawn('ralph', ['init', name], {
        cwd: workspaceRoot,
        shell: false,
      });

      child.stdout!.on('data', (chunk: Buffer) => {
        const text = chunk.toString();
        channel.append(text);

        for (const line of text.split('\n')) {
          if (/Update base branch to '.*'\? \(y\/n\):/.test(line)) {
            vscode.window.showWarningMessage(line, 'Yes', 'No').then(choice => {
              if (choice !== undefined) {
                child.stdin!.write(choice === 'Yes' ? 'y\n' : 'n\n');
              }
            });
          }
        }
      });

      child.stderr!.on('data', (chunk: Buffer) => {
        channel.append(chunk.toString());
      });

      child.on('close', async (exitCode: number | null) => {
        if (exitCode === 0) {
          sidebar.refresh();
          const panel = panelManager.openPanel(name);
          wirePanel(name, panel);

          // Auto-open spec.md and test-instructions.md in split editor
          const specPath = path.join(workspaceRoot, '.ralph', name, 'spec.md');
          const testInstructionsPath = path.join(workspaceRoot, '.ralph', name, 'test-instructions.md');

          try {
            const specDoc = await vscode.workspace.openTextDocument(specPath);
            await vscode.window.showTextDocument(specDoc, { viewColumn: vscode.ViewColumn.Beside });
          } catch {}

          try {
            const testDoc = await vscode.workspace.openTextDocument(testInstructionsPath);
            await vscode.window.showTextDocument(testDoc, { viewColumn: vscode.ViewColumn.Beside });
          } catch {}
        }
      });
    })
  );

  // Register ralph.openProject command
  context.subscriptions.push(
    vscode.commands.registerCommand('ralph.openProject', (projectName: string) => {
      const panel = panelManager.openPanel(projectName);
      wirePanel(projectName, panel);
    })
  );

  // Restore panels from previous session and wire each
  const restoredPanelNames = context.workspaceState.get<string[]>(OPEN_PANELS_KEY, []);
  panelManager.restorePanels();
  for (const projectName of restoredPanelNames) {
    const panel = panelManager.getPanel(projectName);
    if (panel) {
      wirePanel(projectName, panel);
    }
  }
}

export function deactivate() {}
