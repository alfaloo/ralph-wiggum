import * as vscode from 'vscode';
import * as crypto from 'crypto';

const OPEN_PANELS_KEY = 'ralph.openPanels';

export class RalphPanelManager {
  private readonly panels = new Map<string, vscode.WebviewPanel>();

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly extensionUri: vscode.Uri
  ) {}

  openPanel(projectName: string): vscode.WebviewPanel {
    const existing = this.panels.get(projectName);
    if (existing) {
      existing.reveal(vscode.ViewColumn.One);
      return existing;
    }

    const panel = vscode.window.createWebviewPanel(
      'ralph.panel',
      projectName,
      vscode.ViewColumn.One,
      {
        enableScripts: true,
        localResourceRoots: [vscode.Uri.joinPath(this.extensionUri, 'dist')],
      }
    );

    panel.webview.html = this.getHtmlForWebview(panel.webview);
    this.panels.set(projectName, panel);
    this.persistOpenPanels();

    panel.onDidDispose(() => {
      this.panels.delete(projectName);
      this.persistOpenPanels();
    });

    return panel;
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
    const nonce = crypto.randomBytes(16).toString('hex');

    return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta
      http-equiv="Content-Security-Policy"
      content="default-src 'none'; script-src 'nonce-${nonce}'; style-src 'unsafe-inline';"
    />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Ralph Wiggum</title>
  </head>
  <body>
    <div id="root"></div>
    <script nonce="${nonce}" src="${webviewJsUri}"></script>
  </body>
</html>`;
  }
}
