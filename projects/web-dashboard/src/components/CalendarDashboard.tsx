import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import type { AuthConfig } from '../auth/types'
import type {
  CalendarAccount,
  CalendarView,
  CalendarEvent,
  CalendarInfo,
  CalendarSettings,
  CalendarAttentionItem,
  Task,
  TimelineItem,
} from '../types'
import {
  listCalendars,
  listEvents,
  getCalendarSettings,
  updateCalendarSettings,
  createCalendarEvent,
  updateCalendarEvent,
  deleteCalendarEvent,
  getCalendarAttention,
  analyzeCalendarEvents,
  chatAboutCalendar,
  getCalendarConversation,
  clearCalendarConversation,
  updateCalendarConversation,
  type ListEventsOptions,
  type CalendarChatResponse,
  type CalendarEventContext,
  type CalendarAttentionContext,
} from '../api'
import CalendarAttentionPanel from './CalendarAttentionPanel'
import { deriveDomain, getTaskPriority } from '../utils/domain'

// Per-account cache structure - exported for App.tsx to manage
export interface CalendarAccountCache {
  calendars: CalendarInfo[]
  events: CalendarEvent[]
  settings: CalendarSettings | null
  attentionItems: CalendarAttentionItem[]
  loaded: boolean
  loading: boolean
  error?: string
}

export const emptyCalendarCache = (): CalendarAccountCache => ({
  calendars: [],
  events: [],
  settings: null,
  attentionItems: [],
  loaded: false,
  loading: false,
})

export type CalendarCacheMap = Record<CalendarAccount, CalendarAccountCache>
// Alias for App.tsx compatibility
export type CalendarCacheState = CalendarCacheMap

interface CalendarDashboardProps {
  authConfig: AuthConfig
  apiBase: string
  onBack: () => void
  // Optional lifted state for persistence across mode switches
  cache?: CalendarCacheMap
  setCache?: React.Dispatch<React.SetStateAction<CalendarCacheMap>>
  selectedView?: CalendarView
  setSelectedView?: React.Dispatch<React.SetStateAction<CalendarView>>
  // Task integration props
  tasks?: Task[]
  tasksLoading?: boolean
  onRefreshTasks?: () => void
  onSelectTaskInTasksMode?: (taskId: string) => void
}

type CalendarTabView = 'dashboard' | 'events' | 'meetings' | 'tasks' | 'attention' | 'suggestions' | 'settings'

// Selected item type for DATA panel (either event or task)
type SelectedItem =
  | { type: 'event'; item: CalendarEvent }
  | { type: 'task'; item: Task }
  | null

// Helper to format date for display
function formatEventDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
}

function formatEventTime(dateStr: string, isAllDay: boolean): string {
  if (isAllDay) return 'All day'
  const date = new Date(dateStr)
  return date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  })
}

function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  const mins = minutes % 60
  if (mins === 0) return `${hours}h`
  return `${hours}h ${mins}m`
}

// Group events by date
function groupEventsByDate(events: CalendarEvent[]): Map<string, CalendarEvent[]> {
  const groups = new Map<string, CalendarEvent[]>()
  for (const event of events) {
    const dateKey = new Date(event.start).toDateString()
    if (!groups.has(dateKey)) {
      groups.set(dateKey, [])
    }
    groups.get(dateKey)!.push(event)
  }
  return groups
}

// Build unified timeline combining events and tasks
function buildUnifiedTimeline(
  events: CalendarEvent[],
  tasks: Task[],
  selectedView: CalendarView,
  daysAhead: number
): TimelineItem[] {
  const now = new Date()
  const futureDate = new Date()
  futureDate.setDate(futureDate.getDate() + daysAhead)

  const items: TimelineItem[] = []

  // Add events to timeline
  for (const event of events) {
    items.push({
      type: 'event',
      id: `event-${event.id}`,
      title: event.summary,
      dateKey: new Date(event.start).toDateString(),
      sortTime: new Date(event.start),
      sortPriority: 0, // Events sort by time, not priority
      sourceDomain: event.sourceDomain,
      event,
    })
  }

  // Add tasks to timeline (filtered by view and date range)
  for (const task of tasks) {
    // Skip tasks without due dates
    if (!task.due) continue

    const dueDate = new Date(task.due)
    // Skip tasks outside the date range
    if (dueDate < now || dueDate > futureDate) continue

    const taskDomain = deriveDomain(task)

    // Filter by view
    if (selectedView !== 'combined') {
      if (selectedView === 'personal' && taskDomain !== 'personal') continue
      if (selectedView === 'work' && taskDomain !== 'work') continue
      if (selectedView === 'church' && taskDomain !== 'church') continue
    }

    items.push({
      type: 'task',
      id: `task-${task.rowId}`,
      title: task.title,
      dateKey: dueDate.toDateString(),
      sortTime: dueDate,
      sortPriority: getTaskPriority(task.priority),
      sourceDomain: taskDomain,
      task,
    })
  }

  // Sort: by date, then events before tasks, then by time/priority
  items.sort((a, b) => {
    // First by date
    const dateCompare = new Date(a.dateKey).getTime() - new Date(b.dateKey).getTime()
    if (dateCompare !== 0) return dateCompare

    // Events before tasks within the same day
    if (a.type !== b.type) {
      return a.type === 'event' ? -1 : 1
    }

    // Events sort by time
    if (a.type === 'event' && b.type === 'event') {
      return a.sortTime.getTime() - b.sortTime.getTime()
    }

    // Tasks sort by priority
    return a.sortPriority - b.sortPriority
  })

  return items
}

// Group timeline items by date
function groupTimelineByDate(items: TimelineItem[]): Map<string, TimelineItem[]> {
  const groups = new Map<string, TimelineItem[]>()
  for (const item of items) {
    if (!groups.has(item.dateKey)) {
      groups.set(item.dateKey, [])
    }
    groups.get(item.dateKey)!.push(item)
  }
  return groups
}

// Parse date string and normalize to local midnight for accurate day comparisons
function toLocalMidnight(dateStr: string): Date {
  // Parse as local date by splitting the date string (avoids UTC interpretation)
  const [year, month, day] = dateStr.split('T')[0].split('-').map(Number)
  return new Date(year, month - 1, day, 0, 0, 0, 0)
}

function getTodayMidnight(): Date {
  const now = new Date()
  return new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0, 0)
}

// Format due date label for tasks
function formatDueLabel(due: string): string {
  const dueDate = toLocalMidnight(due)
  const today = getTodayMidnight()
  const diff = dueDate.getTime() - today.getTime()
  const days = Math.round(diff / (1000 * 60 * 60 * 24))
  if (days < 0) return `Overdue ${Math.abs(days)}d`
  if (days === 0) return 'Due today'
  if (days === 1) return 'Due tomorrow'
  return `Due in ${days}d`
}

// Get priority badge class
function getPriorityClass(priority: string | undefined): string {
  if (!priority) return ''
  const p = priority.toLowerCase()
  if (p.includes('critical') || p === '5-critical') return 'critical'
  if (p.includes('urgent') || p === '4-urgent') return 'urgent'
  if (p.includes('important') || p === '3-important') return 'important'
  return 'standard'
}

// Domain colors are now handled via CSS classes:
// .domain-personal, .domain-work, .domain-church

// Helper to format datetime for input fields
function formatDateTimeLocal(isoString: string): string {
  const date = new Date(isoString)
  return date.toISOString().slice(0, 16)
}

// Helper to format date only for input fields (all-day events)
function formatDateOnly(isoString: string): string {
  const date = new Date(isoString)
  return date.toISOString().slice(0, 10)
}

// Event Form Component for create/edit
function EventForm({
  event,
  calendars,
  defaultCalendarId,
  onSave,
  onCancel,
  isSaving,
}: {
  event: CalendarEvent | null
  calendars: CalendarInfo[]
  defaultCalendarId: string
  onSave: (eventData: {
    summary: string
    start: string
    end: string
    description?: string
    location?: string
    isAllDay?: boolean
    calendarId: string
  }) => void
  onCancel: () => void
  isSaving: boolean
}) {
  // Form state - initialize from event or defaults
  const isEditing = event !== null
  const now = new Date()
  const oneHourLater = new Date(now.getTime() + 60 * 60 * 1000)

  const [summary, setSummary] = useState(event?.summary || '')
  const [description, setDescription] = useState(event?.description || '')
  const [location, setLocation] = useState(event?.location || '')
  const [isAllDay, setIsAllDay] = useState(event?.isAllDay || false)
  const [calendarId, setCalendarId] = useState(event?.calendarId || defaultCalendarId)
  const [startDate, setStartDate] = useState(
    event ? formatDateOnly(event.start) : formatDateOnly(now.toISOString())
  )
  const [startTime, setStartTime] = useState(
    event && !event.isAllDay
      ? formatDateTimeLocal(event.start).slice(11, 16)
      : now.toTimeString().slice(0, 5)
  )
  const [endDate, setEndDate] = useState(
    event ? formatDateOnly(event.end) : formatDateOnly(oneHourLater.toISOString())
  )
  const [endTime, setEndTime] = useState(
    event && !event.isAllDay
      ? formatDateTimeLocal(event.end).slice(11, 16)
      : oneHourLater.toTimeString().slice(0, 5)
  )

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!summary.trim()) return

    let start: string
    let end: string

    if (isAllDay) {
      // All-day events use date strings
      start = startDate
      end = endDate
    } else {
      // Timed events use full datetime
      start = new Date(`${startDate}T${startTime}`).toISOString()
      end = new Date(`${endDate}T${endTime}`).toISOString()
    }

    onSave({
      summary: summary.trim(),
      start,
      end,
      description: description.trim() || undefined,
      location: location.trim() || undefined,
      isAllDay,
      calendarId,
    })
  }

  return (
    <div className="event-form-overlay">
      <form className="event-form" onSubmit={handleSubmit}>
        <h3 className="event-form-title">
          {isEditing ? 'Edit Event' : 'New Event'}
        </h3>

        {/* Calendar selector (only for new events, not editing) */}
        {!isEditing && calendars.length > 1 && (
          <div className="form-group">
            <label htmlFor="event-calendar">Calendar</label>
            <select
              id="event-calendar"
              value={calendarId}
              onChange={(e) => setCalendarId(e.target.value)}
              className="calendar-select"
            >
              {calendars.map(cal => (
                <option key={cal.id} value={cal.id}>
                  {cal.summary}{cal.isPrimary ? ' (Primary)' : ''}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Summary */}
        <div className="form-group">
          <label htmlFor="event-summary">Title</label>
          <input
            id="event-summary"
            type="text"
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="Event title"
            required
            autoFocus={!(!isEditing && calendars.length > 1)}
          />
        </div>

        {/* All-day toggle */}
        <div className="form-group checkbox">
          <label>
            <input
              type="checkbox"
              checked={isAllDay}
              onChange={(e) => setIsAllDay(e.target.checked)}
            />
            All-day event
          </label>
        </div>

        {/* Date/Time inputs */}
        <div className="form-row">
          <div className="form-group">
            <label htmlFor="event-start-date">Start Date</label>
            <input
              id="event-start-date"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              required
            />
          </div>
          {!isAllDay && (
            <div className="form-group">
              <label htmlFor="event-start-time">Start Time</label>
              <input
                id="event-start-time"
                type="time"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                required
              />
            </div>
          )}
        </div>

        <div className="form-row">
          <div className="form-group">
            <label htmlFor="event-end-date">End Date</label>
            <input
              id="event-end-date"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              required
            />
          </div>
          {!isAllDay && (
            <div className="form-group">
              <label htmlFor="event-end-time">End Time</label>
              <input
                id="event-end-time"
                type="time"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                required
              />
            </div>
          )}
        </div>

        {/* Location */}
        <div className="form-group">
          <label htmlFor="event-location">Location</label>
          <input
            id="event-location"
            type="text"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="Add location"
          />
        </div>

        {/* Description */}
        <div className="form-group">
          <label htmlFor="event-description">Description</label>
          <textarea
            id="event-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Add description"
            rows={3}
          />
        </div>

        {/* Form actions */}
        <div className="form-actions">
          <button
            type="button"
            className="btn-cancel"
            onClick={onCancel}
            disabled={isSaving}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="btn-save"
            disabled={isSaving || !summary.trim()}
          >
            {isSaving ? 'Saving...' : isEditing ? 'Update' : 'Create'}
          </button>
        </div>
      </form>
    </div>
  )
}

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
        title={leftCollapsed ? "Expand calendar" : "Collapse calendar"}
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

export function CalendarDashboard({
  authConfig,
  apiBase,
  onBack,
  cache: externalCache,
  setCache: setExternalCache,
  selectedView: externalSelectedView,
  setSelectedView: setExternalSelectedView,
  tasks = [],
  tasksLoading = false,
  onRefreshTasks,
  onSelectTaskInTasksMode,
}: CalendarDashboardProps) {
  // Use external state if provided, otherwise use local state
  const [localCache, setLocalCache] = useState<CalendarCacheMap>({
    personal: emptyCalendarCache(),
    church: emptyCalendarCache(),
  })
  const [localSelectedView, setLocalSelectedView] = useState<CalendarView>('personal')

  const cache = externalCache ?? localCache
  const setCache = setExternalCache ?? setLocalCache
  const selectedView = externalSelectedView ?? localSelectedView
  const setSelectedView = setExternalSelectedView ?? setLocalSelectedView

  const [activeTab, setActiveTab] = useState<CalendarTabView>('dashboard')
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(null)
  const [selectedItem, setSelectedItem] = useState<SelectedItem>(null)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [chatInput, setChatInput] = useState('')
  const [chatMessages, setChatMessages] = useState<Array<{ role: string; content: string }>>([])
  const [chatLoading, setChatLoading] = useState(false)
  const [pendingAction, setPendingAction] = useState<CalendarChatResponse | null>(null)
  const [detailCollapsed, setDetailCollapsed] = useState(false)

  // Event form state
  const [showEventForm, setShowEventForm] = useState(false)
  const [editingEvent, setEditingEvent] = useState<CalendarEvent | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  // Two-panel layout state
  const [calendarPanelCollapsed, setCalendarPanelCollapsed] = useState(false)
  const [assistPanelCollapsed, setAssistPanelCollapsed] = useState(false)
  const [panelSplitRatio, setPanelSplitRatio] = useState(50) // Percentage for left panel (50 = 50/50 split)
  const panelsContainerRef = useRef<HTMLDivElement>(null)

  // Map view to account(s)
  const getAccountsForView = useCallback((view: CalendarView): CalendarAccount[] => {
    switch (view) {
      case 'personal':
      case 'work':  // Work calendar is in personal account
        return ['personal']
      case 'church':
        return ['church']
      case 'combined':
        return ['personal', 'church']
      default:
        return ['personal']
    }
  }, [])

  // Load calendars and events for an account
  const loadAccountData = useCallback(async (account: CalendarAccount) => {
    setCache(prev => ({
      ...prev,
      [account]: { ...prev[account], loading: true, error: undefined },
    }))

    try {
      // Load calendars
      const calendarsResp = await listCalendars(account, authConfig, apiBase)

      // Load settings
      const settingsResp = await getCalendarSettings(account, authConfig, apiBase)

      // Determine which calendars to fetch events from
      const enabledCalendarIds = settingsResp.settings.enabledCalendars.length > 0
        ? settingsResp.settings.enabledCalendars
        : calendarsResp.calendars.map(c => c.id)

      // Load events from each enabled calendar
      const now = new Date()
      const futureDate = new Date()
      futureDate.setDate(futureDate.getDate() + (settingsResp.settings.defaultDaysAhead || 14))

      const allEvents: CalendarEvent[] = []
      const workCalendarId = settingsResp.settings.workCalendarId
      for (const calendarId of enabledCalendarIds) {
        try {
          // Determine sourceDomain: "work" for work calendar, otherwise account name
          const sourceDomain = (account === 'personal' && workCalendarId && calendarId === workCalendarId)
            ? 'work'
            : account
          const options: ListEventsOptions = {
            calendarId,
            timeMin: now.toISOString(),
            timeMax: futureDate.toISOString(),
            maxResults: 100,
            sourceDomain,
          }
          const eventsResp = await listEvents(account, authConfig, apiBase, options)
          allEvents.push(...eventsResp.events)
        } catch (err) {
          console.warn(`Failed to load events from calendar ${calendarId}:`, err)
        }
      }

      // Filter out events that have already ended (handles multi-day all-day events
      // that started before timeMin but overlap with the requested range)
      const nowTime = now.getTime()
      const activeEvents = allEvents.filter(e => new Date(e.end).getTime() > nowTime)

      // Sort events by start time
      activeEvents.sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())

      // Load attention items
      let attentionItems: CalendarAttentionItem[] = []
      try {
        const attentionResp = await getCalendarAttention(account, authConfig, apiBase)
        attentionItems = attentionResp.items
      } catch (err) {
        console.warn(`Failed to load attention items for ${account}:`, err)
      }

      setCache(prev => ({
        ...prev,
        [account]: {
          calendars: calendarsResp.calendars,
          events: activeEvents,
          settings: settingsResp.settings,
          attentionItems,
          loaded: true,
          loading: false,
        },
      }))
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to load calendar data'
      setCache(prev => ({
        ...prev,
        [account]: { ...prev[account], loading: false, error: errorMsg },
      }))
      setError(errorMsg)
    }
  }, [authConfig, apiBase, setCache])

  // Load data when view changes
  useEffect(() => {
    const accounts = getAccountsForView(selectedView)
    for (const account of accounts) {
      if (!cache[account].loaded && !cache[account].loading) {
        loadAccountData(account)
      }
    }
  }, [selectedView, cache, getAccountsForView, loadAccountData])

  // Get events for current view
  const eventsForView = useMemo(() => {
    const accounts = getAccountsForView(selectedView)
    let events: CalendarEvent[] = []
    const workCalendarId = cache.personal.settings?.workCalendarId

    for (const account of accounts) {
      const accountEvents = cache[account].events

      if (selectedView === 'work') {
        // Work view: only show events from the designated work calendar
        if (workCalendarId) {
          events.push(...accountEvents.filter(e => e.calendarId === workCalendarId))
        }
      } else if (selectedView === 'personal') {
        // Personal view: exclude work calendar events
        if (workCalendarId) {
          events.push(...accountEvents.filter(e => e.calendarId !== workCalendarId))
        } else {
          events.push(...accountEvents)
        }
      } else {
        // Church and Combined views: include all events
        events.push(...accountEvents)
      }
    }

    // Sort by start time
    events.sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())
    return events
  }, [selectedView, cache, getAccountsForView])

  // Filter for meetings only (events with multiple attendees)
  const meetingsForView = useMemo(() => {
    return eventsForView.filter(e => e.isMeeting)
  }, [eventsForView])

  // Build unified timeline (events + tasks)
  const daysAhead = cache.personal.settings?.defaultDaysAhead || 14
  const unifiedTimeline = useMemo(() => {
    return buildUnifiedTimeline(eventsForView, tasks, selectedView, daysAhead)
  }, [eventsForView, tasks, selectedView, daysAhead])

  // Count tasks in timeline
  const tasksInTimeline = useMemo(() => {
    return unifiedTimeline.filter(item => item.type === 'task').length
  }, [unifiedTimeline])

  // Filter unified timeline by search query
  const filteredUnifiedTimeline = useMemo(() => {
    if (!searchQuery.trim()) return unifiedTimeline
    const query = searchQuery.toLowerCase()
    return unifiedTimeline.filter(item => {
      // Search in title
      if (item.title.toLowerCase().includes(query)) return true
      // For events, also search in description and location
      if (item.event) {
        if (item.event.description?.toLowerCase().includes(query)) return true
        if (item.event.location?.toLowerCase().includes(query)) return true
      }
      // For tasks, also search in notes, project, nextStep
      if (item.task) {
        if (item.task.notes?.toLowerCase().includes(query)) return true
        if (item.task.project?.toLowerCase().includes(query)) return true
        if (item.task.nextStep?.toLowerCase().includes(query)) return true
      }
      return false
    })
  }, [unifiedTimeline, searchQuery])

  // Grouped timeline for display (uses filtered timeline)
  const groupedTimeline = useMemo(() => {
    return groupTimelineByDate(filteredUnifiedTimeline)
  }, [filteredUnifiedTimeline])

  // Show loading state if any required account is currently loading OR hasn't been loaded yet
  const isLoading = getAccountsForView(selectedView).some(a => cache[a].loading || !cache[a].loaded)

  // View switcher tabs
  const viewTabs: { view: CalendarView; label: string }[] = [
    { view: 'personal', label: 'Personal' },
    { view: 'work', label: 'Work' },
    { view: 'church', label: 'Church' },
    { view: 'combined', label: 'Combined' },
  ]

  // Content tabs - matching email dashboard structure
  // Get attention items count for current view
  const attentionItemsCount = useMemo(() => {
    const accounts = getAccountsForView(selectedView)
    return accounts.reduce((sum, account) => sum + (cache[account]?.attentionItems?.length || 0), 0)
  }, [selectedView, cache, getAccountsForView])

  // Get attention items for current view (flattened from all relevant accounts)
  const attentionItemsForView = useMemo(() => {
    const accounts = getAccountsForView(selectedView)
    const items: CalendarAttentionItem[] = []
    for (const account of accounts) {
      items.push(...(cache[account]?.attentionItems || []))
    }
    // Sort by start time (nearest first)
    items.sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())
    return items
  }, [selectedView, cache, getAccountsForView])

  // State for attention loading
  const [loadingAttention, setLoadingAttention] = useState(false)

  // Analyze events to find attention items
  const handleAnalyzeEvents = useCallback(async () => {
    const accounts = getAccountsForView(selectedView)
    setLoadingAttention(true)
    try {
      for (const account of accounts) {
        const response = await analyzeCalendarEvents(account, authConfig, apiBase, 7)
        setCache(prev => ({
          ...prev,
          [account]: {
            ...prev[account],
            attentionItems: response.items,
          },
        }))
      }
    } catch (err) {
      console.error('Failed to analyze events:', err)
      setError(err instanceof Error ? err.message : 'Failed to analyze events')
    } finally {
      setLoadingAttention(false)
    }
  }, [selectedView, getAccountsForView, authConfig, apiBase, setCache])

  // Handle attention item dismiss
  const handleAttentionDismiss = useCallback((eventId: string) => {
    // Remove from all relevant accounts in cache
    const accounts = getAccountsForView(selectedView)
    for (const account of accounts) {
      setCache(prev => ({
        ...prev,
        [account]: {
          ...prev[account],
          attentionItems: prev[account].attentionItems.filter(item => item.eventId !== eventId),
        },
      }))
    }
  }, [selectedView, getAccountsForView, setCache])

  // Handle attention item acted
  const handleAttentionAct = useCallback((eventId: string, _actionType: 'task_linked' | 'prep_started') => {
    // Remove from all relevant accounts in cache (item is now "acted upon")
    const accounts = getAccountsForView(selectedView)
    for (const account of accounts) {
      setCache(prev => ({
        ...prev,
        [account]: {
          ...prev[account],
          attentionItems: prev[account].attentionItems.filter(item => item.eventId !== eventId),
        },
      }))
    }
  }, [selectedView, getAccountsForView, setCache])

  // Handle sending chat message to DATA
  const handleSendChatMessage = useCallback(async () => {
    if (!chatInput.trim() || chatLoading) return

    const message = chatInput.trim()
    setChatInput('')
    setChatLoading(true)
    setPendingAction(null)

    // Add user message to display
    setChatMessages(prev => [...prev, { role: 'user', content: message }])

    try {
      // Build context for the API
      const eventContext: CalendarEventContext[] = eventsForView.map(e => ({
        id: e.id,
        summary: e.summary,
        start: e.start,
        end: e.end,
        location: e.location,
        attendees: e.attendees?.map(a => ({
          email: a.email,
          displayName: a.displayName,
          responseStatus: a.responseStatus,
          isSelf: a.isSelf,
        })),
        description: e.description,
        htmlLink: e.htmlLink,
        isMeeting: e.isMeeting,
        sourceDomain: e.sourceDomain,
      }))

      const attentionContext: CalendarAttentionContext[] = attentionItemsForView.map(item => ({
        eventId: item.eventId,
        summary: item.summary,
        start: item.start,
        attentionType: item.attentionType,
        reason: item.reason,
        matchedVip: item.matchedVip,
      }))

      // Filter tasks by domain (matching how events are filtered)
      const filteredTasks = selectedView === 'combined'
        ? tasks
        : tasks.filter(task => {
            const taskDomain = deriveDomain(task)
            return taskDomain === selectedView
          })

      // Compute date range for task filtering (same logic as event fetching)
      const now = new Date()
      const futureDate = new Date()
      futureDate.setDate(futureDate.getDate() + daysAhead)

      const response = await chatAboutCalendar(
        selectedView,
        {
          message,
          selectedEventId: selectedEvent?.id,
          dateRangeStart: now.toISOString(),
          dateRangeEnd: futureDate.toISOString(),
          events: eventContext,
          attentionItems: attentionContext,
          tasks: filteredTasks as unknown as Array<Record<string, unknown>>,
          history: chatMessages,
        },
        authConfig,
        apiBase
      )

      // Add assistant response
      setChatMessages(prev => [...prev, { role: 'assistant', content: response.response }])

      // Store pending action if any
      if (response.pendingCalendarAction || response.pendingTaskCreation || response.pendingTaskUpdate) {
        setPendingAction(response)
      }
    } catch (err) {
      console.error('Chat error:', err)
      setChatMessages(prev => [
        ...prev,
        { role: 'assistant', content: `Sorry, I encountered an error: ${err instanceof Error ? err.message : 'Unknown error'}` }
      ])
    } finally {
      setChatLoading(false)
    }
  }, [chatInput, chatLoading, eventsForView, attentionItemsForView, tasks, selectedEvent, selectedView, chatMessages, authConfig, apiBase])

  // Load conversation history when view changes
  useEffect(() => {
    const loadConversation = async () => {
      try {
        const response = await getCalendarConversation(selectedView, authConfig, apiBase, 50)
        setChatMessages(response.messages.map(m => ({ role: m.role, content: m.content })))
      } catch (err) {
        console.error('Failed to load conversation:', err)
        // Silent fail - just start with empty conversation
        setChatMessages([])
      }
    }
    loadConversation()
  }, [selectedView, authConfig, apiBase])

  // Get primary account for attention panel (for API calls)
  const primaryAccountForAttention = useMemo((): CalendarAccount => {
    const accounts = getAccountsForView(selectedView)
    return accounts[0] || 'personal'
  }, [selectedView, getAccountsForView])

  // Tasks tab count shows only tasks within the date window (respects Days to Show setting)
  const contentTabs: { tab: CalendarTabView; label: string; count?: number }[] = [
    { tab: 'dashboard', label: 'Dashboard' },
    { tab: 'events', label: 'Events', count: eventsForView.length },
    { tab: 'meetings', label: 'Meetings', count: meetingsForView.length },
    { tab: 'tasks', label: 'Tasks', count: tasksInTimeline },
    { tab: 'attention', label: 'Attention', count: attentionItemsCount },
    { tab: 'suggestions', label: 'Suggestions', count: 0 }, // Future: task-event matches
    { tab: 'settings', label: 'Settings' },
  ]

  // Filter events by search query
  const filteredEvents = useMemo(() => {
    if (!searchQuery.trim()) return eventsForView
    const query = searchQuery.toLowerCase()
    return eventsForView.filter(e =>
      e.summary.toLowerCase().includes(query) ||
      e.location?.toLowerCase().includes(query) ||
      e.description?.toLowerCase().includes(query)
    )
  }, [eventsForView, searchQuery])

  const filteredMeetings = useMemo(() => {
    if (!searchQuery.trim()) return meetingsForView
    const query = searchQuery.toLowerCase()
    return meetingsForView.filter(e =>
      e.summary.toLowerCase().includes(query) ||
      e.location?.toLowerCase().includes(query) ||
      e.description?.toLowerCase().includes(query)
    )
  }, [meetingsForView, searchQuery])

  // Grouped events for display (using filtered results)
  const displayGroupedEvents = useMemo(() => {
    const events = activeTab === 'meetings' ? filteredMeetings : filteredEvents
    return groupEventsByDate(events)
  }, [activeTab, filteredEvents, filteredMeetings])

  // Handle refresh
  const handleRefresh = () => {
    const accounts = getAccountsForView(selectedView)
    for (const account of accounts) {
      // Force reload by clearing loaded flag
      setCache(prev => ({
        ...prev,
        [account]: { ...prev[account], loaded: false },
      }))
    }
  }

  // Toggle panel collapse states
  function handleToggleCalendarPanel() {
    setCalendarPanelCollapsed(!calendarPanelCollapsed)
    // If collapsing calendar panel, ensure assist is visible
    if (!calendarPanelCollapsed) {
      setAssistPanelCollapsed(false)
    }
  }

  function handleToggleAssistPanel() {
    setAssistPanelCollapsed(!assistPanelCollapsed)
    // If collapsing assist panel, ensure calendar is visible
    if (!assistPanelCollapsed) {
      setCalendarPanelCollapsed(false)
    }
  }

  // Expand both panels
  function handleExpandBoth() {
    setCalendarPanelCollapsed(false)
    setAssistPanelCollapsed(false)
  }

  // Handle panel divider drag
  function handlePanelDrag(delta: number) {
    if (!panelsContainerRef.current) return
    const containerWidth = panelsContainerRef.current.offsetWidth
    const deltaPercent = (delta / containerWidth) * 100
    setPanelSplitRatio(prev => Math.max(20, Math.min(80, prev + deltaPercent)))
  }

  // Handle Edit Event
  function handleEditEvent(event: CalendarEvent) {
    setEditingEvent(event)
    setShowEventForm(true)
  }

  // Handle New Event
  function handleNewEvent() {
    setEditingEvent(null)
    setShowEventForm(true)
  }

  // Handle Delete Event
  async function handleDeleteEvent(event: CalendarEvent) {
    if (!confirm(`Delete "${event.summary}"?`)) return

    const account: CalendarAccount = event.sourceDomain === 'church' ? 'church' : 'personal'

    setIsSaving(true)
    try {
      await deleteCalendarEvent(account, event.id, authConfig, apiBase, event.calendarId)
      setSelectedEvent(null)
      // Reload calendar data
      loadAccountData(account)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete event')
    } finally {
      setIsSaving(false)
    }
  }

  // Handle Save Event (create or update)
  async function handleSaveEvent(eventData: {
    summary: string
    start: string
    end: string
    description?: string
    location?: string
    isAllDay?: boolean
    calendarId: string
  }) {
    // Determine account based on current view
    const account: CalendarAccount = selectedView === 'church' ? 'church' : 'personal'

    setIsSaving(true)
    try {
      if (editingEvent) {
        // Update existing event (use original calendar)
        await updateCalendarEvent(
          account,
          editingEvent.id,
          { ...eventData, calendarId: editingEvent.calendarId },
          authConfig,
          apiBase
        )
      } else {
        // Create new event (use selected calendar from form)
        await createCalendarEvent(
          account,
          eventData,
          authConfig,
          apiBase
        )
      }
      setShowEventForm(false)
      setEditingEvent(null)
      // Reload calendar data
      loadAccountData(account)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save event')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className={`email-dashboard two-panel ${calendarPanelCollapsed ? 'email-collapsed' : ''} ${assistPanelCollapsed ? 'assist-collapsed' : ''}`}>
      {/* Header - 3-column layout: back button | centered title | view selector */}
      <header className="email-dashboard-header">
        <button className="back-button" onClick={onBack}>
          ← Back to Tasks
        </button>
        <h1>Calendar Management</h1>
        {/* View Switcher - uses same styling as email account selector */}
        <div className="account-selector">
          {viewTabs.map(({ view, label }) => (
            <button
              key={view}
              className={`account-tab ${selectedView === view ? 'active' : ''}`}
              onClick={() => setSelectedView(view)}
            >
              {label}
            </button>
          ))}
        </div>
      </header>

      {/* Error display */}
      {error && (
        <div className="error">
          {error}
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      {/* Two-panel content area */}
      <div className="email-panels" ref={panelsContainerRef}>
        {/* Left Panel - Event List */}
        {calendarPanelCollapsed ? (
          <div className="collapsed-panel-indicator left" onClick={handleExpandBoth}>
            <span className="collapsed-label">Calendar</span>
          </div>
        ) : (
        <section
          className="email-left-panel"
          style={{ width: assistPanelCollapsed ? '100%' : `${panelSplitRatio}%` }}
        >
          {/* Content Tabs - grouped like email tabs */}
          <nav className="email-tabs">
            {contentTabs.map(({ tab, label, count }) => (
              <button
                key={tab}
                className={activeTab === tab ? 'active' : ''}
                onClick={() => setActiveTab(tab)}
              >
                {label}
                {count !== undefined && (
                  <span className="tab-count"> ({count})</span>
                )}
              </button>
            ))}
          </nav>

          {/* Tab content */}
          <div className="email-tab-content">
            {isLoading && (
              <div className="loading">Loading calendar data...</div>
            )}

            {/* Dashboard Tab */}
            {activeTab === 'dashboard' && !isLoading && (
              <div className="calendar-dashboard-view">
                {/* Stats grid */}
                <div className="stats-grid">
                  <div
                    className="stat-card clickable"
                    onClick={() => setActiveTab('events')}
                    title="View all events"
                  >
                    <div className="stat-value">{eventsForView.length}</div>
                    <div className="stat-label">Events</div>
                  </div>
                  <div
                    className="stat-card clickable"
                    onClick={() => setActiveTab('meetings')}
                    title="View meetings"
                  >
                    <div className="stat-value">{meetingsForView.length}</div>
                    <div className="stat-label">Meetings</div>
                  </div>
                  <div
                    className="stat-card important clickable"
                    onClick={() => setActiveTab('suggestions')}
                    title="View suggestions"
                  >
                    <div className="stat-value">0</div>
                    <div className="stat-label">Suggestions</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-value">{cache.personal.settings?.defaultDaysAhead || 14}</div>
                    <div className="stat-label">Days Ahead</div>
                  </div>
                </div>

                {/* Search and refresh - matching email style */}
                <div className="action-buttons">
                  <div className="email-search-container">
                    <input
                      type="text"
                      placeholder="Search events..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="email-search-input"
                    />
                  </div>
                  <button
                    className="action-btn"
                    onClick={handleRefresh}
                    disabled={isLoading}
                  >
                    Refresh
                  </button>
                </div>

                {/* Show upcoming events on dashboard */}
                <h3 className="section-header">Upcoming Events</h3>
                {displayGroupedEvents.size === 0 ? (
                  <div className="empty-state">
                    No events in the next {cache.personal.settings?.defaultDaysAhead || 14} days
                  </div>
                ) : (
                  Array.from(displayGroupedEvents.entries()).slice(0, 3).map(([dateKey, events]) => (
                    <div key={dateKey} className="calendar-date-group">
                      <div className="calendar-date-header">
                        {formatEventDate(events[0].start)}
                      </div>
                      {events.slice(0, 5).map(event => (
                        <div
                          key={`${event.calendarId}-${event.id}`}
                          onClick={() => setSelectedEvent(event)}
                          className={`calendar-event-item domain-${event.sourceDomain} ${selectedEvent?.id === event.id ? 'selected' : ''}`}
                        >
                          <div className="calendar-event-time">
                            {formatEventTime(event.start, event.isAllDay)}
                          </div>
                          <div className="calendar-event-details">
                            <div className="calendar-event-title">{event.summary}</div>
                            {event.location && (
                              <div className="calendar-event-location">{event.location}</div>
                            )}
                            {event.isMeeting && (
                              <div className="calendar-event-attendees">
                                {event.attendeeCount} attendees
                              </div>
                            )}
                          </div>
                          {!event.isAllDay && (
                            <div className="calendar-event-duration">
                              {formatDuration(event.durationMinutes)}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Events/Meetings Tab */}
            {(activeTab === 'events' || activeTab === 'meetings') && !isLoading && (
              <>
                {/* Search and refresh - matching email style */}
                <div className="action-buttons">
                  <div className="email-search-container">
                    <input
                      type="text"
                      placeholder={`Search ${activeTab}...`}
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="email-search-input"
                    />
                  </div>
                  <button
                    className="action-btn"
                    onClick={handleRefresh}
                    disabled={isLoading}
                  >
                    Refresh
                  </button>
                </div>

                {displayGroupedEvents.size === 0 && (
                  <div className="empty-state">
                    No {activeTab === 'meetings' ? 'meetings' : 'events'} in the next{' '}
                    {cache.personal.settings?.defaultDaysAhead || 14} days
                  </div>
                )}
                {Array.from(displayGroupedEvents.entries()).map(([dateKey, events]) => (
                  <div key={dateKey} className="calendar-date-group">
                    <div className="calendar-date-header">
                      {formatEventDate(events[0].start)}
                    </div>
                    {events.map(event => (
                      <div
                        key={`${event.calendarId}-${event.id}`}
                        onClick={() => setSelectedEvent(event)}
                        className={`calendar-event-item domain-${event.sourceDomain} ${selectedEvent?.id === event.id ? 'selected' : ''}`}
                      >
                        <div className="calendar-event-time">
                          {formatEventTime(event.start, event.isAllDay)}
                        </div>
                        <div className="calendar-event-details">
                          <div className="calendar-event-title">{event.summary}</div>
                          {event.location && (
                            <div className="calendar-event-location">{event.location}</div>
                          )}
                          {event.isMeeting && (
                            <div className="calendar-event-attendees">
                              {event.attendeeCount} attendees
                            </div>
                          )}
                        </div>
                        {!event.isAllDay && (
                          <div className="calendar-event-duration">
                            {formatDuration(event.durationMinutes)}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ))}
              </>
            )}

            {/* Tasks Tab - Unified Timeline View */}
            {activeTab === 'tasks' && !isLoading && (
              <>
                {/* Search and refresh - matching event tab style */}
                <div className="action-buttons">
                  <div className="email-search-container">
                    <input
                      type="text"
                      placeholder="Search timeline..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="email-search-input"
                    />
                  </div>
                  <button
                    className="action-btn"
                    onClick={() => {
                      handleRefresh()
                      onRefreshTasks?.()
                    }}
                    disabled={isLoading || tasksLoading}
                  >
                    Refresh
                  </button>
                </div>

                {/* Timeline header showing counts */}
                <div className="timeline-header">
                  <span className="timeline-count">
                    {searchQuery.trim()
                      ? `${filteredUnifiedTimeline.filter(i => i.type === 'event').length} events + ${filteredUnifiedTimeline.filter(i => i.type === 'task').length} tasks (filtered)`
                      : `${eventsForView.length} events + ${tasksInTimeline} tasks`
                    }
                  </span>
                </div>

                {groupedTimeline.size === 0 && (
                  <div className="empty-state">
                    No events or tasks in the next {daysAhead} days
                  </div>
                )}

                {Array.from(groupedTimeline.entries()).map(([dateKey, items]) => (
                  <div key={dateKey} className="calendar-date-group">
                    <div className="calendar-date-header">
                      {formatEventDate(items[0].type === 'event' ? items[0].event!.start : items[0].task!.due)}
                    </div>
                    {items.map(item => (
                      item.type === 'event' ? (
                        // Render event item
                        <div
                          key={item.id}
                          onClick={() => {
                            setSelectedEvent(item.event!)
                            setSelectedItem({ type: 'event', item: item.event! })
                          }}
                          className={`calendar-event-item domain-${item.sourceDomain} ${selectedItem?.type === 'event' && selectedItem.item.id === item.event!.id ? 'selected' : ''}`}
                        >
                          <div className="timeline-icon event-icon">📅</div>
                          <div className="calendar-event-time">
                            {formatEventTime(item.event!.start, item.event!.isAllDay)}
                          </div>
                          <div className="calendar-event-details">
                            <div className="calendar-event-title">{item.title}</div>
                            {item.event!.location && (
                              <div className="calendar-event-location">{item.event!.location}</div>
                            )}
                          </div>
                          {!item.event!.isAllDay && (
                            <div className="calendar-event-duration">
                              {formatDuration(item.event!.durationMinutes)}
                            </div>
                          )}
                        </div>
                      ) : (
                        // Render task item
                        <div
                          key={item.id}
                          onClick={() => {
                            setSelectedEvent(null)
                            setSelectedItem({ type: 'task', item: item.task! })
                          }}
                          className={`calendar-task-item domain-${item.sourceDomain} ${selectedItem?.type === 'task' && selectedItem.item.rowId === item.task!.rowId ? 'selected' : ''}`}
                        >
                          <div className="timeline-icon task-icon">
                            {item.task!.done ? '✓' : '☐'}
                          </div>
                          <div className="calendar-task-due">
                            {formatDueLabel(item.task!.due)}
                          </div>
                          <div className="calendar-task-details">
                            <div className="calendar-task-title">{item.title}</div>
                            {item.task!.project && (
                              <div className="calendar-task-project">{item.task!.project}</div>
                            )}
                          </div>
                          {item.task!.priority && (
                            <div className={`calendar-task-priority ${getPriorityClass(item.task!.priority)}`}>
                              {item.task!.priority}
                            </div>
                          )}
                        </div>
                      )
                    ))}
                  </div>
                ))}
              </>
            )}

            {/* Attention Tab - Calendar items needing attention (Phase CA-1) */}
            {activeTab === 'attention' && !isLoading && (
              <div className="calendar-attention-view">
                <div className="attention-header">
                  <button
                    className="analyze-btn"
                    onClick={handleAnalyzeEvents}
                    disabled={loadingAttention}
                  >
                    {loadingAttention ? 'Analyzing...' : 'Analyze Events'}
                  </button>
                  <span className="help-text">
                    Scan upcoming events for VIP meetings and prep needs
                  </span>
                </div>
                <CalendarAttentionPanel
                  items={attentionItemsForView}
                  account={primaryAccountForAttention}
                  authConfig={authConfig}
                  apiBase={apiBase}
                  onDismiss={handleAttentionDismiss}
                  onAct={handleAttentionAct}
                  onSelectEvent={(eventId) => {
                    // Find the event and select it
                    const event = eventsForView.find(e => e.id === eventId)
                    if (event) {
                      setSelectedItem({ type: 'event', item: event })
                    }
                  }}
                  loading={loadingAttention}
                />
              </div>
            )}

            {/* Suggestions Tab - Placeholder for future task-event matching */}
            {activeTab === 'suggestions' && !isLoading && (
              <div className="calendar-suggestions-view">
                <div className="empty-state">
                  <p>No task-event suggestions yet.</p>
                  <p style={{ fontSize: '0.85rem', opacity: 0.7, marginTop: '0.5rem' }}>
                    DATA will suggest connections between your tasks and calendar events here.
                  </p>
                </div>
              </div>
            )}

            {/* Settings Tab */}
            {activeTab === 'settings' && (
              <CalendarSettingsPanel
                cache={cache}
                selectedView={selectedView}
                authConfig={authConfig}
                apiBase={apiBase}
                onSettingsUpdate={() => {
                  const accounts = getAccountsForView(selectedView)
                  for (const account of accounts) {
                    loadAccountData(account)
                  }
                }}
              />
            )}
          </div>
        </section>
        )}

        {/* Panel Divider */}
        <PanelDivider
          onDrag={handlePanelDrag}
          onCollapseLeft={handleToggleCalendarPanel}
          onCollapseRight={handleToggleAssistPanel}
          leftCollapsed={calendarPanelCollapsed}
          rightCollapsed={assistPanelCollapsed}
        />

        {/* Right Panel - DATA Panel */}
        {assistPanelCollapsed ? (
          <div className="collapsed-panel-indicator right" onClick={handleExpandBoth}>
            <span className="collapsed-label">DATA</span>
          </div>
        ) : (
        <section
          className="email-right-panel"
          style={{ width: calendarPanelCollapsed ? '100%' : `${100 - panelSplitRatio}%` }}
        >
          <div className="email-assist-content">
            {/* DATA Header with Clear Chat and New Event buttons */}
            <div className="email-assist-header">
              <h2>DATA</h2>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                {chatMessages.length > 0 && (
                  <button
                    className="clear-chat-btn"
                    onClick={async () => {
                      setChatMessages([])
                      try {
                        await clearCalendarConversation(selectedView, authConfig, apiBase)
                      } catch (err) {
                        console.error('Failed to clear conversation:', err)
                      }
                    }}
                    title="Clear chat history"
                  >
                    Clear Chat
                  </button>
                )}
                {selectedView !== 'work' && (
                  <button
                    className="new-event-btn"
                    onClick={handleNewEvent}
                    disabled={isSaving}
                    title="Create new event"
                  >
                    + New Event
                  </button>
                )}
              </div>
            </div>

            {/* Event Form Modal */}
            {showEventForm && (() => {
              const account: CalendarAccount = selectedView === 'church' ? 'church' : 'personal'
              const accountCache = cache[account]
              const enabledCalendars = accountCache.calendars.filter(c =>
                accountCache.settings?.enabledCalendars.includes(c.id)
              )
              const availableCalendars = enabledCalendars.length > 0 ? enabledCalendars : accountCache.calendars
              const primaryCal = availableCalendars.find(c => c.isPrimary) || availableCalendars[0]
              const defaultCalId = editingEvent?.calendarId || primaryCal?.id || ''

              return (
                <EventForm
                  event={editingEvent}
                  calendars={availableCalendars}
                  defaultCalendarId={defaultCalId}
                  onSave={handleSaveEvent}
                  onCancel={() => {
                    setShowEventForm(false)
                    setEditingEvent(null)
                  }}
                  isSaving={isSaving}
                />
              )
            })()}

            {/* Event Preview - shown when event is selected */}
            {selectedEvent && !showEventForm && (!selectedItem || selectedItem.type === 'event') ? (
              <>
                <div className="calendar-event-preview">
                  {/* Header with title, controls */}
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '8px', marginBottom: '8px' }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <h3 className="preview-title" style={{ margin: 0 }}>{selectedEvent.summary}</h3>
                      <span className={`calendar-domain-badge ${selectedEvent.sourceDomain}`} style={{ marginTop: '4px' }}>
                        {selectedEvent.sourceDomain}
                      </span>
                    </div>
                    <div style={{ display: 'flex', gap: '4px', flexShrink: 0 }}>
                      <button
                        onClick={() => setDetailCollapsed(!detailCollapsed)}
                        style={{
                          background: 'transparent',
                          border: '1px solid rgba(255,255,255,0.2)',
                          borderRadius: '4px',
                          padding: '4px 8px',
                          cursor: 'pointer',
                          color: 'inherit',
                          fontSize: '12px',
                        }}
                        title={detailCollapsed ? 'Expand details' : 'Collapse details'}
                      >
                        {detailCollapsed ? '▼' : '▲'}
                      </button>
                      <button
                        onClick={() => { setSelectedEvent(null); setSelectedItem(null); }}
                        style={{
                          background: 'transparent',
                          border: '1px solid rgba(255,255,255,0.2)',
                          borderRadius: '4px',
                          padding: '4px 8px',
                          cursor: 'pointer',
                          color: 'inherit',
                          fontSize: '12px',
                        }}
                        title="Close and use full chat"
                      >
                        ✕
                      </button>
                    </div>
                  </div>

                  {/* Collapsible detail content */}
                  {!detailCollapsed && (
                    <>

                  {/* Date & Time */}
                  <div className="preview-row">
                    <span className="preview-icon">📆</span>
                    <span className="preview-text">
                      {new Date(selectedEvent.start).toLocaleDateString('en-US', {
                        weekday: 'long',
                        month: 'long',
                        day: 'numeric',
                        year: 'numeric',
                      })}
                    </span>
                  </div>
                  {!selectedEvent.isAllDay && (
                    <div className="preview-row">
                      <span className="preview-icon">⏰</span>
                      <span className="preview-text">
                        {new Date(selectedEvent.start).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}
                        {' - '}
                        {new Date(selectedEvent.end).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}
                        {' '}
                        <span className="preview-duration">({formatDuration(selectedEvent.durationMinutes)})</span>
                      </span>
                    </div>
                  )}

                  {/* Location */}
                  {selectedEvent.location && (
                    <div className="preview-row">
                      <span className="preview-icon">📍</span>
                      <span className="preview-text">{selectedEvent.location}</span>
                    </div>
                  )}

                  {/* Description */}
                  {selectedEvent.description && (
                    <div className="preview-description">
                      <div className="preview-label">Description</div>
                      <div className="preview-text">{selectedEvent.description}</div>
                    </div>
                  )}

                  {/* Attendees */}
                  {selectedEvent.isMeeting && selectedEvent.attendees.length > 0 && (
                    <div className="preview-attendees">
                      <div className="preview-label">Attendees ({selectedEvent.attendeeCount})</div>
                      {selectedEvent.attendees.slice(0, 5).map(attendee => (
                        <div key={attendee.email} className="calendar-attendee">
                          <span className={`status-dot ${attendee.responseStatus === 'accepted' ? 'accepted' : attendee.responseStatus === 'declined' ? 'declined' : attendee.responseStatus === 'tentative' ? 'tentative' : 'pending'}`} />
                          {attendee.displayName || attendee.email}
                          {attendee.isOrganizer && <span className="organizer-badge">(organizer)</span>}
                        </div>
                      ))}
                      {selectedEvent.attendeeCount > 5 && (
                        <div className="more-attendees">+{selectedEvent.attendeeCount - 5} more</div>
                      )}
                    </div>
                  )}

                  {/* Compact Action Bar */}
                  <div className="calendar-action-bar">
                    {selectedEvent.htmlLink && (
                      <a
                        href={selectedEvent.htmlLink}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="calendar-action-btn open"
                        title="Open in Google Calendar"
                      >
                        <span className="action-icon">🔗</span>
                        <span className="action-label">Open</span>
                      </a>
                    )}
                    {selectedEvent.sourceDomain !== 'work' && (
                      <>
                        <button
                          className="calendar-action-btn edit"
                          onClick={() => handleEditEvent(selectedEvent)}
                          disabled={isSaving}
                          title="Edit event"
                        >
                          <span className="action-icon">✏️</span>
                          <span className="action-label">Edit</span>
                        </button>
                        <button
                          className="calendar-action-btn delete"
                          onClick={() => handleDeleteEvent(selectedEvent)}
                          disabled={isSaving}
                          title="Delete event"
                        >
                          <span className="action-icon">🗑️</span>
                          <span className="action-label">Delete</span>
                        </button>
                      </>
                    )}
                    {selectedEvent.sourceDomain === 'work' && (
                      <span className="calendar-readonly-badge">Read-only</span>
                    )}
                  </div>
                  </>
                  )}
                </div>

{/* Quick action buttons removed - chat area below handles DATA interaction */}
              </>
            ) : selectedItem?.type === 'task' && !showEventForm ? (
              // Task Preview - shown when task is selected in Tasks tab
              <>
                <div className="calendar-task-preview">
                  {/* Header with title, controls */}
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '8px', marginBottom: '8px' }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <h3 className="preview-title" style={{ margin: 0 }}>{selectedItem.item.title}</h3>
                      <span className={`calendar-domain-badge ${deriveDomain(selectedItem.item)}`} style={{ marginTop: '4px' }}>
                        {deriveDomain(selectedItem.item)}
                      </span>
                    </div>
                    <div style={{ display: 'flex', gap: '4px', flexShrink: 0 }}>
                      <button
                        onClick={() => setDetailCollapsed(!detailCollapsed)}
                        style={{
                          background: 'transparent',
                          border: '1px solid rgba(255,255,255,0.2)',
                          borderRadius: '4px',
                          padding: '4px 8px',
                          cursor: 'pointer',
                          color: 'inherit',
                          fontSize: '12px',
                        }}
                        title={detailCollapsed ? 'Expand details' : 'Collapse details'}
                      >
                        {detailCollapsed ? '▼' : '▲'}
                      </button>
                      <button
                        onClick={() => { setSelectedEvent(null); setSelectedItem(null); }}
                        style={{
                          background: 'transparent',
                          border: '1px solid rgba(255,255,255,0.2)',
                          borderRadius: '4px',
                          padding: '4px 8px',
                          cursor: 'pointer',
                          color: 'inherit',
                          fontSize: '12px',
                        }}
                        title="Close and use full chat"
                      >
                        ✕
                      </button>
                    </div>
                  </div>

                  {/* Collapsible detail content */}
                  {!detailCollapsed && (
                  <>
                  {/* Due Date */}
                  <div className="preview-row">
                    <span className="preview-icon">📆</span>
                    <span className="preview-text">
                      {formatDueLabel(selectedItem.item.due)}
                      {' - '}
                      {new Date(selectedItem.item.due).toLocaleDateString('en-US', {
                        weekday: 'long',
                        month: 'long',
                        day: 'numeric',
                      })}
                    </span>
                  </div>

                  {/* Status */}
                  <div className="preview-row">
                    <span className="preview-icon">📋</span>
                    <span className="preview-text">
                      Status: <strong>{selectedItem.item.status || 'Unknown'}</strong>
                    </span>
                  </div>

                  {/* Priority */}
                  {selectedItem.item.priority && (
                    <div className="preview-row">
                      <span className="preview-icon">⚡</span>
                      <span className={`preview-text priority-${getPriorityClass(selectedItem.item.priority)}`}>
                        Priority: <strong>{selectedItem.item.priority}</strong>
                      </span>
                    </div>
                  )}

                  {/* Project */}
                  {selectedItem.item.project && (
                    <div className="preview-row">
                      <span className="preview-icon">📁</span>
                      <span className="preview-text">{selectedItem.item.project}</span>
                    </div>
                  )}

                  {/* Notes */}
                  {selectedItem.item.notes && (
                    <div className="preview-description">
                      <strong>Notes:</strong>
                      <div className="preview-notes">{selectedItem.item.notes}</div>
                    </div>
                  )}

                  {/* Next Step */}
                  {selectedItem.item.nextStep && (
                    <div className="preview-description">
                      <strong>Next Step:</strong>
                      <div className="preview-next-step">{selectedItem.item.nextStep}</div>
                    </div>
                  )}

                  {/* Action Buttons */}
                  <div className="calendar-event-actions">
                    <button
                      className="calendar-action-btn primary"
                      onClick={() => {
                        onSelectTaskInTasksMode?.(selectedItem.item.rowId)
                      }}
                      title="Open in Task Management"
                    >
                      <span className="action-icon">📝</span>
                      <span className="action-label">Open Task</span>
                    </button>
                  </div>
                  </>
                  )}
                </div>

{/* Quick action buttons removed - chat area below handles DATA interaction */}
              </>
            ) : !showEventForm && chatMessages.length === 0 ? (
              // Only show empty state when no event selected AND no chat messages
              <div className="calendar-empty-state">
                <div className="icon">{activeTab === 'tasks' ? '📋' : '📅'}</div>
                <div className="title">
                  {activeTab === 'tasks' ? 'Select an item to view details' : 'Select an event to view details'}
                </div>
                <div className="subtitle">
                  {activeTab === 'tasks'
                    ? 'Click on any event or task in the timeline to see more information'
                    : 'Click on any event in the list to see more information'}
                </div>
              </div>
            ) : null}

            {/* Chat Messages - styled to match Email DATA panel */}
            <div className="email-chat-messages">
              {chatMessages.length === 0 && !chatLoading ? (
                <div className="chat-empty-state">
                  <div className="chat-empty-icon">💬</div>
                  <p>Ask DATA about your calendar, events, or tasks</p>
                </div>
              ) : (
                <>
                  {chatMessages.map((msg, idx) => (
                    <div key={idx} className={`chat-message ${msg.role}`}>
                      <button
                        className="chat-message-delete"
                        onClick={async () => {
                          const newMessages = chatMessages.filter((_, i) => i !== idx)
                          setChatMessages(newMessages)
                          try {
                            await updateCalendarConversation(selectedView, newMessages, authConfig, apiBase)
                          } catch (err) {
                            console.error('Failed to update conversation:', err)
                          }
                        }}
                        title="Delete message"
                      >
                        ✕
                      </button>
                      <div className="chat-message-content">{msg.content}</div>
                    </div>
                  ))}
                  {chatLoading && (
                    <div className="chat-message assistant loading">
                      <div className="chat-message-content">DATA is thinking...</div>
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Chat Input - styled to match Email DATA panel */}
            <div className="email-chat-input">
              <input
                type="text"
                placeholder="Ask DATA about your calendar or tasks..."
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                disabled={chatLoading}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && chatInput.trim() && !chatLoading) {
                    handleSendChatMessage()
                  }
                }}
              />
              <button
                disabled={!chatInput.trim() || chatLoading}
                onClick={handleSendChatMessage}
              >
                {chatLoading ? '...' : 'Send'}
              </button>
            </div>
          </div>
        </section>
        )}
      </div>
    </div>
  )
}

// Calendar Settings Panel Component
function CalendarSettingsPanel({
  cache,
  selectedView,
  authConfig,
  apiBase,
  onSettingsUpdate,
}: {
  cache: CalendarCacheMap
  selectedView: CalendarView
  authConfig: AuthConfig
  apiBase: string
  onSettingsUpdate: () => void
}) {
  const account: CalendarAccount = selectedView === 'church' ? 'church' : 'personal'
  const accountCache = cache[account]
  const [saving, setSaving] = useState(false)
  const [localSettings, setLocalSettings] = useState<CalendarSettings | null>(null)

  useEffect(() => {
    setLocalSettings(accountCache.settings)
  }, [accountCache.settings])

  const handleToggleCalendar = (calendarId: string) => {
    if (!localSettings) return
    const enabled = localSettings.enabledCalendars.includes(calendarId)
    const newEnabled = enabled
      ? localSettings.enabledCalendars.filter(id => id !== calendarId)
      : [...localSettings.enabledCalendars, calendarId]
    setLocalSettings({ ...localSettings, enabledCalendars: newEnabled })
  }

  const handleSave = async () => {
    if (!localSettings) return
    setSaving(true)
    try {
      await updateCalendarSettings(account, {
        enabledCalendars: localSettings.enabledCalendars,
        workCalendarId: localSettings.workCalendarId,
        showDeclinedEvents: localSettings.showDeclinedEvents,
        showAllDayEvents: localSettings.showAllDayEvents,
        defaultDaysAhead: localSettings.defaultDaysAhead,
      }, authConfig, apiBase)
      onSettingsUpdate()
    } catch (err) {
      console.error('Failed to save settings:', err)
    } finally {
      setSaving(false)
    }
  }

  if (!localSettings) {
    return <div style={{ color: '#888' }}>Loading settings...</div>
  }

  return (
    <div>
      <h3 style={{ color: '#e0e0e0', marginBottom: '16px' }}>
        Calendar Settings ({account})
      </h3>

      {/* Enabled Calendars */}
      <div style={{ marginBottom: '24px' }}>
        <h4 style={{ color: '#4cc9f0', fontSize: '14px', marginBottom: '12px' }}>
          Enabled Calendars
        </h4>
        {accountCache.calendars.map(cal => (
          <div
            key={cal.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              padding: '8px 12px',
              backgroundColor: '#252538',
              borderRadius: '6px',
              marginBottom: '8px',
            }}
          >
            <input
              type="checkbox"
              checked={localSettings.enabledCalendars.includes(cal.id)}
              onChange={() => handleToggleCalendar(cal.id)}
              style={{ cursor: 'pointer' }}
            />
            <div
              style={{
                width: '12px',
                height: '12px',
                borderRadius: '3px',
                backgroundColor: cal.backgroundColor || '#888',
              }}
            />
            <span style={{ color: '#e0e0e0', flex: 1 }}>{cal.summary}</span>
            {cal.isPrimary && (
              <span style={{ fontSize: '11px', color: '#4cc9f0' }}>Primary</span>
            )}
          </div>
        ))}
      </div>

      {/* Work Calendar Designation (only for personal account) */}
      {account === 'personal' && (
        <div style={{ marginBottom: '24px' }}>
          <h4 style={{ color: '#4cc9f0', fontSize: '14px', marginBottom: '12px' }}>
            Work Calendar
          </h4>
          <select
            value={localSettings.workCalendarId || ''}
            onChange={(e) => setLocalSettings({
              ...localSettings,
              workCalendarId: e.target.value || undefined,
            })}
            style={{
              width: '100%',
              padding: '8px 12px',
              backgroundColor: '#252538',
              border: '1px solid #444',
              borderRadius: '6px',
              color: '#e0e0e0',
            }}
          >
            <option value="">Select work calendar...</option>
            {accountCache.calendars.map(cal => (
              <option key={cal.id} value={cal.id}>
                {cal.summary}
              </option>
            ))}
          </select>
          <div style={{ fontSize: '12px', color: '#888', marginTop: '4px' }}>
            This calendar will be shown in the &quot;Work&quot; view
          </div>
        </div>
      )}

      {/* Display Options */}
      <div style={{ marginBottom: '24px' }}>
        <h4 style={{ color: '#4cc9f0', fontSize: '14px', marginBottom: '12px' }}>
          Display Options
        </h4>
        <label style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          padding: '8px 12px',
          backgroundColor: '#252538',
          borderRadius: '6px',
          marginBottom: '8px',
          cursor: 'pointer',
        }}>
          <input
            type="checkbox"
            checked={localSettings.showAllDayEvents}
            onChange={(e) => setLocalSettings({
              ...localSettings,
              showAllDayEvents: e.target.checked,
            })}
          />
          <span style={{ color: '#e0e0e0' }}>Show all-day events</span>
        </label>
        <label style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          padding: '8px 12px',
          backgroundColor: '#252538',
          borderRadius: '6px',
          marginBottom: '8px',
          cursor: 'pointer',
        }}>
          <input
            type="checkbox"
            checked={localSettings.showDeclinedEvents}
            onChange={(e) => setLocalSettings({
              ...localSettings,
              showDeclinedEvents: e.target.checked,
            })}
          />
          <span style={{ color: '#e0e0e0' }}>Show declined events</span>
        </label>
      </div>

      {/* Days Ahead */}
      <div style={{ marginBottom: '24px' }}>
        <h4 style={{ color: '#4cc9f0', fontSize: '14px', marginBottom: '12px' }}>
          Days to Show
        </h4>
        <input
          type="number"
          min={1}
          max={90}
          value={localSettings.defaultDaysAhead}
          onChange={(e) => setLocalSettings({
            ...localSettings,
            defaultDaysAhead: parseInt(e.target.value) || 14,
          })}
          style={{
            width: '80px',
            padding: '8px 12px',
            backgroundColor: '#252538',
            border: '1px solid #444',
            borderRadius: '6px',
            color: '#e0e0e0',
          }}
        />
        <span style={{ color: '#888', marginLeft: '8px' }}>days ahead</span>
      </div>

      {/* Save Button */}
      <button
        onClick={handleSave}
        disabled={saving}
        style={{
          padding: '10px 24px',
          backgroundColor: '#4cc9f0',
          color: '#1a1a2e',
          border: 'none',
          borderRadius: '6px',
          cursor: saving ? 'not-allowed' : 'pointer',
          fontWeight: 600,
          opacity: saving ? 0.7 : 1,
        }}
      >
        {saving ? 'Saving...' : 'Save Settings'}
      </button>
    </div>
  )
}

export default CalendarDashboard
