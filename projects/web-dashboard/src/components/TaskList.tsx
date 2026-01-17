import { useMemo, useState, useCallback } from 'react'
import type { Task, WorkBadge, FirestoreTask } from '../types'
import type { AuthConfig } from '../auth/AuthContext'
import { deriveDomain, PRIORITY_ORDER } from '../utils/domain'
import { TaskCreateModal } from './TaskCreateModal'
import { triggerSync } from '../api'
import { useSettings, type AttentionSignals } from '../contexts/SettingsContext'
import '../App.css'

const PREVIEW_LIMIT = 240

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

// Blocked statuses for Firestore tasks (always trigger attention)
const FS_BLOCKED_STATUSES = ['on_hold', 'awaiting_reply', 'needs_approval', 'blocked']

/**
 * Check if a Firestore task needs attention based on configurable signals.
 * Returns true if any attention signal is triggered.
 */
function needsAttention(task: FirestoreTask, signals: AttentionSignals): boolean {
  // Skip completed tasks
  if (task.done || task.status === 'completed') return false
  
  // Always-on signals (not configurable)
  
  // 1. Orphaned tasks - deleted from Smartsheet
  if (task.syncStatus === 'orphaned') return true
  
  // 2. Blocked status
  if (FS_BLOCKED_STATUSES.includes(task.status?.toLowerCase() || '')) return true
  
  // Configurable signals
  
  // 3. Slippage - rescheduled too many times
  if (task.timesRescheduled >= signals.slippageThreshold) return true
  
  // 4. Hard deadline approaching
  if (task.daysUntilDeadline !== null && task.daysUntilDeadline >= 0 && task.daysUntilDeadline <= signals.hardDeadlineDays) {
    return true
  }
  
  // 5. Stale - in_progress with no recent updates
  if (task.status?.toLowerCase() === 'in_progress' && task.updatedAt) {
    const updatedDate = new Date(task.updatedAt)
    const today = new Date()
    const daysSinceUpdate = Math.floor((today.getTime() - updatedDate.getTime()) / (1000 * 60 * 60 * 24))
    if (daysSinceUpdate >= signals.staleDays) return true
  }
  
  return false
}

/**
 * Get a human-readable reason why a task needs attention.
 */
function getAttentionReason(task: FirestoreTask, signals: AttentionSignals): string {
  if (task.syncStatus === 'orphaned') return 'Orphaned - deleted from Smartsheet'
  if (FS_BLOCKED_STATUSES.includes(task.status?.toLowerCase() || '')) return `Blocked - ${task.status}`
  if (task.timesRescheduled >= signals.slippageThreshold) return `Slippage - rescheduled ${task.timesRescheduled}x`
  if (task.daysUntilDeadline !== null && task.daysUntilDeadline >= 0 && task.daysUntilDeadline <= signals.hardDeadlineDays) {
    return task.daysUntilDeadline === 0 ? 'Hard deadline today!' : `Hard deadline in ${task.daysUntilDeadline} day${task.daysUntilDeadline === 1 ? '' : 's'}`
  }
  if (task.status?.toLowerCase() === 'in_progress' && task.updatedAt) {
    const updatedDate = new Date(task.updatedAt)
    const today = new Date()
    const daysSinceUpdate = Math.floor((today.getTime() - updatedDate.getTime()) / (1000 * 60 * 60 * 24))
    if (daysSinceUpdate >= signals.staleDays) return `Stale - no updates in ${daysSinceUpdate} days`
  }
  return ''
}

const FILTERS = [
  { id: 'data_tasks', label: 'DATA Tasks' },
  { id: 'needs_attention', label: 'Needs Attention' },
  { id: 'all', label: 'All' },
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
  // Firestore task selection (for AssistPanel instead of modal)
  selectedFirestoreTask?: FirestoreTask | null
  onSelectFirestoreTask?: (task: FirestoreTask | null) => void
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
  // Firestore task selection (for AssistPanel)
  selectedFirestoreTask,
  onSelectFirestoreTask,
}: TaskListProps) {
  const [filter, setFilter] = useState('data_tasks')
  const [searchTerm, setSearchTerm] = useState('')
  
  // Get attention signals settings
  const { settings } = useSettings()
  
  // Domain sub-filter for Needs Attention view
  const [attentionDomain, setAttentionDomain] = useState<'all' | 'personal' | 'church' | 'work'>('all')
  
  // Domain sub-filter for DATA Tasks view
  const [dataTasksDomain, setDataTasksDomain] = useState<'all' | 'personal' | 'church' | 'work'>('all')
  
  // Phase 1f: Modal state (only for create, not detail - detail uses AssistPanel now)
  const [showCreateModal, setShowCreateModal] = useState(false)
  
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
        { direction: 'bidirectional', include_work: true },
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
  
  // Phase 1f: Handle Firestore task click - now uses AssistPanel instead of modal
  const handleFirestoreTaskClick = useCallback((task: FirestoreTask) => {
    if (onSelectFirestoreTask) {
      onSelectFirestoreTask(task)
    }
  }, [onSelectFirestoreTask])
  
  // Phase 1f: Handle task creation
  const handleTaskCreated = useCallback(() => {
    setShowCreateModal(false)
    if (onTaskCreated) onTaskCreated()
    if (onLoadEmailTasks) onLoadEmailTasks() // Refresh Firestore tasks
  }, [onTaskCreated, onLoadEmailTasks])
  
  // Phase 1f: Handle task update - now just refreshes the list
  const handleTaskUpdated = useCallback(() => {
    if (onTaskUpdated) onTaskUpdated()
    if (onLoadEmailTasks) onLoadEmailTasks() // Refresh Firestore tasks
  }, [onTaskUpdated, onLoadEmailTasks])

  // Phase 1f: Handle task deletion - clear selection and refresh
  const handleTaskDeleted = useCallback(() => {
    if (onSelectFirestoreTask) onSelectFirestoreTask(null)
    if (onTaskDeleted) onTaskDeleted()
    if (onLoadEmailTasks) onLoadEmailTasks() // Refresh Firestore tasks
  }, [onTaskDeleted, onLoadEmailTasks, onSelectFirestoreTask])

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
          // Needs Attention now uses Firestore tasks, not Smartsheet
          return false
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
          {/* Sync controls and domain filter for DATA Tasks */}
          <div className="data-tasks-sync-bar">
            {auth && (
              <button
                className="secondary sync-btn"
                onClick={handleSync}
                disabled={syncing}
                title="Sync tasks with Smartsheet"
              >
                {syncing ? '↻ Syncing...' : '↻ Sync with Smartsheet'}
              </button>
            )}
            {/* Domain sub-filter buttons */}
            <div className="domain-filter-inline">
              {(['all', 'personal', 'church', 'work'] as const).map((domain) => (
                <button
                  key={domain}
                  className={`domain-filter-btn ${dataTasksDomain === domain ? 'active' : ''}`}
                  onClick={() => setDataTasksDomain(domain)}
                >
                  {domain.charAt(0).toUpperCase() + domain.slice(1)}
                </button>
              ))}
            </div>
            {lastSyncResult && (
              <span className="sync-result">
                Created: {lastSyncResult.created}, Updated: {lastSyncResult.updated}
              </span>
            )}
          </div>
          {emailTasksLoading ? (
            <p>Loading DATA tasks…</p>
          ) : emailTasks.filter(t => {
            // Filter out completed tasks
            if (t.done || t.status === 'completed') return false
            // Apply domain filter
            if (dataTasksDomain !== 'all' && t.domain?.toLowerCase() !== dataTasksDomain) return false
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
            <p className="empty-state">{searchTerm.trim() ? 'No tasks match your search.' : (dataTasksDomain !== 'all' ? `No active ${dataTasksDomain} tasks.` : 'No active tasks. Create tasks from emails or click "+ New Task" above.')}</p>
          ) : (
            <ul className="task-list">
            {emailTasks.filter(t => {
              // Filter out completed tasks
              if (t.done || t.status === 'completed') return false
              // Apply domain filter
              if (dataTasksDomain !== 'all' && t.domain?.toLowerCase() !== dataTasksDomain) return false
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
      ) : filter === 'needs_attention' ? (
        /* Needs Attention Filter - Show Firestore tasks that need attention */
        <>
          {/* Domain sub-filter bar */}
          <div className="attention-domain-filter">
            {(['all', 'personal', 'church', 'work'] as const).map((domain) => (
              <button
                key={domain}
                className={`domain-filter-btn ${attentionDomain === domain ? 'active' : ''}`}
                onClick={() => setAttentionDomain(domain)}
              >
                {domain.charAt(0).toUpperCase() + domain.slice(1)}
              </button>
            ))}
          </div>
          
          {emailTasksLoading ? (
            <p>Loading tasks…</p>
          ) : (() => {
            // Filter tasks that need attention
            const attentionTasks = emailTasks.filter(t => {
              if (!needsAttention(t, settings.attentionSignals)) return false
              // Apply domain filter
              if (attentionDomain !== 'all' && t.domain?.toLowerCase() !== attentionDomain) return false
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
            })
            
            if (attentionTasks.length === 0) {
              return <p className="empty-state">{searchTerm.trim() ? 'No tasks match your search.' : 'No tasks need attention right now. Great job! 🎉'}</p>
            }
            
            return (
              <ul className="task-list needs-attention-list">
                {attentionTasks.sort((a, b) => {
                  // Sort: Orphaned first, then by urgency (deadline, slippage)
                  // 1. Orphaned tasks first
                  if (a.syncStatus === 'orphaned' && b.syncStatus !== 'orphaned') return -1
                  if (b.syncStatus === 'orphaned' && a.syncStatus !== 'orphaned') return 1
                  
                  // 2. Hard deadline (closest first)
                  const deadlineA = a.daysUntilDeadline ?? 999
                  const deadlineB = b.daysUntilDeadline ?? 999
                  if (deadlineA !== deadlineB) return deadlineA - deadlineB
                  
                  // 3. Slippage (highest first)
                  if (a.timesRescheduled !== b.timesRescheduled) {
                    return b.timesRescheduled - a.timesRescheduled
                  }
                  
                  // 4. Blocked status
                  const aBlocked = FS_BLOCKED_STATUSES.includes(a.status?.toLowerCase() || '')
                  const bBlocked = FS_BLOCKED_STATUSES.includes(b.status?.toLowerCase() || '')
                  if (aBlocked && !bBlocked) return -1
                  if (bBlocked && !aBlocked) return 1
                  
                  return 0
                }).map((task) => {
                  const domain = task.domain.charAt(0).toUpperCase() + task.domain.slice(1)
                  const reason = getAttentionReason(task, settings.attentionSignals)
                  const dueText = (task.plannedDate || task.dueDate) 
                    ? dueLabel(task.plannedDate || task.dueDate || '')
                    : 'No due date'
                  return (
                    <li
                      key={task.id}
                      className={
                        selectedFirestoreTask?.id === task.id ? 'task-item attention-item selected' : 'task-item attention-item'
                      }
                      onClick={() => handleFirestoreTaskClick(task)}
                    >
                      <div className="attention-reason">
                        {task.syncStatus === 'orphaned' && <span className="attention-icon orphaned">🔗✕</span>}
                        {task.timesRescheduled >= settings.attentionSignals.slippageThreshold && <span className="attention-icon slippage">⏳{task.timesRescheduled}</span>}
                        {task.daysUntilDeadline !== null && task.daysUntilDeadline <= settings.attentionSignals.hardDeadlineDays && <span className="attention-icon deadline">🔴</span>}
                        {FS_BLOCKED_STATUSES.includes(task.status?.toLowerCase() || '') && <span className="attention-icon blocked">🚧</span>}
                        {reason.includes('Stale') && <span className="attention-icon stale">💤</span>}
                        <span className="attention-text">{reason}</span>
                      </div>
                      <div className="task-signals">
                        <span className={`badge domain ${domain.toLowerCase()}`}>{domain}</span>
                        <span className="badge status">{task.status}</span>
                        {task.priority && (
                          <span className={`badge priority ${task.priority.toLowerCase()}`}>
                            {task.priority}
                          </span>
                        )}
                        <span className="badge due">{dueText}</span>
                      </div>
                      <div className="task-title-row">
                        <div className="task-title">{task.title}</div>
                      </div>
                      <div className="task-meta">
                        <span>{task.project || 'No project'}</span>
                      </div>
                    </li>
                  )
                })}
              </ul>
            )
          })()}
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
    </section>
  )
}

