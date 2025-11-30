import type {
  ActivityEntry,
  AssistResponse,
  ConversationMessage,
  DataSource,
  TaskResponse,
} from './types'
import type { AuthConfig } from './auth/types'

const defaultBase =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

const defaultSource: DataSource =
  (import.meta.env.VITE_API_DEFAULT_SOURCE as DataSource) ?? 'auto'

export interface FetchTasksOptions {
  source?: DataSource
  limit?: number
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
  const resp = await fetch(url, {
    headers: buildHeaders(auth),
  })
  if (!resp.ok) {
    throw new Error(`Tasks request failed: ${resp.statusText}`)
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

export interface PendingAction {
  action: 'mark_complete' | 'update_status' | 'update_priority' | 'update_due_date' | 'add_comment'
  status?: string
  priority?: string
  dueDate?: string
  comment?: string
  reason?: string
}

export interface ChatResponse {
  response: string
  history: ConversationMessage[]
  pendingAction?: PendingAction
}

export async function sendChatMessage(
  taskId: string,
  message: string,
  auth: AuthConfig,
  baseUrl: string = defaultBase,
  source: DataSource = 'auto',
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
      source,
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
  options: { source?: DataSource; anthropicModel?: string } = {},
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

// Task Update Types and Functions
export type TaskUpdateAction = 'mark_complete' | 'update_status' | 'update_priority' | 'update_due_date' | 'add_comment'

export interface TaskUpdateRequest {
  action: TaskUpdateAction
  status?: string
  priority?: string
  dueDate?: string
  comment?: string
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
      confirmed: request.confirmed,
    }),
  })
  if (!resp.ok) {
    const detail = await safeJson(resp)
    throw new Error(detail?.detail ?? `Task update failed: ${resp.statusText}`)
  }
  return resp.json()
}

