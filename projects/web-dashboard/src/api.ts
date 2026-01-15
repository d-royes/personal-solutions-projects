import type {
  ActivityEntry,
  AssistResponse,
  AttentionItem,
  ConversationMessage,
  DataSource,
  TaskResponse,
  WorkBadge,
  // Sprint 5: Suggestion Tracking
  SuggestionDecisionResponse,
  PendingSuggestionsResponse,
  SuggestionStats,
  RejectionPatternsResponse,
  AddPatternResponse,
  // Calendar types
  CalendarAccount,
  CalendarListResponse,
  EventListResponse,
  CalendarEventResponse,
  CalendarSettingsResponse,
  CreateEventRequest,
  UpdateEventRequest,
  QuickAddEventRequest,
  UpdateCalendarSettingsRequest,
  // Phase CA-1: Calendar Attention
  CalendarAttentionListResponse,
  CalendarAttentionAnalyzeResponse,
  CalendarAttentionQualityMetrics,
} from './types'
import type { AuthConfig } from './auth/types'

const defaultBase =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

const defaultSource: DataSource =
  (import.meta.env.VITE_API_DEFAULT_SOURCE as DataSource) ?? 'auto'

export interface FetchTasksOptions {
  source?: DataSource
  limit?: number
  sources?: string[]  // Filter to specific source keys (e.g., ['personal', 'work'])
  includeWork?: boolean  // If true, include work tasks in ALL view
}

export async function fetchTasks(
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  options: FetchTasksOptions = {},
): Promise<TaskResponse> {
  const url = new URL('/tasks', baseUrl)
  url.searchParams.set('source', options.source ?? defaultSource)
  if (typeof options.limit === 'number') {
    url.searchParams.set('limit', String(options.limit))
  }
  if (options.sources && options.sources.length > 0) {
    url.searchParams.set('sources', options.sources.join(','))
  }
  if (options.includeWork) {
    url.searchParams.set('includeWork', 'true')
  }
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    throw new Error(`Tasks request failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function fetchWorkBadge(
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<WorkBadge> {
  const url = new URL('/work/badge', baseUrl)
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    throw new Error(`Work badge request failed: ${resp.statusText}`)
  }
  return resp.json()
}

export interface AssistOptions {
  source?: DataSource
  limit?: number
  anthropicModel?: string
  sendEmailAccount?: string
  instructions?: string
  resetConversation?: boolean
}

export async function runAssist(
  taskId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  options: AssistOptions = {},
): Promise<AssistResponse> {
  const url = new URL(`/assist/${taskId}`, baseUrl)
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      source: options.source ?? defaultSource,
      limit: options.limit ?? 50,
      anthropicModel: options.anthropicModel,
      sendEmailAccount: options.sendEmailAccount,
      instructions: options.instructions,
      resetConversation: options.resetConversation ?? false,
    }),
  })

  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Assist failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function fetchConversationHistory(
  taskId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  limit = 50,
): Promise<ConversationMessage[]> {
  const url = new URL(`/assist/${taskId}/history`, baseUrl)
  url.searchParams.set('limit', String(limit))
  const resp = await fetch(url.toString(), {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    throw new Error(`History request failed: ${resp.statusText}`)
  }
  return resp.json()
}

export interface StrikeResponse {
  status: 'struck' | 'unstruck'
  messageTs: string
  history: ConversationMessage[]
}

export async function strikeMessage(
  taskId: string,
  messageTs: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<StrikeResponse> {
  const url = new URL(`/assist/${taskId}/history/strike`, baseUrl)
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({ messageTs }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Strike failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function unstrikeMessage(
  taskId: string,
  messageTs: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<StrikeResponse> {
  const url = new URL(`/assist/${taskId}/history/unstrike`, baseUrl)
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({ messageTs }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Unstrike failed: ${resp.statusText}`)
  }
  return resp.json()
}

export interface PendingAction {
  action: TaskUpdateAction
  status?: string
  priority?: string
  dueDate?: string
  comment?: string
  number?: number
  contactFlag?: boolean
  recurring?: string
  project?: string
  taskTitle?: string
  assignedTo?: string
  notes?: string
  estimatedHours?: string
  reason?: string
}

export interface EmailDraftUpdate {
  to?: string
  cc?: string
  subject?: string
  body?: string
  reason: string
}

export interface ChatResponse {
  response: string
  history: ConversationMessage[]
  pendingAction?: PendingAction
  emailDraftUpdate?: EmailDraftUpdate
}

export interface ChatMessageOptions {
  source?: DataSource
  selectedAttachments?: string[]  // IDs of images to include in context
  workspaceContext?: string  // Checked workspace content
}

export async function sendChatMessage(
  taskId: string,
  message: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  options: ChatMessageOptions = {},
): Promise<ChatResponse> {
  const url = new URL(`/assist/${taskId}/chat`, baseUrl)
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      message,
      source: options.source ?? 'auto',
      selectedAttachments: options.selectedAttachments,
      workspaceContext: options.workspaceContext,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Chat failed: ${resp.statusText}`)
  }
  return resp.json()
}

export interface PlanResponse {
  plan: AssistResponse['plan']
  environment: string
  liveTasks: boolean
  warning: string | null
}

export async function generatePlan(
  taskId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  options: { source?: DataSource; anthropicModel?: string; workspaceContext?: string; contextItems?: string[]; selectedAttachments?: string[] } = {},
): Promise<PlanResponse> {
  const url = new URL(`/assist/${taskId}/plan`, baseUrl)
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      source: options.source ?? defaultSource,
      anthropicModel: options.anthropicModel,
      workspaceContext: options.workspaceContext,
      contextItems: options.contextItems,
      selectedAttachments: options.selectedAttachments,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Plan generation failed: ${resp.statusText}`)
  }
  return resp.json()
}

export interface ResearchResponse {
  research: string
  taskId: string
  taskTitle: string
  history?: ConversationMessage[]
}

export async function runResearch(
  taskId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  options: { source?: DataSource; nextSteps?: string[] } = {},
): Promise<ResearchResponse> {
  const url = new URL(`/assist/${taskId}/research`, baseUrl)
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      source: options.source ?? defaultSource,
      next_steps: options.nextSteps,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Research failed: ${resp.statusText}`)
  }
  return resp.json()
}

export interface SummarizeResponse {
  summary: string
  taskId: string
  taskTitle: string
  history?: ConversationMessage[]
}

export async function runSummarize(
  taskId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  options: {
    source?: DataSource
    planSummary?: string
    nextSteps?: string[]
    efficiencyTips?: string[]
  } = {},
): Promise<SummarizeResponse> {
  const url = new URL(`/assist/${taskId}/summarize`, baseUrl)
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      source: options.source ?? defaultSource,
      planSummary: options.planSummary,
      nextSteps: options.nextSteps,
      efficiencyTips: options.efficiencyTips,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Summarize failed: ${resp.statusText}`)
  }
  return resp.json()
}

// --- Contact Search ---

export interface ContactCard {
  name: string
  email?: string
  phone?: string
  title?: string
  organization?: string
  location?: string
  source: string
  confidence: string
  sourceUrl?: string
}

export interface ContactEntity {
  name: string
  entityType: string
  context?: string
}

export interface ContactSearchResponse {
  contacts: ContactCard[]
  entitiesFound: ContactEntity[]
  needsConfirmation: boolean
  confirmationMessage?: string
  searchPerformed: boolean
  message: string
  taskId: string
  taskTitle: string
  history?: ConversationMessage[]
}

export async function searchContacts(
  taskId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  options: { source?: DataSource; confirmSearch?: boolean } = {},
): Promise<ContactSearchResponse> {
  const url = new URL(`/assist/${taskId}/contact`, baseUrl)
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      source: options.source ?? defaultSource,
      confirmSearch: options.confirmSearch ?? false,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Contact search failed: ${resp.statusText}`)
  }
  return resp.json()
}

// --- Saved Contacts (Phase 2 Foundation) ---

export interface SavedContact {
  id: string
  name: string
  email?: string
  phone?: string
  title?: string
  organization?: string
  location?: string
  notes?: string
  sourceTaskId?: string
  createdAt: string
  updatedAt: string
  userEmail?: string
  tags: string[]
}

export async function saveContact(
  auth: AuthConfig,
  contact: {
    name: string
    email?: string
    phone?: string
    title?: string
    organization?: string
    location?: string
    notes?: string
    sourceTaskId?: string
    tags?: string[]
    contactId?: string
  },
  baseUrl: string = defaultBase,
): Promise<{ status: string; contact: SavedContact }> {
  const url = new URL('/contacts', baseUrl)
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify(contact),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Save contact failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function listContacts(
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  limit: number = 100,
): Promise<{ contacts: SavedContact[]; count: number }> {
  const url = new URL('/contacts', baseUrl)
  url.searchParams.set('limit', String(limit))
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `List contacts failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function deleteContact(
  contactId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ status: string; message: string }> {
  const url = new URL(`/contacts/${contactId}`, baseUrl)
  const resp = await fetch(url, {
    method: 'DELETE',
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Delete contact failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function fetchActivity(
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  limit = 25,
): Promise<ActivityEntry[]> {
  const url = new URL('/activity', baseUrl)
  url.searchParams.set('limit', String(limit))
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    throw new Error(`Activity request failed: ${resp.statusText}`)
  }
  const data = await resp.json()
  return data.entries ?? []
}

// --- Workspace API ---

export interface WorkspaceResponse {
  taskId: string
  items: string[]
  updatedAt: string
}

export async function loadWorkspace(
  taskId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<WorkspaceResponse> {
  const url = new URL(`/assist/${taskId}/workspace`, baseUrl)
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Load workspace failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function saveWorkspace(
  taskId: string,
  items: string[],
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<WorkspaceResponse> {
  const url = new URL(`/assist/${taskId}/workspace`, baseUrl)
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({ items }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Save workspace failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function clearWorkspace(
  taskId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ taskId: string; cleared: boolean }> {
  const url = new URL(`/assist/${taskId}/workspace`, baseUrl)
  const resp = await fetch(url, {
    method: 'DELETE',
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Clear workspace failed: ${resp.statusText}`)
  }
  return resp.json()
}

// --- Attachments API ---

export interface AttachmentInfo {
  attachmentId: string
  name: string
  mimeType: string
  sizeBytes: number
  createdAt: string
  attachmentType: string
  downloadUrl: string
  isImage: boolean
  isPdf: boolean
  source?: string
}

export function getAttachmentDetailUrl(
  taskId: string,
  attachmentId: string,
  baseUrl: string = defaultBase,
): string {
  // Returns backend endpoint to fetch single attachment detail (includes downloadUrl)
  return `${baseUrl}/assist/${taskId}/attachment/${attachmentId}`
}

export async function fetchAttachmentDetail(
  taskId: string,
  attachmentId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<AttachmentInfo> {
  const url = new URL(`/assist/${taskId}/attachment/${attachmentId}`, baseUrl)
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Fetch attachment detail failed: ${resp.statusText}`)
  }
  return resp.json()
}

export interface AttachmentsResponse {
  taskId: string
  attachments: AttachmentInfo[]
}

export async function fetchAttachments(
  taskId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<AttachmentsResponse> {
  const url = new URL(`/assist/${taskId}/attachments`, baseUrl)
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Fetch attachments failed: ${resp.statusText}`)
  }
  return resp.json()
}

function buildHeaders(auth: AuthConfig): HeadersInit {
  if (auth.mode === 'idToken') {
    if (!auth.idToken) {
      throw new Error('Missing ID token for auth mode.')
    }
    return {
      Authorization: `Bearer ${auth.idToken}`,
    }
  }
  if (!auth.userEmail) {
    throw new Error('Provide a user email when using dev auth mode.')
  }
  return {
    'X-User-Email': auth.userEmail,
  }
}

async function safeJson(resp: Response) {
  try {
    return await resp.json()
  } catch {
    return null
  }
}

// Feedback Types and Functions
export type FeedbackType = 'helpful' | 'needs_work'
export type FeedbackContext = 'research' | 'plan' | 'chat' | 'email' | 'task_update'

export interface FeedbackRequest {
  feedback: FeedbackType
  context: FeedbackContext
  messageContent: string
  messageId?: string
  // Phase 1A: Email context fields for quality metrics
  emailId?: string
  emailAccount?: EmailAccount
  suggestionId?: string
  analysisMethod?: 'haiku' | 'regex' | 'vip' | 'profile_match'
  confidence?: number
  actionTaken?: 'dismissed' | 'task_created' | 'replied'
}

export interface FeedbackResponse {
  status: 'success'
  feedbackId: string
  message: string
}

export interface FeedbackSummary {
  totalHelpful: number
  totalNeedsWork: number
  helpfulRate: number
  byContext: Record<string, { helpful: number; needs_work: number }>
  recentIssues: string[]
  periodDays: number
}

export async function submitFeedback(
  taskId: string,
  request: FeedbackRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<FeedbackResponse> {
  const url = new URL(`/assist/${taskId}/feedback`, baseUrl)
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      feedback: request.feedback,
      context: request.context,
      message_content: request.messageContent,
      message_id: request.messageId,
      // Phase 1A: Email context fields
      email_id: request.emailId,
      email_account: request.emailAccount,
      suggestion_id: request.suggestionId,
      analysis_method: request.analysisMethod,
      confidence: request.confidence,
      action_taken: request.actionTaken,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Feedback submission failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function fetchFeedbackSummary(
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  days: number = 30,
): Promise<FeedbackSummary> {
  const url = new URL('/feedback/summary', baseUrl)
  url.searchParams.set('days', String(days))
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    throw new Error(`Feedback summary request failed: ${resp.statusText}`)
  }
  return resp.json()
}

// Task Update Types and Functions
export type TaskUpdateAction = 
  | 'mark_complete' | 'update_status' | 'update_priority' | 'update_due_date' | 'add_comment'
  | 'update_number' | 'update_contact_flag' | 'update_recurring' | 'update_project'
  | 'update_task' | 'update_assigned_to' | 'update_notes' | 'update_estimated_hours'

export interface TaskUpdateRequest {
  source: 'personal' | 'work'  // Which Smartsheet to update
  action: TaskUpdateAction
  status?: string
  priority?: string
  dueDate?: string
  comment?: string
  number?: number
  contactFlag?: boolean
  recurring?: string
  project?: string
  taskTitle?: string
  assignedTo?: string
  notes?: string
  estimatedHours?: string
  confirmed: boolean
}

export interface TaskUpdatePreview {
  taskId: string
  action: TaskUpdateAction
  changes: Record<string, unknown>
  description: string
}

export interface TaskUpdateResponse {
  status: 'pending_confirmation' | 'success'
  preview?: TaskUpdatePreview
  action?: TaskUpdateAction
  changes?: Record<string, unknown>
  message?: string
}

// Smartsheet Task Creation (for Calendar mode)
export interface SmartsheetTaskCreateRequest {
  source: 'personal' | 'work'
  task: string
  project: string
  dueDate: string
  priority?: string
  status?: string
  assignedTo?: string
  estimatedHours?: string
  notes?: string
  confirmed: boolean
}

export interface SmartsheetTaskCreateResponse {
  status: 'preview' | 'created'
  message: string
  task?: Record<string, unknown>
  result?: Record<string, unknown>
}

export async function createSmartsheetTask(
  request: SmartsheetTaskCreateRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<SmartsheetTaskCreateResponse> {
  const url = new URL('/tasks/create', baseUrl)
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      source: request.source,
      task: request.task,
      project: request.project,
      due_date: request.dueDate,
      priority: request.priority || 'Standard',
      status: request.status || 'Scheduled',
      assigned_to: request.assignedTo || 'david.a.royes@gmail.com',
      estimated_hours: request.estimatedHours || '1',
      notes: request.notes,
      confirmed: request.confirmed,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Create task failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function updateTask(
  taskId: string,
  request: TaskUpdateRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<TaskUpdateResponse> {
  const url = new URL(`/assist/${taskId}/update`, baseUrl)
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      source: request.source,
      action: request.action,
      status: request.status,
      priority: request.priority,
      due_date: request.dueDate,
      comment: request.comment,
      number: request.number,
      contactFlag: request.contactFlag,
      recurring: request.recurring,
      project: request.project,
      taskTitle: request.taskTitle,
      assignedTo: request.assignedTo,
      notes: request.notes,
      estimatedHours: request.estimatedHours,
      confirmed: request.confirmed,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Task update failed: ${resp.statusText}`)
  }
  return resp.json()
}

// Email Draft Types and Functions
export interface EmailDraftRequest {
  source?: DataSource
  sourceContent?: string
  recipient?: string
  regenerateInput?: string
}

export interface EmailDraftResponse {
  subject: string
  body: string
  bodyHtml: string
  needsRecipient: boolean
  taskId: string
  taskTitle: string
}

export async function draftEmail(
  taskId: string,
  request: EmailDraftRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<EmailDraftResponse> {
  const url = new URL(`/assist/${taskId}/draft-email`, baseUrl)
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      source: request.source ?? 'auto',
      sourceContent: request.sourceContent,
      recipient: request.recipient,
      regenerateInput: request.regenerateInput,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Email draft failed: ${resp.statusText}`)
  }
  return resp.json()
}

export interface SendEmailRequest {
  source?: DataSource
  account: string
  to: string[]
  cc?: string[]
  subject: string
  body: string
}

export interface SendEmailResponse {
  status: 'sent'
  messageId: string
  taskId: string
  commentPosted: boolean
  history: ConversationMessage[]
}

export async function sendEmail(
  taskId: string,
  request: SendEmailRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<SendEmailResponse> {
  const url = new URL(`/assist/${taskId}/send-email`, baseUrl)
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      source: request.source ?? 'auto',
      account: request.account,
      to: request.to,
      cc: request.cc,
      subject: request.subject,
      body: request.body,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Email send failed: ${resp.statusText}`)
  }
  return resp.json()
}

// Email Draft Persistence Types and Functions
export interface SavedEmailDraft {
  taskId: string
  to: string[]
  cc: string[]
  subject: string
  body: string
  fromAccount: string
  sourceContent: string
  createdAt: string
  updatedAt: string
}

export interface LoadDraftResponse {
  taskId: string
  hasDraft: boolean
  draft: SavedEmailDraft | null
}

export interface SaveDraftRequest {
  to: string[]
  cc: string[]
  subject: string
  body: string
  fromAccount?: string
  sourceContent?: string
}

export interface SaveDraftResponse {
  status: 'saved'
  taskId: string
  draft: SavedEmailDraft
}

export async function loadDraft(
  taskId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<LoadDraftResponse> {
  const url = new URL(`/assist/${taskId}/draft`, baseUrl)
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Load draft failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function saveDraft(
  taskId: string,
  request: SaveDraftRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<SaveDraftResponse> {
  const url = new URL(`/assist/${taskId}/draft`, baseUrl)
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      to: request.to,
      cc: request.cc,
      subject: request.subject,
      body: request.body,
      from_account: request.fromAccount ?? '',
      source_content: request.sourceContent ?? '',
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Save draft failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function deleteDraft(
  taskId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ status: 'deleted'; taskId: string }> {
  const url = new URL(`/assist/${taskId}/draft`, baseUrl)
  const resp = await fetch(url, {
    method: 'DELETE',
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Delete draft failed: ${resp.statusText}`)
  }
  return resp.json()
}


// --- Global Portfolio Mode Types and Functions ---

export type Perspective = 'personal' | 'church' | 'work' | 'holistic'

export interface PortfolioStats {
  totalOpen: number
  overdue: number
  dueToday: number
  dueThisWeek: number
  byPriority: Record<string, number>
  byProject: Record<string, number>
  byDueDate: Record<string, number>
  conflicts: string[]
  domainBreakdown: Record<string, number>
}

export interface GlobalContextResponse {
  perspective: Perspective
  description: string
  portfolio: PortfolioStats
  history: ConversationMessage[]
}

export interface PortfolioPendingAction {
  rowId: string
  source: 'personal' | 'work'  // Which Smartsheet the task belongs to
  action: TaskUpdateAction
  status?: string
  priority?: string
  dueDate?: string
  comment?: string
  number?: number  // 0.1-0.9 = recurring (early AM), 1+ = regular tasks
  contactFlag?: boolean
  recurring?: string
  project?: string
  taskTitle?: string
  assignedTo?: string
  notes?: string
  estimatedHours?: string
  reason?: string
  // Enriched data from portfolio context
  domain?: string
  currentDue?: string
  currentNumber?: number
  currentPriority?: string
  currentStatus?: string
}

export interface GlobalChatResponse {
  response: string
  perspective: Perspective
  portfolio: PortfolioStats
  history: ConversationMessage[]
  pendingActions?: PortfolioPendingAction[]  // Task updates from DATA
}

export async function fetchGlobalContext(
  auth: AuthConfig,
  perspective: Perspective = 'personal',
  baseUrl: string = defaultBase,
): Promise<GlobalContextResponse> {
  const url = new URL('/assist/global/context', baseUrl)
  url.searchParams.set('perspective', perspective)
  
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Global context failed: ${resp.statusText}`)
  }
  return resp.json()
}

export interface GlobalChatOptions {
  perspective?: Perspective
  feedback?: 'helpful' | 'not_helpful'
  anthropicModel?: string
}

export async function sendGlobalChat(
  message: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  options: GlobalChatOptions = {},
): Promise<GlobalChatResponse> {
  const url = new URL('/assist/global/chat', baseUrl)
  
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      message,
      perspective: options.perspective ?? 'personal',
      feedback: options.feedback,
      anthropicModel: options.anthropicModel,
    }),
  })
  
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Global chat failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function clearGlobalHistory(
  auth: AuthConfig,
  perspective: Perspective = 'personal',
  baseUrl: string = defaultBase,
): Promise<{ status: 'cleared'; perspective: Perspective }> {
  const url = new URL('/assist/global/history', baseUrl)
  url.searchParams.set('perspective', perspective)
  
  const resp = await fetch(url, {
    method: 'DELETE',
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Clear history failed: ${resp.statusText}`)
  }
  return resp.json()
}

export interface GlobalMessageActionResponse {
  status: 'struck' | 'unstruck' | 'deleted'
  messageTs: string
  perspective: Perspective
  history: ConversationMessage[]
}

export async function strikeGlobalMessage(
  auth: AuthConfig,
  messageTs: string,
  perspective: Perspective = 'personal',
  baseUrl: string = defaultBase,
): Promise<GlobalMessageActionResponse> {
  const url = new URL('/assist/global/history/strike', baseUrl)
  
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      messageTs,
      perspective,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Strike message failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function unstrikeGlobalMessage(
  auth: AuthConfig,
  messageTs: string,
  perspective: Perspective = 'personal',
  baseUrl: string = defaultBase,
): Promise<GlobalMessageActionResponse> {
  const url = new URL('/assist/global/history/unstrike', baseUrl)
  
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      messageTs,
      perspective,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Unstrike message failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function deleteGlobalMessage(
  auth: AuthConfig,
  messageTs: string,
  perspective: Perspective = 'personal',
  baseUrl: string = defaultBase,
): Promise<GlobalMessageActionResponse> {
  const url = new URL('/assist/global/message', baseUrl)
  
  const resp = await fetch(url, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      messageTs,
      perspective,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Delete message failed: ${resp.statusText}`)
  }
  return resp.json()
}


// --- Portfolio Bulk Update Types and Functions ---

export interface BulkTaskUpdate {
  rowId: string
  source: 'personal' | 'work'  // Which Smartsheet to update
  action: TaskUpdateAction
  status?: string
  priority?: string
  dueDate?: string
  comment?: string
  number?: number  // Supports decimals: 0.1-0.9 for recurring, 1+ for regular tasks
  contactFlag?: boolean
  recurring?: string
  project?: string
  taskTitle?: string
  assignedTo?: string
  notes?: string
  estimatedHours?: string
  reason?: string
}

export interface BulkUpdateResult {
  rowId: string
  success: boolean
  error?: string
}

export interface BulkUpdateResponse {
  success: boolean
  totalUpdates: number
  successCount: number
  failureCount: number
  results: BulkUpdateResult[]
}

export async function bulkUpdateTasks(
  updates: BulkTaskUpdate[],
  auth: AuthConfig,
  perspective: Perspective = 'holistic',
  baseUrl: string = defaultBase,
): Promise<BulkUpdateResponse> {
  const url = new URL('/assist/global/bulk-update', baseUrl)
  
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      updates,
      perspective,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Bulk update failed: ${resp.statusText}`)
  }
  return resp.json()
}


// --- Workload Rebalancing Types and Functions ---

export type RebalanceFocus = 'overdue' | 'today' | 'week' | 'all'

export interface RebalanceProposedChange {
  rowId: string
  title: string
  domain: string
  currentDue: string
  proposedDue: string
  currentNumber?: number  // 0.1-0.9 = recurring (early AM), 1+ = regular
  proposedNumber?: number
  priority: string
  reason: string
}

export interface RebalanceResponse {
  status: 'proposal_ready' | 'no_changes_needed'
  message: string
  perspective?: Perspective
  focus?: RebalanceFocus
  proposedChanges: RebalanceProposedChange[]
}

export interface RebalanceOptions {
  perspective?: Perspective
  focus?: RebalanceFocus
  includeSequencing?: boolean
}

export async function getRebalanceProposal(
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  options: RebalanceOptions = {},
): Promise<RebalanceResponse> {
  const url = new URL('/assist/global/rebalance', baseUrl)
  
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      perspective: options.perspective ?? 'holistic',
      focus: options.focus ?? 'overdue',
      includeSequencing: options.includeSequencing ?? true,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Rebalance request failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Convert a rebalance proposal into bulk update format for execution.
 */
export function proposalToBulkUpdates(
  changes: RebalanceProposedChange[],
): BulkTaskUpdate[] {
  const updates: BulkTaskUpdate[] = []
  
  for (const change of changes) {
    // Derive source from domain - Work domain = work sheet, else personal
    const source: 'personal' | 'work' = change.domain === 'Work' ? 'work' : 'personal'
    
    // Add due date update if changed
    if (change.proposedDue && change.proposedDue !== change.currentDue) {
      updates.push({
        rowId: change.rowId,
        source,
        action: 'update_due_date',
        dueDate: change.proposedDue,
        reason: change.reason,
      })
    }
    
    // Add number update if changed
    if (change.proposedNumber != null && change.proposedNumber !== change.currentNumber) {
      updates.push({
        rowId: change.rowId,
        source,
        action: 'update_number',
        number: change.proposedNumber,
        reason: change.reason,
      })
    }
  }
  
  return updates
}


// =============================================================================
// EMAIL MANAGEMENT API
// =============================================================================

import type {
  EmailAccount,
  FilterRule,
  FilterRulesResponse,
  InboxSummary,
  AnalyzeInboxResponse,
  EmailMessage,
} from './types'

// --- Inbox Reading ---

export async function getInboxSummary(
  account: EmailAccount,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  maxResults: number = 20,
  pageToken?: string,  // For "Load More" pagination
): Promise<InboxSummary> {
  const url = new URL(`/inbox/${account}`, baseUrl)
  url.searchParams.set('max_results', String(maxResults))
  if (pageToken) {
    url.searchParams.set('page_token', pageToken)
  }

  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Inbox request failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function getUnreadEmails(
  account: EmailAccount,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  options: { maxResults?: number; fromFilter?: string } = {},
): Promise<{ account: string; email: string; count: number; messages: EmailMessage[] }> {
  const url = new URL(`/inbox/${account}/unread`, baseUrl)
  url.searchParams.set('max_results', String(options.maxResults ?? 20))
  if (options.fromFilter) {
    url.searchParams.set('from_filter', options.fromFilter)
  }
  
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Unread request failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function searchInbox(
  account: EmailAccount,
  query: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  maxResults: number = 20,
): Promise<{ account: string; email: string; query: string; count: number; messages: EmailMessage[] }> {
  const url = new URL(`/inbox/${account}/search`, baseUrl)
  url.searchParams.set('q', query)
  url.searchParams.set('max_results', String(maxResults))
  
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Search request failed: ${resp.statusText}`)
  }
  return resp.json()
}

// --- Filter Rules Management ---

export async function getFilterRules(
  account: EmailAccount,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<FilterRulesResponse> {
  const url = new URL(`/email/rules/${account}`, baseUrl)
  
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get rules failed: ${resp.statusText}`)
  }
  return resp.json()
}

export interface AddRuleRequest {
  emailAccount: string
  order: number
  category: string
  field: string
  operator: string
  value: string
  action?: string
}

export async function addFilterRule(
  account: EmailAccount,
  rule: AddRuleRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ status: string; account: string; rule: FilterRule }> {
  const url = new URL(`/email/rules/${account}`, baseUrl)
  
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify(rule),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Add rule failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function deleteFilterRule(
  account: EmailAccount,
  rowNumber: number,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ status: string; account: string; rowNumber: number }> {
  const url = new URL(`/email/rules/${account}/${rowNumber}`, baseUrl)
  
  const resp = await fetch(url, {
    method: 'DELETE',
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Delete rule failed: ${resp.statusText}`)
  }
  return resp.json()
}

// --- Inbox Analysis ---

export async function analyzeInbox(
  account: EmailAccount,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  maxMessages: number = 50,
): Promise<AnalyzeInboxResponse> {
  const url = new URL(`/email/analyze/${account}`, baseUrl)
  url.searchParams.set('max_messages', String(maxMessages))
  
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Analysis failed: ${resp.statusText}`)
  }
  return resp.json()
}

// --- Attention Item Actions (Sprint 4) ---

export type DismissReason = 'not_actionable' | 'handled' | 'false_positive'

export interface DismissResult {
  success: boolean
  emailId: string
  account: string
  reason: DismissReason
}

export interface SnoozeResult {
  success: boolean
  emailId: string
  account: string
  snoozedUntil: string
}

export interface PersistedAttentionResponse {
  account: string
  attentionItems: AttentionItem[]
  count: number
}

/**
 * Get persisted attention items from storage (without re-analyzing).
 * Use this on page load to restore previous attention state.
 */
export async function getAttentionItems(
  account: EmailAccount,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<PersistedAttentionResponse> {
  const url = new URL(`/email/attention/${account}`, baseUrl)

  const resp = await fetch(url, {
    method: 'GET',
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Failed to get attention items: ${resp.statusText}`)
  }
  return resp.json()
}

// Response type for last analysis endpoint
export interface LastAnalysisApiResponse {
  account: string
  lastAnalysis: {
    timestamp: string
    emailsFetched: number
    emailsAnalyzed: number
    alreadyTracked: number
    dismissed: number
    suggestionsGenerated: number
    rulesGenerated: number
    attentionItems: number
    haikuAnalyzed: number
    haikuRemaining: { daily: number; weekly: number } | null
  } | null
}

export async function getLastAnalysis(
  account: EmailAccount,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<LastAnalysisApiResponse> {
  const url = new URL(`/email/last-analysis/${account}`, baseUrl)

  const resp = await fetch(url, {
    method: 'GET',
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Failed to get last analysis: ${resp.statusText}`)
  }
  return resp.json()
}

export async function dismissAttentionItem(
  account: EmailAccount,
  emailId: string,
  reason: DismissReason,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<DismissResult> {
  const url = new URL(`/email/attention/${account}/${emailId}/dismiss`, baseUrl)

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({ reason }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Dismiss failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function snoozeAttentionItem(
  account: EmailAccount,
  emailId: string,
  until: Date,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<SnoozeResult> {
  const url = new URL(`/email/attention/${account}/${emailId}/snooze`, baseUrl)

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({ until: until.toISOString() }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Snooze failed: ${resp.statusText}`)
  }
  return resp.json()
}

// --- Phase 1A: Quality Tracking Functions ---

export interface QualityMetrics {
  account: EmailAccount
  periodDays: number
  total: number
  byStatus: Record<string, number>
  byMethod: Record<string, number>
  byAction: Record<string, number>
  acceptanceRate: number
  dismissedRate: number
}

/**
 * Mark an attention item as viewed.
 * Phase 1A: Records first_viewed_at for response latency metrics.
 */
export async function markAttentionViewed(
  account: EmailAccount,
  emailId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ success: boolean; emailId: string; account: EmailAccount }> {
  const url = new URL(`/email/attention/${account}/${emailId}/viewed`, baseUrl)

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Mark viewed failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Get quality metrics for attention items.
 * Phase 1A: Returns acceptance rates, dismissal rates, and breakdowns.
 */
export async function getQualityMetrics(
  account: EmailAccount,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  days: number = 30,
): Promise<QualityMetrics> {
  const url = new URL(`/email/attention/${account}/quality-metrics`, baseUrl)
  url.searchParams.set('days', String(days))

  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Quality metrics request failed: ${resp.statusText}`)
  }
  return resp.json()
}

// --- Rule Sync ---

export async function syncRulesToSheet(
  account: EmailAccount,
  emailAccount: string,
  rules: FilterRule[],
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ status: string; account: string; emailAccount: string; rulesSynced: number }> {
  const url = new URL(`/email/sync/${account}`, baseUrl)
  
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      emailAccount,
      rules,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Sync failed: ${resp.statusText}`)
  }
  return resp.json()
}

// --- Email Actions (Phase 3) ---

export interface EmailActionResult {
  status: string
  account: string
  messageId: string
  labels: string[]
  stale?: boolean
  staleMessage?: string
}

export async function archiveEmail(
  account: EmailAccount,
  messageId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<EmailActionResult> {
  const url = new URL(`/email/${account}/archive/${messageId}`, baseUrl)
  
  const resp = await fetch(url, {
    method: 'POST',
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Archive failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function deleteEmail(
  account: EmailAccount,
  messageId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<EmailActionResult> {
  const url = new URL(`/email/${account}/delete/${messageId}`, baseUrl)
  
  const resp = await fetch(url, {
    method: 'POST',
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Delete failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function starEmail(
  account: EmailAccount,
  messageId: string,
  starred: boolean,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<EmailActionResult> {
  const url = new URL(`/email/${account}/star/${messageId}`, baseUrl)
  url.searchParams.set('starred', String(starred))
  
  const resp = await fetch(url, {
    method: 'POST',
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Star action failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function markEmailImportant(
  account: EmailAccount,
  messageId: string,
  important: boolean,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<EmailActionResult> {
  const url = new URL(`/email/${account}/important/${messageId}`, baseUrl)
  url.searchParams.set('important', String(important))
  
  const resp = await fetch(url, {
    method: 'POST',
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Mark important failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function markEmailRead(
  account: EmailAccount,
  messageId: string,
  read: boolean,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<EmailActionResult> {
  const url = new URL(`/email/${account}/read/${messageId}`, baseUrl)
  url.searchParams.set('read', String(read))
  
  const resp = await fetch(url, {
    method: 'POST',
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Mark read failed: ${resp.statusText}`)
  }
  return resp.json()
}

// --- Email Search ---

export async function searchEmails(
  account: EmailAccount,
  query: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  maxResults: number = 20,
): Promise<{ messages: EmailMessage[]; query: string; account: string }> {
  const url = new URL(`/inbox/${account}/search`, baseUrl)
  url.searchParams.set('q', query)
  url.searchParams.set('max_results', String(maxResults))
  
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Search failed: ${resp.statusText}`)
  }
  return resp.json()
}

// --- Email Chat (Phase 4) ---

export interface EmailChatRequest {
  message: string
  emailId: string
  threadId?: string  // For conversation persistence
  history?: Array<{ role: string; content: string }>
  overridePrivacy?: boolean  // One-time privacy override ("Share with DATA")
}

export interface EmailPendingAction {
  action: string
  reason: string
  taskTitle?: string
  draftBody?: string
  draftSubject?: string
  labelName?: string
}

export interface EmailPrivacyStatus {
  canSeeBody: boolean
  blockedReason: string | null
  blockedReasonDisplay: string | null
  overrideGranted: boolean
}

export interface EmailChatResponse {
  response: string
  account: string
  emailId: string
  threadId: string  // For conversation persistence
  privacyStatus: EmailPrivacyStatus
  pendingAction?: EmailPendingAction
  stale?: boolean  // True if email no longer exists
  staleMessage?: string
}

export async function chatAboutEmail(
  account: EmailAccount,
  request: EmailChatRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<EmailChatResponse> {
  const url = new URL(`/email/${account}/chat`, baseUrl)

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      message: request.message,
      email_id: request.emailId,
      thread_id: request.threadId,
      history: request.history,
      override_privacy: request.overridePrivacy ?? false,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Email chat failed: ${resp.statusText}`)
  }
  return resp.json()
}


// --- Custom Label Operations (Phase A2) ---

export interface GmailLabel {
  id: string
  name: string
  type: 'system' | 'user'
  messagesTotal: number
  messagesUnread: number
  color: string | null
}

export interface LabelsResponse {
  account: string
  labels: GmailLabel[]
}

export async function getEmailLabels(
  account: EmailAccount,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<LabelsResponse> {
  const url = new URL(`/email/${account}/labels`, baseUrl)
  
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get labels failed: ${resp.statusText}`)
  }
  return resp.json()
}

export interface ApplyLabelRequest {
  labelId?: string
  labelName?: string
  action: 'apply' | 'remove'
}

export async function modifyEmailLabel(
  account: EmailAccount,
  messageId: string,
  request: ApplyLabelRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<EmailActionResult> {
  const url = new URL(`/email/${account}/label/${messageId}`, baseUrl)
  
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      label_id: request.labelId,
      label_name: request.labelName,
      action: request.action,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Label modification failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function applyEmailLabel(
  account: EmailAccount,
  messageId: string,
  labelId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<EmailActionResult> {
  return modifyEmailLabel(account, messageId, { labelId, action: 'apply' }, auth, baseUrl)
}

export async function removeEmailLabel(
  account: EmailAccount,
  messageId: string,
  labelId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<EmailActionResult> {
  return modifyEmailLabel(account, messageId, { labelId, action: 'remove' }, auth, baseUrl)
}


// --- Email-to-Task (Phase B) ---

export interface TaskPreview {
  title: string
  dueDate: string | null
  priority: string
  domain: string
  project: string | null
  notes: string | null
}

export interface TaskPreviewResponse {
  account: string
  emailId: string
  emailSubject: string
  emailFrom: string
  emailFromName: string
  preview: TaskPreview
}

export async function getTaskPreviewFromEmail(
  account: EmailAccount,
  emailId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<TaskPreviewResponse> {
  const url = new URL(`/email/${account}/task-preview`, baseUrl)
  
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({ email_id: emailId }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Task preview failed: ${resp.statusText}`)
  }
  return resp.json()
}

export interface TaskCreateRequest {
  emailId: string
  title: string
  dueDate?: string
  priority: string
  domain: string
  project?: string
  notes?: string
}

export interface FirestoreTask {
  id: string
  title: string
  status: string
  priority: string
  domain: string
  createdAt: string
  updatedAt: string
  // Three-date model
  plannedDate: string | null
  targetDate: string | null
  hardDeadline: string | null
  timesRescheduled: number
  dueDate: string | null  // Legacy
  effectiveDueDate: string | null
  // Core fields
  project: string | null
  number: number | null
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
}

export async function createTaskFromEmail(
  account: EmailAccount,
  request: TaskCreateRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ status: string; account: string; emailId: string; task: FirestoreTask }> {
  const url = new URL(`/email/${account}/task-create`, baseUrl)
  
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      email_id: request.emailId,
      title: request.title,
      due_date: request.dueDate,
      priority: request.priority,
      domain: request.domain,
      project: request.project,
      notes: request.notes,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Task creation failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function listFirestoreTasks(
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  options: { domain?: string; status?: string; source?: string; limit?: number } = {},
): Promise<{ count: number; tasks: FirestoreTask[] }> {
  const url = new URL('/tasks/firestore', baseUrl)
  if (options.domain) url.searchParams.set('domain', options.domain)
  if (options.status) url.searchParams.set('status', options.status)
  if (options.source) url.searchParams.set('source', options.source)
  if (options.limit) url.searchParams.set('limit', String(options.limit))
  
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `List tasks failed: ${resp.statusText}`)
  }
  return resp.json()
}

// --- Sync Service (Phase 1c - Internal Task System Migration) ---

export interface SyncStatusResponse {
  totalTasks: number
  synced: number
  pending: number
  localOnly: number
  conflicts: number
}

export interface SyncNowRequest {
  direction?: 'smartsheet_to_firestore' | 'firestore_to_smartsheet' | 'bidirectional'
  sources?: string[]
  include_work?: boolean
}

export interface SyncNowResponse {
  success: boolean
  direction: string
  created: number
  updated: number
  unchanged: number
  conflicts: number
  errors: string[]
  totalProcessed: number
  syncedAt: string
}

export async function getSyncStatus(
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<SyncStatusResponse> {
  const url = new URL('/sync/status', baseUrl)
  
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get sync status failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function triggerSync(
  request: SyncNowRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<SyncNowResponse> {
  const url = new URL('/sync/now', baseUrl)
  
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify(request),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Sync failed: ${resp.statusText}`)
  }
  return resp.json()
}

// --- Task CRUD (Phase 1d - Direct API, no LLM) ---

export interface CreateTaskRequest {
  title: string
  domain: 'personal' | 'church' | 'work'
  status?: string
  priority?: string
  project?: string
  plannedDate?: string  // ISO date string
  targetDate?: string
  hardDeadline?: string
  notes?: string
  estimatedHours?: number
}

export interface UpdateTaskRequest {
  title?: string
  status?: string
  priority?: string
  project?: string
  plannedDate?: string
  targetDate?: string
  hardDeadline?: string
  notes?: string
  estimatedHours?: number
  done?: boolean
}

export async function createFirestoreTask(
  request: CreateTaskRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ task: FirestoreTask }> {
  // This will need a new backend endpoint - for now, use a placeholder
  const url = new URL('/tasks/firestore', baseUrl)
  
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      title: request.title,
      domain: request.domain,
      status: request.status || 'scheduled',
      priority: request.priority || 'Standard',
      project: request.project,
      planned_date: request.plannedDate,
      target_date: request.targetDate,
      hard_deadline: request.hardDeadline,
      notes: request.notes,
      estimated_hours: request.estimatedHours,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Create task failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function updateFirestoreTask(
  taskId: string,
  updates: UpdateTaskRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ task: FirestoreTask }> {
  const url = new URL(`/tasks/firestore/${taskId}`, baseUrl)
  
  const resp = await fetch(url, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      title: updates.title,
      status: updates.status,
      priority: updates.priority,
      project: updates.project,
      planned_date: updates.plannedDate,
      target_date: updates.targetDate,
      hard_deadline: updates.hardDeadline,
      notes: updates.notes,
      estimated_hours: updates.estimatedHours,
      done: updates.done,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Update task failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function deleteFirestoreTask(
  taskId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ status: string; taskId: string }> {
  const url = new URL(`/tasks/firestore/${taskId}`, baseUrl)
  
  const resp = await fetch(url, {
    method: 'DELETE',
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Delete task failed: ${resp.statusText}`)
  }
  return resp.json()
}

// Email-Task linkage info
export interface EmailTaskInfo {
  taskId: string
  title: string
  status: string
  priority: string
}

export interface CheckEmailTasksResponse {
  account: string
  emailsChecked: number
  emailsWithTasks: number
  tasks: Record<string, EmailTaskInfo>  // email_id -> task info
}

export async function checkEmailsHaveTasks(
  account: EmailAccount,
  emailIds: string[],
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<CheckEmailTasksResponse> {
  const url = new URL(`/email/${account}/check-tasks`, baseUrl)
  
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({ email_ids: emailIds }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Check tasks failed: ${resp.statusText}`)
  }
  return resp.json()
}


// --- Email Action Suggestions (Phase A3) ---

export type EmailActionType = 'label' | 'archive' | 'delete' | 'star' | 'mark_important' | 'create_task' | 'reply'

export interface EmailActionSuggestion {
  number: number
  emailId: string
  from: string
  fromName: string
  to: string
  subject: string
  snippet: string
  date: string
  isUnread: boolean
  isImportant: boolean
  isStarred: boolean
  action: EmailActionType
  rationale: string
  labelId: string | null
  labelName: string | null
  taskTitle: string | null
  confidence: 'high' | 'medium' | 'low'
  suggestionId?: string  // Set when persisted to backend
}

export interface EmailSuggestionsResponse {
  account: string
  email: string
  messagesAnalyzed: number
  availableLabels: GmailLabel[]
  suggestions: EmailActionSuggestion[]
}

export async function getEmailActionSuggestions(
  account: EmailAccount,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  maxMessages: number = 30,
): Promise<EmailSuggestionsResponse> {
  const url = new URL(`/email/${account}/suggestions`, baseUrl)
  url.searchParams.set('max_messages', String(maxMessages))
  
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get suggestions failed: ${resp.statusText}`)
  }
  return resp.json()
}

export interface PendingActionSuggestionsResponse {
  account: string
  suggestions: EmailActionSuggestion[]
  count: number
}

/**
 * Get persisted pending action suggestions for the specified account.
 *
 * These are suggestions that were saved during Analyze Inbox and can be
 * displayed after page refresh without re-analyzing.
 */
export async function getPendingActionSuggestions(
  account: EmailAccount,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<PendingActionSuggestionsResponse> {
  const url = new URL(`/email/suggestions/${account}/pending`, baseUrl)

  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get pending suggestions failed: ${resp.statusText}`)
  }
  return resp.json()
}


// =============================================================================
// Email Full Message and Reply API Functions
// =============================================================================

import type { EmailReplyDraft, CalendarView } from './types'

export interface FullMessageResponse {
  account: EmailAccount
  message: EmailMessage
  stale?: boolean
  staleMessage?: string | null
}

/**
 * Fetch a single email message with optional full body content.
 */
export async function getEmailFull(
  account: EmailAccount,
  messageId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  full: boolean = true,
): Promise<FullMessageResponse> {
  const url = new URL(`/email/${account}/message/${messageId}`, baseUrl)
  url.searchParams.set('full', String(full))
  
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get email failed: ${resp.statusText}`)
  }
  return resp.json()
}


export interface ThreadContextResponse {
  account: EmailAccount
  threadId: string
  messageCount: number
  summary: string | null
  messages: Array<{
    id: string
    threadId: string
    fromAddress: string
    fromName: string
    subject: string
    snippet: string
    date: string
    body?: string
    bodyHtml?: string
  }>
}

/**
 * Fetch thread context for composing a reply.
 * Returns all messages in the thread with an optional AI summary.
 */
export async function getThreadContext(
  account: EmailAccount,
  threadId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<ThreadContextResponse> {
  const url = new URL(`/email/${account}/thread/${threadId}`, baseUrl)
  
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get thread context failed: ${resp.statusText}`)
  }
  return resp.json()
}


export interface ReplyDraftRequest {
  messageId: string
  replyAll: boolean
  userContext?: string
}

export interface ReplyDraftResponse {
  account: EmailAccount
  originalMessageId: string
  draft: EmailReplyDraft
}

/**
 * Generate a human-like reply draft using DATA.
 */
export async function generateReplyDraft(
  account: EmailAccount,
  request: ReplyDraftRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<ReplyDraftResponse> {
  const url = new URL(`/email/${account}/reply-draft`, baseUrl)
  
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      messageId: request.messageId,
      replyAll: request.replyAll,
      userContext: request.userContext,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Generate reply draft failed: ${resp.statusText}`)
  }
  return resp.json()
}


export interface ReplySendRequest {
  messageId: string
  replyAll: boolean
  subject: string
  body: string
  cc?: string[]
}

export interface ReplySendResponse {
  status: 'sent'
  account: EmailAccount
  sentMessageId: string
  originalMessageId: string
  threadId: string
  to: string
  cc: string | null
}

/**
 * Send a reply to an email with proper threading headers.
 */
export async function sendReply(
  account: EmailAccount,
  request: ReplySendRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<ReplySendResponse> {
  const url = new URL(`/email/${account}/reply-send`, baseUrl)

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({
      messageId: request.messageId,
      replyAll: request.replyAll,
      subject: request.subject,
      body: request.body,
      cc: request.cc,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Send reply failed: ${resp.statusText}`)
  }
  return resp.json()
}


// =============================================================================
// User Profile API Functions
// =============================================================================

import type { UserProfile } from './types'

export interface ProfileResponse {
  profile: UserProfile
}

export interface ProfileUpdateRequest {
  churchRoles?: string[]
  personalContexts?: string[]
  vipSenders?: Record<string, string[]>
  churchAttentionPatterns?: Record<string, string[]>
  personalAttentionPatterns?: Record<string, string[]>
  notActionablePatterns?: Record<string, string[]>
}

/**
 * Fetch the current user's profile for role-aware email management.
 */
export async function getProfile(
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<ProfileResponse> {
  const url = new URL('/profile', baseUrl)

  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get profile failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Update the current user's profile.
 * Only provided fields are updated; omitted fields retain their current values.
 */
export async function updateProfile(
  request: ProfileUpdateRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<ProfileResponse> {
  const url = new URL('/profile', baseUrl)

  const resp = await fetch(url, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify(request),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Update profile failed: ${resp.statusText}`)
  }
  return resp.json()
}


// =============================================================================
// Sender Blocklist API (Privacy Controls)
// =============================================================================

export interface BlocklistResponse {
  blocklist: string[]
}

export interface BlocklistAddResponse {
  success: boolean
  senderEmail: string
  reason?: string
}

export interface BlocklistRemoveResponse {
  success: boolean
  senderEmail: string
  reason?: string
}

/**
 * Get the current sender blocklist.
 * Blocklist is stored at GLOBAL level (shared across login identities).
 */
export async function getBlocklist(
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<BlocklistResponse> {
  const url = new URL('/profile/blocklist', baseUrl)

  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get blocklist failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Add a sender email to the blocklist.
 * DATA will not see body content from blocked senders unless override is granted.
 */
export async function addToBlocklist(
  senderEmail: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<BlocklistAddResponse> {
  const url = new URL('/profile/blocklist/add', baseUrl)

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({ senderEmail }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Add to blocklist failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Remove a sender email from the blocklist.
 */
export async function removeFromBlocklist(
  senderEmail: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<BlocklistRemoveResponse> {
  const url = new URL('/profile/blocklist/remove', baseUrl)

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({ senderEmail }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Remove from blocklist failed: ${resp.statusText}`)
  }
  return resp.json()
}


// =============================================================================
// Email Privacy Status API
// =============================================================================

export interface EmailPrivacyCheckResponse {
  emailId: string
  fromAddress: string
  privacy: {
    isBlocked: boolean
    reason: string | null
    senderBlocked: boolean
    domainSensitive: boolean
    labelSensitive: boolean
    canRequestOverride: boolean
    overrideGranted?: boolean  // User previously shared this email with DATA
  }
}

/**
 * Check privacy status for an email.
 * Returns whether DATA can see the email body and why it might be blocked.
 */
export async function getEmailPrivacyStatus(
  account: EmailAccount,
  emailId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<EmailPrivacyCheckResponse> {
  const url = new URL(`/email/${account}/privacy/${emailId}`, baseUrl)

  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get privacy status failed: ${resp.statusText}`)
  }
  return resp.json()
}


// =============================================================================
// Email Conversation Persistence API
// =============================================================================

export interface EmailConversationMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  emailContext?: string
  metadata?: Record<string, unknown>
}

export interface EmailConversationResponse {
  account: string
  threadId: string
  messages: EmailConversationMessage[]
  metadata?: {
    subject?: string
    fromEmail?: string
    fromName?: string
    lastEmailDate?: string
    sensitivity?: string
  }
}

export interface ClearConversationResponse {
  success: boolean
  threadId: string
  messagesCleared: number
}

/**
 * Get conversation history for an email thread.
 * Conversations are persisted for 90 days.
 */
export async function getEmailConversation(
  account: EmailAccount,
  threadId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  limit: number = 50,
): Promise<EmailConversationResponse> {
  const url = new URL(`/email/${account}/conversation/${threadId}`, baseUrl)
  url.searchParams.set('limit', String(limit))

  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get conversation failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Clear conversation history for an email thread.
 */
export async function clearEmailConversation(
  account: EmailAccount,
  threadId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<ClearConversationResponse> {
  const url = new URL(`/email/${account}/conversation/${threadId}`, baseUrl)

  const resp = await fetch(url, {
    method: 'DELETE',
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Clear conversation failed: ${resp.statusText}`)
  }
  return resp.json()
}


// --- Pinned Emails (Quick Reference) ---

export interface PinnedEmail {
  emailId: string
  account: string
  subject: string
  fromAddress: string
  snippet: string
  pinnedAt: string
  threadId?: string
}

export interface PinnedEmailsResponse {
  account: string
  pinned: PinnedEmail[]
  count: number
}

export interface PinEmailResponse {
  success: boolean
  emailId: string
  account: string
  pinnedAt: string
}

export interface UnpinEmailResponse {
  success: boolean
  emailId: string
  account: string
}

/**
 * Pin an email for quick reference.
 * Pinned emails appear in the Pinned tab for easy access.
 */
export async function pinEmail(
  account: EmailAccount,
  emailId: string,
  subject: string,
  fromAddress: string,
  snippet: string,
  threadId: string | undefined,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<PinEmailResponse> {
  const url = new URL(`/email/${account}/pin/${emailId}`, baseUrl)

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({ subject, fromAddress, snippet, threadId }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Pin email failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Unpin an email (soft delete with 30-day TTL).
 */
export async function unpinEmail(
  account: EmailAccount,
  emailId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<UnpinEmailResponse> {
  const url = new URL(`/email/${account}/pin/${emailId}`, baseUrl)

  const resp = await fetch(url, {
    method: 'DELETE',
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Unpin email failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Get all pinned emails for the account.
 */
export async function getPinnedEmails(
  account: EmailAccount,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<PinnedEmailsResponse> {
  const url = new URL(`/email/${account}/pinned`, baseUrl)

  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get pinned emails failed: ${resp.statusText}`)
  }
  return resp.json()
}


// --- Suggestion Tracking (Sprint 5) ---

/**
 * Record a decision (approve/reject) on a suggestion.
 * This feedback is critical for the Trust Gradient learning system.
 * Account is now required (storage is by account, not user).
 */
export async function decideSuggestion(
  account: EmailAccount,
  suggestionId: string,
  approved: boolean,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<SuggestionDecisionResponse> {
  const url = new URL(`/email/suggestions/${account}/${suggestionId}/decide`, baseUrl)

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({ approved }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Decide suggestion failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Get all pending suggestions for the specified account.
 * Account is now required (storage is by account, not user).
 */
export async function getPendingSuggestions(
  account: EmailAccount,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<PendingSuggestionsResponse> {
  const url = new URL(`/email/suggestions/${account}/pending`, baseUrl)

  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get pending suggestions failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Get suggestion approval statistics for Trust Gradient tracking.
 * Account is now required (storage is by account, not user).
 */
export async function getSuggestionStats(
  account: EmailAccount,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  days: number = 30,
): Promise<SuggestionStats> {
  const url = new URL(`/email/suggestions/${account}/stats`, baseUrl)
  url.searchParams.set('days', String(days))

  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get suggestion stats failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Get frequently rejected patterns that could be added to not-actionable.
 */
export async function getRejectionPatterns(
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  days: number = 30,
  minRejections: number = 3,
): Promise<RejectionPatternsResponse> {
  const url = new URL('/email/suggestions/rejection-patterns', baseUrl)
  url.searchParams.set('days', String(days))
  url.searchParams.set('min_rejections', String(minRejections))

  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get rejection patterns failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Add a pattern to the not-actionable list.
 * This teaches DATA to skip emails matching this pattern.
 */
export async function addNotActionablePattern(
  account: EmailAccount,
  pattern: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<AddPatternResponse> {
  const url = new URL('/profile/not-actionable/add', baseUrl)

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({ account, pattern }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Add pattern failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Remove a pattern from the not-actionable list.
 */
export async function removeNotActionablePattern(
  account: EmailAccount,
  pattern: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<AddPatternResponse> {
  const url = new URL('/profile/not-actionable/remove', baseUrl)

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({ account, pattern }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Remove pattern failed: ${resp.statusText}`)
  }
  return resp.json()
}


// =============================================================================
// Rule Suggestion API
// =============================================================================

export interface RuleSuggestionRecord {
  ruleId: string
  emailAccount: string
  suggestionType: string
  suggestedRule: {
    field: string
    operator: string
    value: string
    action: string
    category: string
    emailAccount?: string
    order?: number
  }
  reason: string
  examples: string[]
  emailCount: number
  confidence: number
  analysisMethod: string
  category: string
  status: string
  decidedAt?: string
  rejectionReason?: string
  createdAt: string
}

export interface PendingRulesResponse {
  account: string
  rules: RuleSuggestionRecord[]
  count: number
}

export interface RuleDecisionResponse {
  status: 'approved' | 'rejected'
  ruleId: string
  rule?: RuleSuggestionRecord
}

/**
 * Get all pending rule suggestions for the specified account.
 */
export async function getPendingRules(
  account: EmailAccount,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<PendingRulesResponse> {
  const url = new URL(`/email/rules/${account}/pending`, baseUrl)

  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get pending rules failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Decide (approve/reject) a rule suggestion.
 */
export async function decideRuleSuggestion(
  account: EmailAccount,
  ruleId: string,
  approved: boolean,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  rejectionReason?: string,
): Promise<RuleDecisionResponse> {
  const url = new URL(`/email/rules/${account}/${ruleId}/decide`, baseUrl)

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      ...buildHeaders(auth),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ approved, rejectionReason }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Decide rule failed: ${resp.statusText}`)
  }
  return resp.json()
}


// =============================================================================
// Haiku Intelligence Layer API (F1)
// =============================================================================

export interface HaikuSettings {
  enabled: boolean
  dailyLimit: number
  weeklyLimit: number
}

export interface HaikuUsage {
  dailyCount: number
  weeklyCount: number
  dailyLimit: number
  weeklyLimit: number
  dailyRemaining: number
  weeklyRemaining: number
  canAnalyze: boolean
  enabled: boolean
}

export interface HaikuSettingsResponse {
  settings: HaikuSettings
}

export interface HaikuSettingsUpdateRequest {
  enabled?: boolean
  daily_limit?: number
  weekly_limit?: number
}

export interface HaikuUsageResponse {
  usage: HaikuUsage
}

/**
 * Get current Haiku analysis settings for the user.
 */
export async function getHaikuSettings(
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<HaikuSettingsResponse> {
  const url = new URL('/email/haiku/settings', baseUrl)

  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get Haiku settings failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Update Haiku analysis settings.
 * Only provided fields are updated.
 */
export async function updateHaikuSettings(
  request: HaikuSettingsUpdateRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ status: string; settings: HaikuSettings }> {
  const url = new URL('/email/haiku/settings', baseUrl)

  const resp = await fetch(url, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify(request),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Update Haiku settings failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Get current Haiku usage statistics.
 * Shows daily/weekly counts, limits, remaining capacity.
 */
export async function getHaikuUsage(
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<HaikuUsageResponse> {
  const url = new URL('/email/haiku/usage', baseUrl)

  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get Haiku usage failed: ${resp.statusText}`)
  }
  return resp.json()
}


// =============================================================================
// Calendar API Functions
// =============================================================================

/**
 * List all calendars accessible by this account.
 */
export async function listCalendars(
  account: CalendarAccount,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  showHidden = false,
): Promise<CalendarListResponse> {
  const url = new URL(`/calendar/${account}/calendars`, baseUrl)
  if (showHidden) {
    url.searchParams.set('showHidden', 'true')
  }

  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `List calendars failed: ${resp.statusText}`)
  }
  return resp.json()
}

export interface ListEventsOptions {
  calendarId?: string
  timeMin?: string  // ISO datetime
  timeMax?: string  // ISO datetime
  maxResults?: number
  pageToken?: string
  sourceDomain?: 'personal' | 'work' | 'church'
}

/**
 * List events from a calendar.
 */
export async function listEvents(
  account: CalendarAccount,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  options: ListEventsOptions = {},
): Promise<EventListResponse> {
  const url = new URL(`/calendar/${account}/events`, baseUrl)

  if (options.calendarId) url.searchParams.set('calendarId', options.calendarId)
  if (options.timeMin) url.searchParams.set('timeMin', options.timeMin)
  if (options.timeMax) url.searchParams.set('timeMax', options.timeMax)
  if (options.maxResults) url.searchParams.set('maxResults', String(options.maxResults))
  if (options.pageToken) url.searchParams.set('pageToken', options.pageToken)
  if (options.sourceDomain) url.searchParams.set('sourceDomain', options.sourceDomain)

  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `List events failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Get a specific calendar event by ID.
 */
export async function getCalendarEvent(
  account: CalendarAccount,
  eventId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  calendarId = 'primary',
  sourceDomain: 'personal' | 'work' | 'church' = 'personal',
): Promise<CalendarEventResponse> {
  const url = new URL(`/calendar/${account}/events/${eventId}`, baseUrl)
  url.searchParams.set('calendarId', calendarId)
  url.searchParams.set('sourceDomain', sourceDomain)

  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get event failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Create a new calendar event.
 */
export async function createCalendarEvent(
  account: CalendarAccount,
  request: CreateEventRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ status: string; account: string; event: CalendarEventResponse['event'] }> {
  const url = new URL(`/calendar/${account}/events`, baseUrl)

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify(request),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Create event failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Update an existing calendar event.
 */
export async function updateCalendarEvent(
  account: CalendarAccount,
  eventId: string,
  request: UpdateEventRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ status: string; account: string; event: CalendarEventResponse['event'] }> {
  const url = new URL(`/calendar/${account}/events/${eventId}`, baseUrl)

  const resp = await fetch(url, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify(request),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Update event failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Delete a calendar event.
 */
export async function deleteCalendarEvent(
  account: CalendarAccount,
  eventId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  calendarId = 'primary',
  sendNotifications = true,
): Promise<{ status: string; account: string; eventId: string; calendarId: string }> {
  const url = new URL(`/calendar/${account}/events/${eventId}`, baseUrl)
  url.searchParams.set('calendarId', calendarId)
  url.searchParams.set('sendNotifications', String(sendNotifications))

  const resp = await fetch(url, {
    method: 'DELETE',
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Delete event failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Create an event using natural language.
 * Google Calendar will parse the text to create an event.
 * Example: "Meeting with Doug tomorrow at 2pm"
 */
export async function quickAddCalendarEvent(
  account: CalendarAccount,
  request: QuickAddEventRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ status: string; account: string; event: CalendarEventResponse['event'] }> {
  const url = new URL(`/calendar/${account}/quick-add`, baseUrl)

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify(request),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Quick add event failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Get calendar display settings for an account.
 */
export async function getCalendarSettings(
  account: CalendarAccount,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<CalendarSettingsResponse> {
  const url = new URL(`/calendar/${account}/settings`, baseUrl)

  const resp = await fetch(url, {
    headers: buildHeaders(auth),
    cache: 'no-store',  // Prevent browser caching of settings
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get calendar settings failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Update calendar display settings for an account.
 */
export async function updateCalendarSettings(
  account: CalendarAccount,
  request: UpdateCalendarSettingsRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ status: string; account: string; settings: CalendarSettingsResponse['settings'] }> {
  const url = new URL(`/calendar/${account}/settings`, baseUrl)

  const resp = await fetch(url, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify(request),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Update calendar settings failed: ${resp.statusText}`)
  }
  return resp.json()
}


// =============================================================================
// Calendar Attention API Functions (Phase CA-1)
// =============================================================================

/**
 * Get active calendar attention items for an account.
 */
export async function getCalendarAttention(
  account: CalendarAccount,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<CalendarAttentionListResponse> {
  const url = new URL(`/calendar/${account}/attention`, baseUrl)

  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get calendar attention failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Mark a calendar attention item as viewed.
 * Phase 1A: Records first_viewed_at for response latency metrics.
 */
export async function markCalendarAttentionViewed(
  account: CalendarAccount,
  eventId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ success: boolean; eventId: string; account: string }> {
  const url = new URL(`/calendar/${account}/attention/${eventId}/viewed`, baseUrl)

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Mark calendar attention viewed failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Dismiss a calendar attention item.
 */
export async function dismissCalendarAttention(
  account: CalendarAccount,
  eventId: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ success: boolean; eventId: string; account: string }> {
  const url = new URL(`/calendar/${account}/attention/${eventId}/dismiss`, baseUrl)

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Dismiss calendar attention failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Mark a calendar attention item as acted upon.
 */
export async function markCalendarAttentionActed(
  account: CalendarAccount,
  eventId: string,
  actionType: 'task_linked' | 'prep_started' = 'task_linked',
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ success: boolean; eventId: string; account: string; actionType: string }> {
  const url = new URL(`/calendar/${account}/attention/${eventId}/act`, baseUrl)
  url.searchParams.set('action_type', actionType)

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Mark calendar attention acted failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Get quality metrics for calendar attention items.
 * Phase 1A: Returns acceptance rates, dismissal rates, and breakdowns.
 */
export async function getCalendarAttentionQualityMetrics(
  account: CalendarAccount,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  days = 30,
): Promise<CalendarAttentionQualityMetrics> {
  const url = new URL(`/calendar/${account}/attention/quality-metrics`, baseUrl)
  url.searchParams.set('days', String(days))

  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get calendar attention metrics failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Analyze upcoming calendar events and create attention items.
 */
export async function analyzeCalendarEvents(
  account: CalendarAccount,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  daysAhead = 7,
): Promise<CalendarAttentionAnalyzeResponse> {
  const url = new URL(`/calendar/${account}/attention/analyze`, baseUrl)
  url.searchParams.set('days_ahead', String(daysAhead))

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Analyze calendar events failed: ${resp.statusText}`)
  }
  return resp.json()
}


// =============================================================================
// Calendar Chat (DATA Calendar Integration)
// =============================================================================

export interface CalendarEventContext {
  id: string
  summary: string
  start: string  // ISO datetime
  end: string    // ISO datetime
  location?: string
  attendees?: Array<{
    email: string
    displayName?: string
    responseStatus?: string
    isSelf?: boolean
  }>
  description?: string
  htmlLink?: string
  isMeeting?: boolean
  sourceDomain?: string
}

export interface CalendarAttentionContext {
  eventId: string
  summary: string
  start: string  // ISO datetime
  attentionType: string
  reason: string
  matchedVip?: string
}

export interface CalendarChatRequest {
  message: string
  selectedEventId?: string
  selectedTaskId?: string  // Row ID of selected task in DATA panel
  dateRangeStart?: string  // ISO datetime
  dateRangeEnd?: string    // ISO datetime
  events?: CalendarEventContext[]
  attentionItems?: CalendarAttentionContext[]
  tasks?: Array<Record<string, unknown>>
  history?: Array<{ role: string; content: string }>
}

export interface CalendarPendingAction {
  action: string
  domain: string
  reason: string
  eventId?: string
  summary?: string
  startDatetime?: string
  endDatetime?: string
  location?: string
  description?: string
}

export interface CalendarPendingTaskCreation {
  taskTitle: string
  reason: string
  dueDate?: string
  priority?: string
  domain?: string
  project?: string
  notes?: string
  relatedEventId?: string
}

export interface CalendarPendingTaskUpdate {
  action: TaskUpdateAction
  reason: string
  rowId?: string
  source?: 'personal' | 'work'  // Which Smartsheet to update
  status?: string
  priority?: string
  dueDate?: string
  comment?: string
  number?: number
  contactFlag?: boolean
  recurring?: string
  project?: string
  taskTitle?: string
  assignedTo?: string
  notes?: string
  estimatedHours?: string
}

export interface CalendarChatResponse {
  response: string
  domain: string
  pendingCalendarAction?: CalendarPendingAction
  pendingTaskCreation?: CalendarPendingTaskCreation
  pendingTaskUpdate?: CalendarPendingTaskUpdate
}

export interface CalendarConversationMessage {
  role: string
  content: string
  ts: string
  eventContext?: string
}

export interface CalendarConversationMetadata {
  domain: string
  createdAt: string
  expiresAt?: string
  messageCount: number
  lastMessageAt?: string
}

export interface CalendarConversationResponse {
  domain: string
  messages: CalendarConversationMessage[]
  messageCount: number
  metadata?: CalendarConversationMetadata
}

/**
 * Chat with DATA about calendar and tasks.
 *
 * DATA can help analyze schedule, suggest task adjustments, create events,
 * and answer questions about workload.
 */
export async function chatAboutCalendar(
  domain: CalendarView,
  request: CalendarChatRequest,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<CalendarChatResponse> {
  const url = new URL(`/calendar/${domain}/chat`, baseUrl)

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify(request),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Calendar chat failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Get conversation history for a calendar domain.
 */
export async function getCalendarConversation(
  domain: CalendarView,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  limit: number = 50,
): Promise<CalendarConversationResponse> {
  const url = new URL(`/calendar/${domain}/conversation`, baseUrl)
  url.searchParams.append('limit', limit.toString())

  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Get calendar conversation failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Clear conversation history for a calendar domain.
 */
export async function clearCalendarConversation(
  domain: CalendarView,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ domain: string; cleared: boolean }> {
  const url = new URL(`/calendar/${domain}/conversation`, baseUrl)

  const resp = await fetch(url, {
    method: 'DELETE',
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Clear calendar conversation failed: ${resp.statusText}`)
  }
  return resp.json()
}

/**
 * Update/replace calendar conversation messages.
 * Used when deleting individual messages from chat history.
 */
export async function updateCalendarConversation(
  domain: CalendarView,
  messages: Array<{ role: string; content: string }>,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
): Promise<{ domain: string; updated: boolean; message_count: number }> {
  const url = new URL(`/calendar/${domain}/conversation`, baseUrl)

  const resp = await fetch(url, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...buildHeaders(auth),
    },
    body: JSON.stringify({ messages }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Update calendar conversation failed: ${resp.statusText}`)
  }
  return resp.json()
}
