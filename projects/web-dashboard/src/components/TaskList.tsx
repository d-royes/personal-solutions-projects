import { useMemo, useState, useCallback } from 'react'
import type { Task, WorkBadge, FirestoreTask } from '../types'
import type { AuthConfig } from '../auth/AuthContext'
import { deriveDomain, PRIORITY_ORDER } from '../utils/domain'
import { TaskCreateModal } from './TaskCreateModal'
import { TaskDetailModal } from './TaskDetailModal'
import { triggerSync } from '../api'
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

// Status category for Firestore tasks (lowercase values)
const FS_STATUS_CATEGORY: Record<string, number> = {
  'in_progress': 1, 'follow_up': 1, 'delivered': 1,                          // A - Active
  'on_hold': 2, 'awaiting_reply': 2, 'needs_approval': 2, 'blocked': 2,     // B - Blocked
  'scheduled': 3, 'recurring': 3, 'validation': 3, 'pending': 3,            // S - Scheduled
}

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'needs_attention', label: 'Needs attention' },
  { id: 'personal', label: 'Personal' },
  { id: 'church', label: 'Church' },
  { id: 'work', label: 'Work' },
  { id: 'data_tasks', label: 'DATA Tasks' },
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

// Parse date string and normalize to local midnight for accurate day comparisons
function toLocalMidnight(dateStr: string): Date {
  // Parse as local date by splitting the date string (avoids UTC interpretation)
  const [year, month, day] = dateStr.split('T')[0].split('-').map(Number)
  return new Date(year, month - 1, day, 0, 0, 0, 0)
}

function getTodayMidnight(): Date {
  const now = new Date()
  return new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0, 0)
}

function isDueSoon(due: string) {
  const dueDate = toLocalMidnight(due)
  const today = getTodayMidnight()
  const diff = dueDate.getTime() - today.getTime()
  const days = diff / (1000 * 60 * 60 * 24)
  // Only tasks due within the next 3 days (not overdue)
  return days >= 0 && days <= 3
}

function dueLabel(due: string) {
  const dueDate = toLocalMidnight(due)
  const today = getTodayMidnight()
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
  // Phase 1f: New Firestore integration props
  auth?: AuthConfig | null  // For API calls
  baseUrl?: string
  onTaskCreated?: () => void  // Refresh after task creation
  onTaskUpdated?: () => void  // Refresh after task update
  onTaskDeleted?: () => void  // Refresh after task deletion
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
  // Phase 1f props
  auth,
  baseUrl,
  onTaskCreated,
  onTaskUpdated,
  onTaskDeleted,
}: TaskListProps) {
  const [filter, setFilter] = useState('all')
  const [searchTerm, setSearchTerm] = useState('')
  
  // Phase 1f: Modal state
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [selectedFirestoreTask, setSelectedFirestoreTask] = useState<FirestoreTask | null>(null)
  const [showDetailModal, setShowDetailModal] = useState(false)
  
  // Sync state
  const [syncing, setSyncing] = useState(false)
  const [lastSyncResult, setLastSyncResult] = useState<{ created: number; updated: number } | null>(null)
  
  // Handle sync with Smartsheet
  const handleSync = useCallback(async () => {
    if (!auth || syncing) return
    
    setSyncing(true)
    setLastSyncResult(null)
    try {
      const result = await triggerSync(
        { direction: 'bidirectional' },
        auth,
        baseUrl
      )
      setLastSyncResult({ created: result.created, updated: result.updated })
      // Refresh task list after sync
      if (onLoadEmailTasks) onLoadEmailTasks()
    } catch (err) {
      console.error('Sync failed:', err)
    } finally {
      setSyncing(false)
    }
  }, [auth, syncing, baseUrl, onLoadEmailTasks])
  
  // Load email tasks when that filter is selected
  const handleFilterChange = (filterId: string) => {
    setFilter(filterId)
    if (filterId === 'data_tasks' && onLoadEmailTasks && emailTasks.length === 0) {
      onLoadEmailTasks()
    }
  }
  
  // Phase 1f: Handle Firestore task click
  const handleFirestoreTaskClick = useCallback((task: FirestoreTask) => {
    setSelectedFirestoreTask(task)
    setShowDetailModal(true)
  }, [])
  
  // Phase 1f: Handle task creation
  const handleTaskCreated = useCallback(() => {
    setShowCreateModal(false)
    if (onTaskCreated) onTaskCreated()
    if (onLoadEmailTasks) onLoadEmailTasks() // Refresh Firestore tasks
  }, [onTaskCreated, onLoadEmailTasks])
  
  // Phase 1f: Handle task update
  const handleTaskUpdated = useCallback(() => {
    setShowDetailModal(false)
    setSelectedFirestoreTask(null)
    if (onTaskUpdated) onTaskUpdated()
    if (onLoadEmailTasks) onLoadEmailTasks() // Refresh Firestore tasks
  }, [onTaskUpdated, onLoadEmailTasks])
  
  // Phase 1f: Handle task deletion
  const handleTaskDeleted = useCallback(() => {
    setShowDetailModal(false)
    setSelectedFirestoreTask(null)
    if (onTaskDeleted) onTaskDeleted()
    if (onLoadEmailTasks) onLoadEmailTasks() // Refresh Firestore tasks
  }, [onTaskDeleted, onLoadEmailTasks])

  const filteredTasks = useMemo(() => {
    const filtered = tasks.filter((task) => {
      // First apply search filter if there's a search term
      if (searchTerm.trim()) {
        const term = searchTerm.toLowerCase()
        const matchesSearch =
          (task.title?.toLowerCase()?.includes(term)) ||
          (task.notes?.toLowerCase()?.includes(term)) ||
          (task.project?.toLowerCase()?.includes(term)) ||
          (task.nextStep?.toLowerCase()?.includes(term)) ||
          (task.automationHint?.toLowerCase()?.includes(term)) ||
          (task.assignedTo?.toLowerCase()?.includes(term)) ||
          (task.status?.toLowerCase()?.includes(term))
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
        case 'data_tasks':
          // DATA tasks are handled separately, not in this filter
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
          <div className="search-container">
            <input
              type="text"
              className="task-search"
              placeholder="Search..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
            {searchTerm && (
              <button
                className="search-clear"
                onClick={() => setSearchTerm('')}
                title="Clear search"
                type="button"
              >
                ×
              </button>
            )}
          </div>
          {/* Phase 1f: New Task button */}
          {auth && (
            <button
              className="primary new-task-btn"
              onClick={() => setShowCreateModal(true)}
              title="Create new task"
            >
              + New Task
            </button>
          )}
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

      {/* DATA Tasks Filter - Show Firestore tasks */}
      {filter === 'data_tasks' ? (
        <>
          {/* Sync controls for DATA Tasks */}
          {auth && (
            <div className="data-tasks-sync-bar">
              <button
                className="secondary sync-btn"
                onClick={handleSync}
                disabled={syncing}
                title="Sync tasks with Smartsheet"
              >
                {syncing ? '↻ Syncing...' : '↻ Sync with Smartsheet'}
              </button>
              {lastSyncResult && (
                <span className="sync-result">
                  Created: {lastSyncResult.created}, Updated: {lastSyncResult.updated}
                </span>
              )}
            </div>
          )}
          {emailTasksLoading ? (
            <p>Loading DATA tasks…</p>
          ) : emailTasks.filter(t => {
            // Filter out completed tasks
            if (t.done || t.status === 'completed') return false
            // Apply search filter if there's a search term
            if (searchTerm.trim()) {
              const term = searchTerm.toLowerCase()
              return (
                t.title?.toLowerCase()?.includes(term) ||
                t.notes?.toLowerCase()?.includes(term) ||
                t.project?.toLowerCase()?.includes(term) ||
                t.status?.toLowerCase()?.includes(term) ||
                t.priority?.toLowerCase()?.includes(term)
              )
            }
            return true
          }).length === 0 ? (
            <p className="empty-state">{searchTerm.trim() ? 'No tasks match your search.' : 'No active tasks. Create tasks from emails or click "+ New Task" above.'}</p>
          ) : (
            <ul className="task-list">
            {emailTasks.filter(t => {
              // Filter out completed tasks
              if (t.done || t.status === 'completed') return false
              // Apply search filter if there's a search term
              if (searchTerm.trim()) {
                const term = searchTerm.toLowerCase()
                return (
                  t.title?.toLowerCase()?.includes(term) ||
                  t.notes?.toLowerCase()?.includes(term) ||
                  t.project?.toLowerCase()?.includes(term) ||
                  t.status?.toLowerCase()?.includes(term) ||
                  t.priority?.toLowerCase()?.includes(term)
                )
              }
              return true
            }).sort((a, b) => {
              // Sort: Due Date → Priority → Status Category (same as Smartsheet tasks)
              // 1. Due Date (earliest first)
              const dateA = a.plannedDate || a.dueDate || '9999-12-31'
              const dateB = b.plannedDate || b.dueDate || '9999-12-31'
              const dueDiff = new Date(dateA).getTime() - new Date(dateB).getTime()
              if (dueDiff !== 0) return dueDiff

              // 2. Priority (highest first: Critical > Urgent > Important > Standard > Low)
              const priorityA = PRIORITY_ORDER[a.priority ?? ''] ?? 99
              const priorityB = PRIORITY_ORDER[b.priority ?? ''] ?? 99
              if (priorityA !== priorityB) return priorityA - priorityB

              // 3. Status category (Active > Blocked > Scheduled)
              const statusA = FS_STATUS_CATEGORY[a.status ?? ''] ?? 99
              const statusB = FS_STATUS_CATEGORY[b.status ?? ''] ?? 99
              return statusA - statusB
            }).map((task) => {
              const domain = task.domain.charAt(0).toUpperCase() + task.domain.slice(1)
              const status = task.status ?? 'pending'
              const dueText = (task.plannedDate || task.dueDate) 
                ? dueLabel(task.plannedDate || task.dueDate || '')
                : 'No due date'
              const sourceIcon = task.source === 'email' ? '📧' : '📝'
              return (
                <li
                  key={task.id}
                  className={
                    selectedFirestoreTask?.id === task.id ? 'task-item selected' : 'task-item'
                  }
                  onClick={() => handleFirestoreTaskClick(task)}
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
                    <span className="badge source" title={task.source}>{sourceIcon}</span>
                    {task.isOverdue && (
                      <span className="badge overdue" title="Overdue">⚠️</span>
                    )}
                    {task.timesRescheduled > 0 && (
                      <span className="badge slippage" title={`Rescheduled ${task.timesRescheduled}x`}>
                        ⏳{task.timesRescheduled}
                      </span>
                    )}
                    {task.isRecurring && (
                      <span className="badge recurring" title={`Recurring: ${task.recurringType || 'Yes'}`}>🔄</span>
                    )}
                    {task.syncStatus === 'orphaned' && (
                      <span className="badge orphaned" title="Orphaned - deleted from Smartsheet">🔗✕</span>
                    )}
                    {task.syncStatus === 'synced' && (
                      <span className="badge synced" title="Synced with Smartsheet">✓</span>
                    )}
                  </div>
                  <div className="task-title-row">
                    {task.syncStatus === 'orphaned' && (
                      <span className="orphaned-icon" title={task.attentionReason || 'Deleted from Smartsheet - needs decision'}>
                        🔗✕
                      </span>
                    )}
                    <div className="task-title">{task.title}</div>
                    {task.done && <span className="done-indicator">✓ Done</span>}
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
          )}
        </>
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
      
      {/* Phase 1f: Task Create Modal */}
      {auth && (
        <TaskCreateModal
          isOpen={showCreateModal}
          onClose={() => setShowCreateModal(false)}
          onTaskCreated={handleTaskCreated}
          auth={auth}
          baseUrl={baseUrl}
        />
      )}
      
      {/* Phase 1f: Task Detail Modal */}
      {auth && (
        <TaskDetailModal
          task={selectedFirestoreTask}
          isOpen={showDetailModal}
          onClose={() => {
            setShowDetailModal(false)
            setSelectedFirestoreTask(null)
          }}
          onTaskUpdated={handleTaskUpdated}
          onTaskDeleted={handleTaskDeleted}
          auth={auth}
          baseUrl={baseUrl}
        />
      )}
    </section>
  )
}

