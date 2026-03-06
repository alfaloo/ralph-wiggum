import * as React from 'react';
import { useState } from 'react';
import { Button } from './ui/button';
import { CommandDialog } from './CommandDialog';

export interface CommandBarProps {
  isRunning: boolean;
  settings: Record<string, unknown>;
  commandEnabled: Record<string, boolean>;
  onRun: (cmd: string, args: string[]) => void;
  onStop: () => void;
}

const COMMANDS = [
  'interview', 'comment', 'enrich', 'execute', 'status',
  'retry', 'undo', 'oneshot', 'pr', 'validate',
];

export function CommandBar({ isRunning, settings, commandEnabled, onRun, onStop }: CommandBarProps) {
  const [selectedCmd, setSelectedCmd] = useState<string | null>(null);

  const handleClick = (cmd: string) => {
    if (cmd === 'status') {
      onRun('status', []);
    } else {
      setSelectedCmd(cmd);
    }
  };

  const handleRun = (cmd: string, args: string[]) => {
    setSelectedCmd(null);
    onRun(cmd, args);
  };

  return (
    <>
      <div className="flex-shrink-0 flex flex-wrap items-center gap-1.5 px-3 py-2 border-b border-[var(--vscode-panel-border,var(--vscode-editorGroup-border))]">
        {isRunning ? (
          <Button variant="stop" onClick={onStop}>■ Stop</Button>
        ) : (
          COMMANDS.map(cmd => (
            <Button
              key={cmd}
              size="sm"
              disabled={!(commandEnabled[cmd] ?? true)}
              onClick={() => handleClick(cmd)}
              style={cmd === 'undo' ? {
                color: 'var(--vscode-charts-orange, var(--vscode-editorWarning-foreground))',
                borderLeft: '2px solid var(--vscode-editorWarning-foreground)',
              } : undefined}
            >
              {cmd === 'undo' ? '⚠ undo' : cmd}
            </Button>
          ))
        )}
      </div>
      <CommandDialog
        command={selectedCmd}
        settings={settings}
        onClose={() => setSelectedCmd(null)}
        onRun={handleRun}
      />
    </>
  );
}
