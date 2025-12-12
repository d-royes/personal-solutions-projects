import { useState, useEffect, useCallback } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Link from '@tiptap/extension-link'
import type { ContactCard } from '../api'

export interface EmailDraft {
  to: string[]
  cc: string[]
  subject: string
  body: string
  fromAccount: string
}

// Rich text toolbar component
function RichTextToolbar({ editor }: { editor: ReturnType<typeof useEditor> }) {
  if (!editor) return null

  return (
    <div className="rich-text-toolbar">
      <button
        type="button"
        className={`toolbar-btn ${editor.isActive('bold') ? 'active' : ''}`}
        onClick={() => editor.chain().focus().toggleBold().run()}
        title="Bold (Ctrl+B)"
      >
        <strong>B</strong>
      </button>
      <button
        type="button"
        className={`toolbar-btn ${editor.isActive('italic') ? 'active' : ''}`}
        onClick={() => editor.chain().focus().toggleItalic().run()}
        title="Italic (Ctrl+I)"
      >
        <em>I</em>
      </button>
      <span className="toolbar-separator" />
      <button
        type="button"
        className={`toolbar-btn ${editor.isActive('bulletList') ? 'active' : ''}`}
        onClick={() => editor.chain().focus().toggleBulletList().run()}
        title="Bullet List"
      >
        • —
      </button>
      <button
        type="button"
        className={`toolbar-btn ${editor.isActive('orderedList') ? 'active' : ''}`}
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
        title="Numbered List"
      >
        1. —
      </button>
      <span className="toolbar-separator" />
      <button
        type="button"
        className={`toolbar-btn ${editor.isActive('link') ? 'active' : ''}`}
        onClick={() => {
          const previousUrl = editor.getAttributes('link').href
          const url = window.prompt('Enter URL:', previousUrl)
          if (url === null) return
          if (url === '') {
            editor.chain().focus().extendMarkRange('link').unsetLink().run()
          } else {
            editor.chain().focus().extendMarkRange('link').setLink({ href: url }).run()
          }
        }}
        title="Insert Link"
      >
        🔗
      </button>
    </div>
  )
}

interface EmailDraftPanelProps {
  isOpen: boolean
  onClose: (currentDraft: EmailDraft) => void
  onSend: (draft: EmailDraft) => Promise<void>
  onRegenerate: (instructions: string) => Promise<void>
  onDiscard: () => Promise<void>
  initialDraft?: Partial<EmailDraft>
  suggestedContacts?: ContactCard[]
  taskNotes?: string  // Task notes to extract emails from
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
 */
// Helper to extract email addresses from text
function extractEmailsFromText(text: string): string[] {
  if (!text) return []
  // Match email patterns
  const emailRegex = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g
  const matches = text.match(emailRegex) || []
  // Deduplicate and return
  return [...new Set(matches)]
}

export function EmailDraftPanel({
  isOpen,
  onClose,
  onSend,
  onRegenerate,
  onDiscard,
  initialDraft,
  suggestedContacts,
  taskNotes,
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
  const [fromAccount, setFromAccount] = useState('')
  const [regenerateInput, setRegenerateInput] = useState('')
  const [showContactPicker, setShowContactPicker] = useState<'to' | 'cc' | null>(null)

  // Rich text editor
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        bulletList: { HTMLAttributes: { class: 'email-bullet-list' } },
        orderedList: { HTMLAttributes: { class: 'email-ordered-list' } },
      }),
      Link.configure({
        openOnClick: false,
        HTMLAttributes: { class: 'email-link' },
      }),
    ],
    content: '',
    editorProps: {
      attributes: {
        class: 'email-rich-editor',
      },
    },
  })

  // Get body content from editor
  const getBodyContent = useCallback(() => {
    if (!editor) return ''
    // Return plain text for sending
    return editor.getText()
  }, [editor])

  // Extract emails from task notes
  const emailsFromNotes = extractEmailsFromText(taskNotes || '')
  
  // Combine all available contacts/emails for the picker
  const hasContacts = (suggestedContacts && suggestedContacts.length > 0) || emailsFromNotes.length > 0

  // Initialize from draft when it changes
  // Use specific properties as dependencies to ensure updates are detected
  useEffect(() => {
    if (initialDraft) {
      setTo(initialDraft.to ?? [])
      setCc(initialDraft.cc ?? [])
      setSubject(initialDraft.subject ?? '')
      setFromAccount(initialDraft.fromAccount ?? '')
      
      // Set editor content
      if (editor && initialDraft.body) {
        // Convert plain text to HTML for the editor
        const htmlContent = initialDraft.body
          .split('\n\n')
          .map(para => `<p>${para.split('\n').join('<br>')}</p>`)
          .join('')
        editor.commands.setContent(htmlContent)
      }
    }
  }, [initialDraft?.subject, initialDraft?.body, initialDraft?.to, initialDraft?.cc, initialDraft?.fromAccount, editor])

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
    const body = getBodyContent()
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

  const body = getBodyContent()
  const canSend = to.length > 0 && fromAccount && subject.trim() && body.trim()

  return (
    <div className="email-draft-overlay">
      <div className="email-draft-panel">
        {/* Header */}
        <div className="email-draft-header">
          <h3>✉️ Draft Email</h3>
          <div className="email-draft-header-actions">
            <button 
              className="discard-btn" 
              onClick={async () => {
                if (confirm('Discard this draft? This cannot be undone.')) {
                  await onDiscard()
                }
              }}
              title="Discard draft"
            >
              🗑️ Discard
            </button>
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
              <button 
                className={`contact-btn ${hasContacts ? '' : 'disabled'}`}
                onClick={() => hasContacts && setShowContactPicker(showContactPicker === 'to' ? null : 'to')}
                title={hasContacts ? "Select from contacts" : "No contacts available - run Contact search first"}
                disabled={!hasContacts}
              >
                📇
              </button>
            </div>
            {showContactPicker === 'to' && (
              <div className="contact-picker">
                {/* Emails extracted from task notes */}
                {emailsFromNotes.length > 0 && (
                  <>
                    <div className="contact-section-header">From Task Notes</div>
                    {emailsFromNotes
                      .filter(email => !to.includes(email)) // Don't show already added
                      .map((email, idx) => (
                        <button
                          key={`note-${idx}`}
                          className="contact-option email-only"
                          onClick={() => {
                            setTo([...to, email])
                            setShowContactPicker(null)
                          }}
                        >
                          <span className="contact-email">{email}</span>
                        </button>
                      ))}
                  </>
                )}
                {/* Contacts from Contact search */}
                {suggestedContacts && suggestedContacts.filter(c => c.email).length > 0 && (
                  <>
                    <div className="contact-section-header">From Contact Search</div>
                    {suggestedContacts.filter(c => c.email && !to.includes(c.email)).map((contact, idx) => (
                      <button
                        key={`contact-${idx}`}
                        className="contact-option"
                        onClick={() => handleAddContact(contact, 'to')}
                      >
                        <span className="contact-name">{contact.name}</span>
                        <span className="contact-email">{contact.email}</span>
                        {contact.organization && (
                          <span className="contact-org">{contact.organization}</span>
                        )}
                      </button>
                    ))}
                  </>
                )}
                {/* No contacts available message */}
                {emailsFromNotes.filter(e => !to.includes(e)).length === 0 && 
                 (!suggestedContacts || suggestedContacts.filter(c => c.email && !to.includes(c.email)).length === 0) && (
                  <div className="contact-empty">All available contacts already added</div>
                )}
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
              <button 
                className={`contact-btn ${hasContacts ? '' : 'disabled'}`}
                onClick={() => hasContacts && setShowContactPicker(showContactPicker === 'cc' ? null : 'cc')}
                title={hasContacts ? "Select from contacts" : "No contacts available"}
                disabled={!hasContacts}
              >
                📇
              </button>
            </div>
            {showContactPicker === 'cc' && (
              <div className="contact-picker">
                {/* Emails extracted from task notes */}
                {emailsFromNotes.length > 0 && (
                  <>
                    <div className="contact-section-header">From Task Notes</div>
                    {emailsFromNotes
                      .filter(email => !cc.includes(email) && !to.includes(email))
                      .map((email, idx) => (
                        <button
                          key={`note-cc-${idx}`}
                          className="contact-option email-only"
                          onClick={() => {
                            setCc([...cc, email])
                            setShowContactPicker(null)
                          }}
                        >
                          <span className="contact-email">{email}</span>
                        </button>
                      ))}
                  </>
                )}
                {/* Contacts from Contact search */}
                {suggestedContacts && suggestedContacts.filter(c => c.email).length > 0 && (
                  <>
                    <div className="contact-section-header">From Contact Search</div>
                    {suggestedContacts
                      .filter(c => c.email && !cc.includes(c.email) && !to.includes(c.email))
                      .map((contact, idx) => (
                        <button
                          key={`contact-cc-${idx}`}
                          className="contact-option"
                          onClick={() => handleAddContact(contact, 'cc')}
                        >
                          <span className="contact-name">{contact.name}</span>
                          <span className="contact-email">{contact.email}</span>
                          {contact.organization && (
                            <span className="contact-org">{contact.organization}</span>
                          )}
                        </button>
                      ))}
                  </>
                )}
                {/* No contacts available message */}
                {emailsFromNotes.filter(e => !cc.includes(e) && !to.includes(e)).length === 0 && 
                 (!suggestedContacts || suggestedContacts.filter(c => c.email && !cc.includes(c.email) && !to.includes(c.email)).length === 0) && (
                  <div className="contact-empty">All available contacts already added</div>
                )}
              </div>
            )}
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

        {/* Body - Rich Text Editor */}
        <div className="email-draft-field email-body-field">
          <label>Body:</label>
          <RichTextToolbar editor={editor} />
          <div className="email-rich-editor-container">
            <EditorContent editor={editor} />
          </div>
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

