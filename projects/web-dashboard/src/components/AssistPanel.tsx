import { useEffect, useState } from 'react'
import type { AssistPlan, ConversationMessage, Task } from '../types'

const NOTES_PREVIEW_LIMIT = 350

function notesPreview(notes?: string | null) {
  if (!notes) return null
  if (notes.length <= NOTES_PREVIEW_LIMIT) return notes
  return `${notes.slice(0, NOTES_PREVIEW_LIMIT)}…`
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
}: AssistPanelProps) {
  const [showFullNotes, setShowFullNotes] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    setShowFullNotes(false)
    setMessage('')
  }, [selectedTask?.rowId])

  const disableSend = sendingMessage || !message.trim()

  return (
    <section className="panel assist-panel scroll-panel">
      <header>
        <h2>Assistant</h2>
      </header>
      {!selectedTask ? (
        <p>Select a task to view details.</p>
      ) : (
        <>
          <div className="task-details">
            <h3>{selectedTask.title}</h3>
            <div className="task-meta">
              <span>{selectedTask.project}</span>
              <span>{selectedTask.priority}</span>
              <span>{new Date(selectedTask.due).toLocaleString()}</span>
            </div>
            <p>{selectedTask.nextStep}</p>
            {selectedTask.notes && (
              <div className="notes">
                <p>
                  {showFullNotes
                    ? selectedTask.notes
                    : notesPreview(selectedTask.notes)}
                </p>
                {selectedTask.notes.length > NOTES_PREVIEW_LIMIT && (
                  <button
                    className="link-button"
                    onClick={() => setShowFullNotes((prev) => !prev)}
                  >
                    {showFullNotes ? 'Show less' : 'Show full note'}
                  </button>
                )}
              </div>
            )}
          </div>

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

          {error && <p className="warning">{error}</p>}

          <button
            className="primary"
            disabled={running}
            onClick={() =>
              onRunAssist(
                gmailAccount ? { sendEmailAccount: gmailAccount } : undefined,
              )
            }
          >
            {running ? 'Running…' : 'Run Assist'}
          </button>

          {latestPlan && (
            <div className="plan-output">
              <h4>Summary</h4>
              <p>{latestPlan.summary}</p>
              <h4>Next Steps</h4>
              <ul>
                {latestPlan.nextSteps.map((step, index) => (
                  <li key={index}>{step}</li>
                ))}
              </ul>
              <h4>Efficiency Tips</h4>
              <ul>
                {latestPlan.efficiencyTips.map((tip, index) => (
                  <li key={index}>{tip}</li>
                ))}
              </ul>
              <h4>Email Draft</h4>
              <pre>{latestPlan.emailDraft}</pre>
              {latestPlan.messageId && (
                <p className="success">
                  Email sent! Message ID: {latestPlan.messageId}
                </p>
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
            </div>
          )}

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
              Coach the assistant (e.g., “Mention the budget note”)
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
        </>
      )}
    </section>
  )
}

