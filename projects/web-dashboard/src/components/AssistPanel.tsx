import { useEffect, useState } from 'react'
import type { AssistPlan, ConversationMessage, Task } from '../types'
import type { FeedbackContext, FeedbackType, PendingAction } from '../api'

// Feedback callback type
type OnFeedbackSubmit = (
  feedback: FeedbackType,
  context: FeedbackContext,
  messageContent: string,
  messageId?: string
) => Promise<void>

// Reusable feedback controls component
function FeedbackControls({
  context,
  messageContent,
  messageId,
  onSubmit,
}: {
  context: FeedbackContext
  messageContent: string
  messageId?: string
  onSubmit: OnFeedbackSubmit
}) {
  const [submitted, setSubmitted] = useState<FeedbackType | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleFeedback = async (feedback: FeedbackType) => {
    if (submitted || submitting) return
    setSubmitting(true)
    try {
      await onSubmit(feedback, context, messageContent, messageId)
      setSubmitted(feedback)
    } catch (err) {
      console.error('Feedback submission failed:', err)
    } finally {
      setSubmitting(false)
    }
  }

  if (submitted) {
    return (
      <div className="feedback-controls submitted">
        <span className="feedback-thanks">
          {submitted === 'helpful' ? '👍 Thanks!' : '👎 Noted, we\'ll improve'}
        </span>
      </div>
    )
  }

  return (
    <div className="feedback-controls">
      <span className="feedback-label">Was this helpful?</span>
      <div className="feedback-buttons">
        <button
          className="feedback-button helpful"
          onClick={() => handleFeedback('helpful')}
          disabled={submitting}
          title="This was helpful"
        >
          👍
        </button>
        <button
          className="feedback-button needs-work"
          onClick={() => handleFeedback('needs_work')}
          disabled={submitting}
          title="Needs improvement"
        >
          👎
        </button>
      </div>
    </div>
  )
}

const NOTES_PREVIEW_LIMIT = 200

function notesPreview(notes?: string | null) {
  if (!notes) return null
  if (notes.length <= NOTES_PREVIEW_LIMIT) return notes
  return `${notes.slice(0, NOTES_PREVIEW_LIMIT)}…`
}

function truncateCopy(text?: string | null, limit = 200) {
  if (!text) return ''
  if (text.length <= limit) return text
  return `${text.slice(0, limit)}…`
}

function formatActionLabel(action: string): string {
  const labels: Record<string, string> = {
    plan: '📋 Plan',
    research: '🔍 Research',
    draft_email: '✉️ Email',
    review: '📝 Review',
    schedule: '📅 Schedule',
    follow_up: '📞 Follow Up',
    delegate: '👥 Delegate',
    organize: '📁 Organize',
    summarize: '📄 Summarize',
  }
  return labels[action] || action.replace(/_/g, ' ')
}

/**
 * Simple markdown-like renderer for chat content.
 * Handles headers, bold, bullet points, and links.
 */
function renderMarkdown(text: string): JSX.Element {
  // Pre-process: fix bullets that are split across lines (e.g., "-\nContent" -> "- Content")
  const preprocessed = text
    .replace(/^-\s*\n+/gm, '- ')  // Fix "- \n" at start of line
    .replace(/\n-\s*\n+/g, '\n- ') // Fix "\n-\n" patterns
    .replace(/-\s*\n+(?=[A-Z])/g, '- ') // Fix "-\n" followed by capital letter
  
  const lines = preprocessed.split('\n')
  const elements: JSX.Element[] = []
  let listItems: string[] = []
  let listKey = 0

  const flushList = () => {
    if (listItems.length > 0) {
      elements.push(
        <ul key={`list-${listKey++}`} className="chat-list">
          {listItems.map((item, i) => (
            <li key={i}>{formatInline(item)}</li>
          ))}
        </ul>
      )
      listItems = []
    }
  }

  const formatInline = (line: string): JSX.Element | string => {
    // Handle bold **text** and links
    const parts: (string | JSX.Element)[] = []
    let remaining = line
    let partKey = 0

    // Process bold
    while (remaining.includes('**')) {
      const start = remaining.indexOf('**')
      if (start > 0) {
        parts.push(remaining.slice(0, start))
      }
      remaining = remaining.slice(start + 2)
      const end = remaining.indexOf('**')
      if (end === -1) {
        parts.push('**' + remaining)
        remaining = ''
        break
      }
      parts.push(<strong key={`bold-${partKey++}`}>{remaining.slice(0, end)}</strong>)
      remaining = remaining.slice(end + 2)
    }
    if (remaining) {
      parts.push(remaining)
    }

    return parts.length === 1 && typeof parts[0] === 'string' 
      ? parts[0] 
      : <>{parts}</>
  }

  lines.forEach((line, index) => {
    const trimmed = line.trim()

    // Headers
    if (trimmed.startsWith('## ')) {
      flushList()
      elements.push(
        <h4 key={`h-${index}`} className="chat-header">
          {formatInline(trimmed.slice(3))}
        </h4>
      )
    } else if (trimmed.startsWith('# ')) {
      flushList()
      elements.push(
        <h3 key={`h-${index}`} className="chat-header">
          {formatInline(trimmed.slice(2))}
        </h3>
      )
    }
    // Bullet points (-, *, •, or numbered)
    else if (trimmed.match(/^[-*•]\s/) || trimmed.match(/^\d+\.\s/)) {
      const content = trimmed.replace(/^[-*•]\s/, '').replace(/^\d+\.\s/, '')
      if (content) {
        listItems.push(content)
      }
    }
    // Standalone bullet marker (edge case)
    else if (trimmed === '-' || trimmed === '*' || trimmed === '•') {
      // Skip standalone bullets, content should be on next line
    }
    // Empty line
    else if (trimmed === '') {
      flushList()
      // Don't add excessive spacing
    }
    // Regular paragraph (but check if previous was a standalone bullet)
    else {
      // If we have pending list items or this looks like list content, add to list
      if (listItems.length > 0 && !trimmed.startsWith('#')) {
        // This might be continuation of a list item - skip it as it was likely joined
      } else {
        flushList()
        elements.push(
          <p key={`p-${index}`} className="chat-paragraph">
            {formatInline(trimmed)}
          </p>
        )
      }
    }
  })

  flushList()

  return <div className="chat-markdown">{elements}</div>
}

interface AssistPanelProps {
  selectedTask: Task | null
  latestPlan: AssistPlan | null
  running: boolean
  planGenerating: boolean
  researchRunning: boolean
  researchResults: string | null
  gmailAccount: string
  onGmailChange: (account: string) => void
  onRunAssist: (options?: { sendEmailAccount?: string }) => void
  onGeneratePlan: () => void
  onRunResearch: () => void
  gmailOptions: string[]
  error?: string | null
  conversation: ConversationMessage[]
  conversationLoading: boolean
  onSendMessage: (message: string) => Promise<void> | void
  sendingMessage: boolean
  taskPanelCollapsed: boolean
  onExpandTasks: () => void
  onCollapseTasks: () => void
  onQuickAction?: (action: { type: string; content: string }) => void
  // Task update confirmation props
  pendingAction?: PendingAction | null
  updateExecuting?: boolean
  onConfirmUpdate?: () => void
  onCancelUpdate?: () => void
  // Feedback callback
  onFeedbackSubmit?: OnFeedbackSubmit
}

function formatPendingAction(action: PendingAction): string {
  switch (action.action) {
    case 'mark_complete':
      return 'Mark this task as complete'
    case 'update_status':
      return `Update status to "${action.status}"`
    case 'update_priority':
      return `Change priority to "${action.priority}"`
    case 'update_due_date':
      return `Update due date to ${action.dueDate}`
    case 'add_comment':
      return `Add comment: "${(action.comment ?? '').slice(0, 50)}${(action.comment?.length ?? 0) > 50 ? '...' : ''}"`
    default:
      return `Perform action: ${action.action}`
  }
}

export function AssistPanel({
  selectedTask,
  latestPlan,
  running,
  planGenerating,
  researchRunning,
  researchResults,
  onRunAssist,
  onGeneratePlan,
  onRunResearch,
  error,
  conversation,
  conversationLoading,
  onSendMessage,
  sendingMessage,
  taskPanelCollapsed,
  onExpandTasks,
  onQuickAction,
  pendingAction,
  updateExecuting,
  onConfirmUpdate,
  onCancelUpdate,
  onFeedbackSubmit,
}: AssistPanelProps) {
  const [showFullNotes, setShowFullNotes] = useState(false)
  const [message, setMessage] = useState('')
  const [activeAction, setActiveAction] = useState<string | null>(null)

  useEffect(() => {
    setShowFullNotes(false)
    setMessage('')
    setActiveAction(null)
  }, [selectedTask?.rowId])

  const disableSend = sendingMessage || !message.trim()
  const hasPlan = !!latestPlan

  const handleActionClick = (action: string) => {
    setActiveAction(action)
    
    // Handle specific actions
    if (action === 'research') {
      onRunResearch()
    } else {
      onQuickAction?.({ type: action, content: `Help me with: ${action}` })
    }
  }

  // No task selected - prompt user
  if (!selectedTask) {
    return (
      <section className="panel assist-panel">
        <header>
          <h2>Assistant</h2>
          <button className="secondary" onClick={onExpandTasks}>
            Show tasks
          </button>
        </header>
        <p>Select a task to view details.</p>
      </section>
    )
  }

  // Task selected but not engaged - show preview with Engage button
  if (!hasPlan) {
    return (
      <section className="panel assist-panel">
        <header>
          <h2>Assistant</h2>
          {taskPanelCollapsed && (
            <button className="secondary" onClick={onExpandTasks}>
              Show tasks
            </button>
          )}
        </header>
        <div className="task-badges">
          <span className="badge status">{selectedTask.status}</span>
          {selectedTask.priority && (
            <span className={`badge priority ${selectedTask.priority.toLowerCase()}`}>
              {selectedTask.priority}
            </span>
          )}
          <span className="badge due">{new Date(selectedTask.due).toLocaleString()}</span>
        </div>
        <div className="task-title-row">
          <strong>{selectedTask.title}</strong>
          <span className="project-name">{selectedTask.project}</span>
          {selectedTask.assignedTo && (
            <span className="owner">Owner: {selectedTask.assignedTo}</span>
          )}
        </div>
        {selectedTask.notes && (
          <p className="task-notes">{notesPreview(selectedTask.notes)}</p>
        )}
        <button
          className="primary run-assist-btn"
          disabled={running}
          onClick={() => onRunAssist()}
        >
          {running ? 'Loading…' : 'Engage DATA'}
        </button>
        {error && <p className="warning">{error}</p>}
      </section>
    )
  }

  // After Run Assist - full collaboration view
  return (
    <section className="panel assist-panel-full">
      {/* Header row */}
      <header className="assist-header-compact">
        <h2>Assistant</h2>
        <button className="secondary compact" onClick={onExpandTasks}>
          Show tasks
        </button>
      </header>

      {/* Task info + Action buttons row */}
      <div className="task-action-row">
        <div className="task-info-compact">
          <div className="task-badges-inline">
            <span className="badge status">{selectedTask.status}</span>
            {selectedTask.priority && (
              <span className={`badge priority ${selectedTask.priority.toLowerCase()}`}>
                {selectedTask.priority}
              </span>
            )}
            <span className="badge due">{new Date(selectedTask.due).toLocaleString()}</span>
          </div>
          <strong className="task-title-compact">{selectedTask.title}</strong>
          <span className="project-compact">{selectedTask.project}</span>
        </div>
        <div className="action-buttons-row">
          <button
            className={`action-btn plan-btn ${activeAction === 'plan' ? 'active' : ''}`}
            onClick={onGeneratePlan}
            disabled={planGenerating}
          >
            {planGenerating ? 'Planning…' : formatActionLabel('plan')}
          </button>
          {latestPlan.suggestedActions
            ?.filter((action) => action !== 'plan')
            .map((action) => (
              <button
                key={action}
                className={`action-btn ${activeAction === action ? 'active' : ''}`}
                onClick={() => handleActionClick(action)}
              >
                {formatActionLabel(action)}
              </button>
            ))}
        </div>
      </div>

      {/* Notes if present */}
      {selectedTask.notes && (
        <p className="notes-compact">
          {showFullNotes ? selectedTask.notes : notesPreview(selectedTask.notes)}
          {selectedTask.notes.length > NOTES_PREVIEW_LIMIT && (
            <button className="link-button" onClick={() => setShowFullNotes(!showFullNotes)}>
              {showFullNotes ? 'less' : 'more'}
            </button>
          )}
        </p>
      )}

      {/* Two-column: Plan (left) + Action Output (right) */}
      <div className="plan-action-grid">
        {/* Left column: Plan details */}
        <div className="plan-column">
          <div className="plan-section">
            <h4>Current plan</h4>
            <p className="plan-summary-text">{truncateCopy(latestPlan.summary, 150)}</p>
          </div>

          <div className="plan-section">
            <h4>Next steps</h4>
            <ul className="compact-list">
              {latestPlan.nextSteps.slice(0, 4).map((step, i) => (
                <li key={i}>{step}</li>
              ))}
            </ul>
          </div>

          <div className="plan-section">
            <h4>Efficiency tips</h4>
            <ul className="compact-list">
              {latestPlan.efficiencyTips.slice(0, 3).map((tip, i) => (
                <li key={i}>{tip}</li>
              ))}
            </ul>
          </div>
        </div>

        {/* Right column: Action output area */}
        <div className="action-output-column">
          {activeAction === 'research' ? (
            <div className="action-output-content">
              <div className="action-output-header">
                <h4>{formatActionLabel('research')}</h4>
                {researchResults && (
                  <button
                    className="copy-btn"
                    onClick={() => {
                      navigator.clipboard.writeText(researchResults)
                      // Could add a toast notification here
                    }}
                    title="Copy to clipboard"
                  >
                    📋 Copy
                  </button>
                )}
              </div>
              {researchRunning ? (
                <div className="research-loading">
                  <p className="subtle">🔍 Searching the web...</p>
                  <p className="subtle">This may take a moment.</p>
                </div>
              ) : researchResults ? (
                <div className="research-results">
                  {renderMarkdown(researchResults)}
                  {onFeedbackSubmit && (
                    <FeedbackControls
                      context="research"
                      messageContent={researchResults}
                      onSubmit={onFeedbackSubmit}
                    />
                  )}
                </div>
              ) : (
                <p className="subtle">Click Research to search for information about this task.</p>
              )}
            </div>
          ) : activeAction ? (
            <div className="action-output-content">
              <h4>{formatActionLabel(activeAction)}</h4>
              <p className="subtle">
                {activeAction === 'draft_email' 
                  ? 'Email drafting coming soon...'
                  : `${formatActionLabel(activeAction)} functionality coming soon...`
                }
              </p>
            </div>
          ) : (
            <div className="action-output-placeholder">
              <p className="subtle">
                Select an action above to see output here.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Conversation section - takes most space */}
      <div className="conversation-section">
        <h4>Conversation</h4>
        <div className="chat-thread-full">
          {conversationLoading ? (
            <p className="subtle">Loading...</p>
          ) : conversation.length === 0 ? (
            <p className="subtle">Start collaborating with DATA on this task.</p>
          ) : (
            conversation.map((entry, index) => (
              <div key={`${entry.ts}-${index}`} className={`chat-bubble ${entry.role}`}>
                <div className="chat-meta">
                  <span>{entry.role === 'assistant' ? 'DATA' : 'You'}</span>
                  <span>{new Date(entry.ts).toLocaleString()}</span>
                </div>
                <div className="chat-content">
                  {entry.role === 'assistant' 
                    ? renderMarkdown(entry.content)
                    : entry.content
                  }
                </div>
                {/* Feedback controls for assistant responses */}
                {entry.role === 'assistant' && onFeedbackSubmit && (
                  <FeedbackControls
                    context={entry.metadata?.source === 'research' ? 'research' : 
                             entry.metadata?.source === 'plan' ? 'plan' :
                             entry.metadata?.action ? 'task_update' : 'chat'}
                    messageContent={entry.content}
                    messageId={entry.metadata?.messageId as string | undefined}
                    onSubmit={onFeedbackSubmit}
                  />
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Pending action confirmation card */}
      {pendingAction && (
        <div className="pending-action-card">
          <div className="pending-action-header">
            <span className="pending-icon">⚡</span>
            <strong>Confirm Smartsheet Update</strong>
          </div>
          <p className="pending-action-description">
            {formatPendingAction(pendingAction)}
          </p>
          {pendingAction.reason && (
            <p className="pending-action-reason">
              <em>Reason: {pendingAction.reason}</em>
            </p>
          )}
          <div className="pending-action-buttons">
            <button
              className="confirm-btn"
              onClick={onConfirmUpdate}
              disabled={updateExecuting}
            >
              {updateExecuting ? 'Updating...' : '✓ Confirm'}
            </button>
            <button
              className="cancel-btn"
              onClick={onCancelUpdate}
              disabled={updateExecuting}
            >
              ✗ Cancel
            </button>
          </div>
        </div>
      )}

      {/* Chat input - pinned at bottom */}
      <form
        className="chat-input-bottom"
        onSubmit={async (e) => {
          e.preventDefault()
          if (!message.trim()) return
          const payload = message.trim()
          setMessage('')
          await onSendMessage(payload)
        }}
      >
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Message DATA..."
          rows={2}
          disabled={!!pendingAction}
        />
        <button type="submit" disabled={disableSend || !!pendingAction} className="send-btn">
          {sendingMessage ? '...' : 'Send'}
        </button>
      </form>
    </section>
  )
}
