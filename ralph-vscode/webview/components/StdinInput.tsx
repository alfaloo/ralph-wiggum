import * as React from 'react';
import { Button } from './ui/button';

export interface StdinInputProps {
  isInterviewMode: boolean;
  onSubmit: (text: string) => void;
}

export function StdinInput({ isInterviewMode, onSubmit }: StdinInputProps) {
  const [value, setValue] = React.useState('');

  React.useEffect(() => {
    if (isInterviewMode) setValue('');
  }, [isInterviewMode]);

  if (!isInterviewMode) return null;

  function handleSubmit() {
    onSubmit(value);
    setValue('');
  }

  return (
    <div className="flex-shrink-0 border-t border-[var(--vscode-panel-border,var(--vscode-editorGroup-border))] px-3 py-2">
      <p className="text-xs italic mb-2" style={{ color: 'var(--vscode-descriptionForeground)' }}>
        Interview — type your answers below, then press Submit
      </p>
      <textarea rows={3} value={value} onChange={e => setValue(e.target.value)}
        style={{ width: '100%', resize: 'vertical', marginBottom: 8 }} />
      <Button onClick={handleSubmit}>Submit Answers</Button>
    </div>
  );
}
