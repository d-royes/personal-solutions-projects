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

