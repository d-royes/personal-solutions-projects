import { useMemo, useState } from 'react'
import type { Task, WorkBadge, FirestoreTask } from '../types'
import { deriveDomain, PRIORITY_ORDER } from '../utils/domain'
import '../App.css'

const PREVIEW_LIMIT = 240
const BLOCKED_STATUSES = ['On Hold', 'Awaiting Reply', 'Needs Approval']
const URGENT_PRIORITIES = ['Critical', 'Urgent', '5-Critical', '4-Urgent']

// Status category for sorting (A=Active first, B=Blocked second, S=Scheduled last)
const STATUS_CATEGORY: Record<string, number> = {
  'In Progress': 1, 'Follow-up': 1, 'Delivered': 1,                          // A - Active
  'On Hold': 2, 'Awaiting Reply': 2, 'Needs Approval': 2,                    // B - Blocked
  'Scheduled': 3, 'Recurring': 3, 'Validation': 3, 'Create ZD Ticket': 3,   // S - Scheduled
}

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'needs_attention', label: 'Needs attention' },
  { id: 'email_tasks', label: 'Email Tasks' },
  { id: 'personal', label: 'Personal' },
  { id: 'church', label: 'Church' },
  { id: 'work', label: 'Work' },
]

function previewText(task: Task) {
  const textSource =
    (task.nextStep?.trim() || task.automationHint?.trim() || task.notes?.trim() || '')
      .trim()
  if (!textSource) return 'No next step recorded yet.'
  if (textSource.length <= PREVIEW_LIMIT) return textSource
  return `${textSource.slice(0, PREVIEW_LIMIT)}…`
}

// deriveDomain is now imported from '../utils/domain'
// Returns lowercase domain ('personal' | 'church' | 'work')

function isDueSoon(due: string) {
  const dueDate = new Date(due)
  const now = new Date()
  const diff = dueDate.getTime() - now.getTime()
  const days = diff / (1000 * 60 * 60 * 24)
  // Only tasks due within the next 3 days (not overdue)
  return days >= 0 && days <= 3
}

function dueLabel(due: string) {
  const dueDate = new Date(due)
  const today = new Date()
  const diff = dueDate.getTime() - today.getTime()
  const days = Math.round(diff / (1000 * 60 * 60 * 24))
  if (days < 0) return `Overdue ${Math.abs(days)}d`
  if (days === 0) return 'Due today'
  if (days === 1) return 'Due tomorrow'
  return `Due in ${days}d`
}

interface TaskListProps {
  tasks: Task[]
  selectedTaskId: string | null
  onSelect: (taskId: string) => void
  onDeselectAll?: () => void  // Go to Global Mode / Portfolio View
  loading: boolean
  liveTasks: boolean
  warning?: string | null
  onRefresh?: () => void
  refreshing?: boolean
  workBadge?: WorkBadge | null  // Work task counts for badge indicator
  emailTasks?: FirestoreTask[]  // Tasks created from emails (Firestore)
  emailTasksLoading?: boolean
  onLoadEmailTasks?: () => void  // Callback to load email tasks on demand
}

export function TaskList({
  tasks,
  selectedTaskId,
  onSelect,
  onDeselectAll,
  loading,
  liveTasks,
  warning,
  onRefresh,
  refreshing,
  workBadge,
  emailTasks = [],
  emailTasksLoading = false,
  onLoadEmailTasks,
}: TaskListProps) {
  const [filter, setFilter] = useState('all')
  const [searchTerm, setSearchTerm] = useState('')
  
  // Load email tasks when that filter is selected
  const handleFilterChange = (filterId: string) => {
    setFilter(filterId)
    if (filterId === 'email_tasks' && onLoadEmailTasks && emailTasks.length === 0) {
      onLoadEmailTasks()
    }
  }

  const filteredTasks = useMemo(() => {
    const filtered = tasks.filter((task) => {
      // First apply search filter if there's a search term
      if (searchTerm.trim()) {
        const term = searchTerm.toLowerCase()
        const matchesSearch = 
          (task.title?.toLowerCase().includes(term)) ||
          (task.notes?.toLowerCase().includes(term)) ||
          (task.project?.toLowerCase().includes(term))
        if (!matchesSearch) return false
      }
      const domain = deriveDomain(task)
      const status = task.status ?? ''
      switch (filter) {
        case 'needs_attention':
          // Exclude work tasks from "Needs attention" unless explicitly in Work filter
          if (task.source === 'work') return false
          return (
            URGENT_PRIORITIES.includes(task.priority ?? '') ||
            isDueSoon(task.due) ||
            BLOCKED_STATUSES.includes(status)
          )
        case 'email_tasks':
          // Email tasks are handled separately, not in this filter
          return false
        case 'personal':
          return domain === 'personal'
        case 'church':
          return domain === 'church'
        case 'work':
          // Only show work tasks (from work sheet)
          return task.source === 'work'
        default:
          // ALL filter: exclude work tasks (they have their own filter)
          return task.source !== 'work'
      }
    })

    // Sort: Due Date → Priority → Status Category
    return filtered.sort((a, b) => {
      // 1. Due Date (earliest first)
      const dueDiff = new Date(a.due).getTime() - new Date(b.due).getTime()
      if (dueDiff !== 0) return dueDiff

      // 2. Priority (highest first: Critical > Urgent > Important > Standard > Low)
      const priorityA = PRIORITY_ORDER[a.priority ?? ''] ?? 99
      const priorityB = PRIORITY_ORDER[b.priority ?? ''] ?? 99
      if (priorityA !== priorityB) return priorityA - priorityB

      // 3. Status category (Active > Blocked > Scheduled)
      const statusA = STATUS_CATEGORY[a.status ?? ''] ?? 99
      const statusB = STATUS_CATEGORY[b.status ?? ''] ?? 99
      return statusA - statusB
    })
  }, [tasks, filter, searchTerm])

  return (
    <section className="panel task-panel scroll-panel">
      <header>
        <div>
          <h2>Tasks</h2>
          <p className="subtle">
            {liveTasks ? 'Live data' : 'Stubbed data'} · Showing {filteredTasks.length}{' '}
            of {tasks.length}
          </p>
        </div>
        <div className="task-header-buttons">
          <input
            type="text"
            className="task-search"
            placeholder="Search..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          {onDeselectAll && (
            <button
              className="secondary portfolio-btn"
              onClick={onDeselectAll}
              title="View Portfolio Overview"
            >
              📊 Portfolio
            </button>
          )}
          {onRefresh && (
            <button 
              className="secondary refresh-btn" 
              onClick={onRefresh}
              disabled={refreshing || loading}
              title="Refresh tasks"
            >
              {refreshing ? '↻' : '↻'} Refresh
            </button>
          )}
        </div>
      </header>

      {warning && <p className="warning">{warning}</p>}

      <div className="task-filters">
        {FILTERS.map((chip) => {
          // Show badge for Work filter when there are urgent/overdue items
          const showWorkBadge = chip.id === 'work' && workBadge && workBadge.needsAttention > 0
          return (
            <button
              key={chip.id}
              className={`${filter === chip.id ? 'active' : ''} ${showWorkBadge ? 'has-badge' : ''}`}
              onClick={() => handleFilterChange(chip.id)}
            >
              {chip.label}
              {showWorkBadge && (
                <span className="work-badge" title={`${workBadge.needsAttention} work task(s) need attention`}>
                  {workBadge.needsAttention}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* Email Tasks Filter - Show Firestore tasks */}
      {filter === 'email_tasks' ? (
        emailTasksLoading ? (
          <p>Loading email tasks…</p>
        ) : emailTasks.length === 0 ? (
          <p className="empty-state">No email tasks yet. Create tasks from emails using the Email Management view.</p>
        ) : (
          <ul className="task-list">
            {emailTasks.map((task) => {
              const domain = task.domain.charAt(0).toUpperCase() + task.domain.slice(1)
              const status = task.status ?? 'pending'
              const dueText = task.dueDate ? dueLabel(task.dueDate) : 'No due date'
              return (
                <li
                  key={task.id}
                  className={
                    selectedTaskId === task.id ? 'task-item selected' : 'task-item'
                  }
                  onClick={() => onSelect(task.id)}
                >
                  <div className="task-signals">
                    <span className={`badge domain ${domain.toLowerCase()}`}>{domain}</span>
                    <span className="badge status">{status}</span>
                    {task.priority && (
                      <span className={`badge priority ${task.priority.toLowerCase()}`}>
                        {task.priority}
                      </span>
                    )}
                    <span className="badge due">{dueText}</span>
                    <span className="badge source">📧 Email</span>
                  </div>
                  <div className="task-title-row">
                    <div className="task-title">{task.title}</div>
                  </div>
                  <div className="task-meta">
                    <span>{task.project || 'No project'}</span>
                    {task.sourceEmailSubject && (
                      <span title={`From email: ${task.sourceEmailSubject}`}>
                        📨 {task.sourceEmailAccount}
                      </span>
                    )}
                  </div>
                  <p className="task-next">{task.notes || task.nextStep || 'No notes'}</p>
                </li>
              )
            })}
          </ul>
        )
      ) : loading ? (
        <p>Loading tasks…</p>
      ) : filteredTasks.length === 0 ? (
        <p>No tasks match this filter.</p>
      ) : (
        <ul className="task-list">
          {filteredTasks.map((task) => {
            const domain = deriveDomain(task)
            const status = task.status ?? 'Unknown'
            const next = previewText(task)
            return (
              <li
                key={task.rowId}
                className={
                  selectedTaskId === task.rowId ? 'task-item selected' : 'task-item'
                }
                onClick={() => onSelect(task.rowId)}
              >
                <div className="task-signals">
                  <span className={`badge domain ${domain}`}>{domain.charAt(0).toUpperCase() + domain.slice(1)}</span>
                  <span className="badge status">{status}</span>
                  {task.priority && (
                    <span className={`badge priority ${task.priority.toLowerCase()}`}>
                      {task.priority}
                    </span>
                  )}
                  <span className="badge due">{dueLabel(task.due)}</span>
                </div>
                <div className="task-title-row">
                  <div className="task-title">{task.title}</div>
                </div>
                <div className="task-meta">
                  <span>{task.project}</span>
                  {task.assignedTo && <span>Owner: {task.assignedTo}</span>}
                </div>
                <p className="task-next">{next}</p>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

