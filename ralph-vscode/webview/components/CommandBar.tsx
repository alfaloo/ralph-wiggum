import * as React from 'react';

export interface CommandBarProps {
  activeCommand: string | null;
  isRunning: boolean;
  onCommandSelect: (cmd: string) => void;
  onStop: () => void;
  onRun: (cmd: string, args: string[]) => void;
}

// Stub — full implementation in T8
export function CommandBar(_props: CommandBarProps): React.ReactElement {
  return <div className="command-bar" />;
}
