export type DataSource = 'auto' | 'live' | 'stub'

export interface Task {
  rowId: string
  title: string
  status: string
  due: string
  priority: string
  project: string
  assignedTo?: string | null
  estimatedHours?: number | null
  notes?: string | null
  nextStep: string
  automationHint: string
  source: 'personal' | 'work'
  done: boolean
}

export interface TaskResponse {
  tasks: Task[]
  liveTasks: boolean
  environment: string
  warning?: string | null
}

export interface AssistPlan {
  summary: string
  score: number
  labels: string[]
  automationTriggers: string[]
  nextSteps: string[]
  efficiencyTips: string[]
  suggestedActions: string[]
  task: Task
  generator: string
  generatorNotes: string[]
  messageId?: string | null
  commentPosted?: boolean
  warnings?: string[]
  generatedAt?: string | null  // ISO timestamp when plan was generated
}

export interface ConversationMessage {
  role: 'user' | 'assistant'
  content: string
  ts: string
  metadata?: Record<string, unknown>
  plan?: {
    summary: string
    next_steps: string[]
    efficiency_tips: string[]
    suggested_actions: string[]
    labels?: string[]
  }
  struck?: boolean
  struckAt?: string
}

export interface AssistResponse {
  plan: AssistPlan | null
  environment: string
  liveTasks: boolean
  warning?: string | null
  history?: ConversationMessage[]
}

export interface ActivityEntry {
  ts: string
  task_id: string
  task_title: string
  project?: string
  account?: string
  recipient?: string
  message_id?: string
  anthropic_model?: string
  generator?: string
  source?: string
}

export interface WorkBadge {
  needsAttention: number
  overdue: number
  dueToday: number
  total: number
}

// Email Management types
export type EmailAccount = 'church' | 'personal'

export interface FilterRule {
  emailAccount: string
  order: number
  category: string
  field: string
  operator: string
  value: string
  action: string
  rowNumber?: number
}

export interface RuleSuggestion {
  type: 'new_label' | 'deletion' | 'attention'
  suggestedRule: FilterRule
  confidence: 'high' | 'medium' | 'low'
  reason: string
  examples: string[]
  emailCount: number
  ruleId?: string  // Set when loaded from persistence
}

export interface AttentionItem {
  emailId: string
  subject: string
  fromAddress: string
  fromName: string
  date: string
  reason: string
  urgency: 'high' | 'medium' | 'low'
  suggestedAction?: string
  extractedDeadline?: string
  extractedTask?: string
  labels?: string[]
  // Profile-aware analysis fields (Sprint 3)
  matchedRole?: string  // Role/context that triggered (e.g., "Treasurer", "VIP")
  confidence: number  // 0.0-1.0 confidence score
  analysisMethod: 'regex' | 'profile' | 'vip' | 'haiku'  // How item was detected (haiku = AI, others = rule-based)
  // Status fields for dismiss/snooze (Sprint 4)
  status?: 'active' | 'dismissed' | 'snoozed'
  snoozedUntil?: string
}

export interface AttachmentInfo {
  filename: string
  mimeType: string
  size: number
  attachmentId?: string
}

export interface EmailMessage {
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
  labels: string[]
  // Full body fields (populated when requesting full message)
  body?: string
  bodyHtml?: string
  ccAddress?: string
  messageIdHeader?: string
  references?: string
  attachmentCount?: number
  attachments?: AttachmentInfo[]
}

export interface InboxSummary {
  account: string
  email: string
  totalUnread: number
  unreadImportant: number
  unreadFromVips: number
  recentMessages: EmailMessage[]
  vipMessages: EmailMessage[]
  nextPageToken?: string | null  // For "Load More" pagination
}

export interface FilterRulesResponse {
  account: string
  email: string
  ruleCount: number
  rules: FilterRule[]
}

export interface AnalyzeInboxResponse {
  account: string
  email: string
  // Analysis breakdown for auditing
  emailsFetched: number
  emailsDismissed: number
  emailsAlreadyTracked: number
  messagesAnalyzed: number
  existingRulesCount: number
  suggestions: RuleSuggestion[]
  actionSuggestions?: unknown[]  // Action suggestions for Suggestions tab (typed in api.ts)
  attentionItems: AttentionItem[]
  haikuAnalyzed?: number  // Count of emails analyzed by Haiku
  haikuUsage?: HaikuUsage  // Current Haiku usage stats
}

// Haiku usage tracking
export interface HaikuUsage {
  dailyCount: number
  weeklyCount: number
  dailyLimit: number
  weeklyLimit: number
  dailyRemaining: number
  weeklyRemaining: number
  enabled: boolean
  canAnalyze: boolean
}

// App mode for navigation
export type AppMode = 'tasks' | 'email' | 'calendar'

// User Profile types (for email management intelligence)
export interface UserProfile {
  userId: string
  churchRoles: string[]
  personalContexts: string[]
  vipSenders: Record<string, string[]>
  churchAttentionPatterns: Record<string, string[]>
  personalAttentionPatterns: Record<string, string[]>
  notActionablePatterns: Record<string, string[]>
  version: string
  createdAt: string
  updatedAt: string
}

// Firestore Task (created from emails or direct creation)
export interface FirestoreTask {
  id: string
  title: string
  status: string
  priority: string
  domain: string
  createdAt: string
  updatedAt: string
  // Three-date model (from migration plan)
  plannedDate: string | null  // When to work on it (auto-rolls)
  targetDate: string | null   // Original goal (never changes)
  hardDeadline: string | null // External commitment
  timesRescheduled: number    // Slippage counter
  dueDate: string | null      // Legacy - use plannedDate
  effectiveDueDate: string | null  // Computed: plannedDate || dueDate
  // Core fields
  project: string | null
  number: number | null       // Daily ordering
  notes: string | null
  nextStep: string | null
  estimatedHours: number | null
  assignedTo: string | null
  contactRequired: boolean
  done: boolean
  completedOn: string | null
  // Recurring
  isRecurring: boolean
  recurringType: string | null
  recurringDays: string[] | null
  recurringMonthly: string | null
  recurringInterval: number | null
  // Status helpers
  isOverdue: boolean
  daysUntilDeadline: number | null
  // Source tracking
  source: string
  sourceEmailId: string | null
  sourceEmailAccount: string | null
  sourceEmailSubject: string | null
  // Sync tracking
  smartsheetRowId: string | null
  smartsheetSheet: string | null
  syncStatus: string
  lastSyncedAt: string | null
  attentionReason: string | null
}

// Email Reply Types
export interface EmailReplyDraft {
  subject: string
  body: string
  bodyHtml?: string
  to: string[]
  cc: string[]
}

export interface ReplyDraftRequest {
  messageId: string
  replyAll: boolean
  userContext?: string
}

export interface ReplySendRequest {
  messageId: string
  replyAll: boolean
  subject: string
  body: string
  cc?: string[]
}

export interface ThreadContextMessage {
  id: string
  threadId: string
  fromAddress: string
  fromName: string
  subject: string
  snippet: string
  date: string
  body?: string
  bodyHtml?: string
}

export interface ThreadContext {
  threadId: string
  messageCount: number
  summary?: string
  messages: ThreadContextMessage[]
}

// Suggestion Tracking Types (Sprint 5)
export type SuggestionStatus = 'pending' | 'approved' | 'rejected' | 'expired'
export type SuggestionAction = 'archive' | 'label' | 'delete' | 'star' | 'create_task' | 'mark_important'
export type AnalysisMethod = 'regex' | 'haiku' | 'profile_match'

export interface PersistentSuggestion {
  suggestionId: string
  emailId: string
  emailAccount: string
  action: SuggestionAction
  rationale: string
  confidence: number
  labelName?: string
  taskTitle?: string
  status: SuggestionStatus
  decidedAt?: string
  analysisMethod: AnalysisMethod
  createdAt: string
}

export interface SuggestionDecisionResponse {
  success: boolean
  suggestionId: string
  status: SuggestionStatus
  decidedAt?: string
  stale?: boolean  // True if email no longer exists
  staleMessage?: string  // Message to show in toast
}

export interface PendingSuggestionsResponse {
  account?: string
  suggestions: PersistentSuggestion[]
  count: number
}

export interface SuggestionStats {
  days: number
  total: number
  approved: number
  rejected: number
  expired: number
  pending: number
  approvalRate: number
  byAction: Record<string, { approved: number; rejected: number }>
  byMethod: Record<string, { approved: number; rejected: number }>
}

export interface RejectionCandidate {
  pattern: string
  rejectionCount: number
  suggestedAction: string
}

export interface RejectionPatternsResponse {
  days: number
  minRejections: number
  candidates: {
    church: RejectionCandidate[]
    personal: RejectionCandidate[]
  }
}

export interface AddPatternResponse {
  success: boolean
  account: string
  pattern: string
  message: string
}

// =============================================================================
// Calendar Types
// =============================================================================

export type CalendarAccount = 'church' | 'personal'
export type CalendarView = 'personal' | 'work' | 'church' | 'combined'

export interface EventAttendee {
  email: string
  displayName?: string
  responseStatus: 'needsAction' | 'declined' | 'tentative' | 'accepted'
  isOrganizer: boolean
  isSelf: boolean
}

export interface CalendarEvent {
  id: string
  calendarId: string
  summary: string
  start: string  // ISO datetime
  end: string    // ISO datetime
  description?: string
  location?: string
  colorId?: string
  startTimezone?: string
  endTimezone?: string
  isAllDay: boolean
  status: 'confirmed' | 'tentative' | 'cancelled'
  attendees: EventAttendee[]
  organizerEmail?: string
  creatorEmail?: string
  recurringEventId?: string
  recurrence?: string[]
  htmlLink?: string
  hangoutLink?: string
  created?: string
  updated?: string
  sourceDomain: 'personal' | 'work' | 'church'
  // Computed properties from API
  isMeeting: boolean
  attendeeCount: number
  durationMinutes: number
}

export interface CalendarInfo {
  id: string
  summary: string
  description?: string
  colorId?: string
  backgroundColor?: string
  foregroundColor?: string
  isPrimary: boolean
  accessRole: 'owner' | 'writer' | 'reader' | 'freeBusyReader'
  isWritable: boolean
}

export interface CalendarSettings {
  enabledCalendars: string[]
  workCalendarId?: string
  showDeclinedEvents: boolean
  showAllDayEvents: boolean
  defaultDaysAhead: number
  lastSyncedAt?: string
}

// API Response types
export interface CalendarListResponse {
  account: string
  calendars: CalendarInfo[]
  nextPageToken?: string
}

export interface EventListResponse {
  account: string
  calendarId: string
  events: CalendarEvent[]
  nextPageToken?: string
  nextSyncToken?: string
}

export interface CalendarEventResponse {
  account: string
  event: CalendarEvent
}

export interface CalendarSettingsResponse {
  account: string
  settings: CalendarSettings
}

export interface CreateEventRequest {
  summary: string
  start: string  // ISO datetime
  end: string    // ISO datetime
  description?: string
  location?: string
  attendees?: string[]
  isAllDay?: boolean
  sendNotifications?: boolean
  calendarId?: string
}

export interface UpdateEventRequest {
  summary?: string
  start?: string
  end?: string
  description?: string
  location?: string
  attendees?: string[]
  sendNotifications?: boolean
  calendarId: string
}

export interface QuickAddEventRequest {
  text: string
  calendarId?: string
  sendNotifications?: boolean
}

export interface UpdateCalendarSettingsRequest {
  enabledCalendars?: string[]
  workCalendarId?: string
  showDeclinedEvents?: boolean
  showAllDayEvents?: boolean
  defaultDaysAhead?: number
}

// Calendar cache state (for lifting to App.tsx)
export interface CalendarCacheState {
  calendars: CalendarInfo[]
  events: CalendarEvent[]
  settings: CalendarSettings | null
  loaded: boolean
  loading: boolean
  error?: string
}

// =============================================================================
// Timeline Types (Unified Calendar + Tasks View)
// =============================================================================

export type TimelineItemType = 'event' | 'task'
export type TimelineDomain = 'personal' | 'work' | 'church'

export interface TimelineItem {
  type: TimelineItemType
  id: string
  title: string
  dateKey: string        // For grouping: toDateString()
  sortTime: Date         // For sorting within a day
  sortPriority: number   // Secondary sort: 0 for events (by time), 1-5 for tasks (by priority)
  sourceDomain: TimelineDomain
  event?: CalendarEvent
  task?: Task
}

// =============================================================================
// Phase CA-1: Calendar Attention Types
// =============================================================================

export type CalendarAttentionType = 'vip_meeting' | 'prep_needed' | 'task_conflict' | 'overcommitment'
export type CalendarAttentionStatus = 'active' | 'dismissed' | 'acted' | 'expired'
export type CalendarActionType = 'viewed' | 'dismissed' | 'task_linked' | 'prep_started'

export interface CalendarAttentionItem {
  eventId: string
  calendarAccount: string
  calendarId: string
  summary: string
  start: string  // ISO datetime
  end: string    // ISO datetime
  attendees: string[]
  location?: string
  htmlLink?: string
  attentionType: CalendarAttentionType
  reason: string
  confidence: number
  matchedVip?: string
  status: CalendarAttentionStatus
  dismissedAt?: string
  firstViewedAt?: string
  actionTakenAt?: string
  actionType?: CalendarActionType
}

export interface CalendarAttentionListResponse {
  account: string
  items: CalendarAttentionItem[]
  count: number
}

export interface CalendarAttentionAnalyzeResponse {
  account: string
  eventsScanned: number
  attentionItemsCreated: number
  items: CalendarAttentionItem[]
}

export interface CalendarAttentionQualityMetrics {
  total: number
  byStatus: Record<string, number>
  byType: Record<string, number>
  byAction: Record<string, number>
  acceptanceRate: number
  dismissedRate: number
}

