import { useState, useCallback, useEffect } from 'react'
import type { AuthConfig } from '../auth/types'
import { createFirestoreTask, type CreateTaskRequest } from '../api'
import '../App.css'

// Available status values (from migration plan - 12-value model)
const STATUS_OPTIONS = [
  { value: 'scheduled', label: 'Scheduled' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'on_hold', label: 'On Hold' },
  { value: 'blocked', label: 'Blocked' },
  { value: 'awaiting_reply', label: 'Awaiting Reply' },
  { value: 'follow_up', label: 'Follow-up' },
]

// Available priority values
const PRIORITY_OPTIONS = [
  { value: 'Critical', label: 'Critical' },
  { value: 'Urgent', label: 'Urgent' },
  { value: 'Important', label: 'Important' },
  { value: 'Standard', label: 'Standard' },
  { value: 'Low', label: 'Low' },
]

// Domain options
const DOMAIN_OPTIONS = [
  { value: 'personal', label: 'Personal' },
  { value: 'church', label: 'Church' },
  { value: 'work', label: 'Work' },
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

interface TaskCreateModalProps {
  isOpen: boolean
  onClose: () => void
  onTaskCreated: () => void
  auth: AuthConfig
  baseUrl?: string
}

/**
 * Modal for creating a new task directly in Firestore.
 * Part of Phase 1d - Direct API, no LLM involvement.
 */
export function TaskCreateModal({
  isOpen,
  onClose,
  onTaskCreated,
  auth,
  baseUrl,
}: TaskCreateModalProps) {
  // Form state
  const [title, setTitle] = useState('')
  const [domain, setDomain] = useState<'personal' | 'church' | 'work'>('personal')
  const [status, setStatus] = useState('scheduled')
  const [priority, setPriority] = useState('Standard')
  const [project, setProject] = useState('')
  const [plannedDate, setPlannedDate] = useState('')
  const [targetDate, setTargetDate] = useState('')
  const [hardDeadline, setHardDeadline] = useState('')
  const [notes, setNotes] = useState('')
  const [estimatedHours, setEstimatedHours] = useState('')
  
  // Recurring task state
  const [isRecurring, setIsRecurring] = useState(false)
  const [recurringType, setRecurringType] = useState<string>('weekly')
  const [recurringDays, setRecurringDays] = useState<string[]>([])
  const [recurringMonthly, setRecurringMonthly] = useState<string>('1')
  const [recurringInterval, setRecurringInterval] = useState<number>(1)

  // UI state
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Reset form when modal opens
  useEffect(() => {
    if (isOpen) {
      setTitle('')
      setDomain('personal')
      setStatus('scheduled')
      setPriority('Standard')
      setProject('')
      setPlannedDate(new Date().toISOString().split('T')[0]) // Default to today
      setTargetDate('')
      setHardDeadline('')
      setNotes('')
      setEstimatedHours('')
      // Reset recurring state
      setIsRecurring(false)
      setRecurringType('weekly')
      setRecurringDays([])
      setRecurringMonthly('1')
      setRecurringInterval(1)
      setError(null)
    }
  }, [isOpen])

  // Update project options when domain changes
  const availableProjects = PROJECT_OPTIONS[domain] || []

  // Handle domain change
  const handleDomainChange = useCallback((newDomain: 'personal' | 'church' | 'work') => {
    setDomain(newDomain)
    // Reset project if not in new domain's options
    const newProjects = PROJECT_OPTIONS[newDomain] || []
    if (project && !newProjects.includes(project)) {
      setProject('')
    }
  }, [project])

  // Handle form submission
  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSaving(true)

    try {
      // Validate required fields
      if (!title.trim()) {
        throw new Error('Title is required')
      }

      const request: CreateTaskRequest = {
        title: title.trim(),
        domain,
        status,
        priority,
        project: project || undefined,
        plannedDate: plannedDate || undefined,
        targetDate: targetDate || undefined,
        hardDeadline: hardDeadline || undefined,
        notes: notes.trim() || undefined,
        estimatedHours: estimatedHours ? parseFloat(estimatedHours) : undefined,
        // Recurring fields - only set if recurring
        recurringType: isRecurring ? recurringType : undefined,
        recurringDays: isRecurring && (recurringType === 'weekly' || recurringType === 'biweekly') ? recurringDays : undefined,
        recurringMonthly: isRecurring && recurringType === 'monthly' ? recurringMonthly : undefined,
        recurringInterval: isRecurring && recurringType === 'custom' ? recurringInterval : undefined,
      }

      await createFirestoreTask(request, auth, baseUrl)
      
      onTaskCreated()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create task')
    } finally {
      setSaving(false)
    }
  }, [title, domain, status, priority, project, plannedDate, targetDate, hardDeadline, notes, estimatedHours, isRecurring, recurringType, recurringDays, recurringMonthly, recurringInterval, auth, baseUrl, onTaskCreated, onClose])

  // Handle escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose()
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [isOpen, onClose])

  if (!isOpen) return null

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content task-create-modal" onClick={e => e.stopPropagation()}>
        <header className="modal-header">
          <h2>Create New Task</h2>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <form onSubmit={handleSubmit} className="task-create-form">
          {error && (
            <div className="form-error">
              {error}
            </div>
          )}

          {/* Title (required) */}
          <div className="form-group">
            <label htmlFor="task-title">Task Title *</label>
            <input
              id="task-title"
              type="text"
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="What needs to be done?"
              autoFocus
              required
            />
          </div>

          {/* Domain and Priority row */}
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="task-domain">Domain</label>
              <select
                id="task-domain"
                value={domain}
                onChange={e => handleDomainChange(e.target.value as 'personal' | 'church' | 'work')}
              >
                {DOMAIN_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="task-priority">Priority</label>
              <select
                id="task-priority"
                value={priority}
                onChange={e => setPriority(e.target.value)}
              >
                {PRIORITY_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Status and Project row */}
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="task-status">Status</label>
              <select
                id="task-status"
                value={status}
                onChange={e => setStatus(e.target.value)}
              >
                {STATUS_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="task-project">Project</label>
              <select
                id="task-project"
                value={project}
                onChange={e => setProject(e.target.value)}
              >
                <option value="">Select project...</option>
                {availableProjects.map(proj => (
                  <option key={proj} value={proj}>{proj}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Three-date model */}
          <fieldset className="form-fieldset">
            <legend>Dates (Three-Date Model)</legend>
            <div className="form-row three-col">
              <div className="form-group">
                <label htmlFor="task-planned-date">
                  Planned Date
                  <span className="field-hint" title="When you plan to work on this task (can be rescheduled)">ⓘ</span>
                </label>
                <input
                  id="task-planned-date"
                  type="date"
                  value={plannedDate}
                  onChange={e => setPlannedDate(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label htmlFor="task-target-date">
                  Target Date
                  <span className="field-hint" title="Original goal date (tracks slippage if planned date moves)">ⓘ</span>
                </label>
                <input
                  id="task-target-date"
                  type="date"
                  value={targetDate}
                  onChange={e => setTargetDate(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label htmlFor="task-deadline">
                  Hard Deadline
                  <span className="field-hint" title="External commitment - triggers alerts if at risk">ⓘ</span>
                </label>
                <input
                  id="task-deadline"
                  type="date"
                  value={hardDeadline}
                  onChange={e => setHardDeadline(e.target.value)}
                />
              </div>
            </div>
          </fieldset>

          {/* Estimated Hours */}
          <div className="form-group">
            <label htmlFor="task-hours">Estimated Hours</label>
            <select
              id="task-hours"
              value={estimatedHours}
              onChange={e => setEstimatedHours(e.target.value)}
            >
              <option value="">Select estimate...</option>
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
            <label htmlFor="task-notes">Notes</label>
            <textarea
              id="task-notes"
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="Additional context or details..."
              rows={3}
            />
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
                  <label htmlFor="create-recurring-type">Pattern</label>
                  <select
                    id="create-recurring-type"
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
                    <label htmlFor="create-monthly-pattern">Monthly on</label>
                    <select
                      id="create-monthly-pattern"
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
                    <label htmlFor="create-interval">Every N days</label>
                    <input
                      id="create-interval"
                      type="number"
                      min="1"
                      max="365"
                      value={recurringInterval}
                      onChange={e => setRecurringInterval(parseInt(e.target.value) || 1)}
                    />
                  </div>
                )}

                <p className="recurring-note">
                  Recurring tasks reset automatically when due.
                </p>
              </div>
            )}
          </fieldset>

          {/* Actions */}
          <div className="modal-actions">
            <button
              type="button"
              className="secondary"
              onClick={onClose}
              disabled={saving}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="primary"
              disabled={saving || !title.trim()}
            >
              {saving ? 'Creating...' : 'Create Task'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
