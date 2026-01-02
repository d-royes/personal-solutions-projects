import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import type { AuthConfig } from '../auth/types'
import type {
  CalendarAccount,
  CalendarView,
  CalendarEvent,
  CalendarInfo,
  CalendarSettings,
} from '../types'
import {
  listCalendars,
  listEvents,
  getCalendarSettings,
  updateCalendarSettings,
  type ListEventsOptions,
} from '../api'

// Per-account cache structure - exported for App.tsx to manage
export interface CalendarAccountCache {
  calendars: CalendarInfo[]
  events: CalendarEvent[]
  settings: CalendarSettings | null
  loaded: boolean
  loading: boolean
  error?: string
}

export const emptyCalendarCache = (): CalendarAccountCache => ({
  calendars: [],
  events: [],
  settings: null,
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
}

type CalendarTabView = 'dashboard' | 'events' | 'meetings' | 'suggestions' | 'settings'

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

// Domain colors are now handled via CSS classes:
// .domain-personal, .domain-work, .domain-church

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
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [chatInput, setChatInput] = useState('')

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

      // Sort events by start time
      allEvents.sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())

      setCache(prev => ({
        ...prev,
        [account]: {
          calendars: calendarsResp.calendars,
          events: allEvents,
          settings: settingsResp.settings,
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

  const isLoading = getAccountsForView(selectedView).some(a => cache[a].loading)

  // View switcher tabs
  const viewTabs: { view: CalendarView; label: string }[] = [
    { view: 'personal', label: 'Personal' },
    { view: 'work', label: 'Work' },
    { view: 'church', label: 'Church' },
    { view: 'combined', label: 'Combined' },
  ]

  // Content tabs - matching email dashboard structure
  const contentTabs: { tab: CalendarTabView; label: string; count?: number }[] = [
    { tab: 'dashboard', label: 'Dashboard' },
    { tab: 'events', label: 'Events', count: eventsForView.length },
    { tab: 'meetings', label: 'Meetings', count: meetingsForView.length },
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
            {/* DATA Header */}
            <div className="email-assist-header">
              <h2>DATA</h2>
            </div>

            {/* Event Preview - shown when event is selected */}
            {selectedEvent ? (
              <>
                <div className="calendar-event-preview">
                  {/* Event Title */}
                  <h3 className="preview-title">{selectedEvent.summary}</h3>

                  {/* Domain Badge */}
                  <span className={`calendar-domain-badge ${selectedEvent.sourceDomain}`}>
                    {selectedEvent.sourceDomain}
                  </span>

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

                  {/* Google Calendar Link */}
                  {selectedEvent.htmlLink && (
                    <a
                      href={selectedEvent.htmlLink}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="preview-link"
                    >
                      <span>🔗</span> Open in Google Calendar
                    </a>
                  )}
                </div>

                {/* Ask DATA section */}
                <div className="calendar-ask-data">
                  <p className="ask-data-prompt">Ask DATA about this event</p>
                  <div className="quick-actions">
                    <button className="quick-action-btn" onClick={() => setChatInput('What should I do with this?')}>
                      What should I do with this?
                    </button>
                    <button className="quick-action-btn" onClick={() => setChatInput('Summarize')}>
                      Summarize
                    </button>
                    <button className="quick-action-btn" onClick={() => setChatInput('Should I archive?')}>
                      Should I archive?
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <div className="calendar-empty-state">
                <div className="icon">📅</div>
                <div className="title">Select an event to view details</div>
                <div className="subtitle">Click on any event in the list to see more information</div>
              </div>
            )}

            {/* Chat Input - always at bottom */}
            <div className="calendar-chat-input">
              <input
                type="text"
                placeholder={selectedEvent ? 'Ask DATA about this event...' : 'Select an event to chat'}
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                disabled={!selectedEvent}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && chatInput.trim() && selectedEvent) {
                    // Future: Send to DATA
                    console.log('Chat:', chatInput)
                    setChatInput('')
                  }
                }}
              />
              <button
                className="send-btn"
                disabled={!selectedEvent || !chatInput.trim()}
                onClick={() => {
                  if (chatInput.trim() && selectedEvent) {
                    console.log('Chat:', chatInput)
                    setChatInput('')
                  }
                }}
              >
                Send
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
