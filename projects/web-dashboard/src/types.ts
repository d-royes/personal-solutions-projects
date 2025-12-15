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
  analysisMethod: 'regex' | 'profile' | 'vip'  // How item was detected
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
  messagesAnalyzed: number
  existingRulesCount: number
  suggestions: RuleSuggestion[]
  attentionItems: AttentionItem[]
}

// App mode for navigation
export type AppMode = 'tasks' | 'email'

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

// Firestore Task (created from emails)
export interface FirestoreTask {
  id: string
  title: string
  status: string
  priority: string
  domain: string
  createdAt: string
  updatedAt: string
  dueDate: string | null
  project: string | null
  notes: string | null
  nextStep: string | null
  source: string
  sourceEmailId: string | null
  sourceEmailAccount: string | null
  sourceEmailSubject: string | null
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

