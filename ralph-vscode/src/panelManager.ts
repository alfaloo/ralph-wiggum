import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import * as crypto from 'crypto';

const OPEN_PANELS_KEY = 'ralph.openPanels';

export class RalphPanelManager {
  private readonly panels = new Map<string, vscode.WebviewPanel>();

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly extensionUri: vscode.Uri,
    private readonly workspaceRoot: string
  ) {}

  openPanel(projectName: string): vscode.WebviewPanel {
    const existing = this.panels.get(projectName);
    if (existing) {
      existing.reveal(vscode.ViewColumn.One);
      this.postSettings(projectName, existing);
      this.postInitialState(projectName, existing);
      return existing;
    }

    const panel = vscode.window.createWebviewPanel(
      'ralph.panel',
      projectName,
      vscode.ViewColumn.One,
      {
        enableScripts: true,
        localResourceRoots: [vscode.Uri.joinPath(this.extensionUri, 'dist')],
        retainContextWhenHidden: true,
      }
    );

    panel.webview.html = this.getHtmlForWebview(panel.webview);
    this.panels.set(projectName, panel);
    this.persistOpenPanels();

    panel.onDidDispose(() => {
      this.panels.delete(projectName);
      this.persistOpenPanels();
    });

    this.postSettings(projectName, panel);

    // Webview hasn't mounted yet — wait for the ready signal before sending state
    const readySub = panel.webview.onDidReceiveMessage(msg => {
      if (msg.type === 'webview_ready') {
        this.postInitialState(projectName, panel);
        readySub.dispose();
      }
    });

    return panel;
  }

  private postInitialState(projectName: string, panel: vscode.WebviewPanel): void {
    const files: Array<{ file: 'tasks' | 'validation' | 'spec'; name: string }> = [
      { file: 'tasks', name: 'tasks.json' },
      { file: 'validation', name: 'validation.md' },
      { file: 'spec', name: 'spec.md' },
    ];
    for (const { file, name } of files) {
      try {
        const filePath = path.join(this.workspaceRoot, '.ralph', projectName, name);
        const content = fs.readFileSync(filePath, 'utf-8');
        panel.webview.postMessage({ type: 'state_update', file, projectName, content });
      } catch {
        // File missing — skip
      }
    }
  }

  private postSettings(projectName: string, panel: vscode.WebviewPanel): void {
    try {
      const settingsPath = path.join(this.workspaceRoot, '.ralph', projectName, 'settings.json');
      const content = fs.readFileSync(settingsPath, 'utf-8');
      const settings = JSON.parse(content);
      panel.webview.postMessage({ type: 'settings_update', settings });
    } catch {
      // File missing or invalid JSON — no settings to pre-fill
    }
  }

  getPanel(projectName: string): vscode.WebviewPanel | undefined {
    return this.panels.get(projectName);
  }

  disposePanel(projectName: string): void {
    const panel = this.panels.get(projectName);
    if (panel) {
      panel.dispose();
      // onDidDispose handles removing from map and persisting
    }
  }

  restorePanels(): void {
    const openPanels = this.context.workspaceState.get<string[]>(OPEN_PANELS_KEY, []);
    for (const projectName of openPanels) {
      this.openPanel(projectName);
    }
  }

  private persistOpenPanels(): void {
    const openPanelNames = Array.from(this.panels.keys());
    this.context.workspaceState.update(OPEN_PANELS_KEY, openPanelNames);
  }

  private getHtmlForWebview(webview: vscode.Webview): string {
    const webviewJsUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this.extensionUri, 'dist', 'webview.js')
    );
    const webviewCssUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this.extensionUri, 'dist', 'webview.css')
    );
    const nonce = crypto.randomBytes(16).toString('hex');

    return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta
      http-equiv="Content-Security-Policy"
      content="default-src 'none'; script-src 'nonce-${nonce}'; style-src ${webview.cspSource} 'unsafe-inline';"
    />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Ralph Wiggum</title>
    <link rel="stylesheet" href="${webviewCssUri}" />
  </head>
  <body>
    <div id="root"></div>
    <script nonce="${nonce}" src="${webviewJsUri}"></script>
  </body>
</html>`;
  }
}
