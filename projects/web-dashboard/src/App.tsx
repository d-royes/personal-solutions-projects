import { useCallback, useEffect, useState } from 'react'
import './App.css'
import { TaskList } from './components/TaskList'
import { AssistPanel } from './components/AssistPanel'
import { ActivityFeed } from './components/ActivityFeed'
import { AuthPanel } from './components/AuthPanel'
import {
  fetchActivity,
  fetchConversationHistory,
  fetchTasks,
  generatePlan,
  runAssist,
  runResearch,
  sendChatMessage,
  submitFeedback,
  updateTask,
} from './api'
import type {
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
  const [researchResults, setResearchResults] = useState<string | null>(null)
  const [assistError, setAssistError] = useState<string | null>(null)
  const [gmailAccount, setGmailAccount] = useState('')

  const [conversation, setConversation] = useState<ConversationMessage[]>([])
  const [conversationLoading, setConversationLoading] = useState(false)
  const [sendingMessage, setSendingMessage] = useState(false)
  
  // Task update state
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null)
  const [updateExecuting, setUpdateExecuting] = useState(false)

  const [activityEntries, setActivityEntries] = useState<ActivityEntry[]>([])
  const [activityError, setActivityError] = useState<string | null>(null)
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

  const handleSelectTask = useCallback((taskId: string) => {
    if (taskId !== selectedTaskId) {
      // Clear plan and research when selecting a different task
      setAssistPlan(null)
      setAssistError(null)
      setConversation([])
      setResearchResults(null)
    }
    setSelectedTaskId(taskId)
  }, [selectedTaskId])

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
      const response = await fetchTasks(authConfig, apiBase, {
        source: dataSource,
      })
      const activeTasks = response.tasks.filter(
        (task) => {
          const status = task.status?.toLowerCase() || ''
          return status !== 'complete' && status !== 'completed'
        },
      )
      setTasks(activeTasks)
      setLiveTasks(response.liveTasks)
      setTasksWarning(response.warning ?? null)
      if (response.environment) {
        setEnvironmentName(response.environment.toUpperCase())
      }
      if (!selectedTaskId && activeTasks.length > 0) {
        setSelectedTaskId(activeTasks[0].rowId)
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
    // Load task context and conversation history - NO plan generation
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
    setResearchResults(null)
    setAssistError(null)
    try {
      const response = await runResearch(selectedTask.rowId, authConfig, apiBase, {
        source: dataSource,
        nextSteps: assistPlan?.nextSteps,
      })
      setResearchResults(response.research)
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

  async function handleAssist() {
    // Collapse task panel when engaging DATA
    setTaskPanelCollapsed(true)
    await engageTask()
  }

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
              />
            )}

            <AssistPanel
              selectedTask={selectedTask}
              latestPlan={assistPlan}
              running={assistRunning}
              planGenerating={planGenerating}
              researchRunning={researchRunning}
              researchResults={researchResults}
              gmailAccount={gmailAccount}
              onGmailChange={setGmailAccount}
              onRunAssist={handleAssist}
              onGeneratePlan={handleGeneratePlan}
              onRunResearch={handleRunResearch}
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
            />
          </>
        )}
      </main>
    </div>
  )
}

export default App
