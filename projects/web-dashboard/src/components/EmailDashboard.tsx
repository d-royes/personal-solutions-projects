import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import type { AuthConfig } from '../auth/types'
import type {
  EmailAccount,
  EmailMessage,
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
  markEmailRead,
  chatAboutEmail,
  searchEmails,
  getEmailActionSuggestions,
  getEmailLabels,
  applyEmailLabel,
  modifyEmailLabel,
  getTaskPreviewFromEmail,
  createTaskFromEmail,
  checkEmailsHaveTasks,
  getEmailFull,
  generateReplyDraft,
  sendReply,
  dismissAttentionItem,
  snoozeAttentionItem,
  getAttentionItems,
  getPendingRules,
  getPendingActionSuggestions,
  getLastAnalysis,
  getEmailConversation,
  getEmailPrivacyStatus,
  decideSuggestion,
  decideRuleSuggestion,
  pinEmail,
  unpinEmail,
  getPinnedEmails,
  type EmailPendingAction,
  type EmailActionSuggestion,
  type GmailLabel,
  type TaskPreview,
  type EmailTaskInfo,
  type DismissReason,
  type EmailPrivacyStatus,
  type PinnedEmail,
} from '../api'
import { EmailDraftPanel, type EmailDraft } from './EmailDraftPanel'
import { HaikuSettingsPanel } from './HaikuSettingsPanel'

// Last analysis result for auditing
export interface LastAnalysisResult {
  timestamp: Date
  emailsFetched: number
  emailsAnalyzed: number
  alreadyTracked: number
  dismissed: number
  suggestionsGenerated: number
  rulesGenerated: number
  attentionItems: number
  haikuAnalyzed: number
  haikuRemaining: { daily: number; weekly: number } | null
}

// Per-account cache structure - exported for App.tsx to manage
export interface AccountCache {
  inbox: InboxSummary | null
  rules: FilterRule[]
  suggestions: RuleSuggestion[]  // Rule suggestions (New Rules tab)
  attentionItems: AttentionItem[]
  actionSuggestions: EmailActionSuggestion[]  // Email action suggestions (Suggestions tab)
  availableLabels: GmailLabel[]
  emailTaskLinks: Record<string, EmailTaskInfo>  // email_id -> task info
  pinnedEmails: PinnedEmail[]  // Pinned emails for quick reference
  loaded: boolean
  lastAnalysis: LastAnalysisResult | null  // Last analysis result for auditing
}

export const emptyEmailCache = (): AccountCache => ({
  inbox: null,
  rules: [],
  suggestions: [],
  attentionItems: [],
  actionSuggestions: [],
  availableLabels: [],
  emailTaskLinks: {},
  pinnedEmails: [],
  loaded: false,
  lastAnalysis: null,
})

export type EmailCacheState = Record<EmailAccount, AccountCache>

interface EmailDashboardProps {
  authConfig: AuthConfig
  apiBase: string
  onBack: () => void
  // Optional lifted state for persistence across mode switches
  cache?: EmailCacheState
  setCache?: React.Dispatch<React.SetStateAction<EmailCacheState>>
  selectedAccount?: EmailAccount
  setSelectedAccount?: React.Dispatch<React.SetStateAction<EmailAccount>>
  // Callback when a task is created from email (to refresh task list in App)
  onTaskCreated?: () => void
}

type TabView = 'dashboard' | 'rules' | 'newRules' | 'suggestions' | 'attention' | 'pinned' | 'settings'

// Quick action types for email management
type EmailQuickAction =
  | { type: 'archive'; emailId: string }
  | { type: 'delete'; emailId: string }
  | { type: 'star'; emailId: string }
  | { type: 'flag'; emailId: string }
  | { type: 'read'; emailId: string; markAsRead: boolean }
  | { type: 'create_task'; emailId: string; subject: string }

// Draggable panel divider component with collapse arrows
function PanelDivider({
  onDrag,
  onCollapseLeft,
  onCollapseRight,
  leftCollapsed,
  rightCollapsed,
}: {
  onDrag: (delta: number) => void
  onCollapseLeft: () => void
  onCollapseRight: () => void
  leftCollapsed: boolean
  rightCollapsed: boolean
}) {
  const isDragging = useRef(false)
  const startPos = useRef(0)

  const handleMouseDown = (e: React.MouseEvent) => {
    // Don't start drag if clicking on arrows
    if ((e.target as HTMLElement).closest('.divider-arrow')) return
    e.preventDefault()
    isDragging.current = true
    startPos.current = e.clientX
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  const handleMouseMove = (e: MouseEvent) => {
    if (!isDragging.current) return
    const delta = e.clientX - startPos.current
    startPos.current = e.clientX
    onDrag(delta)
  }

  const handleMouseUp = () => {
    isDragging.current = false
    document.removeEventListener('mousemove', handleMouseMove)
    document.removeEventListener('mouseup', handleMouseUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }

  return (
    <div className="email-panel-divider" onMouseDown={handleMouseDown}>
      <button
        className="divider-arrow left"
        onClick={onCollapseLeft}
        title={leftCollapsed ? "Expand inbox" : "Collapse inbox"}
      >
        {leftCollapsed ? '▶' : '◀'}
      </button>
      <div className="divider-handle" />
      <button
        className="divider-arrow right"
        onClick={onCollapseRight}
        title={rightCollapsed ? "Expand DATA" : "Collapse DATA"}
      >
        {rightCollapsed ? '◀' : '▶'}
      </button>
    </div>
  )
}

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

export function EmailDashboard({
  authConfig,
  apiBase,
  onBack,
  cache: externalCache,
  setCache: externalSetCache,
  selectedAccount: externalSelectedAccount,
  setSelectedAccount: externalSetSelectedAccount,
  onTaskCreated,
}: EmailDashboardProps) {
  // Account selection - use external state if provided, otherwise local
  const [localSelectedAccount, localSetSelectedAccount] = useState<EmailAccount>('personal')
  const selectedAccount = externalSelectedAccount ?? localSelectedAccount
  const setSelectedAccount = externalSetSelectedAccount ?? localSetSelectedAccount

  const [activeTab, setActiveTab] = useState<TabView>('dashboard')

  // Two-panel layout state
  const [emailPanelCollapsed, setEmailPanelCollapsed] = useState(false)
  const [assistPanelCollapsed, setAssistPanelCollapsed] = useState(false) // Both panels visible by default
  const [panelSplitRatio, setPanelSplitRatio] = useState(50) // Percentage for left panel (50 = 50/50 split)
  const [selectedEmailId, setSelectedEmailId] = useState<string | null>(null)
  const panelsContainerRef = useRef<HTMLDivElement>(null)

  // Per-account data cache - use external state if provided, otherwise local
  const [localCache, localSetCache] = useState<EmailCacheState>({
    personal: emptyEmailCache(),
    church: emptyEmailCache(),
  })
  const cache = externalCache ?? localCache
  const setCache = externalSetCache ?? localSetCache

  // Derived state from cache for current account
  const inboxSummary = cache[selectedAccount].inbox
  const rules = cache[selectedAccount].rules
  const suggestions = cache[selectedAccount].suggestions  // Rule suggestions (New Rules tab)
  const attentionItems = cache[selectedAccount].attentionItems
  const actionSuggestions = cache[selectedAccount].actionSuggestions  // Email action suggestions
  const availableLabels = cache[selectedAccount].availableLabels
  const emailTaskLinks = cache[selectedAccount].emailTaskLinks  // Emails that have linked tasks
  const pinnedEmails = cache[selectedAccount].pinnedEmails  // Pinned emails for quick reference

  // Thread count by threadId (for "N in thread" badge)
  const threadCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    if (inboxSummary?.recentMessages) {
      for (const msg of inboxSummary.recentMessages) {
        counts[msg.threadId] = (counts[msg.threadId] || 0) + 1
      }
    }
    return counts
  }, [inboxSummary?.recentMessages])

  // Loading states
  const [loadingInbox, setLoadingInbox] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)  // For "Load More" pagination
  const [loadingRules, setLoadingRules] = useState(false)
  const [loadingAnalysis, setLoadingAnalysis] = useState(false)
  const [loadingActionSuggestions, setLoadingActionSuggestions] = useState(false)

  // Last sync timestamp for attention items
  const [lastAttentionSync, setLastAttentionSync] = useState<Date | null>(null)
  
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
  // Store the fetched full email message (for when email isn't in recentMessages/searchResults)
  const [fetchedEmail, setFetchedEmail] = useState<EmailMessage | null>(null)
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

  // Email preview panel controls
  const [emailPreviewCollapsed, setEmailPreviewCollapsed] = useState(false)
  const [showDismissMenu, setShowDismissMenu] = useState(false)

  // Pinned emails state
  const [loadingPinned, setLoadingPinned] = useState(false)

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
      const summary = await getInboxSummary(selectedAccount, authConfig, apiBase, 20)
      updateCache({ inbox: summary })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load inbox')
    } finally {
      setLoadingInbox(false)
    }
  }, [selectedAccount, authConfig, apiBase, cache, updateCache])

  // Load more emails (pagination - appends to existing list)
  const loadMoreEmails = useCallback(async () => {
    const currentInbox = cache[selectedAccount].inbox
    if (!currentInbox?.nextPageToken) return  // No more pages

    setLoadingMore(true)
    setError(null)
    try {
      const nextPage = await getInboxSummary(
        selectedAccount, authConfig, apiBase, 20, currentInbox.nextPageToken
      )
      // Append new messages to existing list
      updateCache({
        inbox: {
          ...nextPage,
          recentMessages: [...currentInbox.recentMessages, ...nextPage.recentMessages],
        }
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load more emails')
    } finally {
      setLoadingMore(false)
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
      const response = await analyzeInbox(selectedAccount, authConfig, apiBase, 20)
      
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
      
      // Merge new rule suggestions with existing ones (don't replace)
      const existingRules = cache[selectedAccount].suggestions
      const newRules = response.suggestions as RuleSuggestion[]

      // Deduplicate by ruleId or by pattern (field + operator + value)
      const existingPatterns = new Set(existingRules.map(r =>
        r.ruleId || `${r.suggestedRule.field}:${r.suggestedRule.operator}:${r.suggestedRule.value}`
      ))
      const mergedRules = [
        ...existingRules,
        ...newRules.filter(r => {
          const pattern = r.ruleId || `${r.suggestedRule.field}:${r.suggestedRule.operator}:${r.suggestedRule.value}`
          return !existingPatterns.has(pattern)
        })
      ]

      // Merge new action suggestions with existing ones
      const existingActions = cache[selectedAccount].actionSuggestions
      const newActions = (response.actionSuggestions || []) as EmailActionSuggestion[]

      // Deduplicate by suggestionId or emailId
      const existingEmailIds = new Set(existingActions.map(s =>
        (s as unknown as { suggestionId?: string }).suggestionId || s.emailId
      ))
      const mergedActions = [
        ...existingActions,
        ...newActions.filter(s => {
          const id = (s as unknown as { suggestionId?: string }).suggestionId || s.emailId
          return !existingEmailIds.has(id)
        })
      ]
      // Re-number action suggestions
      const renumberedActions = mergedActions.map((s, idx) => ({ ...s, number: idx + 1 }))

      updateCache({
        suggestions: mergedRules,  // Rule suggestions for "New Rules" tab (MERGED)
        actionSuggestions: renumberedActions,  // Action suggestions for "Suggestions" tab (MERGED)
        attentionItems: response.attentionItems,
        emailTaskLinks: taskLinks,
      })
      setLastAttentionSync(new Date())  // Update sync timestamp

      // Reload persisted data to ensure cache is in sync with storage
      // This catches any suggestions that were persisted but not in the response
      const suggestionsResponse = await getPendingActionSuggestions(selectedAccount, authConfig, apiBase)
      updateCache({ actionSuggestions: suggestionsResponse.suggestions || [] })

      const rulesResponse = await getPendingRules(selectedAccount, authConfig, apiBase)
      const ruleSuggestions: RuleSuggestion[] = rulesResponse.rules.map(r => ({
        type: r.suggestionType as 'new_label' | 'deletion' | 'attention',
        suggestedRule: {
          emailAccount: r.suggestedRule.emailAccount || selectedAccount,
          order: r.suggestedRule.order || 1,
          category: r.suggestedRule.category,
          field: r.suggestedRule.field,
          operator: r.suggestedRule.operator,
          value: r.suggestedRule.value,
          action: r.suggestedRule.action,
        },
        confidence: r.confidence >= 0.8 ? 'high' : r.confidence >= 0.6 ? 'medium' : 'low',
        reason: r.reason,
        examples: r.examples,
        emailCount: r.emailCount,
        ruleId: r.ruleId,
      }))
      updateCache({ suggestions: ruleSuggestions })

      // Save last analysis result for auditing (Settings page)
      const lastAnalysisResult: LastAnalysisResult = {
        timestamp: new Date(),
        emailsFetched: response.emailsFetched || 0,
        emailsAnalyzed: response.messagesAnalyzed || 0,
        alreadyTracked: response.emailsAlreadyTracked || 0,
        dismissed: response.emailsDismissed || 0,
        suggestionsGenerated: (response.actionSuggestions?.length || 0),
        rulesGenerated: (response.suggestions?.length || 0),
        attentionItems: response.attentionItems?.length || 0,
        haikuAnalyzed: response.haikuAnalyzed || 0,
        haikuRemaining: response.haikuUsage ? {
          daily: response.haikuUsage.dailyRemaining,
          weekly: response.haikuUsage.weeklyRemaining,
        } : null,
      }
      updateCache({ lastAnalysis: lastAnalysisResult })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed')
    } finally {
      setLoadingAnalysis(false)
    }
  }, [selectedAccount, authConfig, apiBase, updateCache])

  // Load persisted attention items (without re-analyzing)
  const loadPersistedAttention = useCallback(async () => {
    try {
      const response = await getAttentionItems(selectedAccount, authConfig, apiBase)

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
        attentionItems: response.attentionItems,
        emailTaskLinks: taskLinks,
      })
      if (response.attentionItems.length > 0) {
        setLastAttentionSync(new Date())  // Update sync timestamp when items loaded
      }
    } catch (err) {
      // Silent fail - persisted attention is optional, user can run analysis
      console.warn('Failed to load persisted attention:', err)
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

  // Load pinned emails (Pinned tab)
  const loadPinnedEmails = useCallback(async () => {
    setLoadingPinned(true)
    try {
      const response = await getPinnedEmails(selectedAccount, authConfig, apiBase)
      updateCache({ pinnedEmails: response.pinned })
    } catch (err) {
      console.warn('Failed to load pinned emails:', err)
    } finally {
      setLoadingPinned(false)
    }
  }, [selectedAccount, authConfig, apiBase, updateCache])

  // Load persisted rule suggestions from storage (without re-analyzing)
  const loadPersistedRules = useCallback(async () => {
    try {
      const rulesResponse = await getPendingRules(selectedAccount, authConfig, apiBase)

      // Convert API response to RuleSuggestion format
      const ruleSuggestions: RuleSuggestion[] = rulesResponse.rules.map(r => ({
        type: r.suggestionType as 'new_label' | 'deletion' | 'attention',
        suggestedRule: {
          emailAccount: r.suggestedRule.emailAccount || selectedAccount,
          order: r.suggestedRule.order || 1,
          category: r.suggestedRule.category,
          field: r.suggestedRule.field,
          operator: r.suggestedRule.operator,
          value: r.suggestedRule.value,
          action: r.suggestedRule.action,
        },
        confidence: r.confidence >= 0.8 ? 'high' : r.confidence >= 0.6 ? 'medium' : 'low',
        reason: r.reason,
        examples: r.examples,
        emailCount: r.emailCount,
        ruleId: r.ruleId,
      }))

      // Always update cache - even if empty - to clear stale data from other accounts
      updateCache({ suggestions: ruleSuggestions })
    } catch (err) {
      // Silent fail - persisted rules are optional
      console.warn('Failed to load persisted rules:', err)
    }
  }, [selectedAccount, authConfig, apiBase, updateCache])

  // Load persisted action suggestions from storage (Suggestions tab)
  const loadPersistedActionSuggestions = useCallback(async () => {
    try {
      const response = await getPendingActionSuggestions(selectedAccount, authConfig, apiBase)

      // Always update cache - even if empty - to clear stale data from other accounts
      updateCache({ actionSuggestions: response.suggestions || [] })
    } catch (err) {
      // Silent fail - persisted suggestions are optional
      console.warn('Failed to load persisted action suggestions:', err)
    }
  }, [selectedAccount, authConfig, apiBase, updateCache])

  // Load last analysis result from server (for cross-machine sync)
  const loadLastAnalysis = useCallback(async (account: EmailAccount) => {
    try {
      const response = await getLastAnalysis(account, authConfig, apiBase)
      if (response.lastAnalysis) {
        const lastAnalysis: LastAnalysisResult = {
          timestamp: new Date(response.lastAnalysis.timestamp),
          emailsFetched: response.lastAnalysis.emailsFetched,
          emailsAnalyzed: response.lastAnalysis.emailsAnalyzed,
          alreadyTracked: response.lastAnalysis.alreadyTracked,
          dismissed: response.lastAnalysis.dismissed,
          suggestionsGenerated: response.lastAnalysis.suggestionsGenerated,
          rulesGenerated: response.lastAnalysis.rulesGenerated,
          attentionItems: response.lastAnalysis.attentionItems,
          haikuAnalyzed: response.lastAnalysis.haikuAnalyzed,
          haikuRemaining: response.lastAnalysis.haikuRemaining,
        }
        // Update the specific account's cache
        setCache(prev => ({
          ...prev,
          [account]: {
            ...prev[account],
            lastAnalysis,
          },
        }))
      }
    } catch (err) {
      // Silent fail - last analysis is optional
      console.warn(`Failed to load last analysis for ${account}:`, err)
    }
  }, [authConfig, apiBase, setCache])

  // Load last analysis for both accounts on initial mount (cross-machine sync)
  useEffect(() => {
    loadLastAnalysis('personal')
    loadLastAnalysis('church')
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Dismiss an attention item
  const handleDismiss = useCallback(async (emailId: string, reason: DismissReason) => {
    try {
      await dismissAttentionItem(selectedAccount, emailId, reason, authConfig, apiBase)
      // Remove from local cache
      updateCache({
        attentionItems: attentionItems.filter(item => item.emailId !== emailId)
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to dismiss')
    }
  }, [selectedAccount, authConfig, apiBase, updateCache, attentionItems])

  // Snooze an attention item
  const handleSnooze = useCallback(async (emailId: string, hours: number) => {
    try {
      const until = new Date()
      until.setHours(until.getHours() + hours)
      await snoozeAttentionItem(selectedAccount, emailId, until, authConfig, apiBase)
      // Remove from local cache (will reappear after snooze expires)
      updateCache({
        attentionItems: attentionItems.filter(item => item.emailId !== emailId)
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to snooze')
    }
  }, [selectedAccount, authConfig, apiBase, updateCache, attentionItems])

  // Dismiss from DATA panel (clears selection after dismiss)
  const handleDismissFromPanel = useCallback(async (reason: DismissReason) => {
    if (!selectedEmailId) return
    try {
      await handleDismiss(selectedEmailId, reason)
      setSelectedEmailId(null)
      setChatHistory([])
      setPendingEmailAction(null)
      setEmailPreviewCollapsed(false)
      setShowDismissMenu(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Dismiss failed')
    }
  }, [selectedEmailId, handleDismiss])

  // Close email panel without dismissing (just clears selection)
  const handleCloseEmailPanel = useCallback(() => {
    setSelectedEmailId(null)
    setChatHistory([])
    setPendingEmailAction(null)
    setPrivacyStatus(null)
    setPrivacyOverrideGranted(false)
    setEmailBodyExpanded(false)
    setEmailPreviewCollapsed(false)
    setFullEmailBody(null)
    setShowDismissMenu(false)
  }, [])

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
    loadLabels()  // Load labels for name lookup
    loadPersistedAttention()  // Load persisted attention items on account change
    loadPersistedRules()  // Load persisted rule suggestions on account change
    loadPersistedActionSuggestions()  // Load persisted action suggestions on account change
    loadPinnedEmails()  // Load pinned emails on account change
  }, [selectedAccount]) // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-select first email when inbox loads and nothing is selected
  useEffect(() => {
    if (!selectedEmailId && inboxSummary?.recentMessages?.length) {
      const firstEmail = inboxSummary.recentMessages[0]
      setSelectedEmailId(firstEmail.id)
    }
  }, [inboxSummary?.recentMessages, selectedEmailId])

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
  async function handleDismissSuggestion(suggestion: RuleSuggestion) {
    // Update local cache immediately for responsive UI
    const updatedSuggestions = suggestions.filter(s => s !== suggestion)
    updateCache({ suggestions: updatedSuggestions })

    // Persist dismissal to backend if we have a ruleId
    if (suggestion.ruleId) {
      try {
        await decideRuleSuggestion(selectedAccount, suggestion.ruleId, false, authConfig, apiBase)
      } catch (err) {
        console.error('Failed to persist rule dismissal:', err)
        // Don't revert UI - the dismissal still "worked" locally
      }
    }
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
  async function handleDismissActionSuggestion(suggestion: EmailActionSuggestion) {
    // Update local cache immediately for responsive UI
    const updated = actionSuggestions.filter(s => s.number !== suggestion.number)
    // Re-number remaining suggestions
    const renumbered = updated.map((s, idx) => ({ ...s, number: idx + 1 }))
    updateCache({ actionSuggestions: renumbered })

    // Persist dismissal to backend if we have a suggestionId
    if (suggestion.suggestionId) {
      try {
        await decideSuggestion(selectedAccount, suggestion.suggestionId, false, authConfig, apiBase)
      } catch (err) {
        console.error('Failed to persist action suggestion dismissal:', err)
        // Don't revert UI - the dismissal still "worked" locally
      }
    }
  }

  // Handle quick action on a suggestion (Archive/Delete/Star/Read without approving the suggested action)
  async function handleSuggestionQuickAction(suggestion: EmailActionSuggestion, action: 'archive' | 'delete' | 'star' | 'flag' | 'read') {
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
        case 'read':
          await markEmailRead(selectedAccount, suggestion.emailId, true, authConfig, apiBase)
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
        plannedDate: response.preview.dueDate || '',  // Map dueDate to plannedDate
        targetDate: '',
        hardDeadline: '',
        status: 'scheduled',
        priority: response.preview.priority || 'Standard',
        domain: domain,
        project: response.preview.project || '',
        notes: response.preview.notes || '',
        estimatedHours: '',
      })
    } catch (err) {
      // Fallback to email subject
      const email = selectedEmail
      const domain = selectedAccount === 'church' ? 'church' : 'personal'
      setTaskFormData({
        title: email?.subject.replace(/^(Re:|Fwd:|FW:)\s*/gi, '').trim() || '',
        plannedDate: '',
        targetDate: '',
        hardDeadline: '',
        status: 'scheduled',
        priority: 'Standard',
        domain: domain,
        project: domain === 'church' ? 'Church Tasks' : 'Sm. Projects & Tasks',
        notes: '',  // Notes will be enhanced with email source in backend
        estimatedHours: '',
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
          threadId: selectedEmail?.threadId,  // Link task to email thread
          title: taskFormData.title.trim(),
          // Three-date model
          plannedDate: taskFormData.plannedDate || undefined,
          targetDate: taskFormData.targetDate || undefined,
          hardDeadline: taskFormData.hardDeadline || undefined,
          // Core fields
          status: taskFormData.status || undefined,
          priority: taskFormData.priority,
          domain: taskFormData.domain,
          project: taskFormData.project || undefined,
          notes: taskFormData.notes || undefined,
          estimatedHours: taskFormData.estimatedHours ? parseFloat(taskFormData.estimatedHours) : undefined,
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
      const syncInfo = response.syncResult?.success ? ` (synced to Smartsheet)` : ''
      setChatHistory(prev => [...prev, { 
        role: 'assistant', 
        content: `✓ Task created: "${taskFormData.title}"${syncInfo}` 
      }])
      
      // Notify parent to refresh task list
      onTaskCreated?.()
      
      // Reset form
      setTaskFormData({
        title: '',
        plannedDate: '',
        targetDate: '',
        hardDeadline: '',
        status: 'scheduled',
        priority: 'Standard',
        domain: 'personal',
        project: '',
        notes: '',
        estimatedHours: '',
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
      plannedDate: '',
      targetDate: '',
      hardDeadline: '',
      status: 'scheduled',
      priority: 'Standard',
      domain: 'personal',
      project: '',
      notes: '',
      estimatedHours: '',
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

  // Find next email to select after disposing of current one
  function getNextEmailId(disposedEmailId: string): string | null {
    // Check search results first, then recent messages
    const emailList = emailSearchResults || inboxSummary?.recentMessages || []
    const currentIndex = emailList.findIndex(m => m.id === disposedEmailId)

    if (currentIndex === -1 || emailList.length <= 1) return null

    // Try next email, or previous if disposing the last one
    if (currentIndex < emailList.length - 1) {
      return emailList[currentIndex + 1].id
    } else {
      return emailList[currentIndex - 1].id
    }
  }

  // Handle selecting an email (opens assist panel)
  async function handleSelectEmail(emailId: string, threadId?: string) {
    setSelectedEmailId(emailId)
    setAssistPanelCollapsed(false)
    // Reset chat state for new email
    setChatHistory([])
    setPendingEmailAction(null)
    setPrivacyStatus(null)
    setPrivacyOverrideGranted(false)

    // Reset email body state
    setEmailBodyExpanded(false)
    setFullEmailBody(null)
    setFetchedEmail(null)

    // Reset preview panel state
    setEmailPreviewCollapsed(false)
    setShowDismissMenu(false)

    // Fetch full email body in the background
    // Pass whether we already have threadId so fallback can load conversation if needed
    fetchFullEmailBody(emailId, !!threadId)

    // Always fetch privacy status (for badge display)
    loadPrivacyStatus(emailId)

    // Load conversation history if we have a threadId
    if (threadId) {
      setCurrentThreadId(threadId)
      loadConversationHistory(threadId)
    } else {
      setCurrentThreadId(null)
    }
  }

  // Load just the privacy status for an email (always called on email select)
  async function loadPrivacyStatus(emailId: string) {
    console.log('[DEBUG] loadPrivacyStatus called for:', emailId)
    try {
      const privacyResponse = await getEmailPrivacyStatus(selectedAccount, emailId, authConfig, apiBase)
      console.log('[DEBUG] Privacy response:', privacyResponse)

      // Format reason for display (e.g., "sender_blocked" -> "Sender Blocked")
      const formatPrivacyReason = (reason: string | null): string => {
        if (!reason) return 'Privacy Protected'
        const formatted = reason
          .replace(/_/g, ' ')
          .replace(/\b\w/g, c => c.toUpperCase())
        return formatted
      }

      const status: EmailPrivacyStatus = {
        canSeeBody: !privacyResponse.privacy.isBlocked,
        blockedReason: privacyResponse.privacy.reason,
        blockedReasonDisplay: formatPrivacyReason(privacyResponse.privacy.reason),
        overrideGranted: privacyResponse.privacy.overrideGranted ?? false
      }
      console.log('[DEBUG] Setting privacy status:', status)
      setPrivacyStatus(status)

      // Initialize local override state from persisted value
      if (privacyResponse.privacy.overrideGranted) {
        setPrivacyOverrideGranted(true)
      }
    } catch (err) {
      console.error('Failed to load privacy status:', err)
      // Non-blocking - user can still chat, just won't see privacy badge
    }
  }

  // Load just the conversation history (only when threadId exists)
  async function loadConversationHistory(threadId: string) {
    setConversationLoading(true)
    try {
      const conversationResponse = await getEmailConversation(selectedAccount, threadId, authConfig, apiBase, 50)

      // Set conversation history if we have messages
      if (conversationResponse.messages && conversationResponse.messages.length > 0) {
        setChatHistory(conversationResponse.messages.map(m => ({
          role: m.role,
          content: m.content
        })))
      }
    } catch (err) {
      console.error('Failed to load conversation history:', err)
      // Non-blocking - user can still chat, just won't have history
    } finally {
      setConversationLoading(false)
    }
  }

  // Fetch full email body when email is selected
  // hasThreadId indicates if caller already has threadId (so we can skip fallback conversation load)
  async function fetchFullEmailBody(emailId: string, hasThreadId: boolean = false) {
    setLoadingFullBody(true)
    try {
      const response = await getEmailFull(selectedAccount, emailId, authConfig, apiBase, true)

      // Check for stale email (deleted/trashed)
      if (response.stale) {
        setToastMessage({
          text: response.staleMessage || 'This email has been deleted or moved to trash',
          type: 'warning'
        })
        // Quietly dismiss the attention item via API
        try {
          await dismissAttentionItem(selectedAccount, emailId, 'handled', authConfig, apiBase)
        } catch {
          // Ignore dismiss errors - just update local state
        }
        // Remove from local cache immediately
        updateCache({
          attentionItems: attentionItems.filter(item => item.emailId !== emailId)
        })
        // Also unpin if this email is pinned (stale cleanup)
        if (pinnedEmails.some(p => p.emailId === emailId)) {
          try {
            await unpinEmail(selectedAccount, emailId, authConfig, apiBase)
          } catch {
            // Ignore unpin errors - just update local state
          }
          updateCache({
            pinnedEmails: pinnedEmails.filter(p => p.emailId !== emailId)
          })
        }
        // Clear selection
        setSelectedEmailId(null)
        return
      }

      // Store the full email message (for emails not in recentMessages/searchResults, like from Attention tab)
      setFetchedEmail(response.message)
      setFullEmailBody({
        body: response.message.body ?? null,
        bodyHtml: response.message.bodyHtml ?? null,
        attachmentCount: response.message.attachmentCount ?? 0,
      })
      
      // Fallback: If caller didn't have threadId but email has one, load conversation
      // This handles older attention items that don't have threadId stored
      if (response.message.threadId && !hasThreadId) {
        setCurrentThreadId(response.message.threadId)
        loadConversationHistory(response.message.threadId)
      }
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

    console.log('[DEBUG] Sending chat - privacyOverrideGranted:', privacyOverrideGranted)

    try {
      const response = await chatAboutEmail(
        selectedAccount,
        {
          message: userMessage,
          emailId: selectedEmailId,
          threadId: currentThreadId ?? undefined,
          history: chatHistory,
          overridePrivacy: privacyOverrideGranted,
        },
        authConfig,
        apiBase
      )

      // Handle stale email detection
      if (response.stale) {
        setToastMessage({
          text: response.staleMessage || 'This email has been deleted or archived',
          type: 'warning'
        })
        // Clear the selection since email no longer exists
        setSelectedEmailId(null)
        setChatHistory([])
        return
      }

      // Add assistant response to history
      setChatHistory(prev => [...prev, { role: 'assistant', content: response.response }])

      // Update privacy status from response
      if (response.privacyStatus) {
        setPrivacyStatus(response.privacyStatus)
      }

      // Update threadId if returned (for new conversations)
      if (response.threadId && !currentThreadId) {
        setCurrentThreadId(response.threadId)
      }

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
        case 'add_label':
          if (pendingEmailAction.labelName) {
            await modifyEmailLabel(
              selectedAccount,
              selectedEmailId,
              { labelName: pendingEmailAction.labelName, action: 'apply' },
              authConfig,
              apiBase
            )
          }
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

  // Conversation persistence & privacy state (Sprint 2)
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(null)
  const [privacyStatus, setPrivacyStatus] = useState<EmailPrivacyStatus | null>(null)
  const [conversationLoading, setConversationLoading] = useState(false)
  const [privacyOverrideGranted, setPrivacyOverrideGranted] = useState(false)
  const [toastMessage, setToastMessage] = useState<{ text: string; type: 'info' | 'warning' | 'error' } | null>(null)

  // Task creation state (Phase B)
  const [showTaskForm, setShowTaskForm] = useState(false)
  const [_taskPreview, setTaskPreview] = useState<TaskPreview | null>(null)
  void _taskPreview // Reserved for future use
  const [taskFormData, setTaskFormData] = useState({
    title: '',
    // Three-date model
    plannedDate: '',
    targetDate: '',
    hardDeadline: '',
    // Core fields
    status: 'scheduled',
    priority: 'Standard',
    domain: 'personal',
    project: '',
    notes: '',
    estimatedHours: '',
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

  // Auto-dismiss toast messages after 5 seconds
  useEffect(() => {
    if (toastMessage) {
      const timer = setTimeout(() => setToastMessage(null), 5000)
      return () => clearTimeout(timer)
    }
  }, [toastMessage])

  // Handle quick action on email
  async function handleEmailQuickAction(action: EmailQuickAction) {
    setActionLoading(action.type)
    setError(null)
    
    try {
      switch (action.type) {
        case 'archive': {
          // Find next email BEFORE removing from list
          const nextEmailAfterArchive = getNextEmailId(action.emailId)
          await archiveEmail(selectedAccount, action.emailId, authConfig, apiBase)
          // Remove from recent messages in cache
          updateCache({
            inbox: inboxSummary ? {
              ...inboxSummary,
              recentMessages: inboxSummary.recentMessages.filter(m => m.id !== action.emailId)
            } : null
          })
          // Also remove from search results if present
          if (emailSearchResults) {
            setEmailSearchResults(emailSearchResults.filter(m => m.id !== action.emailId))
          }
          setSelectedEmailId(nextEmailAfterArchive)
          break
        }

        case 'delete': {
          // Find next email BEFORE removing from list
          const nextEmailAfterDelete = getNextEmailId(action.emailId)
          await deleteEmail(selectedAccount, action.emailId, authConfig, apiBase)
          // Remove from recent messages in cache
          updateCache({
            inbox: inboxSummary ? {
              ...inboxSummary,
              recentMessages: inboxSummary.recentMessages.filter(m => m.id !== action.emailId)
            } : null
          })
          // Also remove from search results if present
          if (emailSearchResults) {
            setEmailSearchResults(emailSearchResults.filter(m => m.id !== action.emailId))
          }
          setSelectedEmailId(nextEmailAfterDelete)
          break
        }
          
        case 'star': {
          const starResult = await starEmail(selectedAccount, action.emailId, true, authConfig, apiBase)
          // Check for stale email (deleted/trashed)
          if (starResult.stale) {
            setToastMessage({ text: starResult.staleMessage || 'Email has been deleted or moved to trash', type: 'warning' })
            // Dismiss and remove from local cache
            try { await dismissAttentionItem(selectedAccount, action.emailId, 'handled', authConfig, apiBase) } catch { /* ignore */ }
            updateCache({ attentionItems: attentionItems.filter(item => item.emailId !== action.emailId) })
            setSelectedEmailId(null)
            break
          }
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
        }

        case 'flag': {
          const flagResult = await markEmailImportant(selectedAccount, action.emailId, true, authConfig, apiBase)
          // Check for stale email (deleted/trashed)
          if (flagResult.stale) {
            setToastMessage({ text: flagResult.staleMessage || 'Email has been deleted or moved to trash', type: 'warning' })
            // Dismiss and remove from local cache
            try { await dismissAttentionItem(selectedAccount, action.emailId, 'handled', authConfig, apiBase) } catch { /* ignore */ }
            updateCache({ attentionItems: attentionItems.filter(item => item.emailId !== action.emailId) })
            setSelectedEmailId(null)
            break
          }
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
        }

        case 'read': {
          const readResult = await markEmailRead(selectedAccount, action.emailId, action.markAsRead, authConfig, apiBase)
          // Check for stale email (deleted/trashed)
          if (readResult.stale) {
            setToastMessage({ text: readResult.staleMessage || 'Email has been deleted or moved to trash', type: 'warning' })
            // Dismiss and remove from local cache
            try { await dismissAttentionItem(selectedAccount, action.emailId, 'handled', authConfig, apiBase) } catch { /* ignore */ }
            updateCache({ attentionItems: attentionItems.filter(item => item.emailId !== action.emailId) })
            setSelectedEmailId(null)
            break
          }
          // Update the message in cache
          updateCache({
            inbox: inboxSummary ? {
              ...inboxSummary,
              totalUnread: inboxSummary.totalUnread + (action.markAsRead ? -1 : 1),
              recentMessages: inboxSummary.recentMessages.map(m =>
                m.id === action.emailId
                  ? { ...m, isUnread: !action.markAsRead }
                  : m
              )
            } : null
          })
          // Also update fetchedEmail if it's the currently viewed email
          if (fetchedEmail?.id === action.emailId) {
            setFetchedEmail({ ...fetchedEmail, isUnread: !action.markAsRead })
          }
          break
        }

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

  // Handle panel divider drag
  function handlePanelDrag(delta: number) {
    if (!panelsContainerRef.current) return
    const containerWidth = panelsContainerRef.current.offsetWidth
    const deltaPercent = (delta / containerWidth) * 100
    setPanelSplitRatio(prev => Math.max(20, Math.min(80, prev + deltaPercent)))
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

  // Get selected email details (check search results, recent messages, and fetched email)
  const selectedEmail = selectedEmailId
    ? (emailSearchResults?.find(m => m.id === selectedEmailId)
       ?? inboxSummary?.recentMessages?.find(m => m.id === selectedEmailId)
       ?? (fetchedEmail?.id === selectedEmailId ? fetchedEmail : null))
    : null

  // Check if selected email is an attention item (for showing dismiss button)
  const isSelectedEmailAttentionItem = selectedEmailId
    ? attentionItems.some(item => item.emailId === selectedEmailId)
    : false

  // Check if selected email is pinned (for pin button state)
  const isSelectedEmailPinned = selectedEmailId
    ? pinnedEmails.some(p => p.emailId === selectedEmailId)
    : false

  // Toggle pin state for current email
  const handleTogglePin = async () => {
    if (!selectedEmailId || !selectedEmail) return
    try {
      if (isSelectedEmailPinned) {
        await unpinEmail(selectedAccount, selectedEmailId, authConfig, apiBase)
        updateCache({
          pinnedEmails: pinnedEmails.filter(p => p.emailId !== selectedEmailId)
        })
      } else {
        await pinEmail(
          selectedAccount,
          selectedEmailId,
          selectedEmail.subject,
          selectedEmail.fromAddress,
          selectedEmail.snippet,
          selectedEmail.threadId,
          authConfig,
          apiBase
        )
        loadPinnedEmails()  // Refresh to get server timestamp
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Pin operation failed')
    }
  }

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

      {/* Toast notifications */}
      {toastMessage && (
        <div className={`email-toast ${toastMessage.type}`}>
          <span>{toastMessage.text}</span>
          <button onClick={() => setToastMessage(null)} style={{ marginLeft: '12px' }}>×</button>
        </div>
      )}

      {/* Two-panel content area */}
      <div className="email-panels" ref={panelsContainerRef}>
        {/* Left Panel - Email List/Rules */}
        {!emailPanelCollapsed && (
          <section
            className="email-left-panel"
            style={{ width: assistPanelCollapsed ? '100%' : `${panelSplitRatio}%` }}
          >
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
                onClick={() => setActiveTab('newRules')}
              >
                New Rules {suggestions.length > 0 && `(${suggestions.length})`}
              </button>
              <button
                className={activeTab === 'suggestions' ? 'active' : ''}
                onClick={() => setActiveTab('suggestions')}
              >
                Suggestions {actionSuggestions.length > 0 && `(${actionSuggestions.length})`}
              </button>
              <button
                className={activeTab === 'attention' ? 'active' : ''}
                onClick={() => {
                  setActiveTab('attention')
                  // Only load persisted items, don't auto-analyze
                  // User should click "Analyze Inbox" on Dashboard to refresh
                  if (attentionItems.length === 0) loadPersistedAttention()
                }}
              >
                Attention {attentionItems.length > 0 && `(${attentionItems.length})`}
              </button>
              <button
                className={activeTab === 'pinned' ? 'active' : ''}
                onClick={() => {
                  setActiveTab('pinned')
                  if (pinnedEmails.length === 0) loadPinnedEmails()
                }}
              >
                Pinned {pinnedEmails.length > 0 && `(${pinnedEmails.length})`}
              </button>
              <button
                className={activeTab === 'settings' ? 'active' : ''}
                onClick={() => setActiveTab('settings')}
              >
                Settings
              </button>
            </nav>

      {/* Tab content */}
      <div className="email-tab-content">
        {/* Dashboard Tab */}
        {activeTab === 'dashboard' && (
          <div className="dashboard-view">
            <div className="stats-grid">
              <div className="stat-card clickable" onClick={() => setActiveTab('dashboard')} title="View Dashboard">
                <div className="stat-value">{inboxSummary?.totalUnread?.toLocaleString() ?? '—'}</div>
                <div className="stat-label">Unread</div>
              </div>
              <div className="stat-card clickable" onClick={() => setActiveTab('rules')} title="View Active Rules">
                <div className="stat-value">{rules.length}</div>
                <div className="stat-label">Active Rules</div>
              </div>
              <div className="stat-card important clickable" onClick={() => setActiveTab('suggestions')} title="View Suggestions">
                <div className="stat-value">{actionSuggestions.length || '—'}</div>
                <div className="stat-label">Suggestions</div>
              </div>
              <div className="stat-card warning clickable" onClick={() => setActiveTab('attention')} title="View Attention Items">
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
                        onClick={() => handleSelectEmail(msg.id, msg.threadId)}
                      >
                      {emailTaskLinks[msg.id] ? (
                          <button
                            className="msg-task-btn task-exists"
                            onClick={(e) => {
                              e.stopPropagation()
                              // Could navigate to task in future
                            }}
                            title={`Task: ${emailTaskLinks[msg.id].title}`}
                          >
                            <span className="task-exists-icon">📋</span>
                            <span className={`task-status-badge mini ${emailTaskLinks[msg.id].status}`}>
                              {emailTaskLinks[msg.id].status}
                            </span>
                          </button>
                        ) : (
                          <button
                            className="msg-task-btn"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleSelectEmail(msg.id, msg.threadId)
                              handleOpenTaskForm(msg.id)
                            }}
                            title="Create task from this email"
                          >
                            📋
                          </button>
                        )}
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
                  {inboxSummary.recentMessages.map(msg => (
                    <li
                      key={msg.id}
                      className={`${msg.isUnread ? 'unread' : ''} ${selectedEmailId === msg.id ? 'selected' : ''}`}
                      onClick={() => handleSelectEmail(msg.id, msg.threadId)}
                    >
                      {emailTaskLinks[msg.id] ? (
                        <button
                          className="msg-task-btn task-exists"
                          onClick={(e) => {
                            e.stopPropagation()
                            // Could navigate to task in future
                          }}
                          title={`Task: ${emailTaskLinks[msg.id].title}`}
                        >
                          <span className="task-exists-icon">📋</span>
                          <span className={`task-status-badge mini ${emailTaskLinks[msg.id].status}`}>
                            {emailTaskLinks[msg.id].status}
                          </span>
                        </button>
                      ) : (
                        <button
                          className="msg-task-btn"
                          onClick={(e) => {
                            e.stopPropagation()
                            handleSelectEmail(msg.id, msg.threadId)
                            handleOpenTaskForm(msg.id)
                          }}
                          title="Create task from this email"
                        >
                          📋
                        </button>
                      )}
                        <div className="msg-from">{msg.fromName || msg.fromAddress}</div>
                      <div className="msg-subject">
                        {msg.subject}
                        {threadCounts[msg.threadId] > 1 && (
                          <span className="thread-count-badge" title={`${threadCounts[msg.threadId]} emails in this thread`}>
                            {threadCounts[msg.threadId]} in thread
                          </span>
                        )}
                      </div>
                      <div className="msg-snippet">{msg.snippet}</div>
                    </li>
                  ))}
                </ul>
                {/* Load More button for pagination */}
                {inboxSummary.nextPageToken && (
                  <button
                    className="load-more-btn"
                    onClick={loadMoreEmails}
                    disabled={loadingMore}
                  >
                    {loadingMore ? 'Loading...' : 'Load More'}
                  </button>
                )}
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
                      
                      {/* Quick actions - Standardized Order: Read, Star, Important, Archive, Delete */}
                      <button
                        className="quick-action"
                        onClick={() => handleSuggestionQuickAction(suggestion, 'read')}
                        disabled={actionLoading !== null}
                        title="Mark as Read"
                      >
                        📬
                      </button>
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
            {/* Attention header with sync timestamp */}
            <div className="attention-view-header">
              {lastAttentionSync && (
                <span className="last-sync" title={lastAttentionSync.toLocaleString()}>
                  Last synced: {lastAttentionSync.toLocaleTimeString()}
                </span>
              )}
            </div>
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
                    onClick={() => handleSelectEmail(item.emailId, item.threadId)}
                  >
                    <div className="attention-header">
                      <span className={`urgency-badge ${item.urgency}`}>
                        {item.urgency}
                      </span>
                      {/* Analysis engine badge - shows AI for Haiku, Regex for others */}
                      <span className={`analysis-engine-badge ${item.analysisMethod === 'haiku' ? 'ai' : 'regex'}`}
                        title={`Analyzed by ${item.analysisMethod === 'haiku' ? 'Haiku AI' : 'pattern matching'} (${Math.round(item.confidence * 100)}% confidence)`}>
                        {item.analysisMethod === 'haiku' ? 'AI' : 'Regex'}
                      </span>
                      {/* Profile-aware role badge */}
                      {item.matchedRole && (
                        <span className={`role-badge ${item.analysisMethod}`} title={`Matched: ${item.matchedRole}`}>
                          {item.matchedRole}
                        </span>
                      )}
                      {/* Show custom labels (filter out system labels, display name not ID) */}
                      {item.labels?.filter(l =>
                        !['INBOX', 'UNREAD', 'SENT', 'DRAFT', 'SPAM', 'TRASH', 'STARRED', 'IMPORTANT', 'CATEGORY_PERSONAL', 'CATEGORY_SOCIAL', 'CATEGORY_PROMOTIONS', 'CATEGORY_UPDATES', 'CATEGORY_FORUMS'].includes(l)
                      ).map(labelId => {
                        // Look up label name from availableLabels
                        const labelInfo = availableLabels.find(l => l.id === labelId)
                        // Use name if found, otherwise show cleaned ID (remove "Label_" prefix)
                        const displayName = labelInfo?.name ||
                          (labelId.startsWith('Label_') ? `#${labelId.slice(6)}` : labelId)
                        return (
                          <span key={labelId} className="email-label-badge" title={labelInfo?.name || labelId}>
                            {displayName}
                          </span>
                        )
                      })}
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
                    {/* Compact action row: Dismiss, Snooze, and Task badge/button */}
                    <div className="attention-actions">
                      <div className="dismiss-dropdown">
                        <button
                          className="dismiss-btn"
                          onClick={(e) => {
                            e.stopPropagation()
                            const dropdown = e.currentTarget.nextElementSibling as HTMLElement
                            if (dropdown) dropdown.classList.toggle('show')
                          }}
                        >
                          Dismiss ▼
                        </button>
                        <div className="dismiss-menu">
                          <button onClick={(e) => {
                            e.stopPropagation()
                            handleDismiss(item.emailId, 'handled')
                          }}>✓ Already handled</button>
                          <button onClick={(e) => {
                            e.stopPropagation()
                            handleDismiss(item.emailId, 'not_actionable')
                          }}>✗ Not actionable</button>
                          <button onClick={(e) => {
                            e.stopPropagation()
                            handleDismiss(item.emailId, 'false_positive')
                          }}>⚠ False positive</button>
                        </div>
                      </div>
                      <div className="snooze-dropdown">
                        <button
                          className="snooze-btn"
                          onClick={(e) => {
                            e.stopPropagation()
                            const dropdown = e.currentTarget.nextElementSibling as HTMLElement
                            if (dropdown) dropdown.classList.toggle('show')
                          }}
                        >
                          Snooze ▼
                        </button>
                        <div className="snooze-menu">
                          <button onClick={(e) => {
                            e.stopPropagation()
                            handleSnooze(item.emailId, 1)
                          }}>1 hour</button>
                          <button onClick={(e) => {
                            e.stopPropagation()
                            handleSnooze(item.emailId, 4)
                          }}>4 hours</button>
                          <button onClick={(e) => {
                            e.stopPropagation()
                            handleSnooze(item.emailId, 24)
                          }}>Tomorrow</button>
                          <button onClick={(e) => {
                            e.stopPropagation()
                            handleSnooze(item.emailId, 168)
                          }}>Next week</button>
                        </div>
                      </div>
                      {/* Task badge/button inline with actions */}
                      {item.extractedTask && (
                        emailTaskLinks[item.emailId] ? (
                          <button
                            className="task-exists-btn compact"
                            onClick={(e) => {
                              e.stopPropagation()
                              onBack()
                            }}
                            title={`View task: ${emailTaskLinks[item.emailId].title}`}
                          >
                            <span className="task-exists-icon">📋</span>
                            <span className={`task-status-badge ${emailTaskLinks[item.emailId].status}`}>
                              {emailTaskLinks[item.emailId].status}
                            </span>
                          </button>
                        ) : (
                          <button
                            className="create-task-btn compact"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleEmailQuickAction({
                                type: 'create_task',
                                emailId: item.emailId,
                                subject: item.extractedTask || item.subject
                              })
                            }}
                            title={`Create task: ${item.extractedTask}`}
                          >
                            + Task
                          </button>
                        )
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Pinned Tab */}
        {activeTab === 'pinned' && (
          <div className="pinned-emails-section">
            <h3>Pinned Emails</h3>
            {loadingPinned ? (
              <div className="loading">Loading pinned emails...</div>
            ) : pinnedEmails.length === 0 ? (
              <div className="empty-state">
                <p>No pinned emails.</p>
                <p className="hint">Click {"\u{1F4CC}"} on any email to pin it for quick reference.</p>
              </div>
            ) : (
              <div className="pinned-list">
                {pinnedEmails.map(pinned => (
                  <div
                    key={pinned.emailId}
                    className={`pinned-item ${selectedEmailId === pinned.emailId ? 'selected' : ''}`}
                    onClick={() => handleSelectEmail(pinned.emailId, pinned.threadId)}
                    style={{
                      padding: '12px',
                      borderBottom: '1px solid rgba(255,255,255,0.1)',
                      cursor: 'pointer',
                    }}
                  >
                    <div className="pinned-from" style={{ fontWeight: 'bold', marginBottom: '4px' }}>
                      {pinned.fromAddress}
                    </div>
                    <div className="pinned-subject" style={{ marginBottom: '4px' }}>
                      {pinned.subject}
                    </div>
                    <div className="pinned-snippet" style={{ fontSize: '12px', opacity: 0.7, marginBottom: '4px' }}>
                      {pinned.snippet}
                    </div>
                    <div className="pinned-date" style={{ fontSize: '10px', opacity: 0.5 }}>
                      Pinned {new Date(pinned.pinnedAt).toLocaleDateString()}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Settings Tab */}
        {activeTab === 'settings' && (
          <div className="settings-view">
            {/* Last Analysis Section */}
            <div className="settings-section">
              <h3>Last Analysis Results</h3>
              <div className="last-analysis-grid">
                {(['personal', 'church'] as const).map(account => {
                  const analysis = cache[account].lastAnalysis
                  return (
                    <div key={account} className="analysis-card">
                      <h4>{account.charAt(0).toUpperCase() + account.slice(1)} Account</h4>
                      {analysis ? (
                        <div className="analysis-details">
                          <div className="analysis-timestamp">
                            {new Date(analysis.timestamp).toLocaleString()}
                          </div>
                          <table className="analysis-table">
                            <tbody>
                              <tr>
                                <td>Emails Fetched</td>
                                <td className="value">{analysis.emailsFetched}</td>
                              </tr>
                              <tr>
                                <td>Already Tracked</td>
                                <td className="value">{analysis.alreadyTracked}</td>
                              </tr>
                              <tr>
                                <td>Dismissed (not actionable)</td>
                                <td className="value">{analysis.dismissed}</td>
                              </tr>
                              <tr>
                                <td>Analyzed by Haiku</td>
                                <td className="value">{analysis.haikuAnalyzed}</td>
                              </tr>
                              <tr className="highlight">
                                <td>Suggestions Generated</td>
                                <td className="value">{analysis.suggestionsGenerated}</td>
                              </tr>
                              <tr className="highlight">
                                <td>Rules Generated</td>
                                <td className="value">{analysis.rulesGenerated}</td>
                              </tr>
                              <tr className="highlight">
                                <td>Attention Items</td>
                                <td className="value">{analysis.attentionItems}</td>
                              </tr>
                            </tbody>
                          </table>
                          {analysis.haikuRemaining && (
                            <div className="haiku-remaining">
                              Haiku Remaining: {analysis.haikuRemaining.daily}/day, {analysis.haikuRemaining.weekly}/week
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="no-analysis">
                          No analysis run yet
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>

            <HaikuSettingsPanel authConfig={authConfig} apiBase={apiBase} />
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

        {/* Draggable divider between panels */}
        {!emailPanelCollapsed && !assistPanelCollapsed && (
          <PanelDivider
            onDrag={handlePanelDrag}
            onCollapseLeft={handleToggleEmailPanel}
            onCollapseRight={handleToggleAssistPanel}
            leftCollapsed={emailPanelCollapsed}
            rightCollapsed={assistPanelCollapsed}
          />
        )}

        {/* Right Panel - DATA Assist (placeholder until Phase 4) */}
        {!assistPanelCollapsed && (
          <section
            className="email-right-panel"
            style={{ width: emailPanelCollapsed ? '100%' : `${100 - panelSplitRatio}%` }}
          >
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
                  <div className="preview-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <strong>{selectedEmail.fromName || selectedEmail.fromAddress}</strong>
                      <span className="preview-date" style={{ marginLeft: '12px' }}>
                        {selectedEmail.date ? new Date(selectedEmail.date).toLocaleString() : ''}
                      </span>
                    </div>
                    <div style={{ display: 'flex', gap: '4px', flexShrink: 0, marginLeft: '8px' }}>
                      {/* Minimize button */}
                      <button
                        onClick={() => setEmailPreviewCollapsed(!emailPreviewCollapsed)}
                        style={{
                          background: 'transparent',
                          border: '1px solid rgba(255,255,255,0.2)',
                          borderRadius: '4px',
                          padding: '2px 6px',
                          cursor: 'pointer',
                          color: 'inherit',
                          fontSize: '10px',
                          lineHeight: 1,
                        }}
                        title={emailPreviewCollapsed ? 'Expand details' : 'Collapse details'}
                      >
                        {emailPreviewCollapsed ? '▼' : '▲'}
                      </button>

                      {/* Dismiss button (only for attention items) */}
                      {isSelectedEmailAttentionItem && (
                        <div style={{ position: 'relative' }}>
                          <button
                            onClick={() => setShowDismissMenu(!showDismissMenu)}
                            style={{
                              background: 'transparent',
                              border: '1px solid rgba(255,255,255,0.2)',
                              borderRadius: '4px',
                              padding: '2px 6px',
                              cursor: 'pointer',
                              color: 'inherit',
                              fontSize: '14px',
                              lineHeight: 1,
                            }}
                            title="Dismiss from attention"
                          >
                            ✔
                          </button>
                          {showDismissMenu && (
                            <div style={{
                              position: 'absolute',
                              top: '100%',
                              right: 0,
                              marginTop: '4px',
                              background: '#1a1a2e',
                              border: '1px solid rgba(255,255,255,0.2)',
                              borderRadius: '4px',
                              zIndex: 100,
                              minWidth: '140px',
                            }}>
                              <button
                                onClick={() => handleDismissFromPanel('handled')}
                                style={{
                                  display: 'block',
                                  width: '100%',
                                  padding: '8px 12px',
                                  background: 'transparent',
                                  border: 'none',
                                  color: 'inherit',
                                  textAlign: 'left',
                                  cursor: 'pointer',
                                  fontSize: '12px',
                                }}
                                onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.1)'}
                                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                              >
                                Already handled
                              </button>
                              <button
                                onClick={() => handleDismissFromPanel('not_actionable')}
                                style={{
                                  display: 'block',
                                  width: '100%',
                                  padding: '8px 12px',
                                  background: 'transparent',
                                  border: 'none',
                                  color: 'inherit',
                                  textAlign: 'left',
                                  cursor: 'pointer',
                                  fontSize: '12px',
                                }}
                                onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.1)'}
                                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                              >
                                Not actionable
                              </button>
                              <button
                                onClick={() => handleDismissFromPanel('false_positive')}
                                style={{
                                  display: 'block',
                                  width: '100%',
                                  padding: '8px 12px',
                                  background: 'transparent',
                                  border: 'none',
                                  color: 'inherit',
                                  textAlign: 'left',
                                  cursor: 'pointer',
                                  fontSize: '12px',
                                }}
                                onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.1)'}
                                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                              >
                                False positive
                              </button>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Pin button */}
                      <button
                        onClick={handleTogglePin}
                        style={{
                          background: isSelectedEmailPinned ? 'rgba(255,200,0,0.2)' : 'transparent',
                          border: '1px solid rgba(255,255,255,0.2)',
                          borderRadius: '4px',
                          padding: '2px 6px',
                          cursor: 'pointer',
                          color: isSelectedEmailPinned ? '#ffc800' : 'inherit',
                          fontSize: '10px',
                          lineHeight: 1,
                        }}
                        title={isSelectedEmailPinned ? 'Unpin email' : 'Pin email'}
                      >
                        {"\u{1F4CC}"}
                      </button>

                      {/* Close button */}
                      <button
                        onClick={handleCloseEmailPanel}
                        style={{
                          background: 'transparent',
                          border: '1px solid rgba(255,255,255,0.2)',
                          borderRadius: '4px',
                          padding: '2px 6px',
                          cursor: 'pointer',
                          color: 'inherit',
                          fontSize: '10px',
                          lineHeight: 1,
                        }}
                        title="Close email panel"
                      >
                        ✕
                      </button>
                    </div>
                  </div>

                  {/* Collapsible content - hidden when minimized */}
                  {!emailPreviewCollapsed && (
                    <>
                      <div className="preview-subject">{selectedEmail.subject}</div>

                      {/* Privacy indicator and override button */}
                  {privacyStatus && !privacyStatus.canSeeBody && (
                    <div className="privacy-indicator">
                      <span className="privacy-badge blocked" title={privacyStatus.blockedReasonDisplay || 'DATA cannot see email body'}>
                        🔒 {privacyStatus.blockedReasonDisplay || 'Privacy Protected'}
                      </span>
                      {!privacyOverrideGranted ? (
                        <button
                          className="share-with-data-btn"
                          onClick={() => setPrivacyOverrideGranted(true)}
                          title="Allow DATA to see the email body for this conversation"
                        >
                          Share with DATA
                        </button>
                      ) : (
                        <span className="privacy-badge override" title="DATA can now see the email body">
                          ✓ Shared
                        </span>
                      )}
                    </div>
                  )}

                  {/* Show "Sender Blocked" + "Shared" badges for previously shared emails from blocked senders */}
                  {privacyStatus && privacyStatus.canSeeBody && privacyStatus.overrideGranted && (
                    <div className="privacy-indicator">
                      <span className="privacy-badge blocked" title="Sender is on your blocklist">
                        🔒 Sender Blocked
                      </span>
                      <span className="privacy-badge override" title="You previously shared this email with DATA">
                        ✓ Shared
                      </span>
                    </div>
                  )}

                  {/* Conversation loading indicator */}
                  {conversationLoading && (
                    <div className="conversation-loading">Loading conversation...</div>
                  )}

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
                  
                  {/* Quick action buttons - Standardized Order: Read, Reply All, Star, Important, Archive, Delete */}
                  <div className="email-quick-actions">
                    <button
                      className="quick-action-btn"
                      onClick={() => handleEmailQuickAction({
                        type: 'read',
                        emailId: selectedEmail.id,
                        markAsRead: selectedEmail.isUnread
                      })}
                      disabled={actionLoading !== null}
                      title={selectedEmail.isUnread ? "Mark as Read" : "Mark as Unread"}
                    >
                      {actionLoading === 'read' ? '⏳' : (selectedEmail.isUnread ? '📬' : '📭')}
                    </button>
                    <button
                      className="quick-action-btn reply-all"
                      onClick={() => handleReply(true)}
                      disabled={actionLoading !== null || generatingReply}
                      title="Reply All"
                    >
                      {generatingReply ? '⏳' : '↩️'}
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
                      className="quick-action-btn"
                      onClick={() => handleEmailQuickAction({ type: 'archive', emailId: selectedEmail.id })}
                      disabled={actionLoading !== null}
                      title="Archive"
                    >
                      {actionLoading === 'archive' ? '⏳' : '📥'}
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
                    </>
                  )}
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
                      
                      {/* Status and Priority row */}
                      <div className="task-form-row">
                        <div className="task-form-field">
                          <label>Status</label>
                          <select
                            value={taskFormData.status}
                            onChange={(e) => setTaskFormData(prev => ({ ...prev, status: e.target.value }))}
                          >
                            <option value="scheduled">Scheduled</option>
                            <option value="in_progress">In Progress</option>
                            <option value="on_hold">On Hold</option>
                            <option value="blocked">Blocked</option>
                            <option value="awaiting_reply">Awaiting Reply</option>
                            <option value="follow_up">Follow-up</option>
                          </select>
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
                      
                      {/* Three-date model row */}
                      <div className="task-form-row task-form-dates">
                        <div className="task-form-field">
                          <label>Planned Date</label>
                          <input
                            type="date"
                            value={taskFormData.plannedDate}
                            onChange={(e) => setTaskFormData(prev => ({ ...prev, plannedDate: e.target.value }))}
                            title="When to work on it"
                          />
                        </div>
                        
                        <div className="task-form-field">
                          <label>Target Date</label>
                          <input
                            type="date"
                            value={taskFormData.targetDate}
                            onChange={(e) => setTaskFormData(prev => ({ ...prev, targetDate: e.target.value }))}
                            title="Original goal date"
                          />
                        </div>
                        
                        <div className="task-form-field">
                          <label>Hard Deadline</label>
                          <input
                            type="date"
                            value={taskFormData.hardDeadline}
                            onChange={(e) => setTaskFormData(prev => ({ ...prev, hardDeadline: e.target.value }))}
                            title="External commitment date"
                          />
                        </div>
                      </div>
                      
                      {/* Domain and Project row */}
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
                        
                        <div className="task-form-field task-form-field-small">
                          <label>Est. Hours</label>
                          <select
                            value={taskFormData.estimatedHours}
                            onChange={(e) => setTaskFormData(prev => ({ ...prev, estimatedHours: e.target.value }))}
                          >
                            <option value="">-</option>
                            <option value="0.25">0.25</option>
                            <option value="0.5">0.5</option>
                            <option value="1">1</option>
                            <option value="2">2</option>
                            <option value="4">4</option>
                            <option value="8">8</option>
                          </select>
                        </div>
                      </div>
                      
                      <div className="task-form-field">
                        <label>Notes</label>
                        <textarea
                          value={taskFormData.notes}
                          onChange={(e) => setTaskFormData(prev => ({ ...prev, notes: e.target.value }))}
                          placeholder="Optional notes (email source details will be added automatically)"
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
                        <button
                          className="chat-message-delete"
                          onClick={() => setChatHistory(prev => prev.filter((_, i) => i !== idx))}
                          title="Delete message"
                        >
                          ✕
                        </button>
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

