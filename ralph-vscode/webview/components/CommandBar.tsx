import * as React from 'react';
import Layout from '../layouts/Layout';

export interface CommandBarProps {
  activeCommand: string | null;
  isRunning: boolean;
  onCommandSelect: (cmd: string) => void;
  onStop: () => void;
  onRun: (cmd: string, args: string[]) => void;
}

const COMMANDS = [
  'interview', 'comment', 'enrich', 'execute', 'status',
  'retry', 'undo', 'oneshot', 'pr', 'validate',
];

export function CommandBar({ activeCommand, isRunning, onCommandSelect, onStop, onRun }: CommandBarProps): React.ReactElement {
  const handleClick = (cmd: string) => {
    if (cmd === 'status') {
      onRun('status', []);
    } else {
      onCommandSelect(cmd);
    }
  };

  if (isRunning) {
    return (
      <div className="command-bar">
        <button className="btn-stop" onClick={onStop}>&#9632; Stop</button>
      </div>
    );
  }

  return (
    <Layout>
      {COMMANDS.map(cmd => (
        <button
          key={cmd}
          className="btn"
          onClick={() => handleClick(cmd)}
          style={
            cmd === 'undo'
              ? {
                color: 'var(--vscode-charts-orange, var(--vscode-editorWarning-foreground))',
                borderLeft: '3px solid var(--vscode-editorWarning-foreground)',
              }
              : activeCommand === cmd
                ? { outline: '1px solid var(--vscode-focusBorder)' }
                : undefined
          }
        >
          {cmd === 'undo' ? '\u26A0 undo' : cmd}
        </button>
      ))}
    </Layout>
  );
}
