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
  emailDraft: string
  task: Task
  generator: string
  generatorNotes: string[]
  messageId?: string | null
  commentPosted?: boolean
  warnings?: string[]
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
    email_draft: string
    labels?: string[]
  }
}

export interface AssistResponse {
  plan: AssistPlan
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

