import * as React from 'react';
import { useState, useEffect, createContext } from 'react';
import { CommandBar } from './components/CommandBar';
import { TaskProgress } from './components/TaskProgress';
import type { Task } from './components/TaskProgress';
import { OutputArea } from './components/OutputArea';
import { StdinInput } from './components/StdinInput';
import { createRoot } from 'react-dom/client';

// VS Code API bridge — acquireVsCodeApi() is injected by the VS Code webview runtime
declare function acquireVsCodeApi(): {
  postMessage(message: unknown): void;
  getState(): unknown;
  setState(state: unknown): void;
};

const vscode = acquireVsCodeApi();

// VS Code context so child components can call vscode.postMessage()
export interface VscodeContextType {
  postMessage: (message: unknown) => void;
}

export const VscodeContext = createContext<VscodeContextType>({
  postMessage: () => { },
});

export interface OutputLine {
  type: 'stdout' | 'stderr' | 'error' | 'user_answer' | 'task_detail';
  text: string;
  task?: Task;
}

function buildCommandString(cmd: string, args: string[]): string {
  const parts = [`ralph ${cmd}`];
  for (let i = 0; i < args.length; i++) {
    if (args[i + 1] === 'false') { i++; continue; }          // skip --flag false
    if (args[i + 1] === 'true') { parts.push(args[i]); i++; continue; } // --flag (omit 'true')
    parts.push(args[i]);
  }
  return parts.join(' ');
}

function App() {
  const [outputLines, setOutputLines] = useState<OutputLine[]>([]);
  const [taskData, setTaskData] = useState<object | null>(null);
  const [isInterviewMode, setIsInterviewMode] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [lastCommand, setLastCommand] = useState<string | null>(null);
  const [fileFlags, setFileFlags] = useState({
    hasTasks: false,
    hasPrDescription: false,
    hasSummary: false,
    hasValidation: false,
  });

  useEffect(() => {
    vscode.postMessage({ type: 'webview_ready' });
  }, []);

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      const msg = event.data;
      switch (msg.type) {
        case 'stdout':
          setOutputLines(lines => {
            // Strip ALL whitespace for echo comparison — PTY wraps at col 120,
            // inserting \r\n mid-word, so trimEnd() comparisons fail.
            const normWS = (s: string) => s.replace(/\s+/g, '');
            const last = lines[lines.length - 1];

            // Merge with previous stdout first, then check (handles multi-chunk echoes)
            const merged = last?.type === 'stdout' ? last.text + msg.chunk : null;
            const candidate = merged ?? msg.chunk;
            const normCandidate = normWS(candidate);

            // Suppress PTY echo and ralph's own answer reprint
            if (normCandidate.length > 20 &&
              lines.some(l => l.type === 'user_answer' && normWS(l.text) === normCandidate)) {
              // Remove the partial accumulated entry if we had started one
              return merged !== null ? lines.slice(0, -1) : lines;
            }

            if (merged !== null) {
              return [...lines.slice(0, -1), { ...last!, text: merged }];
            }
            return [...lines, { type: 'stdout', text: msg.chunk }];
          });
          break;
        case 'stderr':
          setOutputLines(lines => [...lines, { type: 'stderr', text: msg.chunk }]);
          break;
        case 'process_done':
          setIsRunning(false);
          setIsInterviewMode(false);
          if (msg.exitCode !== 0) {
            setOutputLines(lines => [
              ...lines,
              { type: 'error', text: `Command exited with code ${msg.exitCode}` },
            ]);
          } else if (lastCommand?.includes('enrich')) {
            setOutputLines(lines => [
              ...lines,
              { type: 'stdout', text: `Command ${lastCommand ?? ''} completed successfully`}
            ])
          }
          break;
        case 'process_started':
          setIsRunning(true);
          break;
        case 'stdin_ready':
          setIsInterviewMode(true);
          break;
        case 'state_update':
          if (msg.file === 'tasks') {
            try {
              const data = JSON.parse(msg.content);
              setTaskData(data);
              const hasTasks = Array.isArray(data?.tasks) && data.tasks.length > 0;
              setFileFlags(f => ({ ...f, hasTasks }));
            } catch { setTaskData(null); setFileFlags(f => ({ ...f, hasTasks: false })); }
          } else if (msg.file === 'pr_description') {
            setFileFlags(f => ({ ...f, hasPrDescription: !!msg.content?.trim() }));
          } else if (msg.file === 'summary') {
            setFileFlags(f => ({ ...f, hasSummary: !!msg.content?.trim() }));
          } else if (msg.file === 'validation') {
            setFileFlags(f => ({ ...f, hasValidation: !!msg.content?.trim() }));
          }
          break;
        case 'settings_update':
          setSettings(msg.settings);
          break;
        case 'ralph_not_found':
          setOutputLines(lines => [
            ...lines,
            { type: 'error', text: 'ralph not found on PATH. Please install the ralph CLI and ensure it is on your PATH.' },
          ]);
          break;
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [lastCommand]);

  const handleRun = (cmd: string, args: string[]) => {
    setIsRunning(true);
    setLastCommand(buildCommandString(cmd, args));
    vscode.postMessage({ type: 'run_command', command: cmd, args });
  };

  const handleStop = () => vscode.postMessage({ type: 'stop_command' });

  const handleStdinSubmit = (text: string) => {
    setOutputLines(lines => [...lines, { type: 'user_answer', text }]);
    vscode.postMessage({ type: 'stdin_input', text });
    setIsInterviewMode(false);
  };

  const handleTaskClick = (task: Task) => {
    setOutputLines(lines => [...lines, { type: 'task_detail', text: '', task }]);
  };

  const handleClearOutput = () => setOutputLines([]);

  const commandEnabled: Record<string, boolean> = {
    interview: true,
    comment: true,
    oneshot: true,
    status: true,
    enrich: fileFlags.hasTasks,
    execute: fileFlags.hasTasks,
    pr: fileFlags.hasPrDescription,
    validate: fileFlags.hasSummary,
    undo: fileFlags.hasValidation,
    retry: fileFlags.hasValidation,
  };

  return (
    <VscodeContext.Provider value={{ postMessage: vscode.postMessage.bind(vscode) }}>
      <div className="flex flex-col h-full overflow-hidden">
        {/* Top toolbar */}
        <CommandBar
          isRunning={isRunning}
          settings={settings}
          commandEnabled={commandEnabled}
          onRun={handleRun}
          onStop={handleStop}
        />

        {/* Two-column main area */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left: Task progress (~224px) */}
          <div className="w-56 flex-shrink-0 overflow-hidden">
            <TaskProgress taskData={taskData} onTaskClick={handleTaskClick} />
          </div>

          {/* Right: Output + stdin */}
          <div className="flex flex-col flex-1 overflow-hidden">
            <OutputArea
              outputLines={outputLines}
              lastCommand={lastCommand}
              onClear={handleClearOutput}
            />
            <StdinInput
              isInterviewMode={isInterviewMode}
              onSubmit={handleStdinSubmit}
            />
          </div>
        </div>
      </div>
    </VscodeContext.Provider>
  );
}

const container = document.getElementById('root');

if (!container) {
  throw new Error('Root container not found');
}

createRoot(container).render(<App />);
