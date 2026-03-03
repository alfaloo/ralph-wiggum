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

function truncate(text: string, maxLen: number): string {
  return text.length > maxLen ? text.slice(0, maxLen - 1) + '…' : text;
}

export function TaskProgress({ taskData }: TaskProgressProps): React.ReactElement {
  const tasks = getTasks(taskData);
  const total = tasks.length;
  const completed = tasks.filter(t => t.status === 'completed').length;
  const percent = total > 0 ? (completed / total) * 100 : 0;

  return (
    <div className="task-progress">
      <div className="task-progress-header">
        <span>{completed}/{total} tasks complete</span>
      </div>
      <div className="progress-bar-container">
        <div className="progress-bar-fill" style={{ width: `${percent}%` }} />
      </div>
      {total === 0 ? (
        <p style={{ fontSize: '0.85em', color: 'var(--vscode-descriptionForeground)', margin: '4px 0 0 0' }}>
          Run <code>ralph interview</code> or <code>ralph comment</code> to generate the task list.
        </p>
      ) : (
        <ul className="task-list">
          {tasks.map(task => (
            <li key={task.id} className="task-list-item">
              <span className="task-id">{task.id}</span>
              <span className="task-title">{truncate(task.title, 60)}</span>
              <span className={`task-status-chip ${task.status}`}>{task.status}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
