import * as React from 'react';
import { useState, useEffect, createContext } from 'react';
import { CommandBar } from './components/CommandBar';
import { TaskProgress } from './components/TaskProgress';
import type { Task } from './components/TaskProgress';
import { OutputArea } from './components/OutputArea';
import type { OutputLine } from './components/OutputArea';
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

export interface InterviewQuestion {
  question: string;
  options: string[];
}

function buildCommandString(cmd: string, args: string[]): string {
  const parts = [`ralph ${cmd}`];
  for (let i = 0; i < args.length; i++) {
    if (args[i + 1] === 'false') { i++; continue; }
    if (args[i + 1] === 'true') { parts.push(args[i]); i++; continue; }
    parts.push(args[i]);
  }
  return parts.join(' ');
}

function App() {
  const [outputLines, setOutputLines] = useState<OutputLine[]>([]);
  const [taskData, setTaskData] = useState<object | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [lastCommand, setLastCommand] = useState<string | null>(null);
  const [fileFlags, setFileFlags] = useState({
    hasTasks: false,
    hasPrDescription: false,
    hasSummary: false,
    hasValidation: false,
  });

  const [interviewQuestions, setInterviewQuestions] = useState<InterviewQuestion[] | null>(null);

  useEffect(() => {
    vscode.postMessage({ type: 'webview_ready' });
  }, []);

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
          setInterviewQuestions(null);
          if (msg.exitCode !== 0) {
            setOutputLines(lines => [
              ...lines,
              { type: 'error', text: `Command exited with code ${msg.exitCode}` },
            ]);
          } else {
            setOutputLines((lines) => {
              if (lines[lines.length - 1]?.text?.includes('agent has started working')) {
                return [
                  ...lines,
                  { type: 'stdout', text: `Command ${lastCommand ?? ''} completed successfully` }
                ];
              }
              return lines;
            });
          }
          break;

        case 'process_started':
          setIsRunning(true);
          break;

        case 'stdin_interview':
          setInterviewQuestions(msg.questions);
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
    setInterviewQuestions(null);

    if (cmd === 'comment') {
      const flagIdx = args.indexOf('--comment');
      const commentText = flagIdx !== -1 ? (args[flagIdx + 1] ?? '') : '';
      setOutputLines(lines => [
        ...lines,
        { type: 'interview_qa' as const, text: '', question: 'Your comment', answer: commentText },
      ]);
    }

    vscode.postMessage({ type: 'run_command', command: cmd, args });
  };

  const handleStop = () => vscode.postMessage({ type: 'stop_command' });

  const handleInterviewSubmit = (answers: Array<{ question: string; answer: string }>) => {
    // Show Q&A summary in output
    setOutputLines(lines => [
      ...lines,
      ...answers.map(a => ({ type: 'interview_qa' as const, text: '', question: a.question, answer: a.answer })),
    ]);
    setInterviewQuestions(null);
    vscode.postMessage({ type: 'submit_interview', answers });
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
    enrich: true,
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
          taskData={taskData}
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
              questions={interviewQuestions}
              onSubmit={handleInterviewSubmit}
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
