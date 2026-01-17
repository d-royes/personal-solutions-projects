import { useState, useCallback, useEffect } from 'react'
import type { AuthConfig } from '../auth/types'
import type { FirestoreTask } from '../types'
import { updateFirestoreTask, deleteFirestoreTask, type UpdateTaskRequest } from '../api'
import '../App.css'

// Available status values (from migration plan - 12-value model)
const STATUS_OPTIONS = [
  { value: 'scheduled', label: 'Scheduled' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'on_hold', label: 'On Hold' },
  { value: 'blocked', label: 'Blocked' },
  { value: 'awaiting_reply', label: 'Awaiting Reply' },
  { value: 'follow_up', label: 'Follow-up' },
  { value: 'delivered', label: 'Delivered' },
  { value: 'validation', label: 'Validation' },
  { value: 'needs_approval', label: 'Needs Approval' },
  { value: 'completed', label: 'Completed' },
  { value: 'cancelled', label: 'Cancelled' },
  { value: 'delegated', label: 'Delegated' },
]

// Available priority values
const PRIORITY_OPTIONS = [
  { value: 'Critical', label: 'Critical' },
  { value: 'Urgent', label: 'Urgent' },
  { value: 'Important', label: 'Important' },
  { value: 'Standard', label: 'Standard' },
  { value: 'Low', label: 'Low' },
]

// Project options by domain
const PROJECT_OPTIONS: Record<string, string[]> = {
  personal: [
    'Around The House',
    'Family Time',
    'Shopping',
    'Sm. Projects & Tasks',
  ],
  church: [
    'Church Tasks',
    'IT Department',
    'Treasurer',
  ],
  work: [
    'Atlassian (Jira/Confluence)',
    'Crafter Studio',
    'Internal Application Support',
    'Team Management',
    'Strategic Planning',
    'Daily Operations',
    'Zendesk Support',
  ],
}

// Enhanced FirestoreTask - alias for the base type which already has all fields
type EnhancedFirestoreTask = FirestoreTask

// Recurring type options
const RECURRING_TYPE_OPTIONS = [
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'biweekly', label: 'Bi-weekly (every 2 weeks)' },
  { value: 'custom', label: 'Custom interval (every N days)' },
]

// Day options for weekly/bi-weekly
const DAY_OPTIONS = [
  { value: 'M', label: 'Mon' },
  { value: 'T', label: 'Tue' },
  { value: 'W', label: 'Wed' },
  { value: 'H', label: 'Thu' },
  { value: 'F', label: 'Fri' },
  { value: 'Sa', label: 'Sat' },
  { value: 'Su', label: 'Sun' },
]

// Monthly pattern options
const MONTHLY_OPTIONS = [
  { value: '1', label: '1st of month' },
  { value: '15', label: '15th of month' },
  { value: 'last', label: 'Last day of month' },
  { value: 'first_monday', label: 'First Monday' },
  { value: 'first_friday', label: 'First Friday' },
  { value: 'last_friday', label: 'Last Friday' },
]

interface TaskDetailModalProps {
  task: EnhancedFirestoreTask | null
  isOpen: boolean
  onClose: () => void
  onTaskUpdated: () => void
  onTaskDeleted: () => void
  auth: AuthConfig
  baseUrl?: string
}

/**
 * Modal for viewing and editing task details.
 * Part of Phase 1e - Direct API, no LLM involvement.
 */
export function TaskDetailModal({
  task,
  isOpen,
  onClose,
  onTaskUpdated,
  onTaskDeleted,
  auth,
  baseUrl,
}: TaskDetailModalProps) {
  // Form state - initialized from task
  const [title, setTitle] = useState('')
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  const [project, setProject] = useState('')
  const [plannedDate, setPlannedDate] = useState('')
  const [targetDate, setTargetDate] = useState('')
  const [hardDeadline, setHardDeadline] = useState('')
  const [notes, setNotes] = useState('')
  const [estimatedHours, setEstimatedHours] = useState('')
  const [done, setDone] = useState(false)
  
  // Recurring task state
  const [isRecurring, setIsRecurring] = useState(false)
  const [recurringType, setRecurringType] = useState<string>('weekly')
  const [recurringDays, setRecurringDays] = useState<string[]>([])
  const [recurringMonthly, setRecurringMonthly] = useState<string>('1')
  const [recurringInterval, setRecurringInterval] = useState<number>(1)

  // UI state
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)

  // Initialize form from task when modal opens
  useEffect(() => {
    if (isOpen && task) {
      setTitle(task.title || '')
      setStatus(task.status || 'scheduled')
      setPriority(task.priority || 'Standard')
      setProject(task.project || '')
      setPlannedDate(task.plannedDate?.split('T')[0] || task.dueDate?.split('T')[0] || '')
      setTargetDate(task.targetDate?.split('T')[0] || '')
      setHardDeadline(task.hardDeadline?.split('T')[0] || '')
      setNotes(task.notes || '')
      setEstimatedHours(task.estimatedHours?.toString() || '')
      setDone(task.done || false)
      // Recurring fields
      setIsRecurring(task.isRecurring || !!task.recurringType)
      setRecurringType(task.recurringType || 'weekly')
      setRecurringDays(task.recurringDays || [])
      setRecurringMonthly(task.recurringMonthly || '1')
      setRecurringInterval(task.recurringInterval || 1)
      setError(null)
      setHasChanges(false)
      setShowDeleteConfirm(false)
    }
  }, [isOpen, task])

  // Track changes
  useEffect(() => {
    if (!task) return
    
    const taskIsRecurring = task.isRecurring || !!task.recurringType
    const recurringDaysChanged = JSON.stringify(recurringDays.sort()) !== JSON.stringify((task.recurringDays || []).sort())
    
    const changed = 
      title !== (task.title || '') ||
      status !== (task.status || 'scheduled') ||
      priority !== (task.priority || 'Standard') ||
      project !== (task.project || '') ||
      plannedDate !== (task.plannedDate?.split('T')[0] || task.dueDate?.split('T')[0] || '') ||
      targetDate !== (task.targetDate?.split('T')[0] || '') ||
      hardDeadline !== (task.hardDeadline?.split('T')[0] || '') ||
      notes !== (task.notes || '') ||
      done !== (task.done || false) ||
      isRecurring !== taskIsRecurring ||
      (isRecurring && recurringType !== (task.recurringType || 'weekly')) ||
      (isRecurring && recurringDaysChanged) ||
      (isRecurring && recurringMonthly !== (task.recurringMonthly || '1')) ||
      (isRecurring && recurringInterval !== (task.recurringInterval || 1))
    
    setHasChanges(changed)
  }, [task, title, status, priority, project, plannedDate, targetDate, hardDeadline, notes, done, isRecurring, recurringType, recurringDays, recurringMonthly, recurringInterval])

  // Get available projects based on task domain
  const domain = task?.domain || 'personal'
  const availableProjects = PROJECT_OPTIONS[domain] || []

  // Handle save
  const handleSave = useCallback(async () => {
    if (!task) return
    setError(null)
    setSaving(true)

    try {
      const updates: UpdateTaskRequest = {
        title: title.trim() || undefined,
        status: status || undefined,
        priority: priority || undefined,
        project: project || undefined,
        plannedDate: plannedDate || undefined,
        targetDate: targetDate || undefined,
        hardDeadline: hardDeadline || undefined,
        notes: notes.trim() || undefined,
        estimatedHours: estimatedHours ? parseFloat(estimatedHours) : undefined,
        done,
        // Recurring fields - clear if not recurring, set if recurring
        recurringType: isRecurring ? recurringType : null,
        recurringDays: isRecurring && (recurringType === 'weekly' || recurringType === 'biweekly') ? recurringDays : [],
        recurringMonthly: isRecurring && recurringType === 'monthly' ? recurringMonthly : null,
        recurringInterval: isRecurring && recurringType === 'custom' ? recurringInterval : null,
      }

      await updateFirestoreTask(task.id, updates, auth, baseUrl)
      onTaskUpdated()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save task')
    } finally {
      setSaving(false)
    }
  }, [task, title, status, priority, project, plannedDate, targetDate, hardDeadline, notes, estimatedHours, done, isRecurring, recurringType, recurringDays, recurringMonthly, recurringInterval, auth, baseUrl, onTaskUpdated, onClose])

  // Handle delete
  const handleDelete = useCallback(async () => {
    if (!task) return
    setError(null)
    setDeleting(true)

    try {
      await deleteFirestoreTask(task.id, auth, baseUrl)
      onTaskDeleted()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete task')
    } finally {
      setDeleting(false)
      setShowDeleteConfirm(false)
    }
  }, [task, auth, baseUrl, onTaskDeleted, onClose])

  // Handle mark complete
  const handleMarkComplete = useCallback(async () => {
    if (!task) return
    setError(null)
    setSaving(true)

    try {
      await updateFirestoreTask(task.id, { done: true, status: 'completed' }, auth, baseUrl)
      onTaskUpdated()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to mark task complete')
    } finally {
      setSaving(false)
    }
  }, [task, auth, baseUrl, onTaskUpdated, onClose])

  // Handle escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        if (showDeleteConfirm) {
          setShowDeleteConfirm(false)
        } else {
          onClose()
        }
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [isOpen, showDeleteConfirm, onClose])

  if (!isOpen || !task) return null

  // Format dates for display
  const createdAt = task.createdAt ? new Date(task.createdAt).toLocaleDateString() : 'Unknown'
  const updatedAt = task.updatedAt ? new Date(task.updatedAt).toLocaleDateString() : 'Unknown'
  
  // Slippage indicator
  const timesRescheduled = task.timesRescheduled || 0
  const hasSlippage = timesRescheduled > 0

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content task-detail-modal" onClick={e => e.stopPropagation()}>
        <header className="modal-header">
          <div className="modal-header-left">
            <h2>Task Details</h2>
            <span className={`badge domain ${domain}`}>
              {domain.charAt(0).toUpperCase() + domain.slice(1)}
            </span>
            {task.isRecurring && (
              <span className="badge recurring" title="Recurring task">🔄</span>
            )}
            {hasSlippage && (
              <span className="badge slippage" title={`Rescheduled ${timesRescheduled} time(s)`}>
                ⏳ {timesRescheduled}x
              </span>
            )}
          </div>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <div className="task-detail-form">
          {error && (
            <div className="form-error">
              {error}
            </div>
          )}

          {/* Source info if from email */}
          {task.source === 'email' && task.sourceEmailSubject && (
            <div className="task-source-info">
              <span className="source-label">📧 From email:</span>
              <span className="source-value">{task.sourceEmailSubject}</span>
            </div>
          )}

          {/* Title */}
          <div className="form-group">
            <label htmlFor="detail-title">Title</label>
            <input
              id="detail-title"
              type="text"
              value={title}
              onChange={e => setTitle(e.target.value)}
            />
          </div>

          {/* Status and Priority row */}
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="detail-status">Status</label>
              <select
                id="detail-status"
                value={status}
                onChange={e => setStatus(e.target.value)}
              >
                {STATUS_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="detail-priority">Priority</label>
              <select
                id="detail-priority"
                value={priority}
                onChange={e => setPriority(e.target.value)}
              >
                {PRIORITY_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Project */}
          <div className="form-group">
            <label htmlFor="detail-project">Project</label>
            <select
              id="detail-project"
              value={project}
              onChange={e => setProject(e.target.value)}
            >
              <option value="">No project</option>
              {availableProjects.map(proj => (
                <option key={proj} value={proj}>{proj}</option>
              ))}
            </select>
          </div>

          {/* Three-date model */}
          <fieldset className="form-fieldset">
            <legend>
              Dates
              {hasSlippage && (
                <span className="slippage-indicator" title="Original target differs from current plan">
                  {' '}(Slipped {timesRescheduled}x)
                </span>
              )}
            </legend>
            <div className="form-row three-col">
              <div className="form-group">
                <label htmlFor="detail-planned">Planned</label>
                <input
                  id="detail-planned"
                  type="date"
                  value={plannedDate}
                  onChange={e => setPlannedDate(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label htmlFor="detail-target">
                  Target
                  <span className="field-hint" title="Original goal - never auto-changes">ⓘ</span>
                </label>
                <input
                  id="detail-target"
                  type="date"
                  value={targetDate}
                  onChange={e => setTargetDate(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label htmlFor="detail-deadline">
                  Deadline
                  <span className="field-hint" title="External commitment">ⓘ</span>
                </label>
                <input
                  id="detail-deadline"
                  type="date"
                  value={hardDeadline}
                  onChange={e => setHardDeadline(e.target.value)}
                />
              </div>
            </div>
          </fieldset>

          {/* Estimated Hours */}
          <div className="form-group">
            <label htmlFor="detail-hours">Estimated Hours</label>
            <select
              id="detail-hours"
              value={estimatedHours}
              onChange={e => setEstimatedHours(e.target.value)}
            >
              <option value="">Not set</option>
              <option value="0.25">15 minutes</option>
              <option value="0.5">30 minutes</option>
              <option value="1">1 hour</option>
              <option value="2">2 hours</option>
              <option value="3">3 hours</option>
              <option value="4">4 hours</option>
              <option value="5">5+ hours</option>
            </select>
          </div>

          {/* Notes */}
          <div className="form-group">
            <label htmlFor="detail-notes">Notes</label>
            <textarea
              id="detail-notes"
              value={notes}
              onChange={e => setNotes(e.target.value)}
              rows={4}
            />
          </div>

          {/* Done checkbox */}
          <div className="form-group checkbox-group">
            <label>
              <input
                type="checkbox"
                checked={done}
                onChange={e => setDone(e.target.checked)}
              />
              <span>Mark as complete</span>
            </label>
          </div>

          {/* Recurring task configuration */}
          <fieldset className="form-fieldset recurring-config">
            <legend>
              <label className="recurring-toggle">
                <input
                  type="checkbox"
                  checked={isRecurring}
                  onChange={e => setIsRecurring(e.target.checked)}
                />
                <span>Recurring Task</span>
              </label>
            </legend>
            
            {isRecurring && (
              <div className="recurring-options">
                {/* Recurring type selector */}
                <div className="form-group">
                  <label htmlFor="detail-recurring-type">Pattern</label>
                  <select
                    id="detail-recurring-type"
                    value={recurringType}
                    onChange={e => setRecurringType(e.target.value)}
                  >
                    {RECURRING_TYPE_OPTIONS.map(opt => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </div>

                {/* Weekly/Bi-weekly: Day picker */}
                {(recurringType === 'weekly' || recurringType === 'biweekly') && (
                  <div className="form-group">
                    <label>Days</label>
                    <div className="day-picker">
                      {DAY_OPTIONS.map(day => (
                        <label key={day.value} className="day-checkbox">
                          <input
                            type="checkbox"
                            checked={recurringDays.includes(day.value)}
                            onChange={e => {
                              if (e.target.checked) {
                                setRecurringDays([...recurringDays, day.value])
                              } else {
                                setRecurringDays(recurringDays.filter(d => d !== day.value))
                              }
                            }}
                          />
                          <span>{day.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}

                {/* Monthly: Pattern selector */}
                {recurringType === 'monthly' && (
                  <div className="form-group">
                    <label htmlFor="detail-monthly-pattern">Monthly on</label>
                    <select
                      id="detail-monthly-pattern"
                      value={recurringMonthly}
                      onChange={e => setRecurringMonthly(e.target.value)}
                    >
                      {MONTHLY_OPTIONS.map(opt => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </div>
                )}

                {/* Custom: Interval input */}
                {recurringType === 'custom' && (
                  <div className="form-group">
                    <label htmlFor="detail-interval">Every N days</label>
                    <input
                      id="detail-interval"
                      type="number"
                      min="1"
                      max="365"
                      value={recurringInterval}
                      onChange={e => setRecurringInterval(parseInt(e.target.value) || 1)}
                    />
                  </div>
                )}

                <p className="recurring-note">
                  Recurring tasks reset automatically when due. Uncheck "Recurring Task" to end the series.
                </p>
              </div>
            )}
          </fieldset>

          {/* Metadata */}
          <div className="task-metadata">
            <span>Created: {createdAt}</span>
            <span>Updated: {updatedAt}</span>
            {task.syncStatus && (
              <span className={`sync-status ${task.syncStatus}`}>
                Sync: {task.syncStatus}
              </span>
            )}
          </div>

          {/* Actions */}
          <div className="modal-actions task-detail-actions">
            {showDeleteConfirm ? (
              <>
                <span className="delete-confirm-text">Delete this task?</span>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setShowDeleteConfirm(false)}
                  disabled={deleting}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="danger"
                  onClick={handleDelete}
                  disabled={deleting}
                >
                  {deleting ? 'Deleting...' : 'Confirm Delete'}
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  className="danger-outline"
                  onClick={() => setShowDeleteConfirm(true)}
                  disabled={saving || deleting}
                >
                  Delete
                </button>
                {!done && (
                  <button
                    type="button"
                    className="success"
                    onClick={handleMarkComplete}
                    disabled={saving || deleting}
                  >
                    ✓ Complete
                  </button>
                )}
                <div className="action-spacer" />
                <button
                  type="button"
                  className="secondary"
                  onClick={onClose}
                  disabled={saving || deleting}
                >
                  {hasChanges ? 'Discard' : 'Close'}
                </button>
                <button
                  type="button"
                  className="primary"
                  onClick={handleSave}
                  disabled={saving || deleting || !hasChanges}
                >
                  {saving ? 'Saving...' : 'Save Changes'}
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
