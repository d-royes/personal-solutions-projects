import { useState, useEffect, useCallback } from 'react'
import type { AuthConfig } from '../auth/types'
import type {
  EmailAccount,
  FilterRule,
  RuleSuggestion,
  AttentionItem,
  InboxSummary,
} from '../types'
import {
  getInboxSummary,
  getFilterRules,
  analyzeInbox,
  addFilterRule,
  deleteFilterRule,
  archiveEmail,
  deleteEmail,
  starEmail,
  markEmailImportant,
  chatAboutEmail,
  searchEmails,
  getEmailActionSuggestions,
  getEmailLabels,
  applyEmailLabel,
  getTaskPreviewFromEmail,
  createTaskFromEmail,
  checkEmailsHaveTasks,
  getEmailFull,
  generateReplyDraft,
  sendReply,
  type EmailPendingAction,
  type EmailActionSuggestion,
  type GmailLabel,
  type TaskPreview,
  type EmailTaskInfo,
} from '../api'
import { EmailDraftPanel, type EmailDraft } from './EmailDraftPanel'

interface EmailDashboardProps {
  authConfig: AuthConfig
  apiBase: string
  onBack: () => void
}

type TabView = 'dashboard' | 'rules' | 'newRules' | 'suggestions' | 'attention'

// Quick action types for email management
type EmailQuickAction = 
  | { type: 'archive'; emailId: string }
  | { type: 'delete'; emailId: string }
  | { type: 'star'; emailId: string }
  | { type: 'flag'; emailId: string }
  | { type: 'create_task'; emailId: string; subject: string }

// Filter categories with their order priorities
const CATEGORIES = [
  { value: '1 Week Hold', order: 1, color: '#6b7280' },
  { value: 'Personal', order: 2, color: '#3b82f6' },
  { value: 'Admin', order: 3, color: '#8b5cf6' },
  { value: 'Transactional', order: 4, color: '#10b981' },
  { value: 'Promotional', order: 5, color: '#f59e0b' },
  { value: 'Junk', order: 6, color: '#ef4444' },
  { value: 'Trash', order: 7, color: '#374151' },
]

const FILTER_FIELDS = [
  { value: 'Sender Email Address', label: 'Sender Email' },
  { value: 'Email Subject', label: 'Subject' },
  { value: 'Sender Email Name', label: 'Sender Name' },
]

const OPERATORS = [
  { value: 'Contains', label: 'Contains' },
  { value: 'Equals', label: 'Equals' },
]

// Per-account cache structure
interface AccountCache {
  inbox: InboxSummary | null
  rules: FilterRule[]
  suggestions: RuleSuggestion[]  // Rule suggestions (New Rules tab)
  attentionItems: AttentionItem[]
  actionSuggestions: EmailActionSuggestion[]  // Email action suggestions (Suggestions tab)
  availableLabels: GmailLabel[]
  emailTaskLinks: Record<string, EmailTaskInfo>  // email_id -> task info
  loaded: boolean
}

const emptyCache = (): AccountCache => ({
  inbox: null,
  rules: [],
  suggestions: [],
  attentionItems: [],
  actionSuggestions: [],
  availableLabels: [],
  emailTaskLinks: {},
  loaded: false,
})

export function EmailDashboard({ authConfig, apiBase, onBack }: EmailDashboardProps) {
  // Account selection
  const [selectedAccount, setSelectedAccount] = useState<EmailAccount>('personal')
  const [activeTab, setActiveTab] = useState<TabView>('dashboard')
  
  // Two-panel layout state
  const [emailPanelCollapsed, setEmailPanelCollapsed] = useState(false)
  const [assistPanelCollapsed, setAssistPanelCollapsed] = useState(true) // Start collapsed until Phase 4
  const [selectedEmailId, setSelectedEmailId] = useState<string | null>(null)
  
  // Per-account data cache
  const [cache, setCache] = useState<Record<EmailAccount, AccountCache>>({
    personal: emptyCache(),
    church: emptyCache(),
  })
  
  // Derived state from cache for current account
  const inboxSummary = cache[selectedAccount].inbox
  const rules = cache[selectedAccount].rules
  const suggestions = cache[selectedAccount].suggestions  // Rule suggestions (New Rules tab)
  const attentionItems = cache[selectedAccount].attentionItems
  const actionSuggestions = cache[selectedAccount].actionSuggestions  // Email action suggestions
  const availableLabels = cache[selectedAccount].availableLabels
  const emailTaskLinks = cache[selectedAccount].emailTaskLinks  // Emails that have linked tasks
  
  // Loading states
  const [loadingInbox, setLoadingInbox] = useState(false)
  const [loadingRules, setLoadingRules] = useState(false)
  const [loadingAnalysis, setLoadingAnalysis] = useState(false)
  const [loadingActionSuggestions, setLoadingActionSuggestions] = useState(false)
  
  // Error state
  const [error, setError] = useState<string | null>(null)
  
  // New rule form state
  const [showAddRule, setShowAddRule] = useState(false)
  const [newRule, setNewRule] = useState({
    category: 'Personal',
    field: 'Sender Email Address',
    operator: 'Contains',
    value: '',
  })
  const [addingRule, setAddingRule] = useState(false)
  
  // Filter state for rules table
  const [categoryFilter, setCategoryFilter] = useState<string>('all')
  const [searchFilter, setSearchFilter] = useState('')
  
  // Email search state
  const [emailSearchQuery, setEmailSearchQuery] = useState('')
  const [emailSearchResults, setEmailSearchResults] = useState<Array<{
    id: string
    threadId: string
    fromAddress: string
    fromName: string
    toAddress: string
    subject: string
    snippet: string
    date: string
    isUnread: boolean
    isImportant: boolean
    isStarred: boolean
    ageHours: number
  }> | null>(null)
  const [searchingEmails, setSearchingEmails] = useState(false)
  
  // Full email body state
  const [emailBodyExpanded, setEmailBodyExpanded] = useState(false)
  const [fullEmailBody, setFullEmailBody] = useState<{
    body: string | null
    bodyHtml: string | null
    attachmentCount: number
  } | null>(null)
  const [loadingFullBody, setLoadingFullBody] = useState(false)
  
  // Reply panel state
  const [showReplyPanel, setShowReplyPanel] = useState(false)
  const [replyDraft, setReplyDraft] = useState<EmailDraft | null>(null)
  const [replyContext, setReplyContext] = useState<{
    messageId: string
    replyAll: boolean
  } | null>(null)
  const [generatingReply, setGeneratingReply] = useState(false)
  const [sendingReply, setSendingReply] = useState(false)
  const [replyError, setReplyError] = useState<string | null>(null)

  // Helper to update cache for current account
  const updateCache = useCallback((updates: Partial<AccountCache>) => {
    setCache(prev => ({
      ...prev,
      [selectedAccount]: { ...prev[selectedAccount], ...updates }
    }))
  }, [selectedAccount])

  // Invalidate cache for current account (forces reload on next access)
  // Kept for future actions that need to force a full reload
  const _invalidateCache = useCallback(() => {
    setCache(prev => ({
      ...prev,
      [selectedAccount]: { ...prev[selectedAccount], loaded: false }
    }))
  }, [selectedAccount])
  void _invalidateCache // Suppress unused warning - available for future actions

  // Load inbox summary (with force option for refresh)
  const loadInbox = useCallback(async (force = false) => {
    // Skip if already cached and not forcing
    if (!force && cache[selectedAccount].inbox) return
    
    setLoadingInbox(true)
    setError(null)
    try {
      const summary = await getInboxSummary(selectedAccount, authConfig, apiBase, 30)
      updateCache({ inbox: summary })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load inbox')
    } finally {
      setLoadingInbox(false)
    }
  }, [selectedAccount, authConfig, apiBase, cache, updateCache])

  // Load filter rules (with force option for refresh)
  const loadRules = useCallback(async (force = false) => {
    // Skip if already cached and not forcing
    if (!force && cache[selectedAccount].rules.length > 0) return
    
    setLoadingRules(true)
    setError(null)
    try {
      const response = await getFilterRules(selectedAccount, authConfig, apiBase)
      updateCache({ rules: response.rules, loaded: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load rules')
    } finally {
      setLoadingRules(false)
    }
  }, [selectedAccount, authConfig, apiBase, cache, updateCache])

  // Analyze inbox for rule suggestions (New Rules tab)
  const runAnalysis = useCallback(async () => {
    setLoadingAnalysis(true)
    setError(null)
    try {
      const response = await analyzeInbox(selectedAccount, authConfig, apiBase, 50)
      
      // Check which attention emails already have tasks
      let taskLinks: Record<string, EmailTaskInfo> = {}
      if (response.attentionItems.length > 0) {
        try {
          const emailIds = response.attentionItems.map(item => item.emailId)
          const taskCheck = await checkEmailsHaveTasks(selectedAccount, emailIds, authConfig, apiBase)
          taskLinks = taskCheck.tasks
        } catch (err) {
          console.warn('Failed to check email-task links:', err)
        }
      }
      
      updateCache({ 
        suggestions: response.suggestions,
        attentionItems: response.attentionItems,
        emailTaskLinks: taskLinks,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed')
    } finally {
      setLoadingAnalysis(false)
    }
  }, [selectedAccount, authConfig, apiBase, updateCache])

  // Load email action suggestions (Suggestions tab)
  const loadActionSuggestions = useCallback(async () => {
    setLoadingActionSuggestions(true)
    setError(null)
    try {
      const response = await getEmailActionSuggestions(selectedAccount, authConfig, apiBase, 30)
      updateCache({ 
        actionSuggestions: response.suggestions,
        availableLabels: response.availableLabels,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load suggestions')
    } finally {
      setLoadingActionSuggestions(false)
    }
  }, [selectedAccount, authConfig, apiBase, updateCache])

  // Load available labels (used internally by loadActionSuggestions, exposed for future direct use)
  const loadLabels = useCallback(async () => {
    try {
      const response = await getEmailLabels(selectedAccount, authConfig, apiBase)
      updateCache({ availableLabels: response.labels })
    } catch (err) {
      // Non-critical error, continue without labels
      console.error('Failed to load labels:', err)
    }
  }, [selectedAccount, authConfig, apiBase, updateCache])
  // Suppress unused warning - available for future explicit label loading
  void loadLabels

  // Refresh all data for current account
  const refreshAll = useCallback(() => {
    loadInbox(true)
    loadRules(true)
  }, [loadInbox, loadRules])

  // Search emails
  const handleEmailSearch = useCallback(async (query: string) => {
    if (!query.trim()) {
      setEmailSearchResults(null)
      return
    }
    
    setSearchingEmails(true)
    setError(null)
    try {
      const response = await searchEmails(selectedAccount, query.trim(), authConfig, apiBase, 30)
      setEmailSearchResults(response.messages)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed')
      setEmailSearchResults(null)
    } finally {
      setSearchingEmails(false)
    }
  }, [selectedAccount, authConfig, apiBase])

  // Clear search results
  const clearEmailSearch = useCallback(() => {
    setEmailSearchQuery('')
    setEmailSearchResults(null)
  }, [])

  // Load data when account changes (uses cache if available)
  useEffect(() => {
    loadInbox()
    loadRules()
  }, [selectedAccount]) // eslint-disable-line react-hooks/exhaustive-deps

  // Handle adding a new rule
  async function handleAddRule() {
    if (!newRule.value.trim()) {
      setError('Please enter a value for the rule')
      return
    }
    
    setAddingRule(true)
    setError(null)
    try {
      const categoryInfo = CATEGORIES.find(c => c.value === newRule.category)
      await addFilterRule(selectedAccount, {
        emailAccount: inboxSummary?.email || '',
        order: categoryInfo?.order || 1,
        category: newRule.category,
        field: newRule.field,
        operator: newRule.operator,
        value: newRule.value.trim(),
        action: 'Add',
      }, authConfig, apiBase)
      
      // Force refresh rules and reset form
      await loadRules(true)
      setShowAddRule(false)
      setNewRule({
        category: 'Personal',
        field: 'Sender Email Address',
        operator: 'Contains',
        value: '',
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add rule')
    } finally {
      setAddingRule(false)
    }
  }

  // Handle deleting a rule
  async function handleDeleteRule(rowNumber: number) {
    if (!confirm('Delete this rule? This cannot be undone.')) return
    
    try {
      await deleteFilterRule(selectedAccount, rowNumber, authConfig, apiBase)
      await loadRules(true) // Force refresh after delete
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete rule')
    }
  }

  // Handle approving a suggestion
  async function handleApproveSuggestion(suggestion: RuleSuggestion) {
    setAddingRule(true)
    setError(null)
    try {
      const rule = suggestion.suggestedRule
      await addFilterRule(selectedAccount, {
        emailAccount: rule.emailAccount || inboxSummary?.email || '',
        order: rule.order,
        category: rule.category,
        field: rule.field,
        operator: rule.operator,
        value: rule.value,
        action: 'Add',
      }, authConfig, apiBase)
      
      // Remove from suggestions in cache and refresh rules
      const updatedSuggestions = suggestions.filter(s => s !== suggestion)
      updateCache({ suggestions: updatedSuggestions })
      await loadRules(true) // Force refresh after adding
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add rule')
    } finally {
      setAddingRule(false)
    }
  }
  
  // Handle dismissing a rule suggestion
  function handleDismissSuggestion(suggestion: RuleSuggestion) {
    const updatedSuggestions = suggestions.filter(s => s !== suggestion)
    updateCache({ suggestions: updatedSuggestions })
  }

  // Handle approving an email action suggestion
  async function handleApproveActionSuggestion(suggestion: EmailActionSuggestion) {
    setActionLoading(suggestion.action)
    setError(null)
    
    try {
      switch (suggestion.action) {
        case 'archive':
          await archiveEmail(selectedAccount, suggestion.emailId, authConfig, apiBase)
          break
        case 'delete':
          await deleteEmail(selectedAccount, suggestion.emailId, authConfig, apiBase)
          break
        case 'star':
          await starEmail(selectedAccount, suggestion.emailId, true, authConfig, apiBase)
          break
        case 'mark_important':
          await markEmailImportant(selectedAccount, suggestion.emailId, true, authConfig, apiBase)
          break
        case 'label':
          if (suggestion.labelId) {
            await applyEmailLabel(selectedAccount, suggestion.emailId, suggestion.labelId, authConfig, apiBase)
          }
          break
        case 'create_task':
          // TODO: Implement task creation
          alert(`Task creation coming soon: ${suggestion.taskTitle}`)
          break
      }
      
      // Remove from suggestions
      const updated = actionSuggestions.filter(s => s.number !== suggestion.number)
      // Re-number remaining suggestions
      const renumbered = updated.map((s, idx) => ({ ...s, number: idx + 1 }))
      updateCache({ actionSuggestions: renumbered })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed')
    } finally {
      setActionLoading(null)
    }
  }

  // Handle dismissing an email action suggestion
  function handleDismissActionSuggestion(suggestion: EmailActionSuggestion) {
    const updated = actionSuggestions.filter(s => s.number !== suggestion.number)
    // Re-number remaining suggestions
    const renumbered = updated.map((s, idx) => ({ ...s, number: idx + 1 }))
    updateCache({ actionSuggestions: renumbered })
  }

  // Handle quick action on a suggestion (Archive/Delete/Star without approving the suggested action)
  async function handleSuggestionQuickAction(suggestion: EmailActionSuggestion, action: 'archive' | 'delete' | 'star' | 'flag') {
    setActionLoading(action)
    setError(null)
    
    try {
      switch (action) {
        case 'archive':
          await archiveEmail(selectedAccount, suggestion.emailId, authConfig, apiBase)
          break
        case 'delete':
          await deleteEmail(selectedAccount, suggestion.emailId, authConfig, apiBase)
          break
        case 'star':
          await starEmail(selectedAccount, suggestion.emailId, true, authConfig, apiBase)
          break
        case 'flag':
          await markEmailImportant(selectedAccount, suggestion.emailId, true, authConfig, apiBase)
          break
      }
      
      // Remove from suggestions
      const updated = actionSuggestions.filter(s => s.number !== suggestion.number)
      const renumbered = updated.map((s, idx) => ({ ...s, number: idx + 1 }))
      updateCache({ actionSuggestions: renumbered })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed')
    } finally {
      setActionLoading(null)
    }
  }

  // Handle batch approve all suggestions
  async function handleBatchApproveAll() {
    if (actionSuggestions.length === 0) return
    
    setActionLoading('batch')
    setError(null)
    
    let successCount = 0
    const errors: string[] = []
    
    for (const suggestion of actionSuggestions) {
      try {
        switch (suggestion.action) {
          case 'archive':
            await archiveEmail(selectedAccount, suggestion.emailId, authConfig, apiBase)
            break
          case 'delete':
            await deleteEmail(selectedAccount, suggestion.emailId, authConfig, apiBase)
            break
          case 'star':
            await starEmail(selectedAccount, suggestion.emailId, true, authConfig, apiBase)
            break
          case 'mark_important':
            await markEmailImportant(selectedAccount, suggestion.emailId, true, authConfig, apiBase)
            break
          case 'label':
            if (suggestion.labelId) {
              await applyEmailLabel(selectedAccount, suggestion.emailId, suggestion.labelId, authConfig, apiBase)
            }
            break
          case 'create_task':
            // Skip task creation in batch - requires user input
            continue
        }
        successCount++
      } catch (err) {
        errors.push(`#${suggestion.number}: ${err instanceof Error ? err.message : 'Failed'}`)
      }
    }
    
    // Clear all approved suggestions
    updateCache({ actionSuggestions: [] })
    
    if (errors.length > 0) {
      setError(`Approved ${successCount} of ${actionSuggestions.length}. Errors: ${errors.join(', ')}`)
    }
    
    setActionLoading(null)
  }

  // Open task creation form with DATA's suggested values
  async function handleOpenTaskForm(emailId: string) {
    setShowTaskForm(true)
    setCreatingTask(true)
    
    try {
      const response = await getTaskPreviewFromEmail(selectedAccount, emailId, authConfig, apiBase)
      setTaskPreview(response.preview)
      const domain = response.preview.domain || (selectedAccount === 'church' ? 'church' : 'personal')
      setTaskFormData({
        title: response.preview.title || '',
        dueDate: response.preview.dueDate || '',
        priority: response.preview.priority || 'Standard',
        domain: domain,
        project: response.preview.project || '',
        notes: response.preview.notes || '',
      })
    } catch (err) {
      // Fallback to email subject
      const email = selectedEmail
      const domain = selectedAccount === 'church' ? 'church' : 'personal'
      setTaskFormData({
        title: email?.subject.replace(/^(Re:|Fwd:|FW:)\s*/gi, '').trim() || '',
        dueDate: '',
        priority: 'Standard',
        domain: domain,
        project: domain === 'church' ? 'Church Tasks' : 'Sm. Projects & Tasks',
        notes: `From: ${email?.fromName || email?.fromAddress || ''}`,
      })
    } finally {
      setCreatingTask(false)
    }
  }

  // Create task from form data
  async function handleCreateTask() {
    if (!selectedEmailId || !taskFormData.title.trim()) return
    
    setCreatingTask(true)
    setError(null)
    
    try {
      const response = await createTaskFromEmail(
        selectedAccount,
        {
          emailId: selectedEmailId,
          title: taskFormData.title.trim(),
          dueDate: taskFormData.dueDate || undefined,
          priority: taskFormData.priority,
          domain: taskFormData.domain,
          project: taskFormData.project || undefined,
          notes: taskFormData.notes || undefined,
        },
        authConfig,
        apiBase
      )
      
      // Update cache with new task link so UI shows "Task exists" immediately
      updateCache({
        emailTaskLinks: {
          ...emailTaskLinks,
          [selectedEmailId]: {
            taskId: response.task.id,
            title: response.task.title,
            status: response.task.status,
            priority: response.task.priority,
          }
        }
      })
      
      // Success - close form and show confirmation in chat
      setShowTaskForm(false)
      setChatHistory(prev => [...prev, { 
        role: 'assistant', 
        content: `✓ Task created: "${taskFormData.title}"` 
      }])
      
      // Reset form
      setTaskFormData({
        title: '',
        dueDate: '',
        priority: 'Standard',
        domain: 'personal',
        project: '',
        notes: '',
      })
      setTaskPreview(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create task')
    } finally {
      setCreatingTask(false)
    }
  }

  // Cancel task creation
  function handleCancelTaskForm() {
    setShowTaskForm(false)
    setTaskPreview(null)
    setTaskFormData({
      title: '',
      dueDate: '',
      priority: 'Standard',
      domain: 'personal',
      project: '',
      notes: '',
    })
  }

  // Parse chat commands like "approve #1" or "approve #1 and #3" or "approve all"
  function parseApprovalCommand(message: string): number[] | 'all' | null {
    const lowerMsg = message.toLowerCase().trim()
    
    // Check for "approve all"
    if (lowerMsg.includes('approve all') || lowerMsg.includes('approve everything')) {
      return 'all'
    }
    
    // Check for "approve #X" patterns
    const approveMatch = lowerMsg.match(/approve\s+([\d#,\s]+(?:and\s+[\d#,\s]+)*)/i)
    if (approveMatch) {
      const numberPart = approveMatch[1]
      // Extract all numbers from the string
      const numbers = numberPart.match(/\d+/g)
      if (numbers) {
        return numbers.map(n => parseInt(n, 10))
      }
    }
    
    // Check for just "#X" patterns (shorthand)
    const hashMatch = lowerMsg.match(/^#(\d+)$/i)
    if (hashMatch) {
      return [parseInt(hashMatch[1], 10)]
    }
    
    return null
  }

  // Handle selecting an email (opens assist panel)
  async function handleSelectEmail(emailId: string) {
    setSelectedEmailId(emailId)
    setAssistPanelCollapsed(false)
    // Clear chat history when selecting a new email
    setChatHistory([])
    setPendingEmailAction(null)
    
    // Reset email body state
    setEmailBodyExpanded(false)
    setFullEmailBody(null)
    
    // Fetch full email body in the background
    fetchFullEmailBody(emailId)
  }
  
  // Fetch full email body when email is selected
  async function fetchFullEmailBody(emailId: string) {
    setLoadingFullBody(true)
    try {
      const response = await getEmailFull(selectedAccount, emailId, authConfig, apiBase, true)
      setFullEmailBody({
        body: response.message.body ?? null,
        bodyHtml: response.message.bodyHtml ?? null,
        attachmentCount: response.message.attachmentCount ?? 0,
      })
    } catch (err) {
      console.error('Failed to load full email body:', err)
      // Don't show error to user - they can still work with snippet
    } finally {
      setLoadingFullBody(false)
    }
  }
  
  // Handle clicking Reply or Reply All button
  async function handleReply(replyAll: boolean) {
    if (!selectedEmailId || !selectedEmail) return
    
    setGeneratingReply(true)
    setReplyError(null)
    setShowReplyPanel(true)
    
    try {
      const response = await generateReplyDraft(
        selectedAccount,
        {
          messageId: selectedEmailId,
          replyAll,
        },
        authConfig,
        apiBase
      )
      
      setReplyDraft({
        to: response.draft.to,
        cc: response.draft.cc,
        subject: response.draft.subject,
        body: response.draft.body,
        fromAccount: selectedAccount,
      })
      
      setReplyContext({
        messageId: selectedEmailId,
        replyAll,
      })
    } catch (err) {
      console.error('Failed to generate reply draft:', err)
      setReplyError(err instanceof Error ? err.message : 'Failed to generate reply')
    } finally {
      setGeneratingReply(false)
    }
  }
  
  // Handle sending the reply
  async function handleSendReply(draft: EmailDraft) {
    if (!replyContext) return
    
    setSendingReply(true)
    setReplyError(null)
    
    try {
      await sendReply(
        draft.fromAccount as EmailAccount,
        {
          messageId: replyContext.messageId,
          replyAll: replyContext.replyAll,
          subject: draft.subject,
          body: draft.body,
          cc: draft.cc.length > 0 ? draft.cc : undefined,
        },
        authConfig,
        apiBase
      )
      
      // Success - close panel and show confirmation
      setShowReplyPanel(false)
      setReplyDraft(null)
      setReplyContext(null)
      
      setChatHistory(prev => [...prev, {
        role: 'assistant',
        content: `✓ Reply sent successfully to ${draft.to.join(', ')}`
      }])
    } catch (err) {
      console.error('Failed to send reply:', err)
      setReplyError(err instanceof Error ? err.message : 'Failed to send reply')
    } finally {
      setSendingReply(false)
    }
  }
  
  // Handle regenerating reply with instructions
  async function handleRegenerateReply(instructions: string) {
    if (!replyContext) return
    
    setGeneratingReply(true)
    setReplyError(null)
    
    try {
      const response = await generateReplyDraft(
        selectedAccount,
        {
          messageId: replyContext.messageId,
          replyAll: replyContext.replyAll,
          userContext: instructions,
        },
        authConfig,
        apiBase
      )
      
      setReplyDraft({
        to: response.draft.to,
        cc: response.draft.cc,
        subject: response.draft.subject,
        body: response.draft.body,
        fromAccount: selectedAccount,
      })
    } catch (err) {
      console.error('Failed to regenerate reply:', err)
      setReplyError(err instanceof Error ? err.message : 'Failed to regenerate reply')
    } finally {
      setGeneratingReply(false)
    }
  }
  
  // Handle closing the reply panel
  function handleCloseReplyPanel(currentDraft: EmailDraft) {
    setReplyDraft(currentDraft)
    setShowReplyPanel(false)
  }
  
  // Handle discarding the reply
  async function handleDiscardReply() {
    setShowReplyPanel(false)
    setReplyDraft(null)
    setReplyContext(null)
    setReplyError(null)
  }

  // Handle sending a chat message about the selected email
  async function handleSendChatMessage() {
    if (!chatInput.trim()) return
    
    const userMessage = chatInput.trim()
    
    // Check for approval commands first (works even without selected email)
    const approvalCommand = parseApprovalCommand(userMessage)
    if (approvalCommand) {
      setChatHistory(prev => [...prev, { role: 'user', content: userMessage }])
      setChatInput('')
      
      if (approvalCommand === 'all') {
        // Approve all suggestions
        await handleBatchApproveAll()
        setChatHistory(prev => [...prev, { 
          role: 'assistant', 
          content: `✓ Approved all ${actionSuggestions.length} suggestions.` 
        }])
      } else {
        // Approve specific numbers
        const validNumbers = approvalCommand.filter(n => 
          actionSuggestions.some(s => s.number === n)
        )
        
        if (validNumbers.length === 0) {
          setChatHistory(prev => [...prev, { 
            role: 'assistant', 
            content: `I couldn't find suggestions with those numbers. Current suggestions are #${actionSuggestions.map(s => s.number).join(', #')}.` 
          }])
        } else {
          // Approve the specified suggestions
          const toApprove = actionSuggestions.filter(s => validNumbers.includes(s.number))
          for (const suggestion of toApprove) {
            await handleApproveActionSuggestion(suggestion)
          }
          setChatHistory(prev => [...prev, { 
            role: 'assistant', 
            content: `✓ Approved suggestion${validNumbers.length > 1 ? 's' : ''} #${validNumbers.join(', #')}.` 
          }])
        }
      }
      return
    }
    
    // Regular chat requires a selected email
    if (!selectedEmailId) {
      setChatHistory(prev => [...prev, { role: 'user', content: userMessage }])
      setChatInput('')
      setChatHistory(prev => [...prev, { 
        role: 'assistant', 
        content: 'Please select an email to chat about, or use commands like "approve #1" or "approve all" to act on suggestions.' 
      }])
      return
    }
    
    setChatLoading(true)
    setPendingEmailAction(null)
    
    // Add user message to history immediately
    setChatHistory(prev => [...prev, { role: 'user', content: userMessage }])
    setChatInput('')
    
    try {
      const response = await chatAboutEmail(
        selectedAccount,
        {
          message: userMessage,
          emailId: selectedEmailId,
          history: chatHistory,
        },
        authConfig,
        apiBase
      )
      
      // Add assistant response to history
      setChatHistory(prev => [...prev, { role: 'assistant', content: response.response }])
      
      // Handle pending action if DATA suggested one
      if (response.pendingAction) {
        setPendingEmailAction(response.pendingAction)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Chat failed')
      // Add error message to history
      setChatHistory(prev => [...prev, { role: 'assistant', content: 'Sorry, I encountered an error. Please try again.' }])
    } finally {
      setChatLoading(false)
    }
  }

  // Handle confirming a pending email action from chat
  async function handleConfirmEmailAction() {
    if (!pendingEmailAction || !selectedEmailId) return
    
    const action = pendingEmailAction.action
    setActionLoading(action)
    
    try {
      switch (action) {
        case 'archive':
          await handleEmailQuickAction({ type: 'archive', emailId: selectedEmailId })
          break
        case 'delete':
          await handleEmailQuickAction({ type: 'delete', emailId: selectedEmailId })
          break
        case 'star':
          await handleEmailQuickAction({ type: 'star', emailId: selectedEmailId })
          break
        case 'mark_important':
          await handleEmailQuickAction({ type: 'flag', emailId: selectedEmailId })
          break
        case 'create_task':
          await handleOpenTaskForm(selectedEmailId)
          break
        case 'draft_reply':
        case 'draft_reply_all':
          // Open the reply panel with DATA's draft pre-filled
          handleOpenReplyWithDraft(
            action === 'draft_reply_all',
            pendingEmailAction.draftBody ?? '',
            pendingEmailAction.draftSubject
          )
          break
      }
      
      // Add confirmation to chat
      setChatHistory(prev => [...prev, { 
        role: 'assistant', 
        content: `✓ Done! ${pendingEmailAction.reason}` 
      }])
    } finally {
      setPendingEmailAction(null)
      setActionLoading(null)
    }
  }
  
  // Handle opening reply panel with DATA's draft pre-filled from chat
  function handleOpenReplyWithDraft(replyAll: boolean, draftBody: string, draftSubject?: string) {
    if (!selectedEmailId || !selectedEmail) return
    
    // Build the draft from DATA's suggestion
    const subject = draftSubject || (
      selectedEmail.subject.toLowerCase().startsWith('re:') 
        ? selectedEmail.subject 
        : `Re: ${selectedEmail.subject}`
    )
    
    // Get recipients
    const to = [selectedEmail.fromAddress]
    const cc: string[] = []
    // For reply all, we'd need CC from the full email - handled by the panel
    
    setReplyDraft({
      to,
      cc,
      subject,
      body: draftBody,
      fromAccount: selectedAccount,
    })
    
    setReplyContext({
      messageId: selectedEmailId,
      replyAll,
    })
    
    setShowReplyPanel(true)
  }

  // State for email actions
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  
  // Email chat state (Phase 4)
  const [chatHistory, setChatHistory] = useState<Array<{ role: string; content: string }>>([])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [pendingEmailAction, setPendingEmailAction] = useState<EmailPendingAction | null>(null)
  
  // Task creation state (Phase B)
  const [showTaskForm, setShowTaskForm] = useState(false)
  const [_taskPreview, setTaskPreview] = useState<TaskPreview | null>(null)
  void _taskPreview // Reserved for future use
  const [taskFormData, setTaskFormData] = useState({
    title: '',
    dueDate: '',
    priority: 'Standard',
    domain: 'personal',
    project: '',
    notes: '',
  })
  
  // Project options based on domain
  const projectOptions = taskFormData.domain === 'work' 
    ? [
        'Atlassian (Jira/Confluence)',
        'Crafter Studio',
        'Internal Application Support',
        'Team Management',
        'Strategic Planning',
        'Stakeholder Relations',
        'Process Improvement',
        'Daily Operations',
        'Zendesk Support',
        'Intranet Management',
        'Vendor Management',
        'AI/Automation Projects',
        'DTS Transformation',
        'New Technology Evaluation',
      ]
    : [
        'Around The House',
        'Church Tasks',
        'Family Time',
        'Shopping',
        'Sm. Projects & Tasks',
        'Zendesk Ticket',
      ]
  const [creatingTask, setCreatingTask] = useState(false)

  // Handle quick action on email
  async function handleEmailQuickAction(action: EmailQuickAction) {
    setActionLoading(action.type)
    setError(null)
    
    try {
      switch (action.type) {
        case 'archive':
          await archiveEmail(selectedAccount, action.emailId, authConfig, apiBase)
          // Remove from recent messages in cache
          updateCache({
            inbox: inboxSummary ? {
              ...inboxSummary,
              recentMessages: inboxSummary.recentMessages.filter(m => m.id !== action.emailId)
            } : null
          })
          setSelectedEmailId(null)
          break
          
        case 'delete':
          await deleteEmail(selectedAccount, action.emailId, authConfig, apiBase)
          // Remove from recent messages in cache
          updateCache({
            inbox: inboxSummary ? {
              ...inboxSummary,
              recentMessages: inboxSummary.recentMessages.filter(m => m.id !== action.emailId)
            } : null
          })
          setSelectedEmailId(null)
          break
          
        case 'star':
          await starEmail(selectedAccount, action.emailId, true, authConfig, apiBase)
          // Update the message in cache
          updateCache({
            inbox: inboxSummary ? {
              ...inboxSummary,
              recentMessages: inboxSummary.recentMessages.map(m => 
                m.id === action.emailId 
                  ? { ...m, isStarred: true }
                  : m
              )
            } : null
          })
          break
          
        case 'flag':
          await markEmailImportant(selectedAccount, action.emailId, true, authConfig, apiBase)
          // Update the message in cache
          updateCache({
            inbox: inboxSummary ? {
              ...inboxSummary,
              recentMessages: inboxSummary.recentMessages.map(m => 
                m.id === action.emailId 
                  ? { ...m, isImportant: true }
                  : m
              )
            } : null
          })
          break
          
        case 'create_task':
          // Open task creation form with DATA's suggestions
          await handleOpenTaskForm(action.emailId)
          break
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Email action failed')
    } finally {
      setActionLoading(null)
    }
  }

  // Toggle panel collapse states
  function handleToggleEmailPanel() {
    setEmailPanelCollapsed(!emailPanelCollapsed)
    // If collapsing email panel, ensure assist is visible
    if (!emailPanelCollapsed) {
      setAssistPanelCollapsed(false)
    }
  }

  function handleToggleAssistPanel() {
    setAssistPanelCollapsed(!assistPanelCollapsed)
    // If collapsing assist panel, ensure email is visible
    if (!assistPanelCollapsed) {
      setEmailPanelCollapsed(false)
    }
  }

  // Expand both panels
  function handleExpandBoth() {
    setEmailPanelCollapsed(false)
    setAssistPanelCollapsed(false)
  }

  // Filter rules based on category and search
  const filteredRules = rules.filter(rule => {
    if (categoryFilter !== 'all' && rule.category !== categoryFilter) return false
    if (searchFilter && !rule.value.toLowerCase().includes(searchFilter.toLowerCase())) return false
    return true
  })

  // Get category color
  const getCategoryColor = (category: string) => {
    return CATEGORIES.find(c => c.value === category)?.color || '#6b7280'
  }

  // Get selected email details (check both search results and recent messages)
  const selectedEmail = selectedEmailId 
    ? (emailSearchResults?.find(m => m.id === selectedEmailId) 
       ?? inboxSummary?.recentMessages?.find(m => m.id === selectedEmailId))
    : null

  return (
    <div className={`email-dashboard two-panel ${emailPanelCollapsed ? 'email-collapsed' : ''} ${assistPanelCollapsed ? 'assist-collapsed' : ''}`}>
      {/* Header - spans full width */}
      <header className="email-dashboard-header">
        <button className="back-button" onClick={onBack}>
          ← Back to Tasks
        </button>
        <h1>Email Management</h1>
        <div className="account-selector">
          <button
            className={`account-tab ${selectedAccount === 'personal' ? 'active' : ''}`}
            onClick={() => setSelectedAccount('personal')}
          >
            Personal
          </button>
          <button
            className={`account-tab ${selectedAccount === 'church' ? 'active' : ''}`}
            onClick={() => setSelectedAccount('church')}
          >
            Church
          </button>
        </div>
      </header>

      {/* Error display - spans full width */}
      {error && (
        <div className="email-error">
          {error}
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      {/* Two-panel content area */}
      <div className="email-panels">
        {/* Left Panel - Email List/Rules */}
        {!emailPanelCollapsed && (
          <section className="email-left-panel">
            {/* Panel collapse control */}
            <button 
              className="panel-collapse-btn left"
              onClick={handleToggleEmailPanel}
              title="Collapse email panel"
            >
              ◀
            </button>

            {/* Tab navigation */}
            <nav className="email-tabs">
              <button
                className={activeTab === 'dashboard' ? 'active' : ''}
                onClick={() => setActiveTab('dashboard')}
              >
                Dashboard
              </button>
              <button
                className={activeTab === 'rules' ? 'active' : ''}
                onClick={() => setActiveTab('rules')}
              >
                Rules ({rules.length})
              </button>
              <button
                className={activeTab === 'newRules' ? 'active' : ''}
                onClick={() => {
                  setActiveTab('newRules')
                  if (suggestions.length === 0) runAnalysis()
                }}
              >
                New Rules {suggestions.length > 0 && `(${suggestions.length})`}
              </button>
              <button
                className={activeTab === 'suggestions' ? 'active' : ''}
                onClick={() => setActiveTab('suggestions')}
              >
                Suggestions
              </button>
              <button
                className={activeTab === 'attention' ? 'active' : ''}
                onClick={() => {
                  setActiveTab('attention')
                  if (attentionItems.length === 0) runAnalysis()
                }}
              >
                Attention {attentionItems.length > 0 && `(${attentionItems.length})`}
              </button>
            </nav>

      {/* Tab content */}
      <div className="email-tab-content">
        {/* Dashboard Tab */}
        {activeTab === 'dashboard' && (
          <div className="dashboard-view">
            <div className="stats-grid">
              <div className="stat-card">
                <div className="stat-value">{inboxSummary?.totalUnread?.toLocaleString() ?? '—'}</div>
                <div className="stat-label">Unread</div>
              </div>
              <div className="stat-card important">
                <div className="stat-value">{inboxSummary?.unreadImportant?.toLocaleString() ?? '—'}</div>
                <div className="stat-label">Important</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{rules.length}</div>
                <div className="stat-label">Active Rules</div>
              </div>
              <div className="stat-card warning">
                <div className="stat-value">{attentionItems.length || '—'}</div>
                <div className="stat-label">Need Attention</div>
              </div>
            </div>

            <div className="action-buttons">
              <div className="email-search-container">
                <input
                  type="text"
                  className="email-search-input"
                  placeholder="Search emails..."
                  value={emailSearchQuery}
                  onChange={(e) => setEmailSearchQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      handleEmailSearch(emailSearchQuery)
                    }
                  }}
                />
                {emailSearchQuery && (
                  <button 
                    className="email-search-clear"
                    onClick={clearEmailSearch}
                    title="Clear search"
                  >
                    ×
                  </button>
                )}
                <button
                  className="email-search-btn"
                  onClick={() => handleEmailSearch(emailSearchQuery)}
                  disabled={searchingEmails || !emailSearchQuery.trim()}
                >
                  {searchingEmails ? '...' : '🔍'}
                </button>
              </div>
              <button
                className="action-btn primary"
                onClick={runAnalysis}
                disabled={loadingAnalysis}
              >
                {loadingAnalysis ? 'Analyzing...' : 'Analyze Inbox'}
              </button>
              <button
                className="action-btn"
                onClick={refreshAll}
                disabled={loadingInbox || loadingRules}
              >
                {(loadingInbox || loadingRules) ? 'Refreshing...' : 'Refresh'}
              </button>
            </div>

            {/* Search results or Recent messages */}
            {emailSearchResults ? (
              <div className="recent-messages search-results">
                <div className="messages-header">
                  <h3>Search Results ({emailSearchResults.length})</h3>
                  <button className="clear-search-btn" onClick={clearEmailSearch}>
                    Clear Search
                  </button>
                </div>
                {emailSearchResults.length === 0 ? (
                  <div className="no-results">No emails found matching "{emailSearchQuery}"</div>
                ) : (
                  <ul className="message-list">
                    {emailSearchResults.map(msg => (
                      <li 
                        key={msg.id} 
                        className={`${msg.isUnread ? 'unread' : ''} ${selectedEmailId === msg.id ? 'selected' : ''}`}
                        onClick={() => handleSelectEmail(msg.id)}
                      >
                        <button
                          className="msg-task-btn"
                          onClick={(e) => {
                            e.stopPropagation()
                            handleSelectEmail(msg.id)
                            handleOpenTaskForm(msg.id)
                          }}
                          title="Create task from this email"
                        >
                          📋
                        </button>
                        <div className="msg-from">{msg.fromName || msg.fromAddress}</div>
                        <div className="msg-subject">{msg.subject}</div>
                        <div className="msg-snippet">{msg.snippet}</div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : inboxSummary?.recentMessages && inboxSummary.recentMessages.length > 0 ? (
              <div className="recent-messages">
                <h3>Recent Messages</h3>
                <ul className="message-list">
                  {inboxSummary.recentMessages.slice(0, 10).map(msg => (
                    <li 
                      key={msg.id} 
                      className={`${msg.isUnread ? 'unread' : ''} ${selectedEmailId === msg.id ? 'selected' : ''}`}
                      onClick={() => handleSelectEmail(msg.id)}
                    >
                      <button
                        className="msg-task-btn"
                        onClick={(e) => {
                          e.stopPropagation()
                          handleSelectEmail(msg.id)
                          handleOpenTaskForm(msg.id)
                        }}
                        title="Create task from this email"
                      >
                        📋
                      </button>
                      <div className="msg-from">{msg.fromName || msg.fromAddress}</div>
                      <div className="msg-subject">{msg.subject}</div>
                      <div className="msg-snippet">{msg.snippet}</div>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        )}

        {/* Rules Tab */}
        {activeTab === 'rules' && (
          <div className="rules-view">
            <div className="rules-toolbar">
              <div className="filter-group">
                <select
                  value={categoryFilter}
                  onChange={e => setCategoryFilter(e.target.value)}
                >
                  <option value="all">All Categories</option>
                  {CATEGORIES.map(cat => (
                    <option key={cat.value} value={cat.value}>{cat.value}</option>
                  ))}
                </select>
                <input
                  type="text"
                  placeholder="Search rules..."
                  value={searchFilter}
                  onChange={e => setSearchFilter(e.target.value)}
                />
              </div>
              <button
                className="add-rule-btn"
                onClick={() => setShowAddRule(true)}
              >
                + Add Rule
              </button>
            </div>

            {/* Add rule form */}
            {showAddRule && (
              <div className="add-rule-form">
                <h4>Add New Rule</h4>
                <div className="form-row">
                  <select
                    value={newRule.category}
                    onChange={e => setNewRule(prev => ({ ...prev, category: e.target.value }))}
                  >
                    {CATEGORIES.map(cat => (
                      <option key={cat.value} value={cat.value}>{cat.value}</option>
                    ))}
                  </select>
                  <select
                    value={newRule.field}
                    onChange={e => setNewRule(prev => ({ ...prev, field: e.target.value }))}
                  >
                    {FILTER_FIELDS.map(f => (
                      <option key={f.value} value={f.value}>{f.label}</option>
                    ))}
                  </select>
                  <select
                    value={newRule.operator}
                    onChange={e => setNewRule(prev => ({ ...prev, operator: e.target.value }))}
                  >
                    {OPERATORS.map(op => (
                      <option key={op.value} value={op.value}>{op.label}</option>
                    ))}
                  </select>
                </div>
                <div className="form-row">
                  <input
                    type="text"
                    placeholder="Value (e.g., @example.com)"
                    value={newRule.value}
                    onChange={e => setNewRule(prev => ({ ...prev, value: e.target.value }))}
                    className="value-input"
                  />
                </div>
                <div className="form-actions">
                  <button
                    className="cancel-btn"
                    onClick={() => setShowAddRule(false)}
                  >
                    Cancel
                  </button>
                  <button
                    className="save-btn"
                    onClick={handleAddRule}
                    disabled={addingRule || !newRule.value.trim()}
                  >
                    {addingRule ? 'Adding...' : 'Add Rule'}
                  </button>
                </div>
              </div>
            )}

            {/* Rules table */}
            {loadingRules ? (
              <div className="loading">Loading rules...</div>
            ) : (
              <table className="rules-table">
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Field</th>
                    <th>Operator</th>
                    <th>Value</th>
                    <th>Action</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRules.map((rule, idx) => (
                    <tr key={rule.rowNumber || idx}>
                      <td>
                        <span
                          className="category-badge"
                          style={{ backgroundColor: getCategoryColor(rule.category) }}
                        >
                          {rule.category}
                        </span>
                      </td>
                      <td>{FILTER_FIELDS.find(f => f.value === rule.field)?.label || rule.field}</td>
                      <td>{rule.operator}</td>
                      <td className="value-cell" title={rule.value}>{rule.value}</td>
                      <td>{rule.action || '—'}</td>
                      <td>
                        {rule.rowNumber && (
                          <button
                            className="delete-btn"
                            onClick={() => handleDeleteRule(rule.rowNumber!)}
                            title="Delete rule"
                          >
                            ×
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {!loadingRules && filteredRules.length === 0 && (
              <div className="empty-state">No rules found</div>
            )}
          </div>
        )}

        {/* New Rules Tab (formerly Suggestions - for filter rule suggestions) */}
        {activeTab === 'newRules' && (
          <div className="suggestions-view">
            {loadingAnalysis ? (
              <div className="loading">Analyzing inbox patterns...</div>
            ) : suggestions.length === 0 ? (
              <div className="empty-state">
                <p>No new rule suggestions</p>
                <button className="action-btn" onClick={runAnalysis}>
                  Run Analysis
                </button>
              </div>
            ) : (
              <ul className="suggestion-list">
                {suggestions.map((suggestion, idx) => (
                  <li key={idx} className={`suggestion-card ${suggestion.confidence}`}>
                    <div className="suggestion-header">
                      <span className={`confidence-badge ${suggestion.confidence}`}>
                        {suggestion.confidence}
                      </span>
                      <span className="email-count">
                        {suggestion.emailCount} email{suggestion.emailCount !== 1 ? 's' : ''}
                      </span>
                    </div>
                    <div className="suggestion-rule">
                      <strong>{suggestion.suggestedRule.field}</strong>
                      {' '}{suggestion.suggestedRule.operator.toLowerCase()}{' '}
                      <code>{suggestion.suggestedRule.value}</code>
                    </div>
                    <div className="suggestion-reason">{suggestion.reason}</div>
                    {suggestion.examples.length > 0 && (
                      <div className="suggestion-examples">
                        <strong>Examples:</strong>
                        <ul>
                          {suggestion.examples.slice(0, 3).map((ex, i) => (
                            <li key={i}>{ex}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    <div className="suggestion-actions">
                      <select
                        className="category-select"
                        value={suggestion.suggestedRule.category}
                        onChange={e => {
                          const newCategory = e.target.value
                          const categoryInfo = CATEGORIES.find(c => c.value === newCategory)
                          const updatedSuggestions = suggestions.map((s, i) => 
                            i === idx 
                              ? {
                                  ...s,
                                  suggestedRule: {
                                    ...s.suggestedRule,
                                    category: newCategory,
                                    order: categoryInfo?.order || s.suggestedRule.order
                                  }
                                }
                              : s
                          )
                          updateCache({ suggestions: updatedSuggestions })
                        }}
                        style={{ 
                          backgroundColor: getCategoryColor(suggestion.suggestedRule.category),
                          color: 'white'
                        }}
                      >
                        {CATEGORIES.map(cat => (
                          <option key={cat.value} value={cat.value}>{cat.value}</option>
                        ))}
                      </select>
                      <button
                        className="approve-btn"
                        onClick={() => handleApproveSuggestion(suggestion)}
                        disabled={addingRule}
                      >
                        Approve
                      </button>
                      <button
                        className="dismiss-btn"
                        onClick={() => handleDismissSuggestion(suggestion)}
                      >
                        Dismiss
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Suggestions Tab (email action suggestions) */}
        {activeTab === 'suggestions' && (
          <div className="email-suggestions-view">
            <div className="suggestions-header">
              <h3>Email Action Suggestions</h3>
              <p className="suggestions-description">
                DATA analyzes your emails and suggests actions. Reference by number in chat (e.g., "approve #1").
              </p>
              <button
                className="action-btn"
                onClick={loadActionSuggestions}
                disabled={loadingActionSuggestions}
              >
                {loadingActionSuggestions ? 'Analyzing...' : 'Refresh Suggestions'}
              </button>
            </div>
            
            {loadingActionSuggestions ? (
              <div className="loading">Analyzing your emails...</div>
            ) : actionSuggestions.length === 0 ? (
              <div className="empty-state">
                <p>No action suggestions</p>
                <p className="hint">Click "Refresh Suggestions" to analyze your inbox</p>
              </div>
            ) : (
              <>
                {/* Batch controls */}
                <div className="batch-approve-controls">
                  <span className="batch-count">{actionSuggestions.length} suggestion{actionSuggestions.length !== 1 ? 's' : ''}</span>
                  <button
                    className="approve-all-btn"
                    onClick={handleBatchApproveAll}
                    disabled={actionLoading !== null}
                  >
                    {actionLoading === 'batch' ? 'Processing...' : 'Approve All'}
                  </button>
                  <span className="batch-hint">or say "approve #1 and #3" in chat</span>
                </div>
                
                <div className="action-suggestions-list">
                {actionSuggestions.map(suggestion => (
                  <div key={suggestion.number} className={`email-action-suggestion ${suggestion.confidence}`}>
                    <div className="suggestion-header-row">
                      <span className="suggestion-number">#{suggestion.number}</span>
                      <span className={`confidence-badge ${suggestion.confidence}`}>
                        {suggestion.confidence}
                      </span>
                    </div>
                    
                    <div className="email-preview">
                      <div className="email-preview-from">
                        <strong>From:</strong> {suggestion.fromName || suggestion.from}
                      </div>
                      <div className="email-preview-to">
                        <strong>To:</strong> {suggestion.to}
                      </div>
                      <div className="email-preview-subject">{suggestion.subject}</div>
                      <div className="email-preview-snippet">{suggestion.snippet}</div>
                    </div>
                    
                    <div className="suggested-action">
                      <div className="action-type">
                        {suggestion.action === 'label' && suggestion.labelName 
                          ? `Apply label: ${suggestion.labelName}`
                          : suggestion.action === 'create_task' && suggestion.taskTitle
                          ? `Create task: ${suggestion.taskTitle}`
                          : suggestion.action.replace('_', ' ').charAt(0).toUpperCase() + suggestion.action.replace('_', ' ').slice(1)
                        }
                      </div>
                      <div className="action-rationale">{suggestion.rationale}</div>
                    </div>
                    
                    <div className="action-row">
                      {/* Label dropdown for label actions */}
                      {suggestion.action === 'label' && availableLabels.length > 0 && (
                        <select
                          className="label-select"
                          value={suggestion.labelId || ''}
                          onChange={(e) => {
                            const newLabelId = e.target.value
                            const newLabel = availableLabels.find(l => l.id === newLabelId)
                            const updated = actionSuggestions.map(s => 
                              s.number === suggestion.number 
                                ? { ...s, labelId: newLabelId, labelName: newLabel?.name || null }
                                : s
                            )
                            updateCache({ actionSuggestions: updated })
                          }}
                        >
                          <option value="">Select label...</option>
                          {availableLabels.map(label => (
                            <option key={label.id} value={label.id}>{label.name}</option>
                          ))}
                        </select>
                      )}
                      
                      <button
                        className="approve-action"
                        onClick={() => handleApproveActionSuggestion(suggestion)}
                        disabled={actionLoading !== null}
                        title="Approve this suggestion"
                      >
                        Approve
                      </button>
                      <button
                        className="dismiss-action"
                        onClick={() => handleDismissActionSuggestion(suggestion)}
                        title="Dismiss this suggestion"
                      >
                        Dismiss
                      </button>
                      
                      {/* Quick actions */}
                      <button
                        className="quick-action"
                        onClick={() => handleSuggestionQuickAction(suggestion, 'star')}
                        disabled={actionLoading !== null}
                        title="Star"
                      >
                        ⭐
                      </button>
                      <button
                        className="quick-action"
                        onClick={() => handleSuggestionQuickAction(suggestion, 'flag')}
                        disabled={actionLoading !== null}
                        title="Mark Important"
                      >
                        🚩
                      </button>
                      <button
                        className="quick-action"
                        onClick={() => handleSuggestionQuickAction(suggestion, 'archive')}
                        disabled={actionLoading !== null}
                        title="Archive"
                      >
                        📥
                      </button>
                      <button
                        className="quick-action delete"
                        onClick={() => handleSuggestionQuickAction(suggestion, 'delete')}
                        disabled={actionLoading !== null}
                        title="Delete"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                ))}
                </div>
              </>
            )}
          </div>
        )}

        {/* Attention Tab */}
        {activeTab === 'attention' && (
          <div className="attention-view">
            {loadingAnalysis ? (
              <div className="loading">Analyzing inbox...</div>
            ) : attentionItems.length === 0 ? (
              <div className="empty-state">
                <p>No items need attention</p>
                <button className="action-btn" onClick={runAnalysis}>
                  Run Analysis
                </button>
              </div>
            ) : (
              <ul className="attention-list">
                {attentionItems.map(item => (
                  <li 
                    key={item.emailId} 
                    className={`attention-card ${item.urgency} ${selectedEmailId === item.emailId ? 'selected' : ''}`}
                    onClick={() => handleSelectEmail(item.emailId)}
                  >
                    <div className="attention-header">
                      <span className={`urgency-badge ${item.urgency}`}>
                        {item.urgency}
                      </span>
                      <span className="attention-date">
                        {new Date(item.date).toLocaleDateString()}
                      </span>
                    </div>
                    <div className="attention-from">
                      From: {item.fromName || item.fromAddress}
                    </div>
                    <div className="attention-subject">{item.subject}</div>
                    <div className="attention-reason">{item.reason}</div>
                    {item.suggestedAction && (
                      <div className="attention-action">
                        Suggested: <strong>{item.suggestedAction}</strong>
                      </div>
                    )}
                    {item.extractedTask && (
                      <div className="attention-task">
                        {emailTaskLinks[item.emailId] ? (
                          <button 
                            className="task-exists-btn"
                            onClick={(e) => {
                              e.stopPropagation()
                              // Navigate to task view
                              onBack()  // Go back to tasks
                              // Note: Could pass taskId to auto-select, but for now just navigate
                            }}
                            title={`View task: ${emailTaskLinks[item.emailId].title}`}
                          >
                            <span className="task-exists-icon">📋</span>
                            <span className="task-exists-label">Task exists</span>
                            <span className={`task-status-badge ${emailTaskLinks[item.emailId].status}`}>
                              {emailTaskLinks[item.emailId].status}
                            </span>
                          </button>
                        ) : (
                          <button 
                            className="create-task-btn"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleEmailQuickAction({ 
                                type: 'create_task', 
                                emailId: item.emailId, 
                                subject: item.extractedTask || item.subject 
                              })
                            }}
                          >
                            Create Task: {item.extractedTask}
                          </button>
                        )}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
            </div>
          </section>
        )}

        {/* Collapsed email panel indicator */}
        {emailPanelCollapsed && (
          <div className="collapsed-panel-indicator left" onClick={handleExpandBoth}>
            <span className="expand-icon">▶</span>
            <span className="collapsed-label">Inbox</span>
          </div>
        )}

        {/* Right Panel - DATA Assist (placeholder until Phase 4) */}
        {!assistPanelCollapsed && (
          <section className="email-right-panel">
            {/* Panel collapse control */}
            <button 
              className="panel-collapse-btn right"
              onClick={handleToggleAssistPanel}
              title="Collapse DATA panel"
            >
              ▶
            </button>

            <div className="email-assist-content">
              <div className="email-assist-header">
                <h2>DATA</h2>
                {selectedEmail && (
                  <span className="selected-email-indicator">
                    Re: {selectedEmail.subject?.slice(0, 30)}...
                  </span>
                )}
              </div>

              {/* Email preview when selected */}
              {selectedEmail && (
                <div className="email-preview">
                  <div className="preview-header">
                    <strong>{selectedEmail.fromName || selectedEmail.fromAddress}</strong>
                    <span className="preview-date">
                      {selectedEmail.date ? new Date(selectedEmail.date).toLocaleString() : ''}
                    </span>
                  </div>
                  <div className="preview-subject">{selectedEmail.subject}</div>
                  
                  {/* Expandable email body section */}
                  {!emailBodyExpanded ? (
                    <div className="preview-snippet">{selectedEmail.snippet}</div>
                  ) : (
                    <div className="email-body-expanded">
                      {loadingFullBody ? (
                        <div className="loading-body">Loading full email...</div>
                      ) : fullEmailBody?.bodyHtml ? (
                        <div 
                          className="email-body-html"
                          dangerouslySetInnerHTML={{ __html: fullEmailBody.bodyHtml }}
                        />
                      ) : fullEmailBody?.body ? (
                        <div className="email-body-text">
                          {fullEmailBody.body}
                        </div>
                      ) : (
                        <div className="preview-snippet">{selectedEmail.snippet}</div>
                      )}
                    </div>
                  )}
                  
                  {/* Expand/Collapse toggle */}
                  <button 
                    className="email-body-toggle"
                    onClick={() => setEmailBodyExpanded(!emailBodyExpanded)}
                    disabled={loadingFullBody}
                  >
                    <span className={`toggle-arrow ${emailBodyExpanded ? 'expanded' : ''}`}>
                      {emailBodyExpanded ? '▲' : '▼'}
                    </span>
                    <span className="toggle-text">
                      {emailBodyExpanded ? 'Hide full email' : 'Show full email'}
                    </span>
                    {fullEmailBody && fullEmailBody.attachmentCount > 0 && (
                      <span className="attachment-indicator" title={`${fullEmailBody.attachmentCount} attachment(s)`}>
                        📎 {fullEmailBody.attachmentCount}
                      </span>
                    )}
                  </button>
                  
                  {/* Quick action buttons */}
                  <div className="email-quick-actions">
                    <button 
                      className="quick-action-btn reply"
                      onClick={() => handleReply(false)}
                      disabled={actionLoading !== null || generatingReply}
                      title="Reply"
                    >
                      {generatingReply && !replyContext?.replyAll ? '⏳' : '↩️'}
                    </button>
                    <button 
                      className="quick-action-btn reply-all"
                      onClick={() => handleReply(true)}
                      disabled={actionLoading !== null || generatingReply}
                      title="Reply All"
                    >
                      {generatingReply && replyContext?.replyAll ? '⏳' : '↩️⃕'}
                    </button>
                    <button 
                      className="quick-action-btn"
                      onClick={() => handleEmailQuickAction({ type: 'archive', emailId: selectedEmail.id })}
                      disabled={actionLoading !== null}
                      title="Archive"
                    >
                      {actionLoading === 'archive' ? '⏳' : '📥'}
                    </button>
                    <button 
                      className="quick-action-btn"
                      onClick={() => handleEmailQuickAction({ type: 'star', emailId: selectedEmail.id })}
                      disabled={actionLoading !== null}
                      title="Star"
                    >
                      {actionLoading === 'star' ? '⏳' : '⭐'}
                    </button>
                    <button 
                      className="quick-action-btn"
                      onClick={() => handleEmailQuickAction({ type: 'flag', emailId: selectedEmail.id })}
                      disabled={actionLoading !== null}
                      title="Mark Important"
                    >
                      {actionLoading === 'flag' ? '⏳' : '🚩'}
                    </button>
                    <button 
                      className="quick-action-btn delete"
                      onClick={() => handleEmailQuickAction({ type: 'delete', emailId: selectedEmail.id })}
                      disabled={actionLoading !== null}
                      title="Delete"
                    >
                      {actionLoading === 'delete' ? '⏳' : '🗑️'}
                    </button>
                  </div>
                </div>
              )}

              {/* Task Creation Form (Phase B) */}
              {showTaskForm && (
                <div className="task-creation-form">
                  <div className="task-form-header">
                    <h4>Create Task</h4>
                    <button className="close-btn" onClick={handleCancelTaskForm}>×</button>
                  </div>
                  
                  {creatingTask && !taskFormData.title ? (
                    <div className="loading">DATA is analyzing the email...</div>
                  ) : (
                    <>
                      <div className="task-form-field">
                        <label>Title</label>
                        <input
                          type="text"
                          value={taskFormData.title}
                          onChange={(e) => setTaskFormData(prev => ({ ...prev, title: e.target.value }))}
                          placeholder="Task title"
                        />
                      </div>
                      
                      <div className="task-form-row">
                        <div className="task-form-field">
                          <label>Due Date</label>
                          <input
                            type="date"
                            value={taskFormData.dueDate}
                            onChange={(e) => setTaskFormData(prev => ({ ...prev, dueDate: e.target.value }))}
                          />
                        </div>
                        
                        <div className="task-form-field">
                          <label>Priority</label>
                          <select
                            value={taskFormData.priority}
                            onChange={(e) => setTaskFormData(prev => ({ ...prev, priority: e.target.value }))}
                          >
                            <option value="Critical">Critical</option>
                            <option value="Urgent">Urgent</option>
                            <option value="Important">Important</option>
                            <option value="Standard">Standard</option>
                            <option value="Low">Low</option>
                          </select>
                        </div>
                      </div>
                      
                      <div className="task-form-row">
                        <div className="task-form-field">
                          <label>Domain</label>
                          <select
                            value={taskFormData.domain}
                            onChange={(e) => setTaskFormData(prev => ({ 
                              ...prev, 
                              domain: e.target.value,
                              project: '' // Reset project when domain changes
                            }))}
                          >
                            <option value="personal">Personal</option>
                            <option value="church">Church</option>
                            <option value="work">Work</option>
                          </select>
                        </div>
                        
                        <div className="task-form-field">
                          <label>Project</label>
                          <select
                            value={taskFormData.project}
                            onChange={(e) => setTaskFormData(prev => ({ ...prev, project: e.target.value }))}
                          >
                            <option value="">Select project...</option>
                            {projectOptions.map(proj => (
                              <option key={proj} value={proj}>{proj}</option>
                            ))}
                          </select>
                        </div>
                      </div>
                      
                      <div className="task-form-field">
                        <label>Notes</label>
                        <textarea
                          value={taskFormData.notes}
                          onChange={(e) => setTaskFormData(prev => ({ ...prev, notes: e.target.value }))}
                          placeholder="Optional notes..."
                          rows={2}
                        />
                      </div>
                      
                      <div className="task-form-actions">
                        <button className="cancel-btn" onClick={handleCancelTaskForm}>
                          Cancel
                        </button>
                        <button
                          className="create-btn"
                          onClick={handleCreateTask}
                          disabled={creatingTask || !taskFormData.title.trim()}
                        >
                          {creatingTask ? 'Creating...' : 'Create Task'}
                        </button>
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* DATA Chat Interface */}
              {!showTaskForm && (
              <div className="email-chat-container">
                {/* Chat messages */}
                <div className="email-chat-messages">
                  {chatHistory.length === 0 ? (
                    <div className="chat-empty-state">
                      <div className="chat-empty-icon">💬</div>
                      <p>Ask DATA about this email</p>
                      <div className="chat-suggestions">
                        <button onClick={() => setChatInput('What should I do with this email?')}>
                          What should I do with this?
                        </button>
                        <button onClick={() => setChatInput('Summarize this email')}>
                          Summarize
                        </button>
                        <button onClick={() => setChatInput('Should I archive this?')}>
                          Should I archive?
                        </button>
                      </div>
                    </div>
                  ) : (
                    chatHistory.map((msg, idx) => (
                      <div key={idx} className={`chat-message ${msg.role}`}>
                        <div className="chat-message-content">{msg.content}</div>
                      </div>
                    ))
                  )}
                  
                  {chatLoading && (
                    <div className="chat-message assistant loading">
                      <div className="chat-message-content">Thinking...</div>
                    </div>
                  )}
                  
                  {/* Pending action confirmation */}
                  {pendingEmailAction && (
                    <div className="pending-action-card">
                      <div className="pending-action-header">
                        DATA suggests: <strong>{pendingEmailAction.action}</strong>
                      </div>
                      <div className="pending-action-reason">{pendingEmailAction.reason}</div>
                      <div className="pending-action-buttons">
                        <button 
                          className="confirm-btn"
                          onClick={handleConfirmEmailAction}
                          disabled={actionLoading !== null}
                        >
                          {actionLoading ? 'Processing...' : 'Confirm'}
                        </button>
                        <button 
                          className="cancel-btn"
                          onClick={() => setPendingEmailAction(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
                
                {/* Chat input */}
                <form 
                  className="email-chat-input"
                  onSubmit={(e) => {
                    e.preventDefault()
                    handleSendChatMessage()
                  }}
                >
                  <input
                    type="text"
                    placeholder={selectedEmail ? "Ask DATA about this email..." : "Select an email to chat"}
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    disabled={chatLoading}
                  />
                  <button 
                    type="submit"
                    disabled={!chatInput.trim() || chatLoading}
                  >
                    Send
                  </button>
                </form>
              </div>
              )}
            </div>
          </section>
        )}

        {/* Collapsed assist panel indicator */}
        {assistPanelCollapsed && (
          <div className="collapsed-panel-indicator right" onClick={handleToggleAssistPanel}>
            <span className="collapsed-label">DATA</span>
            <span className="expand-icon">◀</span>
          </div>
        )}
      </div>
      
      {/* Email Reply Draft Panel */}
      <EmailDraftPanel
        isOpen={showReplyPanel}
        onClose={handleCloseReplyPanel}
        onSend={handleSendReply}
        onRegenerate={handleRegenerateReply}
        onDiscard={handleDiscardReply}
        initialDraft={replyDraft ?? undefined}
        gmailAccounts={['personal', 'church']}
        sending={sendingReply}
        regenerating={generatingReply}
        error={replyError}
      />
    </div>
  )
}

