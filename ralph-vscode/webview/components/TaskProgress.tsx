import * as React from 'react';

export interface TaskProgressProps {
  taskData: object | null;
}

// Stub — full implementation in T10
export function TaskProgress(_props: TaskProgressProps): React.ReactElement {
  return <div className="task-progress" />;
}
