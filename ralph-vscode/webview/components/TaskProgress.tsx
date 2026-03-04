import * as React from 'react';

export interface TaskProgressProps {
  taskData: object | null;
}

interface Task {
  id: string;
  title: string;
  status: 'pending' | 'in_progress' | 'completed' | 'blocked' | string;
}

function getTasks(taskData: object | null): Task[] {
  if (!taskData) return [];
  const data = taskData as Record<string, unknown>;
  if (!Array.isArray(data['tasks'])) return [];
  return data['tasks'] as Task[];
}

const STATUS_ICON: Record<string, string> = {
  completed: '✓',
  in_progress: '◷',
  blocked: '✗',
  pending: '○',
};

export function TaskProgress({ taskData }: TaskProgressProps) {
  const tasks = getTasks(taskData);
  const total = tasks.length;
  const completed = tasks.filter(t => t.status === 'completed').length;
  const percent = total > 0 ? (completed / total) * 100 : 0;

  return (
    <div className="flex flex-col h-full overflow-hidden border-r border-[var(--vscode-panel-border,var(--vscode-editorGroup-border))]">
      {/* Header with progress bar */}
      <div className="flex-shrink-0 px-3 py-2 border-b border-[var(--vscode-panel-border,var(--vscode-editorGroup-border))]">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs font-semibold uppercase tracking-wide"
            style={{ color: 'var(--vscode-descriptionForeground)' }}>
            Tasks
          </span>
          <span className="text-xs" style={{ color: 'var(--vscode-descriptionForeground)' }}>
            {completed}/{total}
          </span>
        </div>
        <div className="h-1.5 rounded-full overflow-hidden"
          style={{ background: 'var(--vscode-editor-background)', border: '1px solid var(--vscode-panel-border, var(--vscode-editorGroup-border))' }}>
          <div className="h-full transition-all duration-300 ease-out"
            style={{ width: `${percent}%`, background: 'var(--vscode-charts-green)' }} />
        </div>
      </div>

      {/* Scrollable task list */}
      <div className="flex-1 overflow-y-auto">
        {total === 0 ? (
          <p className="px-3 py-3 text-xs" style={{ color: 'var(--vscode-descriptionForeground)' }}>
            Run <code>interview</code> or <code>comment</code> to generate tasks.
          </p>
        ) : (
          <ul className="list-none m-0 p-0">
            {tasks.map(task => (
              <li key={task.id}
                className="flex items-start gap-1.5 px-3 py-1.5 text-xs border-b border-[var(--vscode-panel-border,var(--vscode-editorGroup-border))] last:border-0">
                <span className="flex-shrink-0 mt-px" style={{ color: 'var(--vscode-descriptionForeground)' }}>
                  {STATUS_ICON[task.status] ?? '○'}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="truncate">{task.title}</div>
                  <div className="flex items-center gap-1 mt-0.5">
                    <span className="font-mono" style={{ color: 'var(--vscode-descriptionForeground)' }}>{task.id}</span>
                    <span className={`task-status-chip ${task.status}`}>{task.status}</span>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
