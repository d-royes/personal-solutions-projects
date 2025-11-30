import { useCallback, useEffect, useRef, useState } from 'react'
import type { AssistPlan, ConversationMessage, Task } from '../types'
import type { FeedbackContext, FeedbackType, PendingAction } from '../api'

// Feedback callback type
type OnFeedbackSubmit = (
  feedback: FeedbackType,
  context: FeedbackContext,
  messageContent: string,
  messageId?: string
) => Promise<void>

// Workspace item pushed from conversation - editable text
interface WorkspaceItem {
  id: string
  content: string
  source: 'chat' | 'research' | 'plan'
  timestamp: Date
  isEditing?: boolean
}

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
    summarize: '📄 Summarize',
    contact: '📇 Contact',
    draft_email: '✉️ Draft Email',
    send_email: '📤 Send Email',
    review: '📝 Review',
    schedule: '📅 Schedule',
    follow_up: '📞 Follow Up',
    delegate: '👥 Delegate',
    organize: '📁 Organize',
  }
  return labels[action] || action.replace(/_/g, ' ')
}

// Fixed action buttons that are always available
const FIXED_ACTIONS = ['plan', 'research', 'summarize', 'contact', 'draft_email']

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

// Draggable divider component
function DraggableDivider({
  orientation,
  onDrag,
}: {
  orientation: 'vertical' | 'horizontal'
  onDrag: (delta: number) => void
}) {
  const isDragging = useRef(false)
  const startPos = useRef(0)

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    isDragging.current = true
    startPos.current = orientation === 'vertical' ? e.clientX : e.clientY
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    document.body.style.cursor = orientation === 'vertical' ? 'col-resize' : 'row-resize'
    document.body.style.userSelect = 'none'
  }

  const handleMouseMove = (e: MouseEvent) => {
    if (!isDragging.current) return
    const currentPos = orientation === 'vertical' ? e.clientX : e.clientY
    const delta = currentPos - startPos.current
    startPos.current = currentPos
    onDrag(delta)
  }

  const handleMouseUp = () => {
    isDragging.current = false
    document.removeEventListener('mousemove', handleMouseMove)
    document.removeEventListener('mouseup', handleMouseUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }

  return (
    <div
      className={`divider divider-${orientation}`}
      onMouseDown={handleMouseDown}
    >
      <div className="divider-handle" />
    </div>
  )
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
  
  // Three-zone layout state
  const [verticalSplit, setVerticalSplit] = useState(50) // % for planning zone width
  const [horizontalSplit, setHorizontalSplit] = useState(60) // % for top zones height
  const [conversationCollapsed, setConversationCollapsed] = useState(false)
  
  // Workspace items (content pushed from chat)
  const [workspaceItems, setWorkspaceItems] = useState<WorkspaceItem[]>([])
  
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setShowFullNotes(false)
    setMessage('')
    setActiveAction(null)
    setWorkspaceItems([])
  }, [selectedTask?.rowId])

  const disableSend = sendingMessage || !message.trim()
  const hasPlan = !!latestPlan

  const handleActionClick = (action: string) => {
    setActiveAction(action)
    
    // Handle specific actions
    if (action === 'research') {
      onRunResearch()
    } else if (action === 'summarize') {
      // Summarize will show in workspace, triggered via chat
      onQuickAction?.({ type: 'summarize', content: 'Please provide a summary of this task, including the current plan and any progress made.' })
    } else if (action === 'contact') {
      // Contact search will show in workspace
      onQuickAction?.({ type: 'contact', content: 'Please find contact information for any people or organizations mentioned in this task.' })
    } else if (action === 'draft_email') {
      // Draft email will show in workspace
      onQuickAction?.({ type: 'draft_email', content: 'Please draft an email related to this task.' })
    } else {
      onQuickAction?.({ type: action, content: `Help me with: ${action}` })
    }
  }
  
  // Handle vertical divider drag (between Planning and Collaboration zones)
  const handleVerticalDrag = useCallback((delta: number) => {
    if (!containerRef.current) return
    const containerWidth = containerRef.current.offsetWidth
    const deltaPercent = (delta / containerWidth) * 100
    setVerticalSplit(prev => Math.max(20, Math.min(80, prev + deltaPercent)))
  }, [])
  
  // Handle horizontal divider drag (between top zones and Conversation)
  const handleHorizontalDrag = useCallback((delta: number) => {
    if (!containerRef.current) return
    const containerHeight = containerRef.current.offsetHeight
    const deltaPercent = (delta / containerHeight) * 100
    setHorizontalSplit(prev => Math.max(20, Math.min(85, prev + deltaPercent)))
  }, [])
  
  // Conversation zone states: 'collapsed' (95%), 'normal' (60%), 'expanded' (15%)
  type ConversationState = 'collapsed' | 'normal' | 'expanded'
  
  const getConversationState = (): ConversationState => {
    if (horizontalSplit >= 90) return 'collapsed'
    if (horizontalSplit <= 20) return 'expanded'
    return 'normal'
  }
  
  // Cycle through conversation states: collapsed → normal → expanded → collapsed
  const cycleConversationState = () => {
    const currentState = getConversationState()
    switch (currentState) {
      case 'collapsed':
        // Go to normal (middle)
        setHorizontalSplit(60)
        setConversationCollapsed(false)
        break
      case 'normal':
        // Go to expanded (conversation takes most space)
        setHorizontalSplit(15)
        setConversationCollapsed(false)
        break
      case 'expanded':
        // Go to collapsed
        setHorizontalSplit(95)
        setConversationCollapsed(true)
        break
    }
  }
  
  // Get arrow direction based on state
  const getConversationArrow = (): string => {
    const state = getConversationState()
    // Collapsed → show up arrow (will expand)
    // Normal → show up arrow (will expand more)
    // Expanded → show down arrow (will collapse)
    return state === 'expanded' ? '▼' : '▲'
  }
  
  // Push content to workspace
  const pushToWorkspace = (content: string, source: 'chat' | 'research' | 'plan') => {
    const newItem: WorkspaceItem = {
      id: `ws-${Date.now()}`,
      content,
      source,
      timestamp: new Date(),
    }
    setWorkspaceItems(prev => [...prev, newItem])
  }
  
  // Push full plan to workspace (includes all sections)
  const pushFullPlanToWorkspace = () => {
    if (!latestPlan) return
    
    const planParts: string[] = []
    
    // Summary
    if (latestPlan.summary) {
      planParts.push(`## Current Plan\n${latestPlan.summary}`)
    }
    
    // Next Steps
    if (latestPlan.nextSteps && latestPlan.nextSteps.length > 0) {
      const steps = latestPlan.nextSteps.map(step => `- ${step}`).join('\n')
      planParts.push(`## Next Steps\n${steps}`)
    }
    
    // Efficiency Tips
    if (latestPlan.efficiencyTips && latestPlan.efficiencyTips.length > 0) {
      const tips = latestPlan.efficiencyTips.map(tip => `- ${tip}`).join('\n')
      planParts.push(`## Efficiency Tips\n${tips}`)
    }
    
    const fullPlanContent = planParts.join('\n\n')
    pushToWorkspace(fullPlanContent, 'plan')
  }
  
  // Remove item from workspace
  const removeFromWorkspace = (id: string) => {
    setWorkspaceItems(prev => prev.filter(item => item.id !== id))
  }
  
  // Clear all workspace items
  const clearWorkspace = () => {
    setWorkspaceItems([])
  }
  
  // Update workspace item content (for editing)
  const updateWorkspaceItem = (id: string, newContent: string) => {
    setWorkspaceItems(prev => prev.map(item => 
      item.id === id ? { ...item, content: newContent } : item
    ))
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

  // Collapse tasks and engage (for Expand button)
  const handleExpandAssistant = () => {
    // First collapse tasks, then engage if not already engaged
    if (!taskPanelCollapsed) {
      onRunAssist()
    }
  }

  // Task selected but not engaged - show preview with Engage button
  if (!hasPlan) {
    return (
      <section className="panel assist-panel">
        <header>
          <h2>Assistant</h2>
          <div className="assist-header-controls">
            {taskPanelCollapsed && (
              <button className="secondary" onClick={onExpandTasks}>
                Show tasks
              </button>
            )}
            {!taskPanelCollapsed && (
              <button 
                className="secondary expand-btn" 
                title="Expand Assistant panel"
                onClick={handleExpandAssistant}
              >
                ⛶ Expand
              </button>
            )}
          </div>
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
          <p className="task-notes">{selectedTask.notes}</p>
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

  // After Engage DATA - Three-zone collaboration view
  return (
    <section className="panel assist-panel-three-zone" ref={containerRef}>
      {/* Header row */}
      <header className="assist-header-compact">
        <div className="header-left-group">
          <h2>Assistant</h2>
          <div className="task-badges-inline">
            <span className="badge status">{selectedTask.status}</span>
            {selectedTask.priority && (
              <span className={`badge priority ${selectedTask.priority.toLowerCase()}`}>
                {selectedTask.priority}
              </span>
            )}
          </div>
          <strong className="task-title-compact">{selectedTask.title}</strong>
        </div>
        <div className="action-buttons-row">
          {/* Fixed actions - always available */}
          {FIXED_ACTIONS.map((action) => (
            <button
              key={action}
              className={`action-btn ${activeAction === action ? 'active' : ''} ${action === 'plan' ? 'plan-btn' : ''}`}
              onClick={() => action === 'plan' ? onGeneratePlan() : handleActionClick(action)}
              disabled={action === 'plan' && planGenerating}
            >
              {action === 'plan' && planGenerating ? 'Planning…' : formatActionLabel(action)}
            </button>
          ))}
          {/* Show/Expand toggle based on current state */}
          {taskPanelCollapsed ? (
            <button className="secondary compact" onClick={onExpandTasks}>
              Show tasks
            </button>
          ) : (
            <button 
              className="secondary compact expand-btn" 
              onClick={() => {
                // Collapse task panel to expand assistant
                onRunAssist()
              }}
              title="Expand Assistant panel"
            >
              ⛶ Expand
            </button>
          )}
        </div>
      </header>

      {/* Notes row - full width, collapsible */}
      {selectedTask.notes && (
        <div className="notes-row">
          <span className="notes-label">Notes:</span>
          <span className="notes-text">
            {showFullNotes ? selectedTask.notes : notesPreview(selectedTask.notes)}
          </span>
          {selectedTask.notes.length > NOTES_PREVIEW_LIMIT && (
            <button className="link-button" onClick={() => setShowFullNotes(!showFullNotes)}>
              {showFullNotes ? 'less' : 'more'}
            </button>
          )}
        </div>
      )}

      {/* Three-zone content area */}
      <div className="three-zone-container">
        {/* Top zones: Planning + Collaboration */}
        <div 
          className="top-zones"
          style={{ height: `${horizontalSplit}%` }}
        >
          {/* Planning Zone (left) */}
          <div 
            className="planning-zone"
            style={{ width: `${verticalSplit}%` }}
          >
            <div className="zone-header">
              <h4>Planning</h4>
            </div>
            <div className="zone-content">
              {latestPlan.summary ? (
                <>
                  <div className="plan-section">
                    <h5>
                      Current Plan
                      {latestPlan.generatedAt && (
                        <span className="plan-date">
                          {new Date(latestPlan.generatedAt).toLocaleDateString()}
                        </span>
                      )}
                    </h5>
                    <p className="plan-summary-text">{latestPlan.summary}</p>
                    <button 
                      className="push-btn"
                      onClick={pushFullPlanToWorkspace}
                      title="Push full plan to Workspace"
                    >
                      ➡️
                    </button>
                  </div>

                  {latestPlan.nextSteps.length > 0 && (
                    <div className="plan-section">
                      <h5>Next Steps</h5>
                      <ul className="compact-list">
                        {latestPlan.nextSteps.map((step, i) => (
                          <li key={i}>{step}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {latestPlan.efficiencyTips.length > 0 && (
                    <div className="plan-section">
                      <h5>Efficiency Tips</h5>
                      <ul className="compact-list">
                        {latestPlan.efficiencyTips.map((tip, i) => (
                          <li key={i}>{tip}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              ) : (
                <div className="zone-placeholder">
                  <p className="subtle">Click "Plan" to generate an action plan for this task.</p>
                </div>
              )}
            </div>
          </div>

          {/* Vertical Divider */}
          <DraggableDivider orientation="vertical" onDrag={handleVerticalDrag} />

          {/* Collaboration Zone (right) */}
          <div 
            className="collaboration-zone"
            style={{ width: `${100 - verticalSplit}%` }}
          >
            <div className="zone-header">
              <h4>Workspace</h4>
              {workspaceItems.length > 0 && (
                <div className="workspace-controls">
                  <button
                    className="copy-btn"
                    onClick={() => {
                      const allContent = workspaceItems.map(item => item.content).join('\n\n---\n\n')
                      navigator.clipboard.writeText(allContent)
                    }}
                    title="Copy all"
                  >
                    📋
                  </button>
                  <button
                    className="clear-btn"
                    onClick={clearWorkspace}
                    title="Clear workspace"
                  >
                    🗑️
                  </button>
                </div>
              )}
            </div>
            <div className="zone-content workspace-content">
              {workspaceItems.length > 0 ? (
                workspaceItems.map((item, index) => (
                  <div key={item.id} className="workspace-item-editable">
                    {index > 0 && <div className="workspace-divider" />}
                    <div className="workspace-item-toolbar">
                      <span className="workspace-item-source">{item.source}</span>
                      <span className="workspace-item-time">
                        {item.timestamp.toLocaleTimeString()}
                      </span>
                      <button
                        className="workspace-item-remove"
                        onClick={() => removeFromWorkspace(item.id)}
                        title="Remove"
                      >
                        ×
                      </button>
                    </div>
                    <textarea
                      className="workspace-editor"
                      value={item.content}
                      onChange={(e) => updateWorkspaceItem(item.id, e.target.value)}
                      placeholder="Edit content here..."
                    />
                  </div>
                ))
              ) : activeAction === 'research' ? (
                <div className="action-output-content">
                  <div className="action-output-header">
                    <h5>{formatActionLabel('research')}</h5>
                    {researchResults && (
                      <button
                        className="push-btn"
                        onClick={() => pushToWorkspace(researchResults, 'research')}
                        title="Push to Workspace"
                      >
                        ➡️
                      </button>
                    )}
                  </div>
                  {researchRunning ? (
                    <div className="research-loading">
                      <p className="subtle">🔍 Searching the web...</p>
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
                    <p className="subtle">Click Research to search for information.</p>
                  )}
                </div>
              ) : (
                <div className="zone-placeholder">
                  <p className="subtle">
                    Push content here from the conversation or run an action.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Horizontal Divider with single toggle on right */}
        <div className="horizontal-divider-container">
          <DraggableDivider orientation="horizontal" onDrag={handleHorizontalDrag} />
          <button 
            className="conversation-toggle"
            onClick={cycleConversationState}
            title={
              getConversationState() === 'collapsed' ? 'Expand conversation' :
              getConversationState() === 'normal' ? 'Maximize conversation' :
              'Collapse conversation'
            }
          >
            {getConversationArrow()}
          </button>
        </div>

        {/* Conversation Zone (bottom) */}
        <div 
          className={`conversation-zone ${conversationCollapsed ? 'collapsed' : ''}`}
          style={{ height: `${100 - horizontalSplit}%` }}
        >
          <div className="zone-header">
            <h4>Conversation</h4>
          </div>
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
                    {entry.role === 'assistant' && (
                      <button
                        className="push-btn-inline"
                        onClick={() => pushToWorkspace(entry.content, 'chat')}
                        title="Push to Workspace"
                      >
                        ➡️
                      </button>
                    )}
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
      </div>

      {/* Pending action confirmation card */}
      {pendingAction && (
        <div className="pending-action-card">
          <div className="pending-action-header">
            <span className="pending-icon">⚡</span>
            <strong>Confirm</strong>
          </div>
          <div className="pending-action-content">
            <p className="pending-action-description">
              {formatPendingAction(pendingAction)}
            </p>
            {pendingAction.reason && (
              <p className="pending-action-reason">
                {pendingAction.reason}
              </p>
            )}
          </div>
          <div className="pending-action-buttons">
            <button
              className="confirm-btn"
              onClick={onConfirmUpdate}
              disabled={updateExecuting}
            >
              {updateExecuting ? '...' : '✓ Yes'}
            </button>
            <button
              className="cancel-btn"
              onClick={onCancelUpdate}
              disabled={updateExecuting}
            >
              ✗ No
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
