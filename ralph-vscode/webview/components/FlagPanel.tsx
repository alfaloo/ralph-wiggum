import * as React from 'react';

export interface FlagPanelProps {
  activeCommand: string | null;
  settings: Record<string, unknown>;
  isRunning: boolean;
  onRun: (cmd: string, args: string[]) => void;
}

// Stub — full implementation in T8
export function FlagPanel(_props: FlagPanelProps): React.ReactElement | null {
  return null;
}
