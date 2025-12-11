import type {
  ActivityEntry,
  AssistResponse,
  ConversationMessage,
  DataSource,
  TaskResponse,
  WorkBadge,
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
  options: { source?: DataSource; anthropicModel?: string; workspaceContext?: string } = {},
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
  source?: string
}

export function getAttachmentDownloadUrl(
  taskId: string,
  attachmentId: string,
  baseUrl: string = defaultBase,
): string {
  return `${baseUrl}/assist/${taskId}/attachment/${attachmentId}/download`
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
    // Add due date update if changed
    if (change.proposedDue && change.proposedDue !== change.currentDue) {
      updates.push({
        rowId: change.rowId,
        action: 'update_due_date',
        dueDate: change.proposedDue,
        reason: change.reason,
      })
    }
    
    // Add number update if changed
    if (change.proposedNumber != null && change.proposedNumber !== change.currentNumber) {
      updates.push({
        rowId: change.rowId,
        action: 'update_number',
        number: change.proposedNumber,
        reason: change.reason,
      })
    }
  }
  
  return updates
}

