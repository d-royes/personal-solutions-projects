import { useCallback, useEffect, useState, useRef } from 'react'
import './App.css'
import { TaskList } from './components/TaskList'
import { AssistPanel } from './components/AssistPanel'
import { PanelDivider } from './components/PanelDivider'
import { ActivityFeed } from './components/ActivityFeed'
import { AuthPanel } from './components/AuthPanel'
import { RebalancingEditor } from './components/RebalancingEditor'
import { EmailDashboard, emptyEmailCache, type EmailCacheState } from './components/EmailDashboard'
import { CalendarDashboard, emptyCalendarCache, type CalendarCacheState } from './components/CalendarDashboard'
import { ProfileSettings } from './components/ProfileSettings'
import { SettingsPanel } from './components/SettingsPanel'
import { InactivityWarningModal } from './components/InactivityWarningModal'
import { useInactivityTimeout } from './hooks/useInactivityTimeout'
import { useSettings } from './contexts/SettingsContext'
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
  updateFirestoreTask,
  deleteFirestoreTask,
  runFirestoreAssist,
  sendFirestoreTaskChat,
} from './api'
import type { AttachmentInfo } from './api'
import type { Perspective, PortfolioStats, SavedEmailDraft, PortfolioPendingAction, BulkTaskUpdate } from './api'
import type {
  ContactCard,
  ContactSearchResponse,
  FeedbackContext,
  FeedbackType,
  PendingAction,
  PendingEmailDraft,
} from './api'
import type {
  ActivityEntry,
  AppMode,
  AssistPlan,
  CalendarView,
  ConversationMessage,
  DataSource,
  FirestoreTask,
  Task,
  WorkBadge,
} from './types'
import { useAuth } from './auth/AuthContext'

const gmailAccounts = ['church', 'personal']

function App() {
  const { authConfig, state, clearAuth } = useAuth()
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
  
  // Pending email draft from chat (new draft creation)
  const [pendingEmailDraft, setPendingEmailDraft] = useState<PendingEmailDraft | null>(null)

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
  const [selectedFirestoreTask, setSelectedFirestoreTask] = useState<FirestoreTask | null>(null)
  
  const [environmentName, setEnvironmentName] = useState(
    import.meta.env.VITE_ENVIRONMENT ?? 'DEV',
  )
  const [menuOpen, setMenuOpen] = useState(false)
  const [menuView, setMenuView] = useState<'auth' | 'activity' | 'environment' | 'profile' | 'settings'>('auth')
  const [appMode, setAppMode] = useState<AppMode>('tasks')
  const [taskPanelCollapsed, setTaskPanelCollapsed] = useState(false)
  const [assistPanelCollapsed, setAssistPanelCollapsed] = useState(false)
  const [panelSplitRatio, setPanelSplitRatio] = useState(50) // Percentage for left panel
  const [isEngaged, setIsEngaged] = useState(false)  // Tracks if we've engaged with the current task
  const [autoEngageTaskId, setAutoEngageTaskId] = useState<string | null>(null)  // Auto-engage after selecting from calendar

  // Email dashboard state - lifted up to persist across mode switches
  const [emailCache, setEmailCache] = useState<EmailCacheState>({
    personal: emptyEmailCache(),
    church: emptyEmailCache(),
  })
  const [emailSelectedAccount, setEmailSelectedAccount] = useState<'personal' | 'church'>('personal')

  // Calendar dashboard state - lifted up to persist across mode switches
  const [calendarCache, setCalendarCache] = useState<CalendarCacheState>({
    personal: emptyCalendarCache(),
    church: emptyCalendarCache(),
  })
  const [calendarSelectedView, setCalendarSelectedView] = useState<CalendarView>('combined')

  // Global Mode state
  const [globalPerspective, setGlobalPerspective] = useState<Perspective>('personal')
  const [globalConversation, setGlobalConversation] = useState<ConversationMessage[]>([])
  const [globalStats, setGlobalStats] = useState<PortfolioStats | null>(null)
  const [portfolioPendingActions, setPortfolioPendingActions] = useState<PortfolioPendingAction[]>([])
  const [portfolioActionsExecuting, setPortfolioActionsExecuting] = useState(false)
  const [globalChatLoading, setGlobalChatLoading] = useState(false)
  const [globalExpanded, setGlobalExpanded] = useState(false)

  // Settings from context
  const { settings } = useSettings()
  
  // Inactivity timeout - only enabled when authenticated and not disabled in settings
  const inactivityEnabled = !!authConfig && settings.inactivityTimeoutMinutes > 0
  const { showWarning: showInactivityWarning, secondsRemaining, resetInactivity } = useInactivityTimeout({
    warningTimeout: settings.inactivityTimeoutMinutes * 60 * 1000, // Convert minutes to ms
    logoutTimeout: 2 * 60 * 1000,   // 2 minutes warning countdown
    enabled: inactivityEnabled,
    onLogout: clearAuth,
  })

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

  // Handle Firestore task selection
  const handleSelectFirestoreTask = useCallback(async (task: FirestoreTask | null) => {
    setSelectedFirestoreTask(task)
    if (task) {
      // Clear Smartsheet task selection when selecting a Firestore task
      setSelectedTaskId(null)
      setAssistPlan(null)
      setAssistError(null)
      setConversation([])
      setSavedDraft(null)
      setEmailDraftOpen(false)
      setEmailError(null)
      setIsEngaged(false)
      setAttachments([])
      setSelectedAttachmentIds(new Set())
      // Expand assist panel if collapsed
      setAssistPanelCollapsed(false)
      
      // Load any saved draft for this Firestore task
      if (authConfig) {
        try {
          const draftResponse = await loadDraft(`fs:${task.id}`, authConfig, apiBase)
          if (draftResponse.hasDraft && draftResponse.draft) {
            setSavedDraft(draftResponse.draft)
          }
        } catch (err) {
          console.error('Failed to load draft for Firestore task:', err)
        }
      }
    }
  }, [authConfig, apiBase])

  // Handle Firestore task update
  const handleFirestoreTaskUpdate = useCallback(async (taskId: string, updates: Record<string, unknown>) => {
    if (!authConfig) return
    try {
      await updateFirestoreTask(taskId, updates, authConfig, apiBase)
      // Refresh the task list
      loadEmailTasks()
      // Update the selected task if it's the one being updated
      if (selectedFirestoreTask?.id === taskId) {
        setSelectedFirestoreTask(prev => prev ? { ...prev, ...updates } as FirestoreTask : null)
      }
    } catch (error) {
      console.error('Failed to update Firestore task:', error)
      setAssistError((error as Error).message)
    }
  }, [authConfig, apiBase, selectedFirestoreTask])

  // Handle Firestore task delete
  const handleFirestoreTaskDelete = useCallback(async (taskId: string) => {
    if (!authConfig) return
    try {
      await deleteFirestoreTask(taskId, authConfig, apiBase)
      // Clear selection and refresh
      setSelectedFirestoreTask(null)
      loadEmailTasks()
    } catch (error) {
      console.error('Failed to delete Firestore task:', error)
      setAssistError((error as Error).message)
    }
  }, [authConfig, apiBase])

  // Handle closing Firestore task panel
  const handleFirestoreTaskClose = useCallback(() => {
    setSelectedFirestoreTask(null)
  }, [])

  // Panel collapse handlers
  const handleToggleTaskPanel = useCallback(() => {
    setTaskPanelCollapsed(prev => {
      if (!prev) {
        // Collapsing - ensure assist is visible
        setAssistPanelCollapsed(false)
      }
      return !prev
    })
  }, [])

  const handleToggleAssistPanel = useCallback(() => {
    setAssistPanelCollapsed(prev => {
      if (!prev) {
        // Collapsing - ensure task panel is visible
        setTaskPanelCollapsed(false)
      }
      return !prev
    })
  }, [])

  // Panel divider drag handler
  const panelsContainerRef = useRef<HTMLDivElement>(null)
  const handlePanelDrag = useCallback((delta: number) => {
    if (!panelsContainerRef.current) return
    const containerWidth = panelsContainerRef.current.offsetWidth
    const deltaPercent = (delta / containerWidth) * 100
    setPanelSplitRatio(prev => Math.max(25, Math.min(75, prev + deltaPercent)))
  }, [])

  const selectedTask =
    tasks.find((task) => task.rowId === selectedTaskId) ?? null

  useEffect(() => {
    if (authConfig) {
      refreshTasks()
      refreshActivity()
      loadEmailTasks()  // Load Firestore tasks (DATA Tasks) on mount
    } else {
      setTasks([])
      setEmailTasks([])
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

  // Auto-engage when navigating from Calendar Tasks tab
  useEffect(() => {
    if (autoEngageTaskId && selectedTaskId === autoEngageTaskId && selectedTask && !isEngaged) {
      setAutoEngageTaskId(null)  // Clear the flag
      void engageTask()  // Trigger engagement
    }
  }, [autoEngageTaskId, selectedTaskId, selectedTask, isEngaged])

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

  async function engageFirestoreTask() {
    // Engage with a Firestore task - load context, conversation history
    if (!selectedFirestoreTask) return
    if (!authConfig) {
      setAssistError('Please sign in first.')
      return
    }
    setIsEngaged(true)
    setAssistRunning(true)
    setAssistError(null)
    try {
      const response = await runFirestoreAssist(selectedFirestoreTask.id, authConfig, apiBase)
      // Set a minimal "engaged" state - plan will be null until user clicks Plan
      setAssistPlan(response.plan ?? {
        summary: '',
        score: 0,
        labels: [],
        automationTriggers: [],
        nextSteps: [],
        efficiencyTips: [],
        suggestedActions: ['plan', 'research', 'draft_email', 'follow_up'],
        task: response.task as unknown as Task, // Type cast for compatibility
        generator: 'none',
        generatorNotes: [],
      })
      setConversation(response.history ?? [])

      // Load workspace content using fs: prefixed ID
      try {
        const workspace = await loadWorkspace(`fs:${selectedFirestoreTask.id}`, authConfig, apiBase)
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
    // Support both Smartsheet and Firestore tasks
    const taskId = selectedTask?.rowId ?? (selectedFirestoreTask ? `fs:${selectedFirestoreTask.id}` : null)
    if (!taskId) return
    if (!authConfig) {
      setAssistError('Please sign in first.')
      return
    }
    setPlanGenerating(true)
    setAssistError(null)
    try {
      const response = await generatePlan(taskId, authConfig, apiBase, {
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
    // Support both Smartsheet and Firestore tasks
    const taskId = selectedTask?.rowId ?? (selectedFirestoreTask ? `fs:${selectedFirestoreTask.id}` : null)
    if (!taskId) return
    if (!authConfig) {
      setAssistError('Please sign in first.')
      return
    }
    setResearchRunning(true)
    setAssistError(null)
    try {
      const response = await runResearch(taskId, authConfig, apiBase, {
        source: dataSource,
        nextSteps: assistPlan?.nextSteps,
      })
      // Auto-push research to workspace (additive) and trigger save
      if (response.research) {
        setWorkspaceItems(prev => {
          const newItems = [...prev, response.research]
          // Trigger save after state update - support both Smartsheet and Firestore tasks
          const saveTaskId = selectedTask?.rowId ?? (selectedFirestoreTask ? `fs:${selectedFirestoreTask.id}` : null)
          if (saveTaskId && authConfig) {
            void saveWorkspace(saveTaskId, newItems, authConfig, apiBase)
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
    // Support both Smartsheet and Firestore tasks
    const taskId = selectedTask?.rowId ?? (selectedFirestoreTask ? `fs:${selectedFirestoreTask.id}` : null)
    if (!taskId) return
    if (!authConfig) {
      setAssistError('Please sign in first.')
      return
    }
    setSummarizeRunning(true)
    setAssistError(null)
    try {
      const response = await runSummarize(taskId, authConfig, apiBase, {
        source: dataSource,
        planSummary: assistPlan?.summary,
        nextSteps: assistPlan?.nextSteps,
        efficiencyTips: assistPlan?.efficiencyTips,
      })
      // Auto-push summary to workspace (additive) and trigger save
      if (response.summary) {
        setWorkspaceItems(prev => {
          const newItems = [...prev, response.summary]
          // Trigger save after state update - support both Smartsheet and Firestore tasks
          const saveTaskId = selectedTask?.rowId ?? (selectedFirestoreTask ? `fs:${selectedFirestoreTask.id}` : null)
          if (saveTaskId && authConfig) {
            void saveWorkspace(saveTaskId, newItems, authConfig, apiBase)
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
    // Support both Smartsheet and Firestore tasks
    const taskId = selectedTask?.rowId ?? (selectedFirestoreTask ? `fs:${selectedFirestoreTask.id}` : null)
    if (!taskId) return
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
      const response = await searchContacts(taskId, authConfig, apiBase, {
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
            // Trigger save after state update - support both Smartsheet and Firestore tasks
            const saveTaskId = selectedTask?.rowId ?? (selectedFirestoreTask ? `fs:${selectedFirestoreTask.id}` : null)
            if (saveTaskId && authConfig) {
              void saveWorkspace(saveTaskId, newItems, authConfig, apiBase)
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
    // Support both Smartsheet and Firestore tasks
    const taskId = selectedTask?.rowId ?? (selectedFirestoreTask ? `fs:${selectedFirestoreTask.id}` : null)
    if (!taskId) throw new Error('No task selected')
    if (!authConfig) throw new Error('Please sign in first')

    setEmailDraftLoading(true)
    setEmailError(null)
    try {
      const response = await draftEmail(taskId, {
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

  // Save draft to backend - supports both Smartsheet and Firestore tasks
  async function handleSaveDraft(draft: {
    to: string[]
    cc: string[]
    subject: string
    body: string
    fromAccount: string
  }): Promise<void> {
    const taskId = selectedTask?.rowId ?? (selectedFirestoreTask ? `fs:${selectedFirestoreTask.id}` : null)
    if (!taskId) return
    if (!authConfig) return
    
    try {
      const response = await saveDraft(taskId, {
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

  // Delete draft from backend - supports both Smartsheet and Firestore tasks
  async function handleDeleteDraft(): Promise<void> {
    const taskId = selectedTask?.rowId ?? (selectedFirestoreTask ? `fs:${selectedFirestoreTask.id}` : null)
    if (!taskId) return
    if (!authConfig) return
    
    try {
      await deleteDraft(taskId, authConfig, apiBase)
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

  // Email send handler - supports both Smartsheet and Firestore tasks
  async function handleSendEmail(draft: {
    to: string[]
    cc: string[]
    subject: string
    body: string
    fromAccount: string
  }): Promise<void> {
    const taskId = selectedTask?.rowId ?? (selectedFirestoreTask ? `fs:${selectedFirestoreTask.id}` : null)
    if (!taskId) throw new Error('No task selected')
    if (!authConfig) throw new Error('Please sign in first')
    
    setEmailSending(true)
    setEmailError(null)
    try {
      const response = await sendEmail(taskId, {
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
    // Route to appropriate engage function based on task type
    if (selectedFirestoreTask && !selectedTask) {
      await engageFirestoreTask()
    } else if (selectedTask) {
      await engageTask()
    }
  }

  // Debounced workspace save - supports both Smartsheet and Firestore tasks
  const handleWorkspaceChange = useCallback((items: string[]) => {
    setWorkspaceItems(items)
    
    // Clear any pending save
    if (workspaceSaveTimeout) {
      clearTimeout(workspaceSaveTimeout)
    }
    
    // Get task ID (Smartsheet or Firestore with fs: prefix)
    const taskId = selectedTaskId ?? (selectedFirestoreTask ? `fs:${selectedFirestoreTask.id}` : null)
    
    // Debounce save by 1 second
    if (taskId && authConfig) {
      const timeout = setTimeout(async () => {
        try {
          await saveWorkspace(taskId, items, authConfig, apiBase)
        } catch (error) {
          console.error('Failed to save workspace:', error)
        }
      }, 1000)
      setWorkspaceSaveTimeout(timeout)
    }
  }, [selectedTaskId, selectedFirestoreTask, authConfig, apiBase, workspaceSaveTimeout])

  async function handleSendMessage(message: string, workspaceContext?: string) {
    // Support both Smartsheet and Firestore tasks
    const isFirestoreTask = selectedFirestoreTask && !selectedTask
    const taskId = isFirestoreTask ? selectedFirestoreTask?.id : selectedTaskId
    
    if (!taskId || !authConfig) return

    setSendingMessage(true)
    setAssistError(null)

    try {
      // Route to appropriate chat API
      const result = isFirestoreTask
        ? await sendFirestoreTaskChat(
            taskId,
            message,
            authConfig,
            apiBase,
            { workspaceContext },
          )
        : await sendChatMessage(
            taskId,
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
            // Create a new draft if none exists (requires a task ID)
            if (!selectedTaskId) return null
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
        // Also save to backend (use fs: prefix for Firestore tasks)
        const draftTaskId = isFirestoreTask ? `fs:${taskId}` : taskId
        if (savedDraft || update.subject || update.body) {
          void saveDraft(draftTaskId, {
            to: savedDraft?.to ?? [],
            cc: savedDraft?.cc ?? [],
            subject: update.subject ?? savedDraft?.subject ?? '',
            body: update.body ?? savedDraft?.body ?? '',
            fromAccount: savedDraft?.fromAccount ?? '',
          }, authConfig, apiBase)
        }
      }
      
      // Check if DATA created a new email draft from conversation
      if (result.pendingEmailDraft) {
        setPendingEmailDraft(result.pendingEmailDraft)
      }
    } catch (err) {
      console.error('Chat error:', err)
      setAssistError(err instanceof Error ? err.message : 'Chat failed')
    } finally {
      setSendingMessage(false)
    }
  }

  async function handleConfirmUpdate() {
    // Check if this is a Firestore task update
    const isFirestoreUpdate = (pendingAction as { isFirestoreTask?: boolean })?.isFirestoreTask
    const firestoreTaskId = (pendingAction as { firestoreTaskId?: string })?.firestoreTaskId
    
    console.log('handleConfirmUpdate called', { 
      selectedTaskId, 
      firestoreTaskId,
      isFirestoreUpdate,
      authConfig: !!authConfig, 
      pendingAction 
    })
    
    if (!authConfig || !pendingAction) {
      console.log('Early return - missing:', { authConfig: !authConfig, pendingAction: !pendingAction })
      return
    }
    
    // For Firestore updates, we need the firestoreTaskId; for Smartsheet, we need selectedTaskId
    if (!isFirestoreUpdate && !selectedTaskId) {
      console.log('Early return - no task ID for Smartsheet update')
      return
    }

    setUpdateExecuting(true)
    setAssistError(null)

    try {
      if (isFirestoreUpdate && firestoreTaskId) {
        // Handle Firestore task update
        const updates: Record<string, unknown> = {}
        
        // Map pending action to Firestore update format
        if (pendingAction.action === 'mark_complete') {
          updates.done = true
          updates.status = 'completed'
          updates.completedOn = new Date().toISOString().split('T')[0]
        } else if (pendingAction.action === 'update_status' && pendingAction.status) {
          // Map Smartsheet status names to Firestore status values
          const statusMap: Record<string, string> = {
            'Scheduled': 'scheduled',
            'In Progress': 'in_progress',
            'On Hold': 'on_hold',
            'Blocked': 'blocked',
            'Awaiting Reply': 'awaiting_reply',
            'Follow-up': 'follow_up',
            'Delivered': 'delivered',
            'Validation': 'validation',
            'Needs Approval': 'needs_approval',
            'Completed': 'completed',
            'Cancelled': 'cancelled',
            'Delegated': 'delegated',
          }
          updates.status = statusMap[pendingAction.status] || pendingAction.status.toLowerCase().replace(/ /g, '_')
        } else if (pendingAction.action === 'update_due_date' && pendingAction.dueDate) {
          updates.plannedDate = pendingAction.dueDate
        } else if (pendingAction.action === 'update_priority' && pendingAction.priority) {
          updates.priority = pendingAction.priority
        }
        
        if (Object.keys(updates).length > 0) {
          await updateFirestoreTask(firestoreTaskId, updates, authConfig, apiBase)
        }
        
        // Clear the pending action
        setPendingAction(null)
        // Refresh Firestore tasks
        loadEmailTasks()
        // Refresh conversation for this Firestore task
        const historyResponse = await fetch(
          new URL(`/assist/firestore/${firestoreTaskId}/history`, apiBase),
          { headers: authConfig.userEmail ? { 'X-User-Email': authConfig.userEmail } : {} }
        )
        if (historyResponse.ok) {
          const data = await historyResponse.json()
          setConversation(data.history ?? [])
        }
      } else if (selectedTaskId) {
        // Handle Smartsheet task update (existing logic)
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
  
  // Handle confirming a new email draft created from chat
  function handleConfirmEmailDraft() {
    if (!pendingEmailDraft) return
    
    // Get the task ID - works with both Smartsheet and Firestore tasks
    const taskId = selectedTaskId || (selectedFirestoreTask ? `fs:${selectedFirestoreTask.id}` : null)
    if (!taskId) return
    
    // Populate the saved draft with the pending draft content
    setSavedDraft({
      taskId: taskId,
      to: [pendingEmailDraft.recipient],
      cc: [],
      subject: pendingEmailDraft.subject,
      body: pendingEmailDraft.body,
      fromAccount: '',
      sourceContent: '',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    })
    
    // Open the email draft panel
    setEmailDraftOpen(true)
    
    // Clear the pending draft
    setPendingEmailDraft(null)
  }
  
  function handleCancelEmailDraft() {
    setPendingEmailDraft(null)
  }

  // Feedback submission handler - supports both Smartsheet and Firestore tasks
  async function handleFeedbackSubmit(
    feedback: FeedbackType,
    context: FeedbackContext,
    messageContent: string,
    messageId?: string
  ) {
    const taskId = selectedTaskId ?? (selectedFirestoreTask ? `fs:${selectedFirestoreTask.id}` : null)
    if (!taskId || !authConfig) return
    
    try {
      await submitFeedback(
        taskId,
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
  // Supports both Smartsheet and Firestore tasks
  async function handleStrikeMessage(messageTs: string) {
    const taskId = selectedTaskId ?? (selectedFirestoreTask ? `fs:${selectedFirestoreTask.id}` : null)
    if (!taskId || !authConfig) return
    
    try {
      const result = await strikeMessage(taskId, messageTs, authConfig, apiBase)
      setConversation(result.history)
    } catch (err) {
      console.error('Strike message failed:', err)
    }
  }

  // Unstrike message handler - restores a struck message
  // Supports both Smartsheet and Firestore tasks
  async function handleUnstrikeMessage(messageTs: string) {
    const taskId = selectedTaskId ?? (selectedFirestoreTask ? `fs:${selectedFirestoreTask.id}` : null)
    if (!taskId || !authConfig) return
    
    try {
      const result = await unstrikeMessage(taskId, messageTs, authConfig, apiBase)
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
          {/* Mode switcher - Cyberpunk card style with custom images */}
          {isAuthenticated && (
            <div className="mode-switcher">
              <button
                className={`mode-card ${appMode === 'tasks' ? 'active' : ''}`}
                onClick={() => setAppMode('tasks')}
                aria-label="Task Management"
                title="Task Management"
              >
                <img src="/Selector_Task_v1.png" alt="Task" className="mode-card-img" />
              </button>
              <button
                className={`mode-card ${appMode === 'email' ? 'active' : ''}`}
                onClick={() => setAppMode('email')}
                aria-label="Email Management"
                title="Email Management"
              >
                <img src="/Selector_Email_v1.png" alt="Email" className="mode-card-img" />
              </button>
              <button
                className={`mode-card ${appMode === 'calendar' ? 'active' : ''}`}
                onClick={() => setAppMode('calendar')}
                aria-label="Calendar"
                title="Calendar"
              >
                <img src="/Selector_Calendar_v1.png" alt="Calendar" className="mode-card-img" />
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
              <button
                className={menuView === 'settings' ? 'active' : ''}
                onClick={() => setMenuView('settings')}
              >
                Settings
              </button>
            </nav>
            <div className="menu-view">
              {menuView === 'auth' && <AuthPanel onLogin={() => setMenuOpen(false)} />}
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
              {menuView === 'settings' && (
                <SettingsPanel
                  onClose={() => setMenuOpen(false)}
                  authConfig={authConfig}
                  apiBase={apiBase}
                />
              )}
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
            onTaskCreated={loadEmailTasks}
          />
        ) : appMode === 'calendar' ? (
          <CalendarDashboard
            authConfig={authConfig}
            apiBase={apiBase}
            onBack={() => setAppMode('tasks')}
            cache={calendarCache}
            setCache={setCalendarCache}
            selectedView={calendarSelectedView}
            setSelectedView={setCalendarSelectedView}
            tasks={tasks}
            tasksLoading={tasksLoading}
            onRefreshTasks={() => refreshTasks(true)}
            onSelectTaskInTasksMode={(taskId) => {
              setAppMode('tasks')
              handleSelectTask(taskId)
              setAutoEngageTaskId(taskId)  // Auto-engage after selecting
            }}
          />
        ) : (
          <div 
            className={`tasks-panels-container ${taskPanelCollapsed ? 'left-collapsed' : ''} ${assistPanelCollapsed ? 'right-collapsed' : ''}`}
            ref={panelsContainerRef}
          >
            {/* Task List Panel */}
            {!taskPanelCollapsed ? (
              <div 
                className="task-panel-wrapper"
                style={{ width: assistPanelCollapsed ? '100%' : `${panelSplitRatio}%` }}
              >
                <TaskList
                  tasks={tasks}
                  selectedTaskId={selectedTaskId}
                  onSelect={(taskId) => {
                    handleSelectTask(taskId)
                    setSelectedFirestoreTask(null) // Clear Firestore selection
                  }}
                  onDeselectAll={() => {
                    setSelectedTaskId(null)
                    setSelectedFirestoreTask(null)
                  }}
                  loading={tasksLoading}
                  liveTasks={liveTasks}
                  warning={tasksWarning}
                  onRefresh={refreshTasks}
                  refreshing={tasksLoading}
                  workBadge={workBadge}
                  emailTasks={emailTasks}
                  emailTasksLoading={emailTasksLoading}
                  onLoadEmailTasks={loadEmailTasks}
                  // Phase 1f: Firestore integration
                  auth={authConfig}
                  baseUrl={apiBase}
                  onTaskCreated={loadEmailTasks}
                  onTaskUpdated={loadEmailTasks}
                  onTaskDeleted={loadEmailTasks}
                  // Firestore task selection
                  selectedFirestoreTask={selectedFirestoreTask}
                  onSelectFirestoreTask={handleSelectFirestoreTask}
                />
              </div>
            ) : (
              <div className="collapsed-panel-indicator left" onClick={handleToggleTaskPanel}>
                <span className="expand-icon">▶</span>
                <span className="collapsed-label">Tasks</span>
              </div>
            )}

            {/* Panel Divider with collapse arrows */}
            {!taskPanelCollapsed && !assistPanelCollapsed && (
              <PanelDivider
                onDrag={handlePanelDrag}
                onCollapseLeft={handleToggleTaskPanel}
                onCollapseRight={handleToggleAssistPanel}
                leftCollapsed={taskPanelCollapsed}
                rightCollapsed={assistPanelCollapsed}
                leftLabel="Tasks"
                rightLabel="Assistant"
              />
            )}

            {/* Assist Panel */}
            {!assistPanelCollapsed ? (
              <div 
                className="assist-panel-wrapper"
                style={{ width: taskPanelCollapsed ? '100%' : `${100 - panelSplitRatio}%` }}
              >
                <AssistPanel
                  selectedTask={selectedTask}
                  // Firestore task props
                  selectedFirestoreTask={selectedFirestoreTask}
                  onFirestoreTaskUpdate={handleFirestoreTaskUpdate}
                  onFirestoreTaskDelete={handleFirestoreTaskDelete}
                  onFirestoreTaskClose={handleFirestoreTaskClose}
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
                  onCollapseTasks={handleToggleTaskPanel}
                  onQuickAction={handleQuickAction}
                  pendingAction={pendingAction}
                  updateExecuting={updateExecuting}
                  onConfirmUpdate={handleConfirmUpdate}
                  onCancelUpdate={handleCancelUpdate}
                  pendingEmailDraft={pendingEmailDraft}
                  onConfirmEmailDraft={handleConfirmEmailDraft}
                  onCancelEmailDraft={handleCancelEmailDraft}
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
              </div>
            ) : (
              <div className="collapsed-panel-indicator right" onClick={handleToggleAssistPanel}>
                <span className="collapsed-label">Assistant</span>
                <span className="expand-icon">◀</span>
              </div>
            )}
          </div>
        )}
      </main>

      {/* Inactivity Warning Modal */}
      {showInactivityWarning && (
        <InactivityWarningModal
          secondsRemaining={secondsRemaining}
          onStayLoggedIn={resetInactivity}
        />
      )}
    </div>
  )
}

export default App
