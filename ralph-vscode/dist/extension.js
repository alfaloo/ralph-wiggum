"use strict";
var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/extension.ts
var extension_exports = {};
__export(extension_exports, {
  activate: () => activate,
  deactivate: () => deactivate
});
module.exports = __toCommonJS(extension_exports);
var vscode5 = __toESM(require("vscode"));
var fs4 = __toESM(require("fs"));
var path4 = __toESM(require("path"));
var import_child_process2 = require("child_process");

// src/sidebarProvider.ts
var vscode = __toESM(require("vscode"));
var fs = __toESM(require("fs"));
var path = __toESM(require("path"));
var ProjectItem = class extends vscode.TreeItem {
  constructor(label, description, command, iconPath) {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.label = label;
    this.description = description;
    this.command = command;
    this.iconPath = iconPath;
    this.description = description;
    this.command = command;
    this.iconPath = iconPath;
  }
};
var RalphSidebarProvider = class {
  constructor(workspaceRoot, context) {
    this.workspaceRoot = workspaceRoot;
    this._onDidChangeTreeData = new vscode.EventEmitter();
    this.onDidChangeTreeData = this._onDidChangeTreeData.event;
    const tasksWatcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(workspaceRoot, ".ralph/*/tasks.json")
    );
    tasksWatcher.onDidChange(() => this.refresh());
    tasksWatcher.onDidCreate(() => this.refresh());
    tasksWatcher.onDidDelete(() => this.refresh());
    context.subscriptions.push(tasksWatcher);
    const dirWatcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(workspaceRoot, ".ralph/*")
    );
    dirWatcher.onDidCreate(() => this.refresh());
    dirWatcher.onDidDelete(() => this.refresh());
    context.subscriptions.push(dirWatcher);
  }
  refresh() {
    this._onDidChangeTreeData.fire();
  }
  getTreeItem(element) {
    return element;
  }
  getChildren() {
    const items = [];
    const newProjectItem = new ProjectItem(
      "New Project",
      "",
      {
        command: "ralph.newProject",
        title: "New Project"
      },
      new vscode.ThemeIcon("add")
    );
    items.push(newProjectItem);
    const ralphDir = path.join(this.workspaceRoot, ".ralph");
    if (!fs.existsSync(ralphDir)) {
      return items;
    }
    let entries;
    try {
      entries = fs.readdirSync(ralphDir, { withFileTypes: true });
    } catch {
      return items;
    }
    for (const entry of entries) {
      if (!entry.isDirectory()) {
        continue;
      }
      const firstChar = entry.name[0];
      if (!firstChar || !/[a-zA-Z]/.test(firstChar)) {
        continue;
      }
      const specPath = path.join(ralphDir, entry.name, "spec.md");
      if (!fs.existsSync(specPath)) {
        continue;
      }
      const projectName = entry.name;
      const status = this.computeStatus(ralphDir, projectName);
      const projectItem = new ProjectItem(
        projectName,
        status,
        {
          command: "ralph.openProject",
          title: "Open",
          arguments: [projectName]
        }
      );
      items.push(projectItem);
    }
    return items;
  }
  computeStatus(ralphDir, projectName) {
    const tasksPath = path.join(ralphDir, projectName, "tasks.json");
    if (!fs.existsSync(tasksPath)) {
      return "pending";
    }
    let content;
    try {
      content = fs.readFileSync(tasksPath, "utf8");
    } catch {
      return "pending";
    }
    let parsed;
    try {
      parsed = JSON.parse(content);
    } catch {
      return "pending";
    }
    if (!parsed || typeof parsed !== "object") {
      return "pending";
    }
    const obj = parsed;
    if (!Array.isArray(obj["tasks"]) || obj["tasks"].length === 0) {
      return "pending";
    }
    const tasks = obj["tasks"];
    if (tasks.some((t) => t.status === "in_progress")) {
      return "in_progress";
    }
    if (tasks.every((t) => t.status === "completed")) {
      return "completed";
    }
    if (tasks.some((t) => t.status === "blocked") && !tasks.some((t) => t.status === "in_progress")) {
      return "failed";
    }
    return "pending";
  }
};

// src/panelManager.ts
var vscode2 = __toESM(require("vscode"));
var fs2 = __toESM(require("fs"));
var path2 = __toESM(require("path"));
var crypto = __toESM(require("crypto"));
var OPEN_PANELS_KEY = "ralph.openPanels";
var RalphPanelManager = class {
  constructor(context, extensionUri, workspaceRoot) {
    this.context = context;
    this.extensionUri = extensionUri;
    this.workspaceRoot = workspaceRoot;
    this.panels = /* @__PURE__ */ new Map();
  }
  openPanel(projectName) {
    const existing = this.panels.get(projectName);
    if (existing) {
      existing.reveal(vscode2.ViewColumn.One);
      this.postSettings(projectName, existing);
      return existing;
    }
    const panel = vscode2.window.createWebviewPanel(
      "ralph.panel",
      projectName,
      vscode2.ViewColumn.One,
      {
        enableScripts: true,
        localResourceRoots: [vscode2.Uri.joinPath(this.extensionUri, "dist")]
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
    return panel;
  }
  postSettings(projectName, panel) {
    try {
      const settingsPath = path2.join(this.workspaceRoot, ".ralph", projectName, "settings.json");
      const content = fs2.readFileSync(settingsPath, "utf-8");
      const settings = JSON.parse(content);
      panel.webview.postMessage({ type: "settings_update", settings });
    } catch {
    }
  }
  getPanel(projectName) {
    return this.panels.get(projectName);
  }
  disposePanel(projectName) {
    const panel = this.panels.get(projectName);
    if (panel) {
      panel.dispose();
    }
  }
  restorePanels() {
    const openPanels = this.context.workspaceState.get(OPEN_PANELS_KEY, []);
    for (const projectName of openPanels) {
      this.openPanel(projectName);
    }
  }
  persistOpenPanels() {
    const openPanelNames = Array.from(this.panels.keys());
    this.context.workspaceState.update(OPEN_PANELS_KEY, openPanelNames);
  }
  getHtmlForWebview(webview) {
    const webviewJsUri = webview.asWebviewUri(
      vscode2.Uri.joinPath(this.extensionUri, "dist", "webview.js")
    );
    const nonce = crypto.randomBytes(16).toString("hex");
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
};

// src/processManager.ts
var vscode3 = __toESM(require("vscode"));
var import_child_process = require("child_process");
var YN_PATTERNS = [
  /already exists\. Overwrite\? \(y\/n\):/,
  /Delete branch '.*'\. This cannot be undone\. \(y\/n\):/
];
function resolveShellPath() {
  const home = process.env.HOME || "";
  const commonPaths = [
    `${home}/.local/bin`,
    "/opt/homebrew/bin",
    "/opt/homebrew/sbin",
    "/usr/local/bin"
  ];
  let shellPath = process.env.PATH || "";
  try {
    const shell = process.env.SHELL || "/bin/zsh";
    shellPath = (0, import_child_process.execSync)(
      `${shell} -l -c 'source ~/.zshrc 2>/dev/null; echo $PATH'`,
      { encoding: "utf8", timeout: 5e3 }
    ).trim();
  } catch {
  }
  return [...commonPaths, shellPath].join(":");
}
var RalphProcessManager = class {
  constructor(workspaceRoot) {
    this.processes = /* @__PURE__ */ new Map();
    this.workspaceRoot = workspaceRoot;
    this.shellPath = resolveShellPath();
  }
  run(projectName, command, args, panel) {
    if (this.isRunning(projectName)) {
      return;
    }
    const child = (0, import_child_process.spawn)("ralph", [command, projectName, ...args], {
      cwd: this.workspaceRoot,
      shell: false,
      env: { ...process.env, PATH: this.shellPath }
    });
    this.processes.set(projectName, child);
    panel.webview.postMessage({ type: "process_started" });
    child.stdout.on("data", (chunk) => {
      const text = chunk.toString();
      panel.webview.postMessage({ type: "stdout", chunk: text });
      if (text.includes("Type your answers below")) {
        panel.webview.postMessage({ type: "stdin_ready" });
      }
      for (const line of text.split("\n")) {
        this.handleYNPrompt(line, projectName);
      }
    });
    child.stderr.on("data", (chunk) => {
      panel.webview.postMessage({ type: "stderr", chunk: chunk.toString() });
    });
    child.on("close", (exitCode) => {
      panel.webview.postMessage({ type: "process_done", exitCode });
      this.processes.delete(projectName);
    });
    child.on("error", (err) => {
      if (err.code === "ENOENT") {
        panel.webview.postMessage({ type: "ralph_not_found" });
      }
    });
  }
  stop(projectName) {
    const child = this.processes.get(projectName);
    if (child) {
      child.kill("SIGTERM");
    }
  }
  isRunning(projectName) {
    return this.processes.has(projectName);
  }
  writeToStdin(projectName, text) {
    const child = this.processes.get(projectName);
    if (child && child.stdin) {
      child.stdin.write(text);
    }
  }
  handleYNPrompt(line, projectName) {
    for (const pattern of YN_PATTERNS) {
      if (pattern.test(line)) {
        vscode3.window.showInformationMessage(line, "Yes", "No").then((choice) => {
          if (choice !== void 0) {
            this.writeToStdin(projectName, choice === "Yes" ? "y\n" : "n\n");
          }
        });
        return;
      }
    }
  }
};

// src/fileWatcher.ts
var vscode4 = __toESM(require("vscode"));
var fs3 = __toESM(require("fs"));
var path3 = __toESM(require("path"));
function extractProjectName(uri, workspaceRoot) {
  const ralphDir = path3.join(workspaceRoot, ".ralph");
  const filePath = uri.fsPath;
  if (!filePath.startsWith(ralphDir + path3.sep)) {
    return void 0;
  }
  const relative = filePath.slice(ralphDir.length + 1);
  const parts = relative.split(path3.sep);
  if (parts.length < 2) {
    return void 0;
  }
  return parts[0];
}
function readFileContent(uri) {
  try {
    return fs3.readFileSync(uri.fsPath, "utf8");
  } catch {
    return "";
  }
}
var RalphFileWatcher = class {
  constructor(panelManager, sidebarProvider, workspaceRoot) {
    this.panelManager = panelManager;
    this.sidebarProvider = sidebarProvider;
    this.workspaceRoot = workspaceRoot;
    this.watchers = [];
    const patterns = [
      [".ralph/*/tasks.json", "tasks"],
      [".ralph/*/validation.md", "validation"],
      [".ralph/*/spec.md", "spec"]
    ];
    for (const [pattern, fileType] of patterns) {
      const watcher = vscode4.workspace.createFileSystemWatcher(
        new vscode4.RelativePattern(workspaceRoot, pattern)
      );
      const handler = (uri, deleted = false) => {
        this.handleChange(uri, fileType, deleted);
      };
      watcher.onDidChange((uri) => handler(uri));
      watcher.onDidCreate((uri) => handler(uri));
      watcher.onDidDelete((uri) => handler(uri, true));
      this.watchers.push(watcher);
    }
  }
  handleChange(uri, fileType, deleted) {
    const projectName = extractProjectName(uri, this.workspaceRoot);
    if (!projectName) {
      return;
    }
    const content = deleted ? "" : readFileContent(uri);
    const panel = this.panelManager.getPanel(projectName);
    if (panel) {
      panel.webview.postMessage({
        type: "state_update",
        file: fileType,
        projectName,
        content
      });
    }
    if (fileType === "tasks") {
      this.sidebarProvider.refresh();
    }
  }
  dispose() {
    for (const watcher of this.watchers) {
      watcher.dispose();
    }
    this.watchers.length = 0;
  }
};

// src/extension.ts
var OPEN_PANELS_KEY2 = "ralph.openPanels";
function activate(context) {
  const workspaceRoot = vscode5.workspace.workspaceFolders[0].uri.fsPath;
  const sidebar = new RalphSidebarProvider(workspaceRoot, context);
  const panelManager = new RalphPanelManager(context, context.extensionUri, workspaceRoot);
  const processManager = new RalphProcessManager(workspaceRoot);
  const fileWatcher = new RalphFileWatcher(panelManager, sidebar, workspaceRoot);
  context.subscriptions.push(
    vscode5.window.registerTreeDataProvider("ralph.projectList", sidebar)
  );
  context.subscriptions.push(fileWatcher);
  const wiredPanels = /* @__PURE__ */ new Set();
  function wirePanel(projectName, panel) {
    if (wiredPanels.has(projectName)) {
      return;
    }
    wiredPanels.add(projectName);
    panel.onDidDispose(() => {
      wiredPanels.delete(projectName);
    }, void 0, context.subscriptions);
    panel.webview.onDidReceiveMessage(
      (msg) => {
        switch (msg.type) {
          case "run_command":
            processManager.run(projectName, msg.command, msg.args, panel);
            break;
          case "stdin_input":
            processManager.writeToStdin(projectName, msg.text + "\n");
            break;
          case "stop_command":
            processManager.stop(projectName);
            break;
          case "open_url":
            vscode5.env.openExternal(vscode5.Uri.parse(msg.url));
            break;
        }
      },
      void 0,
      context.subscriptions
    );
  }
  context.subscriptions.push(
    vscode5.commands.registerCommand("ralph.newProject", async () => {
      const name = await vscode5.window.showInputBox({
        prompt: "Enter project name",
        placeHolder: "my-project",
        validateInput(v) {
          if (!v || v.trim() === "") {
            return "Project name cannot be empty";
          }
          if (!/^[a-zA-Z]/.test(v)) {
            return "Project name must begin with a letter";
          }
          if (/[/\\:*?"<>|\x00]/.test(v)) {
            return 'Project name cannot contain /, \\, :, *, ?, ", <, >, or |';
          }
          const projectPath = path4.join(workspaceRoot, ".ralph", v);
          if (fs4.existsSync(projectPath)) {
            return `Project '${v}' already exists`;
          }
          return void 0;
        }
      });
      if (!name) {
        return;
      }
      const channel = vscode5.window.createOutputChannel("Ralph Init");
      channel.show();
      const child = (0, import_child_process2.spawn)("ralph", ["init", name], {
        cwd: workspaceRoot,
        shell: false
      });
      child.stdout.on("data", (chunk) => {
        const text = chunk.toString();
        channel.append(text);
        for (const line of text.split("\n")) {
          if (/Update base branch to '.*'\? \(y\/n\):/.test(line)) {
            vscode5.window.showWarningMessage(line, "Yes", "No").then((choice) => {
              if (choice !== void 0) {
                child.stdin.write(choice === "Yes" ? "y\n" : "n\n");
              }
            });
          }
        }
      });
      child.stderr.on("data", (chunk) => {
        channel.append(chunk.toString());
      });
      child.on("close", async (exitCode) => {
        if (exitCode === 0) {
          sidebar.refresh();
          const panel = panelManager.openPanel(name);
          wirePanel(name, panel);
          const specPath = path4.join(workspaceRoot, ".ralph", name, "spec.md");
          const testInstructionsPath = path4.join(workspaceRoot, ".ralph", name, "test-instructions.md");
          try {
            const specDoc = await vscode5.workspace.openTextDocument(specPath);
            await vscode5.window.showTextDocument(specDoc, { viewColumn: vscode5.ViewColumn.Beside });
          } catch {
          }
          try {
            const testDoc = await vscode5.workspace.openTextDocument(testInstructionsPath);
            await vscode5.window.showTextDocument(testDoc, { viewColumn: vscode5.ViewColumn.Beside });
          } catch {
          }
        }
      });
    })
  );
  context.subscriptions.push(
    vscode5.commands.registerCommand("ralph.openProject", (projectName) => {
      const panel = panelManager.openPanel(projectName);
      wirePanel(projectName, panel);
    })
  );
  const restoredPanelNames = context.workspaceState.get(OPEN_PANELS_KEY2, []);
  panelManager.restorePanels();
  for (const projectName of restoredPanelNames) {
    const panel = panelManager.getPanel(projectName);
    if (panel) {
      wirePanel(projectName, panel);
    }
  }
}
function deactivate() {
}
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  activate,
  deactivate
});
//# sourceMappingURL=extension.js.map
