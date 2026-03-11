import * as React from 'react';
import { Button } from './ui/button';
import type { InterviewQuestion } from '../app';

const CUSTOM_OPTION = 'Describe yourself...';

export interface StdinInputProps {
  questions: InterviewQuestion[] | null;
  onSubmit: (answers: Array<{ question: string; answer: string }>) => void;
}

interface QuestionState {
  selectedIndex: number;
  customText: string;
}

export function StdinInput({ questions, onSubmit }: StdinInputProps) {
  const [states, setStates] = React.useState<QuestionState[]>([]);

  React.useEffect(() => {
    if (questions) {
      setStates(questions.map(() => ({ selectedIndex: 0, customText: '' })));
    }
  }, [questions]);

  if (!questions || questions.length === 0) return null;

  function setSelected(qi: number, index: number) {
    setStates(prev => prev.map((s, i) => i === qi ? { ...s, selectedIndex: index } : s));
  }

  function setCustom(qi: number, text: string) {
    setStates(prev => prev.map((s, i) => i === qi ? { ...s, customText: text } : s));
  }

  function handleSubmit() {
    const answers = questions!.map((q, qi) => {
      const s = states[qi] ?? { selectedIndex: 0, customText: '' };
      const isCustom = q.options[s.selectedIndex] === CUSTOM_OPTION;
      return { question: q.question, answer: isCustom ? s.customText : q.options[s.selectedIndex] };
    });
    onSubmit(answers);
  }

  return (
    <div className="flex-shrink-0 border-t border-[var(--vscode-panel-border,var(--vscode-editorGroup-border))] overflow-y-auto"
      style={{ maxHeight: '50%' }}>
      <div className="px-3 py-2 flex flex-col gap-4">
        {questions.map((q, qi) => {
          const s = states[qi] ?? { selectedIndex: 0, customText: '' };
          const isCustom = q.options[s.selectedIndex] === CUSTOM_OPTION;
          return (
            <div key={qi}>
              <p className="text-sm font-medium mb-1.5" style={{ color: 'var(--vscode-foreground)' }}>
                {qi + 1}. {q.question}
              </p>
              <div className="flex flex-col gap-0.5 mb-1">
                {q.options.map((opt, oi) => (
                  <div
                    key={oi}
                    onClick={() => setSelected(qi, oi)}
                    className="flex items-center gap-2 px-2 py-0.5 rounded cursor-pointer text-sm"
                    style={{
                      background: oi === s.selectedIndex
                        ? 'var(--vscode-list-activeSelectionBackground)'
                        : 'transparent',
                      color: oi === s.selectedIndex
                        ? 'var(--vscode-list-activeSelectionForeground)'
                        : 'var(--vscode-foreground)',
                    }}
                  >
                    <span style={{ width: '1em', flexShrink: 0, fontFamily: 'monospace' }}>
                      {oi === s.selectedIndex ? '›' : ' '}
                    </span>
                    <span>{opt}</span>
                  </div>
                ))}
              </div>
              {isCustom && (
                <textarea
                  rows={3}
                  autoFocus={qi === 0}
                  value={s.customText}
                  onChange={e => setCustom(qi, e.target.value)}
                  placeholder="Type your custom answer..."
                  className="w-full resize-y text-sm"
                />
              )}
            </div>
          );
        })}
        <div className="pb-1">
          <Button onClick={handleSubmit}>Submit All</Button>
        </div>
      </div>
    </div>
  );
}
