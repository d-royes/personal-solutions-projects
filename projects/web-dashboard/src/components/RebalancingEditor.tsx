import { useState, useMemo } from 'react'
import type { PortfolioPendingAction, BulkTaskUpdate } from '../api'

interface RebalancingEditorProps {
  pendingActions: PortfolioPendingAction[]
  onApply: (updates: BulkTaskUpdate[]) => Promise<void>
  onCancel: () => void
  executing: boolean
}

// Domain order for grouping
const DOMAIN_ORDER = ['Church', 'Personal', 'Work', 'Unknown']

// Priority options
const PRIORITY_OPTIONS = [
  'Critical',
  'Urgent', 
  'Important',
  'Standard',
  'Low',
]

// Status options
const STATUS_OPTIONS = [
  'Scheduled',
  'Recurring',
  'On Hold',
  'In Progress',
  'Follow-up',
  'Awaiting Reply',
  'Completed',
  'Cancelled',
]

interface EditableAction extends PortfolioPendingAction {
  // Track which fields were modified (originals come from enriched data)
  originalDueDate?: string
  originalNumber?: number
  originalPriority?: string
  originalStatus?: string
}

export function RebalancingEditor({
  pendingActions,
  onApply,
  onCancel,
  executing,
}: RebalancingEditorProps) {
  // Convert pending actions to editable state - use enriched current values as originals
  const [editableActions, setEditableActions] = useState<EditableAction[]>(() => 
    pendingActions.map(action => ({
      ...action,
      // Use proposed values for editing, current values as originals
      dueDate: action.dueDate || action.currentDue,
      number: action.number ?? action.currentNumber,
      priority: action.priority || action.currentPriority,
      status: action.status || action.currentStatus,
      // Track originals to detect changes
      originalDueDate: action.currentDue,
      originalNumber: action.currentNumber,
      originalPriority: action.currentPriority,
      originalStatus: action.currentStatus,
    }))
  )

  // Group actions by domain (using enriched domain field from backend)
  const groupedActions = useMemo(() => {
    const groups: Record<string, EditableAction[]> = {}
    
    for (const action of editableActions) {
      // Use enriched domain field, fallback to extraction from reason
      const domain = action.domain || extractDomain(action.reason) || 'Unknown'
      if (!groups[domain]) {
        groups[domain] = []
      }
      groups[domain].push(action)
    }
    
    // Sort by domain order
    const sorted: { domain: string; actions: EditableAction[] }[] = []
    for (const domain of DOMAIN_ORDER) {
      if (groups[domain] && groups[domain].length > 0) {
        sorted.push({ domain, actions: groups[domain] })
      }
    }
    
    return sorted
  }, [editableActions])

  // Update a specific action's field
  const updateAction = (rowId: string, field: keyof EditableAction, value: string | number | boolean | undefined) => {
    setEditableActions(prev => prev.map(action => 
      action.rowId === rowId ? { ...action, [field]: value } : action
    ))
  }

  // Handle apply - convert editable actions to bulk updates
  const handleApply = async () => {
    const updates: BulkTaskUpdate[] = []
    
    for (const action of editableActions) {
      // Check what changed and create appropriate updates
      if (action.dueDate && action.dueDate !== action.originalDueDate) {
        updates.push({
          rowId: action.rowId,
          action: 'update_due_date',
          dueDate: action.dueDate,
          reason: action.reason || 'Rebalancing',
        })
      }
      
      if (action.number !== undefined && action.number !== action.originalNumber) {
        updates.push({
          rowId: action.rowId,
          action: 'update_number',
          number: action.number,
          reason: action.reason || 'Rebalancing',
        })
      }
      
      if (action.priority && action.priority !== action.originalPriority) {
        updates.push({
          rowId: action.rowId,
          action: 'update_priority',
          priority: action.priority,
          reason: action.reason || 'Rebalancing',
        })
      }
      
      if (action.status && action.status !== action.originalStatus) {
        updates.push({
          rowId: action.rowId,
          action: 'update_status',
          status: action.status,
          reason: action.reason || 'Rebalancing',
        })
      }

      // Handle mark_complete action
      if (action.action === 'mark_complete') {
        updates.push({
          rowId: action.rowId,
          action: 'mark_complete',
          reason: action.reason || 'Marked complete during rebalancing',
        })
      }
    }
    
    if (updates.length > 0) {
      await onApply(updates)
    } else {
      onCancel() // No changes to apply
    }
  }

  // Count total changes
  const changeCount = editableActions.filter(a => 
    (a.dueDate && a.dueDate !== a.originalDueDate) ||
    (a.number !== undefined && a.number !== a.originalNumber) ||
    (a.priority && a.priority !== a.originalPriority) ||
    (a.status && a.status !== a.originalStatus) ||
    a.action === 'mark_complete'
  ).length

  return (
    <div className="rebalancing-editor">
      <header className="rebalancing-header">
        <div className="header-left">
          <h1>📋 Rebalancing Editor</h1>
          <p className="subtitle">Review and adjust DATA's proposed changes before applying</p>
        </div>
        <div className="header-right">
          <span className="change-count">{changeCount} changes</span>
        </div>
      </header>

      <div className="rebalancing-content">
        {groupedActions.map(({ domain, actions }) => (
          <div key={domain} className="domain-group">
            <h2 className="domain-header">
              <span className="domain-icon">{getDomainIcon(domain)}</span>
              {domain}
              <span className="domain-count">{actions.length} tasks</span>
            </h2>
            
            <div className="tasks-table">
              <div className="table-header">
                <div className="col-task">Task</div>
                <div className="col-date">Due Date</div>
                <div className="col-number">#</div>
                <div className="col-priority">Priority</div>
                <div className="col-status">Status</div>
              </div>
              
              {actions.map(action => (
                <div key={action.rowId} className="table-row">
                  <div className="col-task">
                    <span className="task-title" title={action.taskTitle || action.rowId}>
                      {action.taskTitle || `Task ${action.rowId.slice(-6)}`}
                    </span>
                    {action.reason && (
                      <span className="task-reason">{action.reason}</span>
                    )}
                  </div>
                  
                  <div className="col-date">
                    <input
                      type="date"
                      value={action.dueDate || ''}
                      onChange={(e) => updateAction(action.rowId, 'dueDate', e.target.value)}
                      className={action.dueDate !== action.originalDueDate ? 'modified' : ''}
                    />
                    {action.originalDueDate && action.dueDate !== action.originalDueDate && (
                      <span className="original-value">was: {action.originalDueDate}</span>
                    )}
                  </div>
                  
                  <div className="col-number">
                    <input
                      type="number"
                      step="0.1"
                      min="0.1"
                      value={action.number ?? ''}
                      onChange={(e) => updateAction(action.rowId, 'number', e.target.value ? parseFloat(e.target.value) : undefined)}
                      className={action.number !== action.originalNumber ? 'modified' : ''}
                      placeholder="#"
                    />
                  </div>
                  
                  <div className="col-priority">
                    <select
                      value={action.priority || ''}
                      onChange={(e) => updateAction(action.rowId, 'priority', e.target.value || undefined)}
                      className={action.priority !== action.originalPriority ? 'modified' : ''}
                    >
                      <option value="">—</option>
                      {PRIORITY_OPTIONS.map(p => (
                        <option key={p} value={p}>{p}</option>
                      ))}
                    </select>
                  </div>
                  
                  <div className="col-status">
                    <select
                      value={action.status || ''}
                      onChange={(e) => updateAction(action.rowId, 'status', e.target.value || undefined)}
                      className={action.status !== action.originalStatus ? 'modified' : ''}
                    >
                      <option value="">—</option>
                      {STATUS_OPTIONS.map(s => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <footer className="rebalancing-footer">
        <button 
          className="cancel-btn"
          onClick={onCancel}
          disabled={executing}
        >
          Cancel
        </button>
        <button 
          className="apply-btn"
          onClick={handleApply}
          disabled={executing || changeCount === 0}
        >
          {executing ? 'Applying...' : `Apply ${changeCount} Changes`}
        </button>
      </footer>
    </div>
  )
}

// Helper: Extract domain from reason text
function extractDomain(reason?: string): string | null {
  if (!reason) return null
  const lower = reason.toLowerCase()
  if (lower.includes('church')) return 'Church'
  if (lower.includes('personal') || lower.includes('home') || lower.includes('family')) return 'Personal'
  if (lower.includes('work') || lower.includes('professional')) return 'Work'
  return null
}

// Helper: Get icon for domain
function getDomainIcon(domain: string): string {
  switch (domain) {
    case 'Church': return '⛪'
    case 'Personal': return '🏠'
    case 'Work': return '💼'
    default: return '📋'
  }
}

