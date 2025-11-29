import type { Task } from '../types'
import '../App.css'

const PREVIEW_LIMIT = 350

function previewText(task: Task) {
  const source = (task.notes?.trim() || task.nextStep || '').trim()
  if (!source) return ''
  if (source.length <= PREVIEW_LIMIT) return source
  return `${source.slice(0, PREVIEW_LIMIT)}…`
}

interface TaskListProps {
  tasks: Task[]
  selectedTaskId: string | null
  onSelect: (taskId: string) => void
  loading: boolean
  liveTasks: boolean
  warning?: string | null
}

export function TaskList({
  tasks,
  selectedTaskId,
  onSelect,
  loading,
  liveTasks,
  warning,
}: TaskListProps) {
  return (
    <section className="panel task-panel scroll-panel">
      <header>
        <div>
          <h2>Tasks</h2>
          <p className="subtle">{liveTasks ? 'Live' : 'Stubbed'} data</p>
        </div>
      </header>

      {warning && <p className="warning">{warning}</p>}

      {loading ? (
        <p>Loading tasks…</p>
      ) : tasks.length === 0 ? (
        <p>No tasks available.</p>
      ) : (
        <ul className="task-list">
          {tasks.map((task) => (
            <li
              key={task.rowId}
              className={
                selectedTaskId === task.rowId ? 'task-item selected' : 'task-item'
              }
              onClick={() => onSelect(task.rowId)}
            >
              <div className="task-title">{task.title}</div>
              <div className="task-meta">
                <span>{task.project}</span>
                <span>{task.priority}</span>
                <span>{new Date(task.due).toLocaleDateString()}</span>
              </div>
              <p>{previewText(task)}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

