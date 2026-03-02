import * as React from 'react';
import { useState, useEffect, createContext } from 'react';
import * as ReactDOM from 'react-dom';
import { CommandBar } from './components/CommandBar';
import { FlagPanel } from './components/FlagPanel';
import { TaskProgress } from './components/TaskProgress';
import { OutputArea } from './components/OutputArea';
import { StdinInput } from './components/StdinInput';

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
  postMessage: () => {},
});

export interface OutputLine {
  type: 'stdout' | 'stderr' | 'error' | 'user_answer';
  text: string;
}

function App() {
  const [outputLines, setOutputLines] = useState<OutputLine[]>([]);
  const [taskData, setTaskData] = useState<object | null>(null);
  const [isInterviewMode, setIsInterviewMode] = useState(false);
  const [activeCommand, setActiveCommand] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [settings, setSettings] = useState<Record<string, unknown>>({});

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      const msg = event.data;
      switch (msg.type) {
        case 'stdout':
          setOutputLines(lines => [...lines, { type: 'stdout', text: msg.chunk }]);
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
              setTaskData(JSON.parse(msg.content));
            } catch {
              setTaskData(null);
            }
          }
          break;
        case 'settings_update':
          setSettings(msg.settings);
          break;
        case 'ralph_not_found':
          setOutputLines(lines => [
            ...lines,
            {
              type: 'error',
              text: 'ralph not found on PATH. Please install the ralph CLI and ensure it is on your PATH.',
            },
          ]);
          break;
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, []);

  const handleRun = (cmd: string, args: string[]) => {
    setIsRunning(true);
    setActiveCommand(null);
    vscode.postMessage({ type: 'run_command', command: cmd, args });
  };

  const handleStop = () => {
    vscode.postMessage({ type: 'stop_command' });
  };

  const handleStdinSubmit = (text: string) => {
    setOutputLines(lines => [...lines, { type: 'user_answer', text }]);
    vscode.postMessage({ type: 'stdin_input', text });
    setIsInterviewMode(false);
  };

  const handleClearOutput = () => {
    setOutputLines([]);
  };

  return (
    <VscodeContext.Provider value={{ postMessage: vscode.postMessage.bind(vscode) }}>
      <CommandBar
        activeCommand={activeCommand}
        isRunning={isRunning}
        onCommandSelect={setActiveCommand}
        onStop={handleStop}
        onRun={handleRun}
      />
      <FlagPanel
        activeCommand={activeCommand}
        settings={settings}
        isRunning={isRunning}
        onRun={handleRun}
      />
      <TaskProgress taskData={taskData} />
      <OutputArea outputLines={outputLines} onClear={handleClearOutput} />
      <StdinInput isInterviewMode={isInterviewMode} onSubmit={handleStdinSubmit} />
    </VscodeContext.Provider>
  );
}

ReactDOM.render(<App />, document.getElementById('root'));
