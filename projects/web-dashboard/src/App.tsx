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
  runAssist,
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
  const [assistError, setAssistError] = useState<string | null>(null)
  const [gmailAccount, setGmailAccount] = useState('')

  const [conversation, setConversation] = useState<ConversationMessage[]>([])
  const [conversationLoading, setConversationLoading] = useState(false)
  const [sendingMessage, setSendingMessage] = useState(false)

  const [activityEntries, setActivityEntries] = useState<ActivityEntry[]>([])
  const [activityError, setActivityError] = useState<string | null>(null)
  const [environmentName, setEnvironmentName] = useState(
    import.meta.env.VITE_ENVIRONMENT ?? 'DEV',
  )
  const [menuOpen, setMenuOpen] = useState(false)
  const [menuView, setMenuView] = useState<'auth' | 'activity'>('auth')
  const [taskPanelCollapsed, setTaskPanelCollapsed] = useState(false)

  const handleQuickAction = useCallback((action: { type: string; content: string }) => {
    console.debug('Quick action', action)
  }, [])

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
        (task) => task.status?.toLowerCase() !== 'completed',
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

  async function triggerAssist(options?: {
    sendEmailAccount?: string
    instructions?: string
  }) {
    if (!selectedTask) return
    if (!authConfig) {
      setAssistError('Please sign in first.')
      return
    }
    const hasInstructions = Boolean(options?.instructions)
    if (hasInstructions) {
      setSendingMessage(true)
    } else {
      setAssistRunning(true)
    }
    setAssistError(null)
    try {
      const response = await runAssist(selectedTask.rowId, authConfig, apiBase, {
        source: dataSource,
        sendEmailAccount: options?.sendEmailAccount,
        instructions: options?.instructions,
      })
      setAssistPlan(response.plan)
      setConversation(response.history ?? [])
      void refreshActivity()
    } catch (error) {
      setAssistError((error as Error).message)
    } finally {
      setAssistRunning(false)
      setSendingMessage(false)
    }
  }

  async function handleAssist(options?: { sendEmailAccount?: string }) {
    await triggerAssist({ sendEmailAccount: options?.sendEmailAccount })
  }

  async function handleSendMessage(message: string) {
    await triggerAssist({ instructions: message })
  }

  const isAuthenticated = !!authConfig
  const envLabel = environmentName ?? 'DEV'

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-left">
          <div className="status-chip">
            <span
              className={`status-dot ${isAuthenticated ? 'online' : 'offline'}`}
              aria-label={isAuthenticated ? 'Connected' : 'Not connected'}
            />
            <div className="status-text">
              <strong>{state.userEmail ?? 'Not signed in'}</strong>
              <span className="env-badge">{envLabel}</span>
            </div>
          </div>
          <h1 className="app-title">Daily Task Assistant</h1>
        </div>

        <div className="header-controls">
          <div className="field">
            <label htmlFor="api-base">API Base URL</label>
            <input
              id="api-base"
              value={apiBase}
              onChange={(e) => setApiBase(e.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="source">Data Source</label>
            <select
              id="source"
              value={dataSource}
              onChange={(e) => setDataSource(e.target.value as DataSource)}
            >
              <option value="auto">Auto</option>
              <option value="live">Live</option>
              <option value="stub">Stub</option>
            </select>
          </div>

          <button onClick={refreshTasks} disabled={tasksLoading}>
            Refresh Tasks
          </button>

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
                className={menuView === 'activity' ? 'active' : ''}
                onClick={() => setMenuView('activity')}
                disabled={!authConfig}
              >
                Activity
              </button>
            </nav>
            <div className="menu-view">
              {menuView === 'auth' && <AuthPanel onClose={() => setMenuOpen(false)} />}
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
                onSelect={setSelectedTaskId}
                loading={tasksLoading}
                liveTasks={liveTasks}
                warning={tasksWarning}
                onCollapse={() => setTaskPanelCollapsed(true)}
              />
            )}

            <AssistPanel
              selectedTask={selectedTask}
              latestPlan={assistPlan}
              running={assistRunning}
              gmailAccount={gmailAccount}
              onGmailChange={setGmailAccount}
              onRunAssist={handleAssist}
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
            />
          </>
        )}
      </main>
    </div>
  )
}

export default App
