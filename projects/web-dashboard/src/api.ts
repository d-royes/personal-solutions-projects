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

