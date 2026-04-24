import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import { spawn, exec, execSync } from 'child_process';
import { RalphSidebarProvider } from './sidebarProvider';
import { RalphPanelManager } from './panelManager';
import { RalphProcessManager } from './processManager';
import { RalphFileWatcher } from './fileWatcher';

const OPEN_PANELS_KEY = 'ralph.openPanels';

function buildExtendedPath(): string {
  const home = process.env.HOME || '';
  const sep = process.platform === 'win32' ? ';' : ':';
  const extraPaths = [
    `${home}/.local/bin`,
    '/opt/homebrew/bin',
    '/opt/homebrew/sbin',
    '/usr/local/bin',
  ].join(sep);
  return [extraPaths, process.env.PATH || ''].join(sep);
}

function readBundledVersion(bundledPath: string): string | null {
  try {
    const toml = fs.readFileSync(path.join(bundledPath, 'pyproject.toml'), 'utf-8');
    const match = toml.match(/^version\s*=\s*"([^"]+)"/m);
    return match ? match[1] : null;
  } catch {
    return null;
  }
}

function getInstalledVersion(extendedPath: string): string | null {
  try {
    const pip = process.platform === 'win32' ? 'pip' : 'python3 -m pip';
    const output = execSync(`${pip} show ralph-wiggum`, {
      env: { ...process.env, PATH: extendedPath },
      timeout: 10000,
      stdio: 'pipe',
    }).toString();
    const match = output.match(/^Version:\s*(.+)$/m);
    return match ? match[1].trim() : null;
  } catch {
    return null;
  }
}

async function ensureRalphInstalled(context: vscode.ExtensionContext): Promise<void> {
  const bundledPath = path.join(context.extensionPath, 'bundled');
  const extendedPath = buildExtendedPath();

  const bundledVersion = readBundledVersion(bundledPath);
  const installedVersion = getInstalledVersion(extendedPath);

  if (bundledVersion && installedVersion === bundledVersion) {
    return;
  }

  const isUpgrade = installedVersion !== null;
  const title = isUpgrade
    ? `Ralph Wiggum: Updating CLI ${installedVersion} → ${bundledVersion}...`
    : 'Ralph Wiggum: Installing CLI...';

  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title, cancellable: false },
    () => new Promise<void>((resolve) => {
      const pip = process.platform === 'win32' ? 'pip' : 'python3 -m pip';
      const cmd = `${pip} install --user --quiet "${bundledPath}"`;
      exec(cmd, { timeout: 120000 }, (err, _stdout, stderr) => {
        if (err) {
          vscode.window.showErrorMessage(
            `Ralph CLI ${isUpgrade ? 'update' : 'installation'} failed: ${stderr || err.message}. ` +
            `Run \`pip install --user "${bundledPath}"\` manually.`
          );
        } else {
          vscode.window.showInformationMessage(
            isUpgrade ? `Ralph CLI updated to ${bundledVersion}.` : 'Ralph CLI installed successfully.'
          );
        }
        resolve();
      });
    })
  );
}

export async function activate(context: vscode.ExtensionContext) {
  await ensureRalphInstalled(context);

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
            processManager.writeToStdin(projectName, msg.text);
            break;
          case 'stop_command':
            processManager.stop(projectName);
            break;
          case 'submit_interview': {
            const answersPath = path.join(workspaceRoot, '.ralph', projectName, 'interview_answers.json');
            fs.writeFileSync(answersPath, JSON.stringify(msg.answers), 'utf-8');
            break;
          }
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
