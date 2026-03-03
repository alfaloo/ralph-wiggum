import * as React from 'react';

export interface StdinInputProps {
  isInterviewMode: boolean;
  onSubmit: (text: string) => void;
}

export function StdinInput({ isInterviewMode, onSubmit }: StdinInputProps): React.ReactElement | null {
  const [value, setValue] = React.useState('');

  // Reset textarea whenever interview mode becomes active
  React.useEffect(() => {
    if (isInterviewMode) {
      setValue('');
    }
  }, [isInterviewMode]);

  if (!isInterviewMode) {
    return null;
  }

  function handleSubmit() {
    onSubmit(value);
    setValue('');
  }

  return (
    <div className="stdin-input">
      <div className="stdin-input-header">
        Interview — type your answers below, then press Submit
      </div>
      <textarea
        className="stdin-input-textarea"
        rows={4}
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <button className="btn" onClick={handleSubmit}>
        Submit Answers
      </button>
    </div>
  );
}
