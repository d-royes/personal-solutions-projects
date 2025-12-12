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
  type EmailPendingAction,
} from '../api'

interface EmailDashboardProps {
  authConfig: AuthConfig
  apiBase: string
  onBack: () => void
}

type TabView = 'dashboard' | 'rules' | 'suggestions' | 'attention'

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
  suggestions: RuleSuggestion[]
  attentionItems: AttentionItem[]
  loaded: boolean
}

const emptyCache = (): AccountCache => ({
  inbox: null,
  rules: [],
  suggestions: [],
  attentionItems: [],
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
  const suggestions = cache[selectedAccount].suggestions
  const attentionItems = cache[selectedAccount].attentionItems
  
  // Loading states
  const [loadingInbox, setLoadingInbox] = useState(false)
  const [loadingRules, setLoadingRules] = useState(false)
  const [loadingAnalysis, setLoadingAnalysis] = useState(false)
  
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

  // Analyze inbox for suggestions
  const runAnalysis = useCallback(async () => {
    setLoadingAnalysis(true)
    setError(null)
    try {
      const response = await analyzeInbox(selectedAccount, authConfig, apiBase, 50)
      updateCache({ 
        suggestions: response.suggestions,
        attentionItems: response.attentionItems 
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed')
    } finally {
      setLoadingAnalysis(false)
    }
  }, [selectedAccount, authConfig, apiBase, updateCache])

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
  
  // Handle dismissing a suggestion
  function handleDismissSuggestion(suggestion: RuleSuggestion) {
    const updatedSuggestions = suggestions.filter(s => s !== suggestion)
    updateCache({ suggestions: updatedSuggestions })
  }

  // Handle selecting an email (opens assist panel)
  function handleSelectEmail(emailId: string) {
    setSelectedEmailId(emailId)
    setAssistPanelCollapsed(false)
    // Clear chat history when selecting a new email
    setChatHistory([])
    setPendingEmailAction(null)
  }

  // Handle sending a chat message about the selected email
  async function handleSendChatMessage() {
    if (!selectedEmailId || !chatInput.trim()) return
    
    setChatLoading(true)
    setPendingEmailAction(null)
    
    // Add user message to history immediately
    const userMessage = chatInput.trim()
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
          handleEmailQuickAction({ 
            type: 'create_task', 
            emailId: selectedEmailId,
            subject: pendingEmailAction.taskTitle || selectedEmail?.subject || 'Task from email'
          })
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

  // State for email actions
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  
  // Email chat state (Phase 4)
  const [chatHistory, setChatHistory] = useState<Array<{ role: string; content: string }>>([])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [pendingEmailAction, setPendingEmailAction] = useState<EmailPendingAction | null>(null)

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
          // TODO: Implement task creation - for now show alert
          alert(`Task creation coming soon: ${action.subject}`)
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
                className={activeTab === 'suggestions' ? 'active' : ''}
                onClick={() => {
                  setActiveTab('suggestions')
                  if (suggestions.length === 0) runAnalysis()
                }}
              >
                Suggestions {suggestions.length > 0 && `(${suggestions.length})`}
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

        {/* Suggestions Tab */}
        {activeTab === 'suggestions' && (
          <div className="suggestions-view">
            {loadingAnalysis ? (
              <div className="loading">Analyzing inbox patterns...</div>
            ) : suggestions.length === 0 ? (
              <div className="empty-state">
                <p>No new suggestions</p>
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
                  <div className="preview-snippet">{selectedEmail.snippet}</div>
                  
                  {/* Quick action buttons */}
                  <div className="email-quick-actions">
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

              {/* DATA Chat Interface */}
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
                    disabled={!selectedEmail || chatLoading}
                  />
                  <button 
                    type="submit"
                    disabled={!selectedEmail || !chatInput.trim() || chatLoading}
                  >
                    Send
                  </button>
                </form>
              </div>
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
    </div>
  )
}

