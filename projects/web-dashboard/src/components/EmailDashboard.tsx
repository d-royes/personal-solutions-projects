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
} from '../api'

interface EmailDashboardProps {
  authConfig: AuthConfig
  apiBase: string
  onBack: () => void
}

type TabView = 'dashboard' | 'rules' | 'suggestions' | 'attention'

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

export function EmailDashboard({ authConfig, apiBase, onBack }: EmailDashboardProps) {
  // Account selection
  const [selectedAccount, setSelectedAccount] = useState<EmailAccount>('personal')
  const [activeTab, setActiveTab] = useState<TabView>('dashboard')
  
  // Data state
  const [inboxSummary, setInboxSummary] = useState<InboxSummary | null>(null)
  const [rules, setRules] = useState<FilterRule[]>([])
  const [suggestions, setSuggestions] = useState<RuleSuggestion[]>([])
  const [attentionItems, setAttentionItems] = useState<AttentionItem[]>([])
  
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

  // Load inbox summary
  const loadInbox = useCallback(async () => {
    setLoadingInbox(true)
    setError(null)
    try {
      const summary = await getInboxSummary(selectedAccount, authConfig, apiBase, 30)
      setInboxSummary(summary)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load inbox')
    } finally {
      setLoadingInbox(false)
    }
  }, [selectedAccount, authConfig, apiBase])

  // Load filter rules
  const loadRules = useCallback(async () => {
    setLoadingRules(true)
    setError(null)
    try {
      const response = await getFilterRules(selectedAccount, authConfig, apiBase)
      setRules(response.rules)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load rules')
    } finally {
      setLoadingRules(false)
    }
  }, [selectedAccount, authConfig, apiBase])

  // Analyze inbox for suggestions
  const runAnalysis = useCallback(async () => {
    setLoadingAnalysis(true)
    setError(null)
    try {
      const response = await analyzeInbox(selectedAccount, authConfig, apiBase, 50)
      setSuggestions(response.suggestions)
      setAttentionItems(response.attentionItems)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed')
    } finally {
      setLoadingAnalysis(false)
    }
  }, [selectedAccount, authConfig, apiBase])

  // Load data when account changes
  useEffect(() => {
    loadInbox()
    loadRules()
  }, [selectedAccount, loadInbox, loadRules])

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
      
      // Refresh rules and reset form
      await loadRules()
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
      await loadRules()
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
      
      // Remove from suggestions and refresh rules
      setSuggestions(prev => prev.filter(s => s !== suggestion))
      await loadRules()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add rule')
    } finally {
      setAddingRule(false)
    }
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

  return (
    <div className="email-dashboard">
      {/* Header */}
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

      {/* Error display */}
      {error && (
        <div className="email-error">
          {error}
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

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
                <div className="stat-value">{inboxSummary?.totalUnread ?? '—'}</div>
                <div className="stat-label">Unread</div>
              </div>
              <div className="stat-card important">
                <div className="stat-value">{inboxSummary?.unreadImportant ?? '—'}</div>
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
              <button
                className="action-btn primary"
                onClick={runAnalysis}
                disabled={loadingAnalysis}
              >
                {loadingAnalysis ? 'Analyzing...' : 'Analyze Inbox'}
              </button>
              <button
                className="action-btn"
                onClick={loadInbox}
                disabled={loadingInbox}
              >
                {loadingInbox ? 'Refreshing...' : 'Refresh'}
              </button>
            </div>

            {/* Recent messages preview */}
            {inboxSummary?.recentMessages && inboxSummary.recentMessages.length > 0 && (
              <div className="recent-messages">
                <h3>Recent Messages</h3>
                <ul className="message-list">
                  {inboxSummary.recentMessages.slice(0, 10).map(msg => (
                    <li key={msg.id} className={msg.isUnread ? 'unread' : ''}>
                      <div className="msg-from">{msg.fromName || msg.fromAddress}</div>
                      <div className="msg-subject">{msg.subject}</div>
                      <div className="msg-snippet">{msg.snippet}</div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
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
                      <span
                        className="category-badge"
                        style={{ backgroundColor: getCategoryColor(suggestion.suggestedRule.category) }}
                      >
                        {suggestion.suggestedRule.category}
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
                      <button
                        className="approve-btn"
                        onClick={() => handleApproveSuggestion(suggestion)}
                        disabled={addingRule}
                      >
                        Approve
                      </button>
                      <button
                        className="dismiss-btn"
                        onClick={() => setSuggestions(prev => prev.filter(s => s !== suggestion))}
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
                  <li key={item.emailId} className={`attention-card ${item.urgency}`}>
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
                        <button className="create-task-btn">
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
    </div>
  )
}

