import type { Task, TimelineDomain } from '../types'

/**
 * Derives the domain (Personal, Church, Work) for a task based on its source and project.
 * - Work: source === 'work' (from work Smartsheet)
 * - Church: project name contains 'church' (case-insensitive)
 * - Personal: everything else
 */
export function deriveDomain(task: Task): TimelineDomain {
  // Work tasks come from the work Smartsheet
  if (task.source === 'work') return 'work'

  // For personal sheet tasks, check project name for church
  const project = task.project
  if (!project) return 'personal'

  const value = project.toLowerCase()
  if (value.includes('church')) return 'church'

  return 'personal'
}

/**
 * Maps a domain to a display label with proper capitalization.
 */
export function domainLabel(domain: TimelineDomain): string {
  return domain.charAt(0).toUpperCase() + domain.slice(1)
}

/**
 * Priority order for sorting tasks (lower = higher priority)
 */
export const PRIORITY_ORDER: Record<string, number> = {
  'Critical': 1,
  'Urgent': 2,
  'Important': 3,
  'Standard': 4,
  'Low': 5,
  '5-Critical': 1,
  '4-Urgent': 2,
  '3-Important': 3,
  '2-Standard': 4,
  '1-Low': 5,
}

/**
 * Gets the sort priority for a task (1-5, with 99 as fallback)
 */
export function getTaskPriority(priority: string | undefined): number {
  if (!priority) return 99
  return PRIORITY_ORDER[priority] ?? 99
}
