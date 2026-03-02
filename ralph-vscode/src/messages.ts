// Messages from Extension Host to Webview

export interface StdoutMessage {
  type: 'stdout';
  chunk: string;
}

export interface StderrMessage {
  type: 'stderr';
  chunk: string;
}

export interface ProcessDoneMessage {
  type: 'process_done';
  exitCode: number;
}

export interface ProcessStartedMessage {
  type: 'process_started';
}

export interface StdinReadyMessage {
  type: 'stdin_ready';
}

export interface ShowConfirmMessage {
  type: 'show_confirm';
  message: string;
}

export interface StateUpdateMessage {
  type: 'state_update';
  file: 'tasks' | 'validation' | 'spec';
  projectName: string;
  content: string;
}

export interface SettingsUpdateMessage {
  type: 'settings_update';
  settings: Record<string, unknown>;
}

export interface RalphNotFoundMessage {
  type: 'ralph_not_found';
}

export type ExtensionToWebviewMessage =
  | StdoutMessage
  | StderrMessage
  | ProcessDoneMessage
  | ProcessStartedMessage
  | StdinReadyMessage
  | ShowConfirmMessage
  | StateUpdateMessage
  | SettingsUpdateMessage
  | RalphNotFoundMessage;

// Messages from Webview to Extension Host

export interface RunCommandMessage {
  type: 'run_command';
  command: string;
  args: string[];
}

export interface StdinInputMessage {
  type: 'stdin_input';
  text: string;
}

export interface StopCommandMessage {
  type: 'stop_command';
}

export interface OpenUrlMessage {
  type: 'open_url';
  url: string;
}

export type WebviewToExtensionMessage =
  | RunCommandMessage
  | StdinInputMessage
  | StopCommandMessage
  | OpenUrlMessage;
