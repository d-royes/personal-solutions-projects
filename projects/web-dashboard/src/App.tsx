import { useCallback, useEffect, useState } from 'react'
import './App.css'
import { TaskList } from './components/TaskList'
import { AssistPanel } from './components/AssistPanel'
import { ActivityFeed } from './components/ActivityFeed'
import { AuthPanel } from './components/AuthPanel'
import {
  deleteDraft,
  draftEmail,
  fetchActivity,
  fetchConversationHistory,
  fetchTasks,
  fetchWorkBadge,
  generatePlan,
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
  strikeMessage,
  submitFeedback,
  unstrikeMessage,
  updateTask,
} from './api'
import type { SavedEmailDraft } from './api'
import type {
  ContactCard,
  ContactSearchResponse,
  FeedbackContext,
  FeedbackType,
  PendingAction,
} from './api'
import type {
  ActivityEntry,
  AssistPlan,
  ConversationMessage,
  DataSource,
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

  const [activityEntries, setActivityEntries] = useState<ActivityEntry[]>([])
  const [activityError, setActivityError] = useState<string | null>(null)
  const [workBadge, setWorkBadge] = useState<WorkBadge | null>(null)
  const [environmentName, setEnvironmentName] = useState(
    import.meta.env.VITE_ENVIRONMENT ?? 'DEV',
  )
  const [menuOpen, setMenuOpen] = useState(false)
  const [menuView, setMenuView] = useState<'auth' | 'activity' | 'environment'>('auth')
  const [taskPanelCollapsed, setTaskPanelCollapsed] = useState(false)

  const handleQuickAction = useCallback((action: { type: string; content: string }) => {
    // Action handling is now done within AssistPanel
    console.debug('Quick action triggered:', action)
  }, [])

  const handleSelectTask = useCallback(async (taskId: string) => {
    if (taskId !== selectedTaskId) {
      // Clear plan when selecting a different task
      setAssistPlan(null)
      setAssistError(null)
      setConversation([])
      setSavedDraft(null)
      setEmailDraftOpen(false)
      setEmailError(null)
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

  async function refreshTasks() {
    if (!authConfig) return
    setTasksLoading(true)
    setTasksWarning(null)
    try {
      // Fetch tasks from all sheets (personal + work) so Work filter can show them
      const response = await fetchTasks(authConfig, apiBase, {
        source: dataSource,
        includeWork: true,  // Include work tasks in the response
      })
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
      if (!selectedTaskId && activeTasks.length > 0) {
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

  async function handleGeneratePlan() {
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
      })
      setAssistPlan(response.plan)
      void refreshActivity()
    } catch (error) {
      setAssistError((error as Error).message)
    } finally {
      setPlanGenerating(false)
    }
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
  ): Promise<{ subject: string; body: string }> {
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

  async function handleSendMessage(message: string) {
    if (!selectedTaskId || !authConfig) return
    
    setSendingMessage(true)
    setAssistError(null)
    
    try {
      const result = await sendChatMessage(
        selectedTaskId,
        message,
        authConfig,
        apiBase,
        dataSource,
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
    if (!selectedTaskId || !authConfig || !pendingAction) return
    
    setUpdateExecuting(true)
    setAssistError(null)
    
    try {
      const result = await updateTask(
        selectedTaskId,
        {
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
            </nav>
            <div className="menu-view">
              {menuView === 'auth' && <AuthPanel onClose={() => setMenuOpen(false)} />}
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
            </div>
          </div>
      </div>
      )}

      <main className={`grid ${taskPanelCollapsed ? 'task-collapsed' : ''}`}>
        {!authConfig ? (
          <section className="panel">
            <p>Please sign in to load tasks.</p>
          </section>
        ) : (
          <>
            {!taskPanelCollapsed && (
              <TaskList
                tasks={tasks}
                selectedTaskId={selectedTaskId}
                onSelect={handleSelectTask}
                loading={tasksLoading}
                liveTasks={liveTasks}
                warning={tasksWarning}
                onRefresh={refreshTasks}
                refreshing={tasksLoading}
                workBadge={workBadge}
              />
            )}

            <AssistPanel
              selectedTask={selectedTask}
              latestPlan={assistPlan}
              running={assistRunning}
              planGenerating={planGenerating}
              researchRunning={researchRunning}
              summarizeRunning={summarizeRunning}
              gmailAccount={gmailAccount}
              onGmailChange={setGmailAccount}
              onRunAssist={handleAssist}
              onGeneratePlan={handleGeneratePlan}
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
              onExpandTasks={() => setTaskPanelCollapsed(false)}
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
            />
          </>
        )}
      </main>
    </div>
  )
}

export default App
