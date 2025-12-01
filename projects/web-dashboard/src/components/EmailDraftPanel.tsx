import { useState, useEffect } from 'react'
import type { ContactCard } from '../api'

export interface EmailDraft {
  to: string[]
  cc: string[]
  subject: string
  body: string
  fromAccount: string
}

interface EmailDraftPanelProps {
  isOpen: boolean
  onClose: (currentDraft: EmailDraft) => void
  onSend: (draft: EmailDraft) => Promise<void>
  onRegenerate: (instructions: string) => Promise<void>
  onRefineInChat: (draft: EmailDraft) => void
  initialDraft?: Partial<EmailDraft>
  suggestedContacts?: ContactCard[]
  gmailAccounts: string[]
  sending: boolean
  regenerating: boolean
  error?: string | null
}

/**
 * Email Draft Panel - Overlay for composing and sending emails
 * 
 * Features:
 * - To/CC recipient fields with manual entry
 * - Subject and body editing
 * - Gmail account selection (church/personal)
 * - Regenerate with instructions
 * - Refine in Chat option
 */
export function EmailDraftPanel({
  isOpen,
  onClose,
  onSend,
  onRegenerate,
  onRefineInChat,
  initialDraft,
  suggestedContacts,
  gmailAccounts,
  sending,
  regenerating,
  error,
}: EmailDraftPanelProps) {
  const [toInput, setToInput] = useState('')
  const [ccInput, setCcInput] = useState('')
  const [to, setTo] = useState<string[]>([])
  const [cc, setCc] = useState<string[]>([])
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [fromAccount, setFromAccount] = useState('')
  const [regenerateInput, setRegenerateInput] = useState('')
  const [showContactPicker, setShowContactPicker] = useState<'to' | 'cc' | null>(null)

  // Initialize from draft when it changes
  useEffect(() => {
    if (initialDraft) {
      setTo(initialDraft.to ?? [])
      setCc(initialDraft.cc ?? [])
      setSubject(initialDraft.subject ?? '')
      setBody(initialDraft.body ?? '')
      setFromAccount(initialDraft.fromAccount ?? '')
    }
  }, [initialDraft])

  if (!isOpen) return null

  const handleAddRecipient = (field: 'to' | 'cc') => {
    const input = field === 'to' ? toInput : ccInput
    const setInput = field === 'to' ? setToInput : setCcInput
    const list = field === 'to' ? to : cc
    const setList = field === 'to' ? setTo : setCc

    // Split by comma and add valid emails
    const emails = input.split(',').map(e => e.trim()).filter(e => e.includes('@'))
    if (emails.length > 0) {
      setList([...list, ...emails])
      setInput('')
    }
  }

  const handleRemoveRecipient = (field: 'to' | 'cc', email: string) => {
    if (field === 'to') {
      setTo(to.filter(e => e !== email))
    } else {
      setCc(cc.filter(e => e !== email))
    }
  }

  const handleAddContact = (contact: ContactCard, field: 'to' | 'cc') => {
    if (contact.email) {
      if (field === 'to') {
        setTo([...to, contact.email])
      } else {
        setCc([...cc, contact.email])
      }
    }
    setShowContactPicker(null)
  }

  const handleSend = async () => {
    if (to.length === 0 || !fromAccount) return
    await onSend({
      to,
      cc,
      subject,
      body,
      fromAccount,
    })
  }

  const handleRegenerate = async () => {
    if (!regenerateInput.trim()) return
    await onRegenerate(regenerateInput)
    setRegenerateInput('')
  }

  const handleRefineInChat = () => {
    onRefineInChat({
      to,
      cc,
      subject,
      body,
      fromAccount,
    })
  }

  const canSend = to.length > 0 && fromAccount && subject.trim() && body.trim()

  return (
    <div className="email-draft-overlay">
      <div className="email-draft-panel">
        {/* Header */}
        <div className="email-draft-header">
          <h3>✉️ Draft Email</h3>
          <div className="email-draft-header-actions">
            <button 
              className="secondary" 
              onClick={() => onClose({ to, cc, subject, body, fromAccount })}
              title="Save and close"
            >
              Save
            </button>
            <button 
              className="icon-btn" 
              onClick={() => onClose({ to, cc, subject, body, fromAccount })}
              title="Close"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Error message */}
        {error && (
          <div className="email-draft-error">
            <span>⚠️ {error}</span>
          </div>
        )}

        {/* From Account */}
        <div className="email-draft-field">
          <label>From:</label>
          <div className="email-account-selector">
            {gmailAccounts.map(account => (
              <label key={account} className="radio-option">
                <input
                  type="radio"
                  name="fromAccount"
                  value={account}
                  checked={fromAccount === account}
                  onChange={(e) => setFromAccount(e.target.value)}
                />
                <span className="radio-label">{account.charAt(0).toUpperCase() + account.slice(1)}</span>
              </label>
            ))}
          </div>
        </div>

        {/* To Field */}
        <div className="email-draft-field">
          <label>To:</label>
          <div className="email-recipients">
            <div className="recipient-chips">
              {to.map(email => (
                <span key={email} className="recipient-chip">
                  {email}
                  <button 
                    className="chip-remove" 
                    onClick={() => handleRemoveRecipient('to', email)}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
            <div className="recipient-input-row">
              <input
                type="email"
                value={toInput}
                onChange={(e) => setToInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ',') {
                    e.preventDefault()
                    handleAddRecipient('to')
                  }
                }}
                placeholder="Enter email address"
              />
              <button 
                className="add-btn"
                onClick={() => handleAddRecipient('to')}
                title="Add recipient"
              >
                +
              </button>
              {suggestedContacts && suggestedContacts.length > 0 && (
                <button 
                  className="contact-btn"
                  onClick={() => setShowContactPicker(showContactPicker === 'to' ? null : 'to')}
                  title="Select from contacts"
                >
                  📇
                </button>
              )}
            </div>
            {showContactPicker === 'to' && suggestedContacts && (
              <div className="contact-picker">
                {suggestedContacts.filter(c => c.email).map((contact, idx) => (
                  <button
                    key={idx}
                    className="contact-option"
                    onClick={() => handleAddContact(contact, 'to')}
                  >
                    <span className="contact-name">{contact.name}</span>
                    <span className="contact-email">{contact.email}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* CC Field */}
        <div className="email-draft-field">
          <label>Cc:</label>
          <div className="email-recipients">
            <div className="recipient-chips">
              {cc.map(email => (
                <span key={email} className="recipient-chip">
                  {email}
                  <button 
                    className="chip-remove" 
                    onClick={() => handleRemoveRecipient('cc', email)}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
            <div className="recipient-input-row">
              <input
                type="email"
                value={ccInput}
                onChange={(e) => setCcInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ',') {
                    e.preventDefault()
                    handleAddRecipient('cc')
                  }
                }}
                placeholder="Optional CC"
              />
              <button 
                className="add-btn"
                onClick={() => handleAddRecipient('cc')}
                title="Add CC"
              >
                +
              </button>
            </div>
          </div>
        </div>

        {/* Subject */}
        <div className="email-draft-field">
          <label>Subject:</label>
          <input
            type="text"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Email subject"
            className="subject-input"
          />
        </div>

        {/* Body */}
        <div className="email-draft-field email-body-field">
          <label>Body:</label>
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Email body..."
            className="email-body-input"
          />
        </div>

        {/* Regenerate Section */}
        <div className="email-draft-regenerate">
          <input
            type="text"
            value={regenerateInput}
            onChange={(e) => setRegenerateInput(e.target.value)}
            placeholder="Make it more formal, add urgency, etc..."
            className="regenerate-input"
          />
          <button
            className="secondary"
            onClick={handleRegenerate}
            disabled={regenerating || !regenerateInput.trim()}
          >
            {regenerating ? '🔄 Regenerating...' : '🔄 Regenerate'}
          </button>
          <button
            className="secondary"
            onClick={handleRefineInChat}
          >
            💬 Refine in Chat
          </button>
        </div>

        {/* Send Button */}
        <div className="email-draft-footer">
          <div className="send-requirements">
            {!fromAccount && <span className="requirement">Select a From account</span>}
            {to.length === 0 && <span className="requirement">Add at least one recipient</span>}
          </div>
          <button
            className="primary send-btn"
            onClick={handleSend}
            disabled={!canSend || sending}
          >
            {sending ? 'Sending...' : 'Send ➤'}
          </button>
        </div>
      </div>
    </div>
  )
}

