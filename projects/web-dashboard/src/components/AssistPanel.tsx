import { useCallback, useEffect, useRef, useState } from 'react'
import type { AssistPlan, ConversationMessage, Task, FirestoreTask } from '../types'
import type { AttachmentInfo, ContactCard, ContactSearchResponse, FeedbackContext, FeedbackType, PendingAction } from '../api'
import { EmailDraftPanel, type EmailDraft } from './EmailDraftPanel'
import { AttachmentsGallery } from './AttachmentsGallery'

// Feedback callback type
type OnFeedbackSubmit = (
  feedback: FeedbackType,
  context: FeedbackContext,
  messageContent: string,
  messageId?: string
) => Promise<void>

// Workspace item - simple editable text block
interface WorkspaceItem {
  id: string
  content: string
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

// FirestoreTask is imported from types

interface AssistPanelProps {
  selectedTask: Task | null
  // Firestore task support
  selectedFirestoreTask?: FirestoreTask | null
  onFirestoreTaskUpdate?: (taskId: string, updates: Record<string, unknown>) => Promise<void>
  onFirestoreTaskDelete?: (taskId: string) => Promise<void>
  onFirestoreTaskClose?: () => void
  latestPlan: AssistPlan | null
  isEngaged?: boolean  // Whether we've engaged with the current task (separate from having a plan)
  running: boolean
  planGenerating: boolean
  researchRunning: boolean
  summarizeRunning: boolean
  contactRunning: boolean
  contactResults: ContactCard[] | null
  contactConfirmation: ContactSearchResponse | null
  gmailAccount: string
  onGmailChange: (account: string) => void
  onRunAssist: (options?: { sendEmailAccount?: string }) => void
  onGeneratePlan: (contextItems?: string[]) => void
  onClearPlan?: () => void
  onRunResearch: () => void
  onRunSummarize: () => void
  onRunContact: (confirmSearch?: boolean) => void
  gmailOptions: string[]
  error?: string | null
  conversation: ConversationMessage[]
  conversationLoading: boolean
  onSendMessage: (message: string, workspaceContext?: string) => Promise<void> | void
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
  // Workspace persistence
  initialWorkspaceItems?: string[]
  onWorkspaceChange?: (items: string[]) => void
  // Selected workspace item index for email drafting
  selectedWorkspaceIndex?: number | null
  onSelectWorkspaceItem?: (index: number | null) => void
  // Email draft props
  onDraftEmail?: (sourceContent: string, recipient?: string, regenerateInput?: string) => Promise<{ subject: string; body: string; bodyHtml?: string }>
  onSendEmail?: (draft: EmailDraft) => Promise<void>
  onSaveDraft?: (draft: EmailDraft) => Promise<void>
  onDeleteDraft?: () => Promise<void>
  onToggleEmailDraft?: () => void
  emailDraftLoading?: boolean
  emailSending?: boolean
  emailError?: string | null
  savedDraft?: {
    to: string[]
    cc: string[]
    subject: string
    body: string
    fromAccount: string
  } | null
  emailDraftOpen?: boolean
  setEmailDraftOpen?: (open: boolean) => void
  // Strike/unstrike message handlers
  onStrikeMessage?: (messageTs: string) => Promise<void>
  onUnstrikeMessage?: (messageTs: string) => Promise<void>
  // Global Mode props
  globalPerspective?: 'personal' | 'church' | 'work' | 'holistic'
  onPerspectiveChange?: (perspective: 'personal' | 'church' | 'work' | 'holistic') => void
  globalConversation?: ConversationMessage[]
  globalStats?: {
    totalOpen: number
    overdue: number
    dueToday: number
    dueThisWeek: number
    byPriority: Record<string, number>
    byProject: Record<string, number>
    byDueDate: Record<string, number>
    conflicts: string[]
    domainBreakdown: Record<string, number>
  } | null
  onSendGlobalMessage?: (message: string) => Promise<void>
  globalChatLoading?: boolean
  onClearGlobalHistory?: () => Promise<void>
  globalExpanded?: boolean
  onToggleGlobalExpand?: () => void
  onStrikeGlobalMessages?: (messageTimestamps: string[]) => Promise<void>
  onDeleteGlobalMessage?: (messageTs: string) => Promise<void>
  // Attachment props
  attachments?: AttachmentInfo[]
  attachmentsLoading?: boolean
  selectedAttachmentIds?: Set<string>
  onAttachmentSelectionChange?: (ids: Set<string>) => void
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
    case 'update_number':
      return `Update task number to ${action.number}`
    case 'update_contact_flag':
      return `Set contact flag to ${action.contactFlag ? 'checked' : 'unchecked'}`
    case 'update_recurring':
      return `Set recurring pattern to "${action.recurring}"`
    case 'update_project':
      return `Change project to "${action.project}"`
    case 'update_task':
      return `Update task title to "${(action.taskTitle ?? '').slice(0, 50)}${(action.taskTitle?.length ?? 0) > 50 ? '...' : ''}"`
    case 'update_assigned_to':
      return `Assign to "${action.assignedTo}"`
    case 'update_notes':
      return `Update notes to "${(action.notes ?? '').slice(0, 50)}${(action.notes?.length ?? 0) > 50 ? '...' : ''}"`
    case 'update_estimated_hours':
      return `Set estimated hours to ${action.estimatedHours}`
    default:
      return `Perform action: ${action.action}`
  }
}

export function AssistPanel({
  selectedTask,
  // Firestore task props
  selectedFirestoreTask,
  onFirestoreTaskUpdate,
  onFirestoreTaskDelete,
  onFirestoreTaskClose,
  latestPlan,
  isEngaged = false,
  running,
  planGenerating,
  researchRunning,
  summarizeRunning,
  contactRunning,
  contactResults,
  contactConfirmation,
  onRunAssist,
  onGeneratePlan,
  onClearPlan,
  onRunResearch,
  onRunSummarize,
  onRunContact,
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
  initialWorkspaceItems,
  onWorkspaceChange,
  selectedWorkspaceIndex,
  onSelectWorkspaceItem: _onSelectWorkspaceItem,
  onDraftEmail,
  onSendEmail,
  onSaveDraft,
  onDeleteDraft,
  onToggleEmailDraft: _onToggleEmailDraft,
  emailDraftLoading,
  emailSending,
  emailError,
  savedDraft,
  emailDraftOpen: emailDraftOpenProp,
  setEmailDraftOpen: setEmailDraftOpenProp,
  onStrikeMessage,
  onUnstrikeMessage,
  // Global Mode props
  globalPerspective,
  onPerspectiveChange,
  globalConversation,
  globalStats,
  onSendGlobalMessage,
  globalChatLoading,
  onClearGlobalHistory,
  globalExpanded,
  onToggleGlobalExpand,
  onStrikeGlobalMessages,
  onDeleteGlobalMessage,
  // Attachment props
  attachments,
  attachmentsLoading: _attachmentsLoading,
  selectedAttachmentIds,
  onAttachmentSelectionChange,
}: AssistPanelProps) {
  const [showFullNotes, setShowFullNotes] = useState(false)
  const [attachmentsCollapsed, setAttachmentsCollapsed] = useState(false)
  const [message, setMessage] = useState('')
  const [activeAction, setActiveAction] = useState<string | null>(null)
  
  // Email draft panel state - use props if provided, otherwise local state
  const [localEmailDraftOpen, setLocalEmailDraftOpen] = useState(false)
  const emailDraftOpen = emailDraftOpenProp ?? localEmailDraftOpen
  const setEmailDraftOpen = setEmailDraftOpenProp ?? setLocalEmailDraftOpen
  const [emailDraft, setEmailDraft] = useState<Partial<EmailDraft> | null>(null)
  
  // Three-zone layout state
  const [verticalSplit, setVerticalSplit] = useState(50) // % for planning zone width
  const [horizontalSplit, setHorizontalSplit] = useState(60) // % for top zones height
  const [conversationCollapsed, setConversationCollapsed] = useState(false)
  
  // Portfolio dashboard collapsed state (for global mode)
  const [dashboardCollapsed, setDashboardCollapsed] = useState(true)
  
  // Firestore task edit mode state
  const [isEditingFirestore, setIsEditingFirestore] = useState(false)
  const [editTitle, setEditTitle] = useState('')
  const [editStatus, setEditStatus] = useState('')
  const [editPriority, setEditPriority] = useState('')
  const [editPlannedDate, setEditPlannedDate] = useState('')
  const [editTargetDate, setEditTargetDate] = useState('')
  const [editHardDeadline, setEditHardDeadline] = useState('')
  const [editNotes, setEditNotes] = useState('')
  const [editSaving, setEditSaving] = useState(false)
  
  // Workspace items (content pushed from chat) - initialized from props
  const [workspaceItems, setWorkspaceItems] = useState<WorkspaceItem[]>(() => {
    if (initialWorkspaceItems && initialWorkspaceItems.length > 0) {
      return initialWorkspaceItems.map((content, index) => ({
        id: `ws-init-${index}`,
        content,
      }))
    }
    return []
  })
  
  const containerRef = useRef<HTMLDivElement>(null)
  
  // Track if workspace has been modified by user (not just initialized)
  const workspaceModifiedRef = useRef(false)

  // Re-initialize workspace when initialWorkspaceItems changes (task switch)
  useEffect(() => {
    // Reset modified flag when loading new workspace data
    workspaceModifiedRef.current = false
    if (initialWorkspaceItems) {
      setWorkspaceItems(
        initialWorkspaceItems.map((content, index) => ({
          id: `ws-init-${index}`,
          content,
        }))
      )
    } else {
      setWorkspaceItems([])
    }
  }, [initialWorkspaceItems])

  useEffect(() => {
    setShowFullNotes(false)
    setMessage('')
    setActiveAction(null)
    // Reset modified flag when task changes
    workspaceModifiedRef.current = false
    // Clear workspace selections when task changes
    setSelectedWorkspaceIds(new Set())
  }, [selectedTask?.rowId])
  
  // Reset edit mode when Firestore task changes
  useEffect(() => {
    setIsEditingFirestore(false)
    if (selectedFirestoreTask) {
      setEditTitle(selectedFirestoreTask.title || '')
      setEditStatus(selectedFirestoreTask.status || 'scheduled')
      setEditPriority(selectedFirestoreTask.priority || 'Standard')
      setEditPlannedDate(selectedFirestoreTask.plannedDate || selectedFirestoreTask.dueDate || '')
      setEditTargetDate(selectedFirestoreTask.targetDate || '')
      setEditHardDeadline(selectedFirestoreTask.hardDeadline || '')
      setEditNotes(selectedFirestoreTask.notes || '')
    }
  }, [selectedFirestoreTask?.id])
  
  // Notify parent when workspace changes (for persistence) - only if modified by user
  useEffect(() => {
    if (onWorkspaceChange && workspaceModifiedRef.current) {
      const contents = workspaceItems.map(item => item.content)
      onWorkspaceChange(contents)
    }
  }, [workspaceItems, onWorkspaceChange])

  const disableSend = sendingMessage || !message.trim()

  const handleActionClick = async (action: string) => {
    setActiveAction(action)
    
    // Handle specific actions
    if (action === 'research') {
      onRunResearch()
    } else if (action === 'summarize') {
      // Run the summarize action
      onRunSummarize()
    } else if (action === 'contact') {
      // Run contact search
      onRunContact()
    } else if (action === 'draft_email') {
      // Open email draft panel
      await handleOpenEmailDraft()
    } else {
      onQuickAction?.({ type: action, content: `Help me with: ${action}` })
    }
  }
  
  // Handle opening email draft panel
  const handleOpenEmailDraft = async () => {
    // If we have a saved draft, just open the panel with it
    if (savedDraft && (savedDraft.subject || savedDraft.body || savedDraft.to.length > 0)) {
      setEmailDraft({
        subject: savedDraft.subject,
        body: savedDraft.body,
        to: savedDraft.to,
        cc: savedDraft.cc,
        fromAccount: savedDraft.fromAccount,
      })
      setEmailDraftOpen(true)
      return
    }
    
    // No saved draft - generate a new one
    if (!onDraftEmail) return

    // Get source content - prioritize checkbox-selected items, then single selection, then plan
    let sourceContent = ''
    const selectedContent = getSelectedWorkspaceContent()
    if (selectedContent.length > 0) {
      // Use checkbox-selected workspace items
      sourceContent = selectedContent.join('\n\n---\n\n')
    } else if (selectedWorkspaceIndex !== null && selectedWorkspaceIndex !== undefined && workspaceItems[selectedWorkspaceIndex]) {
      sourceContent = workspaceItems[selectedWorkspaceIndex].content
    } else if (latestPlan) {
      // Use plan summary as source
      sourceContent = [
        latestPlan.summary,
        ...(latestPlan.nextSteps || []).map(s => `- ${s}`),
      ].filter(Boolean).join('\n')
    }
    
    try {
      const result = await onDraftEmail(sourceContent)
      setEmailDraft({
        subject: result.subject,
        body: result.body,
        bodyHtml: result.bodyHtml,
        to: [],
        cc: [],
        fromAccount: '',
      })
      setEmailDraftOpen(true)
    } catch (err) {
      console.error('Failed to generate email draft:', err)
    }
  }
  
  // Handle sending email
  const handleSendEmail = async (draft: EmailDraft) => {
    if (!onSendEmail) return
    await onSendEmail(draft)
    // Close panel on success (backend deletes draft)
    setEmailDraftOpen(false)
    setEmailDraft(null)
  }
  
  // Handle regenerating email draft
  const handleRegenerateEmail = async (instructions: string) => {
    if (!onDraftEmail || !emailDraft) return

    // Get source content - prioritize checkbox-selected items, then single selection, then plan
    let sourceContent = ''
    const selectedContent = getSelectedWorkspaceContent()
    if (selectedContent.length > 0) {
      sourceContent = selectedContent.join('\n\n---\n\n')
    } else if (selectedWorkspaceIndex !== null && selectedWorkspaceIndex !== undefined && workspaceItems[selectedWorkspaceIndex]) {
      sourceContent = workspaceItems[selectedWorkspaceIndex].content
    } else if (latestPlan) {
      sourceContent = [
        latestPlan.summary,
        ...(latestPlan.nextSteps || []).map(s => `- ${s}`),
      ].filter(Boolean).join('\n')
    }
    
    try {
      const result = await onDraftEmail(sourceContent, undefined, instructions)
      setEmailDraft(prev => ({
        ...prev,
        subject: result.subject,
        body: result.body,
        bodyHtml: result.bodyHtml,
      }))
    } catch (err) {
      console.error('Failed to regenerate email draft:', err)
    }
  }
  
  // Handle closing email draft panel - auto-save the draft
  const handleCloseEmailDraft = async (currentDraft: EmailDraft) => {
    // Update local draft state
    setEmailDraft(currentDraft)
    
    // Auto-save the current draft state before closing
    if (onSaveDraft && (currentDraft.subject || currentDraft.body || currentDraft.to.length > 0)) {
      await onSaveDraft({
        to: currentDraft.to,
        cc: currentDraft.cc,
        subject: currentDraft.subject,
        body: currentDraft.body,
        fromAccount: currentDraft.fromAccount,
      })
    }
    setEmailDraftOpen(false)
  }
  
  // Handle discarding email draft
  const handleDiscardEmailDraft = async () => {
    // Delete the draft from backend
    if (onDeleteDraft) {
      await onDeleteDraft()
    }
    // Clear local state
    setEmailDraft(null)
    setEmailDraftOpen(false)
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
  
  // Fix bullet points that are split across lines (e.g., "-\nContent" -> "- Content")
  const fixBulletFormatting = (text: string): string => {
    return text
      .replace(/^-\s*\n+/gm, '- ')      // Fix "- \n" at start of line
      .replace(/\n-\s*\n+/g, '\n- ')    // Fix "\n-\n" patterns
      .replace(/-\s*\n+(?=[A-Z])/g, '- ') // Fix "-\n" followed by capital letter
      .replace(/\n{3,}/g, '\n\n')       // Collapse excessive newlines
  }

  // Push content to workspace
  const pushToWorkspace = (content: string) => {
    workspaceModifiedRef.current = true
    const cleanedContent = fixBulletFormatting(content)
    const newItem: WorkspaceItem = {
      id: `ws-${Date.now()}`,
      content: cleanedContent,
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
    pushToWorkspace(fullPlanContent)
  }
  
  // Clear all workspace items
  const clearWorkspace = () => {
    workspaceModifiedRef.current = true
    setWorkspaceItems([])
    setSelectedWorkspaceIds(new Set())
  }
  
  // Update workspace item content (for editing)
  const updateWorkspaceItem = (id: string, newContent: string) => {
    workspaceModifiedRef.current = true
    setWorkspaceItems(prev => prev.map(item => 
      item.id === id ? { ...item, content: newContent } : item
    ))
  }
  
  // Remove a single workspace item
  const removeWorkspaceItem = (id: string) => {
    workspaceModifiedRef.current = true
    setWorkspaceItems(prev => prev.filter(item => item.id !== id))
  }

  // State for selected workspace items (for including in plan/email)
  const [selectedWorkspaceIds, setSelectedWorkspaceIds] = useState<Set<string>>(new Set())

  // Toggle workspace item selection
  const toggleWorkspaceSelection = (id: string) => {
    setSelectedWorkspaceIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  // Get content of selected workspace items
  const getSelectedWorkspaceContent = (): string[] => {
    return workspaceItems
      .filter(item => selectedWorkspaceIds.has(item.id))
      .map(item => item.content)
  }

  // State for selected messages in global chat (for bulk strike)
  const [selectedGlobalMessages, setSelectedGlobalMessages] = useState<Set<string>>(new Set())
  
  // State for quick questions collapsible - default expanded only if no history
  const [quickQuestionsExpanded, setQuickQuestionsExpanded] = useState(false)
  
  // Toggle message selection
  const toggleMessageSelection = (ts: string) => {
    setSelectedGlobalMessages(prev => {
      const next = new Set(prev)
      if (next.has(ts)) {
        next.delete(ts)
      } else {
        next.add(ts)
      }
      return next
    })
  }
  
  // Handle clear button - behavior depends on selection
  const handleGlobalClear = async () => {
    if (selectedGlobalMessages.size > 0 && onStrikeGlobalMessages) {
      // Strike selected messages (soft delete - preserved in DB)
      await onStrikeGlobalMessages(Array.from(selectedGlobalMessages))
      setSelectedGlobalMessages(new Set())
    } else if (onClearGlobalHistory) {
      // No selection - just reset UI (could also be a full clear)
      // For now, we'll just clear selections and do nothing to backend
      setSelectedGlobalMessages(new Set())
    }
  }

  // Firestore task selected (not engaged) - show task details with CRUD actions
  if (selectedFirestoreTask && !selectedTask && !isEngaged) {
    const task = selectedFirestoreTask
    const domain = task.domain || 'personal'
    const status = task.status || 'scheduled'
    const dueDate = task.plannedDate || task.dueDate
    
    // Format due date status - parse date as local midnight to avoid UTC issues
    const getDueStatus = () => {
      if (!dueDate) return { label: '', className: '' }
      // Get today at local midnight
      const today = new Date()
      today.setHours(0, 0, 0, 0)
      // Parse date string as local date (YYYY-MM-DD format)
      // Using split to avoid UTC parsing issues
      const [year, month, day] = dueDate.split('-').map(Number)
      const due = new Date(year, month - 1, day) // month is 0-indexed
      const diff = Math.round((due.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))
      if (diff < 0) return { label: `Overdue ${Math.abs(diff)}d`, className: 'overdue' }
      if (diff === 0) return { label: 'Due today', className: 'due-today' }
      if (diff === 1) return { label: 'Due tomorrow', className: 'due-soon' }
      if (diff <= 3) return { label: `Due in ${diff}d`, className: 'due-soon' }
      return { label: `Due in ${diff}d`, className: '' }
    }
    const dueStatus = getDueStatus()
    
    return (
      <section className="panel assist-panel firestore-task-view">
        <header>
          <div className="header-left-group">
            <h2>Assistant</h2>
            <div className="task-badges-inline">
              <span className={`badge domain ${domain}`}>{domain.charAt(0).toUpperCase() + domain.slice(1)}</span>
              <span className={`badge status ${status.toLowerCase().replace(/ /g, '-')}`}>
                {status.charAt(0).toUpperCase() + status.slice(1).replace(/_/g, ' ')}
              </span>
              {task.priority && (
                <span className={`badge priority ${task.priority.toLowerCase()}`}>{task.priority}</span>
              )}
            </div>
          </div>
          <div className="assist-header-controls">
            {taskPanelCollapsed && (
              <button className="secondary expand-btn" onClick={onExpandTasks}>
                ⛶ Expand
              </button>
            )}
            {onFirestoreTaskClose && (
              <button className="close-btn-small" onClick={onFirestoreTaskClose} title="Close">×</button>
            )}
          </div>
        </header>
        
        {/* Due status banner */}
        {dueStatus.label && (
          <div className={`fs-due-banner ${dueStatus.className}`}>{dueStatus.label}</div>
        )}
        
        {/* Task title and details */}
        <div className="fs-task-header">
          <strong className="fs-task-title">{task.title}</strong>
          <span className="fs-task-project">{task.project || 'No project'}</span>
        </div>
        
        {/* CRUD Action Buttons */}
        {!isEditingFirestore ? (
          <div className="fs-crud-actions">
            <button
              className="crud-btn complete-btn"
              onClick={async () => {
                if (onFirestoreTaskUpdate) {
                  // For recurring tasks: only check Done box (don't change status)
                  // This allows Smartsheet automation to reset the task
                  const isRecurring = task.isRecurring || !!task.recurringType
                  if (isRecurring) {
                    await onFirestoreTaskUpdate(task.id, {
                      done: true,
                      completedOn: new Date().toISOString().split('T')[0],
                    })
                  } else {
                    // For regular tasks: set both status and done
                    await onFirestoreTaskUpdate(task.id, {
                      done: true,
                      status: 'completed',
                      completedOn: new Date().toISOString().split('T')[0],
                    })
                  }
                }
              }}
              disabled={task.done}
            >
              {task.done ? '✓ Completed' : '✓ Mark Complete'}
            </button>
            <button
              className="crud-btn edit-btn"
              onClick={() => {
                setEditTitle(task.title || '')
                setEditStatus(task.status || 'scheduled')
                setEditPriority(task.priority || 'Standard')
                setEditPlannedDate(task.plannedDate || task.dueDate || '')
                setEditTargetDate(task.targetDate || '')
                setEditHardDeadline(task.hardDeadline || '')
                setEditNotes(task.notes || '')
                setIsEditingFirestore(true)
              }}
            >
              ✎ Edit
            </button>
            <button
              className="crud-btn delete-btn"
              onClick={async () => {
                if (onFirestoreTaskDelete && confirm('Delete this task?')) {
                  await onFirestoreTaskDelete(task.id)
                }
              }}
            >
              🗑 Delete
            </button>
          </div>
        ) : (
          /* Edit Form */
          <div className="fs-edit-form">
            <div className="fs-edit-field">
              <label>Title</label>
              <input
                type="text"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                className="fs-edit-input"
              />
            </div>
            <div className="fs-edit-row">
              <div className="fs-edit-field">
                <label>Status</label>
                <select
                  value={editStatus}
                  onChange={(e) => setEditStatus(e.target.value)}
                  className="fs-edit-select"
                >
                  <option value="scheduled">Scheduled</option>
                  <option value="in_progress">In Progress</option>
                  <option value="on_hold">On Hold</option>
                  <option value="awaiting_reply">Awaiting Reply</option>
                  <option value="follow_up">Follow-up</option>
                  <option value="completed">Completed</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              </div>
              <div className="fs-edit-field">
                <label>Priority</label>
                <select
                  value={editPriority}
                  onChange={(e) => setEditPriority(e.target.value)}
                  className="fs-edit-select"
                >
                  <option value="Critical">Critical</option>
                  <option value="Urgent">Urgent</option>
                  <option value="Important">Important</option>
                  <option value="Standard">Standard</option>
                  <option value="Low">Low</option>
                </select>
              </div>
            </div>
            {/* Dates - Three-Date Model */}
            <fieldset className="fs-edit-dates">
              <legend>Dates (Three-Date Model)</legend>
              <div className="fs-edit-date-row">
                <div className="fs-edit-field">
                  <label>Planned Date</label>
                  <input
                    type="date"
                    value={editPlannedDate}
                    onChange={(e) => setEditPlannedDate(e.target.value)}
                    className="fs-edit-input"
                  />
                </div>
                <div className="fs-edit-field">
                  <label>Target Date</label>
                  <input
                    type="date"
                    value={editTargetDate}
                    onChange={(e) => setEditTargetDate(e.target.value)}
                    className="fs-edit-input"
                  />
                </div>
                <div className="fs-edit-field">
                  <label>Hard Deadline</label>
                  <input
                    type="date"
                    value={editHardDeadline}
                    onChange={(e) => setEditHardDeadline(e.target.value)}
                    className="fs-edit-input"
                  />
                </div>
              </div>
            </fieldset>
            <div className="fs-edit-field">
              <label>Notes</label>
              <textarea
                value={editNotes}
                onChange={(e) => setEditNotes(e.target.value)}
                className="fs-edit-textarea"
                rows={3}
              />
            </div>
            <div className="fs-edit-actions">
              <button
                className="crud-btn save-btn"
                disabled={editSaving}
                onClick={async () => {
                  if (onFirestoreTaskUpdate) {
                    setEditSaving(true)
                    try {
                      await onFirestoreTaskUpdate(task.id, {
                        title: editTitle,
                        status: editStatus,
                        priority: editPriority,
                        plannedDate: editPlannedDate,
                        targetDate: editTargetDate || null,
                        hardDeadline: editHardDeadline || null,
                        notes: editNotes,
                      })
                      setIsEditingFirestore(false)
                    } finally {
                      setEditSaving(false)
                    }
                  }
                }}
              >
                {editSaving ? 'Saving...' : '✓ Save'}
              </button>
              <button
                className="crud-btn cancel-btn"
                onClick={() => setIsEditingFirestore(false)}
                disabled={editSaving}
              >
                ✕ Cancel
              </button>
            </div>
          </div>
        )}
        
        {/* Task details */}
        <div className="fs-task-details">
          {dueDate && (
            <div className="fs-detail-row">
              <span className="fs-detail-label">Due:</span>
              <span className="fs-detail-value">{new Date(dueDate).toLocaleDateString()}</span>
            </div>
          )}
          {task.targetDate && (
            <div className="fs-detail-row">
              <span className="fs-detail-label">Target:</span>
              <span className="fs-detail-value">{new Date(task.targetDate).toLocaleDateString()}</span>
            </div>
          )}
          {task.timesRescheduled && task.timesRescheduled > 0 && (
            <div className="fs-detail-row slippage">
              <span>⏳ Rescheduled {task.timesRescheduled} time{task.timesRescheduled > 1 ? 's' : ''}</span>
            </div>
          )}
        </div>
        
        {/* Notes */}
        {task.notes && (
          <div className="fs-notes-section">
            <span className="fs-notes-label">Notes:</span>
            <p className="fs-notes-text">{task.notes}</p>
          </div>
        )}
        
        {/* Recurring indicator */}
        {task.isRecurring && (
          <div className="fs-recurring-badge">
            🔄 Recurring: {task.recurringType || 'Unknown pattern'}
          </div>
        )}
        
        {/* Sync status */}
        <div className="fs-sync-status">
          {task.syncStatus === 'synced' && <span className="sync-badge synced">✓ Synced</span>}
          {task.syncStatus === 'pending' && <span className="sync-badge pending">⏳ Pending sync</span>}
          {task.syncStatus === 'orphaned' && <span className="sync-badge orphaned">⚠️ Orphaned</span>}
          {task.syncStatus === 'local_only' && <span className="sync-badge local">📍 Local only</span>}
        </div>
        
        {/* Source info */}
        {task.source === 'email' && task.sourceEmailSubject && (
          <div className="fs-source-info">
            <span className="source-icon">📧</span>
            <span className="source-text">{task.sourceEmailSubject}</span>
          </div>
        )}
        
        {/* Engage DATA button */}
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

  // No task selected - show Global Mode (Portfolio View)
  if (!selectedTask && !selectedFirestoreTask) {
    const perspective = globalPerspective ?? 'personal'
    const stats = globalStats
    // Filter out struck messages for display
    const globalHistory = (globalConversation ?? []).filter(msg => !msg.struck)
    const isExpanded = globalExpanded ?? false
    
    const perspectiveLabels: Record<string, string> = {
      personal: 'Personal',
      church: 'Church',
      work: 'Work',
      holistic: 'Holistic',
    }
    
    const perspectiveDescriptions: Record<string, string> = {
      personal: 'Home, family, and personal projects',
      church: 'Ministry and church leadership',
      work: 'Professional responsibilities',
      holistic: 'Complete view across all domains',
    }
    
    return (
      <section className={`panel assist-panel global-mode ${isExpanded ? 'expanded' : ''}`}>
        <header className="global-header">
          <div className="global-header-top">
            <h2>DATA - Portfolio View</h2>
            <button className="secondary" onClick={isExpanded ? onExpandTasks : onToggleGlobalExpand}>
              {isExpanded ? 'Show tasks' : '⛶ Expand'}
            </button>
          </div>
          
          {/* Perspective Selector */}
          <div className="perspective-selector">
            {(['personal', 'church', 'work', 'holistic'] as const).map((p) => (
              <button
                key={p}
                className={`perspective-tab ${perspective === p ? 'active' : ''}`}
                onClick={() => onPerspectiveChange?.(p)}
              >
                {perspectiveLabels[p]}
              </button>
            ))}
          </div>
          <p className="perspective-description">{perspectiveDescriptions[perspective]}</p>
        </header>
        
        {/* Portfolio Stats - Collapsible */}
        {stats && (
          <div className={`portfolio-stats ${dashboardCollapsed ? 'collapsed' : ''}`}>
            {/* Compact summary bar (always visible) */}
            <div 
              className="stats-summary-bar"
              onClick={() => setDashboardCollapsed(!dashboardCollapsed)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && setDashboardCollapsed(!dashboardCollapsed)}
            >
              <div className="stats-compact">
                <span className="stat-compact">{stats.totalOpen} open</span>
                {stats.overdue > 0 && <span className="stat-compact overdue">• {stats.overdue} overdue</span>}
                <span className="stat-compact today">• {stats.dueToday} today</span>
                <span className="stat-compact">• {stats.dueThisWeek} this week</span>
                {perspective === 'holistic' && stats.conflicts.length > 0 && (
                  <span className="stat-compact conflict">• ⚠️ {stats.conflicts.length} conflicts</span>
                )}
              </div>
              <button className="collapse-toggle" aria-label={dashboardCollapsed ? 'Expand dashboard' : 'Collapse dashboard'}>
                {dashboardCollapsed ? '▼' : '▲'}
              </button>
            </div>
            
            {/* Full stats (collapsible) */}
            {!dashboardCollapsed && (
              <>
                <div className="stats-row">
                  <div className="stat-item">
                    <span className="stat-value">{stats.totalOpen}</span>
                    <span className="stat-label">Open</span>
                  </div>
                  <div className="stat-item overdue">
                    <span className="stat-value">{stats.overdue}</span>
                    <span className="stat-label">Overdue</span>
                  </div>
                  <div className="stat-item today">
                    <span className="stat-value">{stats.dueToday}</span>
                    <span className="stat-label">Due Today</span>
                  </div>
                  <div className="stat-item week">
                    <span className="stat-value">{stats.dueThisWeek}</span>
                    <span className="stat-label">This Week</span>
                  </div>
                </div>
                
                {/* Conflicts warning for holistic mode */}
                {perspective === 'holistic' && stats.conflicts.length > 0 && (
                  <div className="conflicts-warning">
                    <strong>⚠️ Cross-Domain Conflicts:</strong>
                    <ul>
                      {stats.conflicts.map((c, i) => (
                        <li key={i}>{c}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {/* Domain breakdown for holistic mode */}
                {perspective === 'holistic' && Object.keys(stats.domainBreakdown).length > 0 && (
                  <div className="domain-breakdown">
                    {Object.entries(stats.domainBreakdown).map(([domain, count]) => (
                      count > 0 && (
                        <span key={domain} className="domain-badge">
                          {domain}: {count}
                        </span>
                      )
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        )}
        
        {/* Global Chat Interface */}
        <div className="global-chat-container">
          {/* Chat header with clear button */}
          {globalHistory.length > 0 && (
            <div className="global-chat-header">
              {selectedGlobalMessages.size > 0 && (
                <span className="selection-count">{selectedGlobalMessages.size} selected</span>
              )}
              <button 
                className="clear-chat-btn" 
                onClick={handleGlobalClear}
                title={selectedGlobalMessages.size > 0 
                  ? "Hide selected messages (preserved for learning)" 
                  : "Clear view"}
              >
                {selectedGlobalMessages.size > 0 ? 'Hide selected' : 'Clear view'}
              </button>
            </div>
          )}
          <div className="global-chat-messages">
            {/* Collapsible Quick Questions - always available */}
            <div className={`quick-questions-section ${quickQuestionsExpanded ? 'expanded' : ''}`}>
              <button 
                className="quick-questions-toggle"
                onClick={() => setQuickQuestionsExpanded(!quickQuestionsExpanded)}
              >
                <span className="toggle-icon">{quickQuestionsExpanded ? '▼' : '▶'}</span>
                Quick Questions
              </button>
              {quickQuestionsExpanded && (
                <div className="sample-questions">
                  <button 
                    className="sample-question-btn"
                    onClick={() => {
                      onSendGlobalMessage?.("What should I focus on today?")
                      setQuickQuestionsExpanded(false)
                    }}
                  >
                    "What should I focus on today?"
                  </button>
                  <button 
                    className="sample-question-btn"
                    onClick={() => {
                      onSendGlobalMessage?.("Am I overloaded this week?")
                      setQuickQuestionsExpanded(false)
                    }}
                  >
                    "Am I overloaded this week?"
                  </button>
                  <button 
                    className="sample-question-btn"
                    onClick={() => {
                      onSendGlobalMessage?.("What are my highest priority items?")
                      setQuickQuestionsExpanded(false)
                    }}
                  >
                    "What are my highest priority items?"
                  </button>
                  {perspective === 'holistic' && (
                    <button 
                      className="sample-question-btn"
                      onClick={() => {
                        onSendGlobalMessage?.("Do I have any conflicts between work and personal?")
                        setQuickQuestionsExpanded(false)
                      }}
                    >
                      "Do I have any conflicts between work and personal?"
                    </button>
                  )}
                </div>
              )}
            </div>
            
            {/* Chat history - always shown if any */}
            {globalHistory.length === 0 ? (
              <div className="global-chat-empty">
                <p className="subtle">No conversation yet. Ask a question or use Quick Questions above.</p>
              </div>
            ) : (
              globalHistory.map((msg) => (
                <div 
                  key={msg.ts} 
                  className={`chat-bubble ${msg.role} ${selectedGlobalMessages.has(msg.ts) ? 'selected' : ''}`}
                >
                  {/* Checkbox - like workspace delete button pattern */}
                  <input
                    type="checkbox"
                    className="chat-bubble-checkbox"
                    checked={selectedGlobalMessages.has(msg.ts)}
                    onChange={() => toggleMessageSelection(msg.ts)}
                    title="Select for bulk hide"
                  />
                  {/* Delete button - matching workspace pattern */}
                  <button
                    className="chat-bubble-delete"
                    onClick={() => onDeleteGlobalMessage?.(msg.ts)}
                    title="Permanently delete"
                  >
                    ×
                  </button>
                  <div className="chat-meta">
                    <span className="chat-role">
                      {msg.role === 'user' ? 'You' : 'DATA'} | {new Date(msg.ts).toLocaleDateString('en-US', { month: 'numeric', day: 'numeric', year: '2-digit' })}
                    </span>
                  </div>
                  <div className="chat-content">
                    {renderMarkdown(msg.content)}
                  </div>
                </div>
              ))
            )}
            {globalChatLoading && (
              <div className="chat-bubble assistant loading">
                <div className="chat-meta">
                  <span className="chat-role">DATA</span>
                </div>
                <div className="chat-content">
                  <span className="typing-indicator">thinking...</span>
                </div>
              </div>
            )}
          </div>
          
          {/* Chat Input */}
          <form
            className="global-chat-input"
            onSubmit={(e) => {
              e.preventDefault()
              const input = e.currentTarget.elements.namedItem('globalMessage') as HTMLInputElement
              if (input.value.trim() && onSendGlobalMessage) {
                onSendGlobalMessage(input.value.trim())
                input.value = ''
              }
            }}
          >
            <input
              type="text"
              name="globalMessage"
              placeholder={`Ask about your ${perspectiveLabels[perspective].toLowerCase()} tasks...`}
              disabled={globalChatLoading}
              autoComplete="off"
            />
            <button type="submit" disabled={globalChatLoading}>
              {globalChatLoading ? '...' : 'Send'}
            </button>
          </form>
        </div>
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
  // Note: At this point, selectedTask must be non-null because:
  // - If selectedFirestoreTask was set and selectedTask was null, we returned at line ~894
  // - If both were null, we returned at line ~1202 (Global Mode)
  if (!isEngaged && selectedTask) {
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
  // Create unified task object that works for both Smartsheet and Firestore tasks
  const engagedTask = selectedTask ?? (selectedFirestoreTask ? {
    rowId: `fs:${selectedFirestoreTask.id}`,
    title: selectedFirestoreTask.title,
    status: selectedFirestoreTask.status || 'scheduled',
    priority: selectedFirestoreTask.priority || 'Standard',
    due: selectedFirestoreTask.plannedDate || selectedFirestoreTask.dueDate || '',
    project: selectedFirestoreTask.project || '',
    notes: selectedFirestoreTask.notes || '',
    source: selectedFirestoreTask.domain || 'personal',
    done: selectedFirestoreTask.done || false,
  } : null)

  // Safety check - should not happen but prevents crashes
  if (!engagedTask) {
    return <section className="panel assist-panel"><p>No task selected</p></section>
  }

  return (
    <section className="panel assist-panel-three-zone" ref={containerRef}>
      {/* Header row */}
      <header className="assist-header-compact">
        <div className="header-left-group">
          <h2>Assistant</h2>
          <div className="task-badges-inline">
            <span className="badge status">{engagedTask.status}</span>
            {engagedTask.priority && (
              <span className={`badge priority ${engagedTask.priority.toLowerCase()}`}>
                {engagedTask.priority}
              </span>
            )}
          </div>
          <strong className="task-title-compact">{engagedTask.title}</strong>
        </div>
        <div className="action-buttons-row">
          {/* Fixed actions - always available */}
          {FIXED_ACTIONS.map((action) => (
            <button
              key={action}
              className={`action-btn ${activeAction === action ? 'active' : ''} ${action === 'plan' ? 'plan-btn' : ''}`}
              onClick={() => action === 'plan' ? onGeneratePlan(getSelectedWorkspaceContent()) : handleActionClick(action)}
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
      {engagedTask.notes && (
        <div className="notes-row">
          <span className="notes-label">Notes:</span>
          <span className="notes-text">
            {showFullNotes ? engagedTask.notes : notesPreview(engagedTask.notes || '')}
          </span>
          {(engagedTask.notes?.length || 0) > NOTES_PREVIEW_LIMIT && (
            <button className="link-button" onClick={() => setShowFullNotes(!showFullNotes)}>
              {showFullNotes ? 'less' : 'more'}
            </button>
          )}
        </div>
      )}

      {/* Attachments Gallery - below notes, above Planning */}
      {attachments && attachments.length > 0 && selectedAttachmentIds && onAttachmentSelectionChange && (
        <AttachmentsGallery
          taskId={engagedTask.rowId}
          attachments={attachments}
          selectedIds={selectedAttachmentIds}
          onSelectionChange={onAttachmentSelectionChange}
          collapsed={attachmentsCollapsed}
          onToggleCollapse={() => setAttachmentsCollapsed(!attachmentsCollapsed)}
        />
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
              {latestPlan?.summary ? (
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
                    {onClearPlan && (
                      <button
                        className="clear-plan-btn"
                        onClick={onClearPlan}
                        title="Clear plan"
                      >
                        ×
                      </button>
                    )}
                  </div>

                  {latestPlan.nextSteps?.length > 0 && (
                    <div className="plan-section">
                      <h5>Next Steps</h5>
                      <ul className="compact-list">
                        {latestPlan.nextSteps.map((step, i) => (
                          <li key={i}>{step}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {latestPlan.efficiencyTips?.length > 0 && (
                    <div className="plan-section">
                      <h5>Efficiency Tips</h5>
                      <ul className="compact-list">
                        {latestPlan.efficiencyTips.map((tip, i) => (
                          <li key={i}>{tip}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Feedback controls for plan */}
                  {onFeedbackSubmit && latestPlan.summary && (
                    <div className="plan-feedback">
                      <FeedbackControls
                        context="plan"
                        messageContent={latestPlan.summary}
                        onSubmit={onFeedbackSubmit}
                      />
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
              <div className="workspace-controls">
                <button
                  className="add-btn"
                  onClick={() => {
                    workspaceModifiedRef.current = true
                    const newItem: WorkspaceItem = {
                      id: `ws-${Date.now()}`,
                      content: '',
                    }
                    setWorkspaceItems(prev => [...prev, newItem])
                  }}
                  title="Add new card"
                >
                  +
                </button>
                {workspaceItems.length > 0 && (
                  <>
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
                  </>
                )}
              </div>
            </div>
            <div className="zone-content workspace-content">
              {/* Action status banner - shows ONLY while action is running */}
              {activeAction === 'research' && researchRunning && (
                <div className="action-output-content action-status-banner">
                  <div className="action-output-header">
                    <h5>{formatActionLabel('research')}</h5>
                  </div>
                  <div className="research-loading">
                    <p className="subtle">🔍 Searching the web...</p>
                  </div>
                </div>
              )}
              {activeAction === 'summarize' && summarizeRunning && (
                <div className="action-output-content action-status-banner">
                  <div className="action-output-header">
                    <h5>{formatActionLabel('summarize')}</h5>
                  </div>
                  <div className="research-loading">
                    <p className="subtle">📄 Generating summary...</p>
                  </div>
                </div>
              )}
              {activeAction === 'contact' && (contactRunning || contactConfirmation) && (
                <div className="action-output-content action-status-banner">
                  <div className="action-output-header">
                    <h5>{formatActionLabel('contact')}</h5>
                  </div>
                  {contactRunning ? (
                    <div className="research-loading">
                      <p className="subtle">📇 Searching for contacts...</p>
                    </div>
                  ) : contactConfirmation ? (
                    <div className="contact-confirmation">
                      <p className="confirmation-message">{contactConfirmation.confirmationMessage}</p>
                      <p className="entities-found">
                        Entities found: {contactConfirmation.entitiesFound
                          .filter(e => e.entityType === 'person' || e.entityType === 'organization')
                          .map(e => e.name)
                          .slice(0, 6)
                          .join(', ')}
                        {contactConfirmation.entitiesFound.length > 6 ? '...' : ''}
                      </p>
                      <div className="confirmation-buttons">
                        <button 
                          className="primary compact"
                          onClick={() => onRunContact(true)}
                        >
                          Yes, search all
                        </button>
                        <button 
                          className="secondary compact"
                          onClick={() => setActiveAction(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : null}
                </div>
              )}
              
              {/* Workspace items */}
              {workspaceItems.length > 0 ? (
                <div className="workspace-items-container">
                  {selectedWorkspaceIds.size > 0 && (
                    <div className="workspace-selection-hint">
                      {selectedWorkspaceIds.size} item{selectedWorkspaceIds.size > 1 ? 's' : ''} selected for context
                    </div>
                  )}
                  {workspaceItems.map((item, index) => (
                    <div key={item.id} className={`workspace-item-simple ${selectedWorkspaceIds.has(item.id) ? 'selected' : ''}`}>
                      {index > 0 && <hr className="workspace-separator" />}
                      <div className="workspace-item-wrapper">
                        <textarea
                          className="workspace-editor"
                          value={item.content}
                          onChange={(e) => updateWorkspaceItem(item.id, e.target.value)}
                          placeholder="Edit content here..."
                        />
                        <div className="workspace-item-controls">
                          <input
                            type="checkbox"
                            className="workspace-item-checkbox"
                            checked={selectedWorkspaceIds.has(item.id)}
                            onChange={() => toggleWorkspaceSelection(item.id)}
                            title="Include in planning context"
                          />
                          <button
                            className="workspace-item-delete"
                            onClick={() => removeWorkspaceItem(item.id)}
                            title="Remove this section"
                          >
                            ×
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : !activeAction ? (
                <div className="zone-placeholder">
                  <p className="subtle">
                    Push content here from the conversation or run an action.
                  </p>
                </div>
              ) : null}
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
                entry.struck ? (
                  // Struck message - show single line with undo option
                  <div key={`${entry.ts}-${index}`} className="chat-bubble struck">
                    <div className="struck-message">
                      <span className="struck-icon">⚡</span>
                      <span className="struck-text">
                        Response removed on {entry.struckAt ? new Date(entry.struckAt).toLocaleDateString() : 'unknown date'}
                      </span>
                      {onUnstrikeMessage && (
                        <button
                          className="unstrike-btn"
                          onClick={() => onUnstrikeMessage(entry.ts)}
                          title="Restore this response"
                        >
                          Undo
                        </button>
                      )}
                    </div>
                  </div>
                ) : (
                  // Normal message
                  <div key={`${entry.ts}-${index}`} className={`chat-bubble ${entry.role}`}>
                    <div className="chat-meta">
                      <span>{entry.role === 'assistant' ? 'DATA' : 'You'} | {new Date(entry.ts).toLocaleDateString('en-US', { month: 'numeric', day: 'numeric', year: '2-digit' })}</span>
                      {entry.role === 'assistant' && (
                        <>
                          <button
                            className="push-btn-inline"
                            onClick={() => pushToWorkspace(entry.content)}
                            title="Push to Workspace"
                          >
                            ➡️
                          </button>
                          {onStrikeMessage && (
                            <button
                              className="strike-btn"
                              onClick={() => onStrikeMessage(entry.ts)}
                              title="Strike this response"
                            >
                              ⚡
                            </button>
                          )}
                        </>
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
                )
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
          // Include selected workspace items as context if any are checked
          const selectedContent = getSelectedWorkspaceContent()
          const workspaceContext = selectedContent.length > 0
            ? selectedContent.join('\n\n---\n\n')
            : undefined
          await onSendMessage(payload, workspaceContext)
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

      {/* Email Draft Panel Overlay */}
      <EmailDraftPanel
        isOpen={emailDraftOpen}
        onClose={handleCloseEmailDraft}
        onSend={handleSendEmail}
        onRegenerate={handleRegenerateEmail}
        onDiscard={handleDiscardEmailDraft}
        initialDraft={emailDraft ?? undefined}
        suggestedContacts={contactResults ?? undefined}
        taskNotes={selectedTask?.notes ?? undefined}
        gmailAccounts={['church', 'personal']}
        sending={emailSending ?? false}
        regenerating={emailDraftLoading ?? false}
        error={emailError}
      />
    </section>
  )
}
