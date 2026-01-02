import { useCallback, useEffect, useState } from 'react'
import './App.css'
import { TaskList } from './components/TaskList'
import { AssistPanel } from './components/AssistPanel'
import { ActivityFeed } from './components/ActivityFeed'
import { AuthPanel } from './components/AuthPanel'
import { RebalancingEditor } from './components/RebalancingEditor'
import { EmailDashboard, emptyEmailCache, type EmailCacheState } from './components/EmailDashboard'
import { ProfileSettings } from './components/ProfileSettings'
import {
  clearGlobalHistory,
  deleteGlobalMessage,
  deleteDraft,
  draftEmail,
  fetchActivity,
  fetchAttachments,
  fetchConversationHistory,
  fetchGlobalContext,
  fetchTasks,
  fetchWorkBadge,
  generatePlan,
  listFirestoreTasks,
  loadDraft,
  loadWorkspace,
  runAssist,
  runResearch,
  runSummarize,
  saveDraft,
  saveWorkspace,
  searchContacts,
  sendChatMessage,
  sendEmail,
  sendGlobalChat,
  strikeGlobalMessage,
  strikeMessage,
  submitFeedback,
  unstrikeMessage,
  updateTask,
  bulkUpdateTasks,
} from './api'
import type { AttachmentInfo } from './api'
import type { Perspective, PortfolioStats, SavedEmailDraft, PortfolioPendingAction, BulkTaskUpdate } from './api'
import type {
  ContactCard,
  ContactSearchResponse,
  FeedbackContext,
  FeedbackType,
  PendingAction,
} from './api'
import type {
  ActivityEntry,
  AppMode,
  AssistPlan,
  ConversationMessage,
  DataSource,
  FirestoreTask,
  Task,
  WorkBadge,
} from './types'
import { useAuth } from './auth/AuthContext'

const gmailAccounts = ['church', 'personal']

function App() {
  const { authConfig, state } = useAuth()
  const [apiBase, setApiBase] = useState(
    import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000',
  )
  const [dataSource, setDataSource] = useState<DataSource>(
    (import.meta.env.VITE_API_DEFAULT_SOURCE as DataSource) ?? 'auto',
  )
  const [tasks, setTasks] = useState<Task[]>([])
  const [tasksLoading, setTasksLoading] = useState(false)
  const [tasksWarning, setTasksWarning] = useState<string | null>(null)
  const [liveTasks, setLiveTasks] = useState(false)
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)

  const [assistPlan, setAssistPlan] = useState<AssistPlan | null>(null)
  const [assistRunning, setAssistRunning] = useState(false)
  const [planGenerating, setPlanGenerating] = useState(false)
  const [researchRunning, setResearchRunning] = useState(false)
  const [summarizeRunning, setSummarizeRunning] = useState(false)
  const [contactRunning, setContactRunning] = useState(false)
  const [contactResults, setContactResults] = useState<ContactCard[] | null>(null)
  const [contactConfirmation, setContactConfirmation] = useState<ContactSearchResponse | null>(null)
  const [assistError, setAssistError] = useState<string | null>(null)
  const [gmailAccount, setGmailAccount] = useState('')

  const [conversation, setConversation] = useState<ConversationMessage[]>([])
  const [conversationLoading, setConversationLoading] = useState(false)
  
  // Workspace persistence
  const [workspaceItems, setWorkspaceItems] = useState<string[]>([])
  const [workspaceSaveTimeout, setWorkspaceSaveTimeout] = useState<ReturnType<typeof setTimeout> | null>(null)
  const [sendingMessage, setSendingMessage] = useState(false)
  
  // Task update state
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null)
  const [updateExecuting, setUpdateExecuting] = useState(false)

  // Email draft state
  const [emailDraftLoading, setEmailDraftLoading] = useState(false)
  const [emailSending, setEmailSending] = useState(false)
  const [emailError, setEmailError] = useState<string | null>(null)
  const [savedDraft, setSavedDraft] = useState<SavedEmailDraft | null>(null)
  const [emailDraftOpen, setEmailDraftOpen] = useState(false)

  // Attachments state
  const [attachments, setAttachments] = useState<AttachmentInfo[]>([])
  const [attachmentsLoading, setAttachmentsLoading] = useState(false)
  const [selectedAttachmentIds, setSelectedAttachmentIds] = useState<Set<string>>(new Set())

  const [activityEntries, setActivityEntries] = useState<ActivityEntry[]>([])
  const [activityError, setActivityError] = useState<string | null>(null)
  const [workBadge, setWorkBadge] = useState<WorkBadge | null>(null)
  
  // Email Tasks (Firestore) state
  const [emailTasks, setEmailTasks] = useState<FirestoreTask[]>([])
  const [emailTasksLoading, setEmailTasksLoading] = useState(false)
  
  const [environmentName, setEnvironmentName] = useState(
    import.meta.env.VITE_ENVIRONMENT ?? 'DEV',
  )
  const [menuOpen, setMenuOpen] = useState(false)
  const [menuView, setMenuView] = useState<'auth' | 'activity' | 'environment' | 'profile'>('auth')
  const [appMode, setAppMode] = useState<AppMode>('tasks')
  const [taskPanelCollapsed, setTaskPanelCollapsed] = useState(false)
  const [isEngaged, setIsEngaged] = useState(false)  // Tracks if we've engaged with the current task

  // Email dashboard state - lifted up to persist across mode switches
  const [emailCache, setEmailCache] = useState<EmailCacheState>({
    personal: emptyEmailCache(),
    church: emptyEmailCache(),
  })
  const [emailSelectedAccount, setEmailSelectedAccount] = useState<'personal' | 'church'>('personal')

  // Global Mode state
  const [globalPerspective, setGlobalPerspective] = useState<Perspective>('personal')
  const [globalConversation, setGlobalConversation] = useState<ConversationMessage[]>([])
  const [globalStats, setGlobalStats] = useState<PortfolioStats | null>(null)
  const [portfolioPendingActions, setPortfolioPendingActions] = useState<PortfolioPendingAction[]>([])
  const [portfolioActionsExecuting, setPortfolioActionsExecuting] = useState(false)
  const [globalChatLoading, setGlobalChatLoading] = useState(false)
  const [globalExpanded, setGlobalExpanded] = useState(false)

  const handleQuickAction = useCallback((action: { type: string; content: string }) => {
    // Action handling is now done within AssistPanel
    console.debug('Quick action triggered:', action)
  }, [])

  const handleSelectTask = useCallback(async (taskId: string) => {
    if (taskId !== selectedTaskId) {
      // Clear plan and engagement when selecting a different task
      setAssistPlan(null)
      setAssistError(null)
      setConversation([])
      setSavedDraft(null)
      setEmailDraftOpen(false)
      setEmailError(null)
      setIsEngaged(false)
      // Clear attachments for new task
      setAttachments([])
      setSelectedAttachmentIds(new Set())
    }
    setSelectedTaskId(taskId)
    
    // Load any saved draft for this task
    if (authConfig) {
      try {
        const draftResponse = await loadDraft(taskId, authConfig, apiBase)
        if (draftResponse.hasDraft && draftResponse.draft) {
          setSavedDraft(draftResponse.draft)
        }
      } catch (err) {
        console.error('Failed to load draft:', err)
      }
    }
  }, [selectedTaskId, authConfig, apiBase])

  const selectedTask =
    tasks.find((task) => task.rowId === selectedTaskId) ?? null

  useEffect(() => {
    if (authConfig) {
      refreshTasks()
      refreshActivity()
    } else {
      setTasks([])
      setAssistPlan(null)
      setConversation([])
    }
  }, [apiBase, dataSource, authConfig])

  useEffect(() => {
    if (!authConfig || !selectedTaskId) {
      setConversation([])
      return
    }
    void loadConversation(selectedTaskId)
  }, [authConfig, selectedTaskId])

  // Load attachments when task is selected
  useEffect(() => {
    if (!authConfig || !selectedTaskId) {
      setAttachments([])
      return
    }
    async function loadAttachments() {
      setAttachmentsLoading(true)
      try {
        const response = await fetchAttachments(selectedTaskId!, authConfig!, apiBase)
        setAttachments(response.attachments)
      } catch (err) {
        console.error('Failed to load attachments:', err)
        setAttachments([])
      } finally {
        setAttachmentsLoading(false)
      }
    }
    void loadAttachments()
  }, [authConfig, selectedTaskId, apiBase])

  // Load global context (stats + history) when Portfolio View opens
  useEffect(() => {
    if (!authConfig || selectedTaskId !== null) {
      // Not in global mode - don't load
      return
    }
    async function loadGlobalContext() {
      try {
        const result = await fetchGlobalContext(authConfig!, globalPerspective, apiBase)
        setGlobalStats(result.portfolio)
        setGlobalConversation(result.history || [])
      } catch (err) {
        console.error('Failed to load portfolio context:', err)
      }
    }
    void loadGlobalContext()
  }, [authConfig, selectedTaskId, apiBase])

  async function refreshTasks(skipAutoSelect = false) {
    if (!authConfig) return
    setTasksLoading(true)
    setTasksWarning(null)
    try {
      // Fetch tasks from all sheets (personal + work) so Work filter can show them
      const response = await fetchTasks(authConfig, apiBase, {
        source: dataSource,
        includeWork: true,  // Include work tasks in the response
      })
      
      // Also refresh portfolio stats if in global mode
      if (!selectedTaskId) {
        try {
          const portfolioResult = await fetchGlobalContext(authConfig, globalPerspective, apiBase)
          setGlobalStats(portfolioResult.portfolio)
        } catch (err) {
          console.error('Failed to refresh portfolio stats:', err)
        }
      }
      // X statuses to exclude from all views
      const EXCLUDED_STATUSES = [
        'completed', 'cancelled', 'delegated',
        'create zd ticket', 'ticket created'
      ]
      const activeTasks = response.tasks.filter(
        (task) => {
          // Exclude tasks with Done checkbox checked
          if (task.done === true) return false
          // Exclude tasks with excluded statuses
          const status = task.status?.toLowerCase() || ''
          return !EXCLUDED_STATUSES.includes(status)
        },
      )
      setTasks(activeTasks)
      setLiveTasks(response.liveTasks)
      setTasksWarning(response.warning ?? null)
      if (response.environment) {
        setEnvironmentName(response.environment.toUpperCase())
      }
      // Only auto-select first task on initial load, not when refreshing from Portfolio View
      if (!skipAutoSelect && !selectedTaskId && activeTasks.length > 0) {
        // Default to first personal task (not work)
        const firstPersonal = activeTasks.find(t => t.source !== 'work')
        setSelectedTaskId(firstPersonal?.rowId ?? activeTasks[0].rowId)
      }
      
      // Fetch work badge for notification indicator
      try {
        const badge = await fetchWorkBadge(authConfig, apiBase)
        setWorkBadge(badge)
      } catch {
        // Work badge is optional - don't fail if it errors
        setWorkBadge(null)
      }
    } catch (error) {
      setTasksWarning((error as Error).message)
      setTasks([])
    } finally {
      setTasksLoading(false)
    }
  }
  
  // Load email tasks from Firestore
  async function loadEmailTasks() {
    if (!authConfig) return
    setEmailTasksLoading(true)
    try {
      const response = await listFirestoreTasks(authConfig, apiBase, { limit: 100 })
      setEmailTasks(response.tasks)
    } catch (error) {
      console.error('Failed to load email tasks:', error)
      setEmailTasks([])
    } finally {
      setEmailTasksLoading(false)
    }
  }

  async function refreshActivity() {
    if (!authConfig) {
      setActivityEntries([])
      return
    }
    try {
      const entries = await fetchActivity(authConfig, apiBase, 25)
      setActivityEntries(entries.reverse())
      setActivityError(null)
    } catch (error) {
      setActivityError((error as Error).message)
    }
  }

  async function loadConversation(taskId: string) {
    if (!authConfig) return
    setConversationLoading(true)
    try {
      const history = await fetchConversationHistory(taskId, authConfig, apiBase)
      setConversation(history)
    } catch (error) {
      setAssistError((error as Error).message)
      setConversation([])
    } finally {
      setConversationLoading(false)
    }
  }

  async function engageTask() {
    // Load task context, conversation history, and workspace - NO plan generation
    if (!selectedTask) return
    if (!authConfig) {
      setAssistError('Please sign in first.')
      return
    }
    setIsEngaged(true)  // Mark as engaged with this task
    setAssistRunning(true)
    setAssistError(null)
    try {
      const response = await runAssist(selectedTask.rowId, authConfig, apiBase, {
        source: dataSource,
      })
      // Set a minimal "engaged" state - plan will be null until user clicks Plan
      setAssistPlan(response.plan ?? {
        summary: '',
        score: 0,
        labels: [],
        automationTriggers: [],
        nextSteps: [],
        efficiencyTips: [],
        suggestedActions: ['plan', 'research', 'draft_email', 'follow_up'],
        task: selectedTask,
        generator: 'none',
        generatorNotes: [],
      })
      setConversation(response.history ?? [])
      
      // Load workspace content
      try {
        const workspace = await loadWorkspace(selectedTask.rowId, authConfig, apiBase)
        setWorkspaceItems(workspace.items ?? [])
      } catch {
        // Workspace load failed - start with empty
        setWorkspaceItems([])
      }
    } catch (error) {
      setAssistError((error as Error).message)
    } finally {
      setAssistRunning(false)
    }
  }

  async function handleGeneratePlan(contextItems?: string[]) {
    // Explicitly generate/update the plan based on task + conversation
    if (!selectedTask) return
    if (!authConfig) {
      setAssistError('Please sign in first.')
      return
    }
    setPlanGenerating(true)
    setAssistError(null)
    try {
      const response = await generatePlan(selectedTask.rowId, authConfig, apiBase, {
        source: dataSource,
        anthropicModel: import.meta.env.VITE_ANTHROPIC_MODEL,
        contextItems: contextItems && contextItems.length > 0 ? contextItems : undefined,
        selectedAttachments: Array.from(selectedAttachmentIds),
      })
      setAssistPlan(response.plan)
      void refreshActivity()
    } catch (error) {
      setAssistError((error as Error).message)
    } finally {
      setPlanGenerating(false)
    }
  }

  function handleClearPlan() {
    // Clear the current plan so user can visually confirm a new one is generated
    setAssistPlan(null)
  }

  async function handleRunResearch() {
    // Run web research based on task context and next steps
    if (!selectedTask) return
    if (!authConfig) {
      setAssistError('Please sign in first.')
      return
    }
    setResearchRunning(true)
    setAssistError(null)
    try {
      const response = await runResearch(selectedTask.rowId, authConfig, apiBase, {
        source: dataSource,
        nextSteps: assistPlan?.nextSteps,
      })
      // Auto-push research to workspace (additive) and trigger save
      if (response.research) {
        setWorkspaceItems(prev => {
          const newItems = [...prev, response.research]
          // Trigger save after state update
          if (selectedTask?.rowId && authConfig) {
            void saveWorkspace(selectedTask.rowId, newItems, authConfig, apiBase)
          }
          return newItems
        })
      }
      // Update conversation history with research summary
      if (response.history) {
        setConversation(response.history)
      }
      void refreshActivity()
    } catch (error) {
      setAssistError((error as Error).message)
    } finally {
      setResearchRunning(false)
    }
  }

  async function handleRunSummarize() {
    // Generate a summary of task, plan, and conversation progress
    if (!selectedTask) return
    if (!authConfig) {
      setAssistError('Please sign in first.')
      return
    }
    setSummarizeRunning(true)
    setAssistError(null)
    try {
      const response = await runSummarize(selectedTask.rowId, authConfig, apiBase, {
        source: dataSource,
        planSummary: assistPlan?.summary,
        nextSteps: assistPlan?.nextSteps,
        efficiencyTips: assistPlan?.efficiencyTips,
      })
      // Auto-push summary to workspace (additive) and trigger save
      if (response.summary) {
        setWorkspaceItems(prev => {
          const newItems = [...prev, response.summary]
          // Trigger save after state update
          if (selectedTask?.rowId && authConfig) {
            void saveWorkspace(selectedTask.rowId, newItems, authConfig, apiBase)
          }
          return newItems
        })
      }
      // Update conversation history
      if (response.history) {
        setConversation(response.history)
      }
      void refreshActivity()
    } catch (error) {
      setAssistError((error as Error).message)
    } finally {
      setSummarizeRunning(false)
    }
  }

  async function handleRunContact(confirmSearch = false) {
    // Search for contact information based on task context
    if (!selectedTask) return
    if (!authConfig) {
      setAssistError('Please sign in first.')
      return
    }
    setContactRunning(true)
    if (!confirmSearch) {
      setContactResults(null)
      setContactConfirmation(null)
    }
    setAssistError(null)
    try {
      const response = await searchContacts(selectedTask.rowId, authConfig, apiBase, {
        source: dataSource,
        confirmSearch,
      })
      
      if (response.needsConfirmation && !confirmSearch) {
        // Store confirmation request for user to approve
        setContactConfirmation(response)
        setContactResults(null)
      } else {
        // Got results - push each contact to workspace individually
        setContactResults(response.contacts)
        setContactConfirmation(null)
        
        // Auto-push contacts to workspace (additive) and trigger save
        if (response.contacts && response.contacts.length > 0) {
          const contactCards = response.contacts.map(c => formatContactCardMarkdown(c))
          // Add each contact as a separate workspace item
          setWorkspaceItems(prev => {
            const newItems = [...prev, ...contactCards]
            // Trigger save after state update
            if (selectedTask?.rowId && authConfig) {
              void saveWorkspace(selectedTask.rowId, newItems, authConfig, apiBase)
            }
            return newItems
          })
        }
        
        // Update conversation history
        if (response.history) {
          setConversation(response.history)
        }
      }
      void refreshActivity()
    } catch (error) {
      setAssistError((error as Error).message)
    } finally {
      setContactRunning(false)
    }
  }
  
  // Helper to format contact card as markdown
  function formatContactCardMarkdown(contact: ContactCard): string {
    const lines: string[] = [`📇 **${contact.name}**`]
    if (contact.email) lines.push(`📧 ${contact.email}`)
    if (contact.phone) lines.push(`📱 ${contact.phone}`)
    if (contact.title && contact.organization) {
      lines.push(`🏢 ${contact.organization} - ${contact.title}`)
    } else if (contact.organization) {
      lines.push(`🏢 ${contact.organization}`)
    } else if (contact.title) {
      lines.push(`💼 ${contact.title}`)
    }
    if (contact.location) lines.push(`📍 ${contact.location}`)
    let sourceText = `Source: ${contact.source}`
    if (contact.sourceUrl) sourceText = `Source: [${contact.source}](${contact.sourceUrl})`
    lines.push(`🔗 ${sourceText} | Confidence: ${contact.confidence.charAt(0).toUpperCase() + contact.confidence.slice(1)}`)
    return lines.join('\n')
  }

  // Email draft handler - generates new draft or returns saved draft
  async function handleDraftEmail(
    sourceContent: string,
    recipient?: string,
    regenerateInput?: string
  ): Promise<{ subject: string; body: string; bodyHtml?: string }> {
    if (!selectedTask) throw new Error('No task selected')
    if (!authConfig) throw new Error('Please sign in first')

    setEmailDraftLoading(true)
    setEmailError(null)
    try {
      const response = await draftEmail(selectedTask.rowId, {
        source: dataSource,
        sourceContent,
        recipient,
        regenerateInput,
      }, authConfig, apiBase)
      return {
        subject: response.subject,
        body: response.body,
        bodyHtml: response.bodyHtml,
      }
    } catch (error) {
      const message = (error as Error).message
      setEmailError(message)
      throw error
    } finally {
      setEmailDraftLoading(false)
    }
  }

  // Save draft to backend
  async function handleSaveDraft(draft: {
    to: string[]
    cc: string[]
    subject: string
    body: string
    fromAccount: string
  }): Promise<void> {
    if (!selectedTask) return
    if (!authConfig) return
    
    try {
      const response = await saveDraft(selectedTask.rowId, {
        to: draft.to,
        cc: draft.cc,
        subject: draft.subject,
        body: draft.body,
        fromAccount: draft.fromAccount,
      }, authConfig, apiBase)
      setSavedDraft(response.draft)
    } catch (error) {
      console.error('Failed to save draft:', error)
    }
  }

  // Delete draft from backend
  async function handleDeleteDraft(): Promise<void> {
    if (!selectedTask) return
    if (!authConfig) return
    
    try {
      await deleteDraft(selectedTask.rowId, authConfig, apiBase)
      setSavedDraft(null)
    } catch (error) {
      console.error('Failed to delete draft:', error)
    }
  }

  // Toggle email draft panel - smart behavior based on state
  function handleToggleEmailDraft() {
    if (emailDraftOpen) {
      // Close panel (draft will be auto-saved by panel)
      setEmailDraftOpen(false)
    } else {
      // Open panel
      setEmailDraftOpen(true)
    }
  }

  // Email send handler
  async function handleSendEmail(draft: {
    to: string[]
    cc: string[]
    subject: string
    body: string
    fromAccount: string
  }): Promise<void> {
    if (!selectedTask) throw new Error('No task selected')
    if (!authConfig) throw new Error('Please sign in first')
    
    setEmailSending(true)
    setEmailError(null)
    try {
      const response = await sendEmail(selectedTask.rowId, {
        source: dataSource,
        account: draft.fromAccount,
        to: draft.to,
        cc: draft.cc.length > 0 ? draft.cc : undefined,
        subject: draft.subject,
        body: draft.body,
      }, authConfig, apiBase)
      
      // Clear saved draft after successful send (backend also deletes)
      setSavedDraft(null)
      setEmailDraftOpen(false)
      
      // Update conversation history from response
      if (response.history) {
        setConversation(response.history)
      }
      
      // Refresh activity
      void refreshActivity()
    } catch (error) {
      const message = (error as Error).message
      setEmailError(message)
      throw error
    } finally {
      setEmailSending(false)
    }
  }

  async function handleAssist() {
    // Collapse task panel when engaging DATA
    setTaskPanelCollapsed(true)
    await engageTask()
  }

  // Debounced workspace save
  const handleWorkspaceChange = useCallback((items: string[]) => {
    setWorkspaceItems(items)
    
    // Clear any pending save
    if (workspaceSaveTimeout) {
      clearTimeout(workspaceSaveTimeout)
    }
    
    // Debounce save by 1 second
    if (selectedTaskId && authConfig) {
      const timeout = setTimeout(async () => {
        try {
          await saveWorkspace(selectedTaskId, items, authConfig, apiBase)
        } catch (error) {
          console.error('Failed to save workspace:', error)
        }
      }, 1000)
      setWorkspaceSaveTimeout(timeout)
    }
  }, [selectedTaskId, authConfig, apiBase, workspaceSaveTimeout])

  async function handleSendMessage(message: string, workspaceContext?: string) {
    if (!selectedTaskId || !authConfig) return

    setSendingMessage(true)
    setAssistError(null)

    try {
      const result = await sendChatMessage(
        selectedTaskId,
        message,
        authConfig,
        apiBase,
        {
          source: dataSource,
          workspaceContext,
          selectedAttachments: Array.from(selectedAttachmentIds),
        },
      )
      // Update conversation with the response
      setConversation(result.history)
      
      // Check if DATA detected a task update intent
      if (result.pendingAction) {
        setPendingAction(result.pendingAction)
      }
      
      // Check if DATA suggested email draft updates
      if (result.emailDraftUpdate) {
        const update = result.emailDraftUpdate
        // Update the saved draft with the new content
        setSavedDraft(prev => {
          if (!prev) {
            // Create a new draft if none exists
            return {
              taskId: selectedTaskId,
              to: [],
              cc: [],
              subject: update.subject ?? '',
              body: update.body ?? '',
              fromAccount: '',
              sourceContent: '',
              createdAt: new Date().toISOString(),
              updatedAt: new Date().toISOString(),
            }
          }
          // Update existing draft
          return {
            ...prev,
            subject: update.subject ?? prev.subject,
            body: update.body ?? prev.body,
            updatedAt: new Date().toISOString(),
          }
        })
        // Also save to backend
        if (savedDraft || update.subject || update.body) {
          void saveDraft(selectedTaskId, {
            to: savedDraft?.to ?? [],
            cc: savedDraft?.cc ?? [],
            subject: update.subject ?? savedDraft?.subject ?? '',
            body: update.body ?? savedDraft?.body ?? '',
            fromAccount: savedDraft?.fromAccount ?? '',
          }, authConfig, apiBase)
        }
      }
    } catch (err) {
      console.error('Chat error:', err)
      setAssistError(err instanceof Error ? err.message : 'Chat failed')
    } finally {
      setSendingMessage(false)
    }
  }

  async function handleConfirmUpdate() {
    console.log('handleConfirmUpdate called', { selectedTaskId, authConfig: !!authConfig, pendingAction })
    if (!selectedTaskId || !authConfig || !pendingAction) {
      console.log('Early return - missing:', { selectedTaskId: !selectedTaskId, authConfig: !authConfig, pendingAction: !pendingAction })
      return
    }
    
    setUpdateExecuting(true)
    setAssistError(null)
    
    try {
      const result = await updateTask(
        selectedTaskId,
        {
          source: selectedTask?.source ?? 'personal',
          action: pendingAction.action,
          status: pendingAction.status,
          priority: pendingAction.priority,
          dueDate: pendingAction.dueDate,
          comment: pendingAction.comment,
          number: pendingAction.number,
          contactFlag: pendingAction.contactFlag,
          recurring: pendingAction.recurring,
          project: pendingAction.project,
          taskTitle: pendingAction.taskTitle,
          assignedTo: pendingAction.assignedTo,
          notes: pendingAction.notes,
          estimatedHours: pendingAction.estimatedHours,
          confirmed: true,
        },
        authConfig,
        apiBase,
      )
      
      if (result.status === 'success') {
        // Clear the pending action
        setPendingAction(null)
        // Refresh tasks to show updated state
        await refreshTasks()
        // Refresh conversation to show the update confirmation
        await loadConversation(selectedTaskId)
        void refreshActivity()
      }
    } catch (err) {
      console.error('Update error:', err)
      setAssistError(err instanceof Error ? err.message : 'Update failed')
    } finally {
      setUpdateExecuting(false)
    }
  }

  function handleCancelUpdate() {
    setPendingAction(null)
  }

  // Feedback submission handler
  async function handleFeedbackSubmit(
    feedback: FeedbackType,
    context: FeedbackContext,
    messageContent: string,
    messageId?: string
  ) {
    if (!selectedTaskId || !authConfig) return
    
    try {
      await submitFeedback(
        selectedTaskId,
        {
          feedback,
          context,
          messageContent,
          messageId,
        },
        authConfig,
        apiBase
      )
      // Optionally refresh activity to show feedback was logged
      void refreshActivity()
    } catch (err) {
      console.error('Feedback submission failed:', err)
    }
  }

  // Strike message handler - hides a response from view and excludes from LLM context
  async function handleStrikeMessage(messageTs: string) {
    if (!selectedTaskId || !authConfig) return
    
    try {
      const result = await strikeMessage(selectedTaskId, messageTs, authConfig, apiBase)
      setConversation(result.history)
    } catch (err) {
      console.error('Strike message failed:', err)
    }
  }

  // Unstrike message handler - restores a struck message
  async function handleUnstrikeMessage(messageTs: string) {
    if (!selectedTaskId || !authConfig) return
    
    try {
      const result = await unstrikeMessage(selectedTaskId, messageTs, authConfig, apiBase)
      setConversation(result.history)
    } catch (err) {
      console.error('Unstrike message failed:', err)
    }
  }

  // Global Mode handlers
  async function handlePerspectiveChange(perspective: Perspective) {
    setGlobalPerspective(perspective)
    
    // Fetch fresh stats AND conversation history for the new perspective
    if (!authConfig) return
    try {
      const result = await fetchGlobalContext(authConfig, perspective, apiBase)
      setGlobalStats(result.portfolio)
      // Only update conversation if we got valid history back
      if (result.history) {
        setGlobalConversation(result.history)
      }
    } catch (err) {
      console.error('Failed to load portfolio context:', err)
      // Don't clear conversation on error - keep existing conversation
    }
  }
  
  async function handleSendGlobalMessage(message: string) {
    if (!authConfig) return
    
    setGlobalChatLoading(true)
    try {
      const result = await sendGlobalChat(message, authConfig, apiBase, {
        perspective: globalPerspective,
      })
      setGlobalConversation(result.history)
      setGlobalStats(result.portfolio)
      // Capture pending actions for user editing and confirmation
      if (result.pendingActions && result.pendingActions.length > 0) {
        setPortfolioPendingActions(result.pendingActions)
      }
    } catch (err) {
      console.error('Global chat failed:', err)
      setAssistError(err instanceof Error ? err.message : 'Global chat failed')
    } finally {
      setGlobalChatLoading(false)
    }
  }
  
  async function handleConfirmPortfolioActions(updates: BulkTaskUpdate[]) {
    if (!authConfig || updates.length === 0) return
    
    setPortfolioActionsExecuting(true)
    try {
      const result = await bulkUpdateTasks(updates, authConfig, globalPerspective, apiBase)
      
      if (result.success) {
        setPortfolioPendingActions([])
        // Refresh tasks but stay in Portfolio View (don't auto-select a task)
        await refreshTasks(true)
      } else {
        setAssistError(`${result.failureCount} of ${result.totalUpdates} updates failed`)
      }
    } catch (err) {
      console.error('Bulk update failed:', err)
      setAssistError(err instanceof Error ? err.message : 'Failed to execute updates')
    } finally {
      setPortfolioActionsExecuting(false)
    }
  }
  
  function handleCancelPortfolioActions() {
    setPortfolioPendingActions([])
  }
  
  async function handleClearGlobalHistory() {
    if (!authConfig) return
    
    try {
      await clearGlobalHistory(authConfig, apiBase, globalPerspective)
      setGlobalConversation([])
    } catch (err) {
      console.error('Failed to clear global history:', err)
    }
  }
  
  async function handleStrikeGlobalMessages(messageTimestamps: string[]) {
    if (!authConfig) return
    
    try {
      // Strike each message sequentially (could optimize with batch endpoint later)
      for (const ts of messageTimestamps) {
        const result = await strikeGlobalMessage(authConfig, ts, globalPerspective, apiBase)
        setGlobalConversation(result.history)
      }
    } catch (err) {
      console.error('Failed to strike global messages:', err)
    }
  }
  
  async function handleDeleteGlobalMessage(messageTs: string) {
    if (!authConfig) return
    
    try {
      const result = await deleteGlobalMessage(authConfig, messageTs, globalPerspective, apiBase)
      setGlobalConversation(result.history)
    } catch (err) {
      console.error('Failed to delete global message:', err)
    }
  }
  
  function handleToggleGlobalExpand() {
    setGlobalExpanded(prev => !prev)
    if (!globalExpanded) {
      // Collapsing tasks when expanding global view
      setTaskPanelCollapsed(true)
    }
  }
  
  function handleExpandTasksFromGlobal() {
    setGlobalExpanded(false)
    setTaskPanelCollapsed(false)
  }
  
  // Fetch global context when entering global mode (no task selected)
  useEffect(() => {
    async function loadGlobalContext() {
      if (selectedTaskId || !authConfig) return
      
      try {
        const result = await fetchGlobalContext(authConfig, globalPerspective, apiBase)
        setGlobalStats(result.portfolio)
      } catch (err) {
        console.error('Failed to load portfolio context:', err)
      }
    }
    
    loadGlobalContext()
  }, [selectedTaskId, authConfig, apiBase, globalPerspective])

  const isAuthenticated = !!authConfig
  const envLabel = environmentName ?? 'DEV'

  return (
    <div className="app">
      <header className="app-header-minimal">
        <div className="header-status">
          <span
            className={`status-dot ${isAuthenticated ? 'online' : 'offline'}`}
            aria-label={isAuthenticated ? 'Connected' : 'Not connected'}
          />
          <span className="status-user">{state.userEmail ?? 'Not signed in'}</span>
          <span className="env-badge">{envLabel}</span>
        </div>

        <div className="header-logo-center">
          <img src="/DATA_Logo.png" alt="DATA - Daily Autonomous Task Assistant" className="logo-img-large" />
        </div>

        <div className="header-menu">
          {/* Mode switcher - Cyberpunk card style */}
          {isAuthenticated && (
            <div className="mode-switcher">
              <button
                className={`mode-card ${appMode === 'tasks' ? 'active' : ''}`}
                onClick={() => setAppMode('tasks')}
              >
                <div className="mode-card-inner">
                  <svg className="mode-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                    <path d="M9 12l2 2 4-4" />
                    <circle cx="17" cy="17" r="3" />
                    <path d="M15 17h4M17 15v4" />
                  </svg>
                  <span className="mode-label">TASK</span>
                </div>
                <div className="circuit-lines circuit-left" />
                <div className="circuit-lines circuit-right" />
              </button>
              <button
                className={`mode-card ${appMode === 'email' ? 'active' : ''}`}
                onClick={() => setAppMode('email')}
              >
                <div className="mode-card-inner">
                  <svg className="mode-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <rect x="2" y="4" width="20" height="16" rx="2" />
                    <path d="M22 6l-10 7L2 6" />
                    <path d="M15 12l4-3M15 12l3 4" strokeLinecap="round" />
                  </svg>
                  <span className="mode-label">EMAIL</span>
                </div>
                <div className="circuit-lines circuit-left" />
                <div className="circuit-lines circuit-right" />
              </button>
            </div>
          )}
          <button
            className="icon-button"
            aria-label="Open admin menu"
            onClick={() => {
              setMenuView('auth')
              setMenuOpen(true)
            }}
          >
            ☰
          </button>
      </div>
      </header>

      {menuOpen && (
        <div className="menu-overlay" onClick={() => setMenuOpen(false)}>
          <div className="menu-shell" onClick={(e) => e.stopPropagation()}>
            <button
              className="menu-close-btn"
              onClick={() => setMenuOpen(false)}
              aria-label="Close menu"
            >
              ×
            </button>
            <nav className="menu-nav" aria-label="Admin menu">
              <button
                className={menuView === 'auth' ? 'active' : ''}
                onClick={() => setMenuView('auth')}
              >
                Authentication
              </button>
              <button
                className={menuView === 'environment' ? 'active' : ''}
                onClick={() => setMenuView('environment')}
              >
                Environment
              </button>
              <button
                className={menuView === 'activity' ? 'active' : ''}
                onClick={() => setMenuView('activity')}
                disabled={!authConfig}
              >
                Activity
              </button>
              <button
                className={menuView === 'profile' ? 'active' : ''}
                onClick={() => setMenuView('profile')}
                disabled={!authConfig}
              >
                Profile
              </button>
            </nav>
            <div className="menu-view">
              {menuView === 'auth' && <AuthPanel />}
              {menuView === 'environment' && (
                <div className="menu-panel">
                  <h3>Environment Settings</h3>
                  <div className="field">
                    <label htmlFor="api-base-menu">API Base URL</label>
                    <input
                      id="api-base-menu"
                      value={apiBase}
                      onChange={(e) => setApiBase(e.target.value)}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="source-menu">Data Source</label>
                    <select
                      id="source-menu"
                      value={dataSource}
                      onChange={(e) => setDataSource(e.target.value as DataSource)}
                    >
                      <option value="auto">Auto</option>
                      <option value="live">Live</option>
                      <option value="stub">Stub</option>
                    </select>
                  </div>
                  <div className="env-info">
                    <p><strong>Environment:</strong> {envLabel}</p>
                    <p><strong>Live Tasks:</strong> {liveTasks ? 'Yes' : 'No'}</p>
                  </div>
                </div>
              )}
              {menuView === 'activity' &&
                (authConfig ? (
                  <div className="menu-activity-wrapper">
                    <ActivityFeed
                      entries={activityEntries}
                      onRefresh={refreshActivity}
                      error={activityError}
                      variant="inline"
                    />
                  </div>
                ) : (
                  <p className="subtle">Sign in to view activity.</p>
                ))}
              {menuView === 'profile' &&
                (authConfig ? (
                  <ProfileSettings
                    authConfig={authConfig}
                    apiBase={apiBase}
                  />
                ) : (
                  <p className="subtle">Sign in to view profile.</p>
                ))}
            </div>
          </div>
      </div>
      )}

      {/* Rebalancing Editor - Full page overlay when pending actions exist */}
      {portfolioPendingActions.length > 0 && (
        <RebalancingEditor
          pendingActions={portfolioPendingActions}
          onApply={handleConfirmPortfolioActions}
          onCancel={handleCancelPortfolioActions}
          executing={portfolioActionsExecuting}
        />
      )}

      <main className={`grid ${taskPanelCollapsed ? 'task-collapsed' : ''}`}>
        {!authConfig ? (
          <section className="panel">
            <p>Please sign in to load tasks.</p>
          </section>
        ) : appMode === 'email' ? (
          <EmailDashboard
            authConfig={authConfig}
            apiBase={apiBase}
            onBack={() => setAppMode('tasks')}
            cache={emailCache}
            setCache={setEmailCache}
            selectedAccount={emailSelectedAccount}
            setSelectedAccount={setEmailSelectedAccount}
          />
        ) : (
          <>
            {!taskPanelCollapsed && (
              <TaskList
                tasks={tasks}
                selectedTaskId={selectedTaskId}
                onSelect={handleSelectTask}
                onDeselectAll={() => setSelectedTaskId(null)}
                loading={tasksLoading}
                liveTasks={liveTasks}
                warning={tasksWarning}
                onRefresh={refreshTasks}
                refreshing={tasksLoading}
                workBadge={workBadge}
                emailTasks={emailTasks}
                emailTasksLoading={emailTasksLoading}
                onLoadEmailTasks={loadEmailTasks}
              />
            )}

            <AssistPanel
              selectedTask={selectedTask}
              latestPlan={assistPlan}
              isEngaged={isEngaged}
              running={assistRunning}
              planGenerating={planGenerating}
              researchRunning={researchRunning}
              summarizeRunning={summarizeRunning}
              gmailAccount={gmailAccount}
              onGmailChange={setGmailAccount}
              onRunAssist={handleAssist}
              onGeneratePlan={handleGeneratePlan}
              onClearPlan={handleClearPlan}
              onRunResearch={handleRunResearch}
              onRunSummarize={handleRunSummarize}
              onRunContact={handleRunContact}
              contactRunning={contactRunning}
              contactResults={contactResults}
              contactConfirmation={contactConfirmation}
              gmailOptions={gmailAccounts}
              error={assistError}
              conversation={conversation}
              conversationLoading={conversationLoading}
              onSendMessage={handleSendMessage}
              sendingMessage={sendingMessage}
              taskPanelCollapsed={taskPanelCollapsed}
              onCollapseTasks={() => setTaskPanelCollapsed(true)}
              onQuickAction={handleQuickAction}
              pendingAction={pendingAction}
              updateExecuting={updateExecuting}
              onConfirmUpdate={handleConfirmUpdate}
              onCancelUpdate={handleCancelUpdate}
              onFeedbackSubmit={handleFeedbackSubmit}
              initialWorkspaceItems={workspaceItems}
              onWorkspaceChange={handleWorkspaceChange}
              onDraftEmail={handleDraftEmail}
              onSendEmail={handleSendEmail}
              onSaveDraft={handleSaveDraft}
              onDeleteDraft={handleDeleteDraft}
              onToggleEmailDraft={handleToggleEmailDraft}
              emailDraftLoading={emailDraftLoading}
              emailSending={emailSending}
              emailError={emailError}
              savedDraft={savedDraft}
              emailDraftOpen={emailDraftOpen}
              setEmailDraftOpen={setEmailDraftOpen}
              onStrikeMessage={handleStrikeMessage}
              onUnstrikeMessage={handleUnstrikeMessage}
              // Global Mode props
              globalPerspective={globalPerspective}
              onPerspectiveChange={handlePerspectiveChange}
              globalConversation={globalConversation}
              globalStats={globalStats}
              onSendGlobalMessage={handleSendGlobalMessage}
              globalChatLoading={globalChatLoading}
              onClearGlobalHistory={handleClearGlobalHistory}
              globalExpanded={globalExpanded}
              onToggleGlobalExpand={handleToggleGlobalExpand}
              onExpandTasks={handleExpandTasksFromGlobal}
              onStrikeGlobalMessages={handleStrikeGlobalMessages}
              onDeleteGlobalMessage={handleDeleteGlobalMessage}
              // Attachment props
              attachments={attachments}
              attachmentsLoading={attachmentsLoading}
              selectedAttachmentIds={selectedAttachmentIds}
              onAttachmentSelectionChange={setSelectedAttachmentIds}
            />
          </>
        )}
      </main>
    </div>
  )
}

export default App
