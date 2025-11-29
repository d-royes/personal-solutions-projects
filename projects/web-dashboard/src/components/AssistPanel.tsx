import { useEffect, useState } from 'react'
import type { AssistPlan, ConversationMessage, Task } from '../types'

const NOTES_PREVIEW_LIMIT = 350

function notesPreview(notes?: string | null) {
  if (!notes) return null
  if (notes.length <= NOTES_PREVIEW_LIMIT) return notes
  return `${notes.slice(0, NOTES_PREVIEW_LIMIT)}…`
}

function truncateCopy(text?: string | null, limit = 320) {
  if (!text) return ''
  if (text.length <= limit) return text
  return `${text.slice(0, limit)}…`
}

interface AssistPanelProps {
  selectedTask: Task | null
  latestPlan: AssistPlan | null
  running: boolean
  gmailAccount: string
  onGmailChange: (account: string) => void
  onRunAssist: (options?: { sendEmailAccount?: string }) => void
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
}

export function AssistPanel({
  selectedTask,
  latestPlan,
  running,
  gmailAccount,
  onGmailChange,
  onRunAssist,
  gmailOptions,
  error,
  conversation,
  conversationLoading,
  onSendMessage,
  sendingMessage,
  taskPanelCollapsed,
  onExpandTasks,
  onCollapseTasks,
  onQuickAction,
}: AssistPanelProps) {
  const [showFullNotes, setShowFullNotes] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    setShowFullNotes(false)
    setMessage('')
  }, [selectedTask?.rowId])

  const disableSend = sendingMessage || !message.trim()

  const handleQuickInsert = (content: string, type: string) => {
    if (!content) return
    setMessage(content)
    onQuickAction?.({ type, content })
  }

  return (
    <section className="panel assist-panel scroll-panel">
      <header>
        <h2>Assistant</h2>
        <div className="assist-header-controls">
          {taskPanelCollapsed ? (
            <button className="secondary" onClick={onExpandTasks}>
              Show tasks
            </button>
          ) : (
            <button className="secondary" onClick={onCollapseTasks}>
              Collapse tasks
            </button>
          )}
        </div>
      </header>
      {!selectedTask ? (
        <p>Select a task to view details.</p>
      ) : (
        <>
          <section className="assist-context">
            <div className="task-signals">
              <span className="badge status">{selectedTask.status}</span>
              {selectedTask.priority && (
                <span className={`badge priority ${selectedTask.priority.toLowerCase()}`}>
                  {selectedTask.priority}
                </span>
              )}
              <span className="badge due">
                {new Date(selectedTask.due).toLocaleString()}
              </span>
            </div>
            <div className="task-context-meta">
              <strong>{selectedTask.title}</strong>
              <span>{selectedTask.project}</span>
              {selectedTask.assignedTo && <span>Owner: {selectedTask.assignedTo}</span>}
            </div>
            <div className="notes">
              <p>
                {showFullNotes
                  ? selectedTask.notes || 'No additional notes.'
                  : notesPreview(selectedTask.notes) ||
                    'No additional notes captured yet.'}
              </p>
              {selectedTask.notes &&
                selectedTask.notes.length > NOTES_PREVIEW_LIMIT && (
                  <button
                    className="link-button"
                    onClick={() => setShowFullNotes((prev) => !prev)}
                  >
                    {showFullNotes ? 'Show less' : 'Show full note'}
                  </button>
                )}
            </div>
          </section>

          <section className="assist-plan">
            <div className="assist-plan-header">
              <h3>Current plan</h3>
              {error && <p className="warning">{error}</p>}
            </div>
            {latestPlan ? (
              <>
                <p className="plan-summary">
                  {truncateCopy(latestPlan.summary)}
                  <button
                    type="button"
                    className="link-button inline"
                    onClick={() =>
                      handleQuickInsert(
                        'Can you provide a tighter summary focusing on the first actionable step?',
                        'refine-summary',
                      )
                    }
                  >
                    Shorten summary
                  </button>
                </p>
                <div className="plan-columns">
                  <div>
                    <h4>Next steps</h4>
                    {latestPlan.nextSteps.length ? (
                      <ul>
                        {latestPlan.nextSteps.slice(0, 5).map((step, index) => (
                          <li key={index}>
                            {step}
                            <button
                              type="button"
                              className="link-button inline"
                              onClick={() =>
                                handleQuickInsert(
                                  `Refine this next step: ${step}`,
                                  'refine-step',
                                )
                              }
                            >
                              Refine
                            </button>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="subtle">No next steps yet—run an assist to draft some.</p>
                    )}
                  </div>
                  <div>
                    <h4>Efficiency tips</h4>
                    {latestPlan.efficiencyTips.length ? (
                      <ul>
                        {latestPlan.efficiencyTips.slice(0, 4).map((tip, index) => (
                          <li key={index}>
                            {tip}
                            <button
                              type="button"
                              className="link-button inline"
                              onClick={() =>
                                handleQuickInsert(
                                  `Adapt this efficiency tip: ${tip}`,
                                  'refine-tip',
                                )
                              }
                            >
                              Apply
                            </button>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="subtle">No efficiency tips for this task.</p>
                    )}
                  </div>
                </div>
                {latestPlan.emailDraft && (
                  <details>
                    <summary>Email draft</summary>
                    <pre>{latestPlan.emailDraft}</pre>
                  </details>
                )}
                {latestPlan.warnings && latestPlan.warnings.length > 0 && (
                  <div className="warning">
                    <p>Warnings:</p>
                    <ul>
                      {latestPlan.warnings.map((warning, index) => (
                        <li key={index}>{warning}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            ) : (
              <p className="subtle">Run an assist to generate a plan for this task.</p>
            )}
          </section>

          <section className="assist-actions">
            <div className="field">
              <label htmlFor="gmail-account">Send with Gmail account</label>
              <select
                id="gmail-account"
                value={gmailAccount}
                onChange={(e) => onGmailChange(e.target.value)}
              >
                <option value="">Do not send</option>
                {gmailOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
            <button
              className="primary"
              disabled={running}
              onClick={() =>
                onRunAssist(gmailAccount ? { sendEmailAccount: gmailAccount } : undefined)
              }
            >
              {running ? 'Running…' : 'Run Assist'}
            </button>
          </section>

          <section className="assistant-chat">
            <h3>Conversation</h3>
            <div className="chat-thread">
              {conversationLoading ? (
                <p className="subtle">Loading conversation…</p>
              ) : conversation.length === 0 ? (
                <p className="subtle">
                  Start a conversation to collaborate on this task.
                </p>
              ) : (
                conversation.map((entry, index) => (
                  <div
                    key={`${entry.ts}-${index}`}
                    className={`chat-bubble ${entry.role}`}
                  >
                    <div className="chat-meta">
                      <span>{entry.role === 'assistant' ? 'Assistant' : 'You'}</span>
                      <span>{new Date(entry.ts).toLocaleString()}</span>
                    </div>
                    <div className="chat-content">{entry.content}</div>
                  </div>
                ))
              )}
            </div>

            <form
              className="chat-input"
              onSubmit={async (event) => {
                event.preventDefault()
                if (!message.trim()) return
                const payload = message.trim()
                setMessage('')
                await onSendMessage(payload)
              }}
            >
              <label htmlFor="assistant-chat" className="subtle">
                Coach the assistant (e.g., “Ask for a shorter summary”)
              </label>
              <textarea
                id="assistant-chat"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
              />
              <button type="submit" disabled={disableSend}>
                {sendingMessage ? 'Sending…' : 'Send'}
              </button>
            </form>
          </section>
        </>
      )}
    </section>
  )
}

