import * as React from 'react';

export interface OutputLine {
  type: 'stdout' | 'stderr' | 'error' | 'user_answer';
  text: string;
}

export interface OutputAreaProps {
  outputLines: OutputLine[];
  onClear: () => void;
}

// Stub — full implementation in T9
export function OutputArea(_props: OutputAreaProps): React.ReactElement {
  return <div className="output-area" />;
}
