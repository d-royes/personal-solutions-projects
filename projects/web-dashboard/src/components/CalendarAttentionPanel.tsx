import { useState, useCallback } from 'react'
import type { AuthConfig } from '../auth/types'
import type {
  CalendarAccount,
  CalendarAttentionItem,
} from '../types'
import {
  dismissCalendarAttention,
  markCalendarAttentionViewed,
  markCalendarAttentionActed,
} from '../api'

interface CalendarAttentionPanelProps {
  items: CalendarAttentionItem[]
  account: CalendarAccount
  authConfig: AuthConfig
  apiBase: string
  onDismiss: (eventId: string) => void
  onAct: (eventId: string, actionType: 'task_linked' | 'prep_started') => void
  onSelectEvent?: (eventId: string) => void
  loading?: boolean
}

// Friendly labels for attention types
const attentionTypeLabels: Record<string, { label: string; icon: string; color: string }> = {
  vip_meeting: { label: 'VIP Meeting', icon: '👤', color: '#f59e0b' },
  prep_needed: { label: 'Needs Prep', icon: '📝', color: '#3b82f6' },
  task_conflict: { label: 'Task Conflict', icon: '⚠️', color: '#ef4444' },
  overcommitment: { label: 'Overcommitted', icon: '📊', color: '#8b5cf6' },
}

function formatEventDate(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const tomorrow = new Date(now)
  tomorrow.setDate(tomorrow.getDate() + 1)

  if (date.toDateString() === now.toDateString()) {
    return 'Today'
  } else if (date.toDateString() === tomorrow.toDateString()) {
    return 'Tomorrow'
  }
  return date.toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
}

function formatEventTime(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  })
}

function getTimeUntil(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const hours = Math.round((date.getTime() - now.getTime()) / (1000 * 60 * 60))

  if (hours < 0) return 'Past'
  if (hours < 1) return 'Less than 1 hour'
  if (hours < 24) return `${hours}h`
  const days = Math.round(hours / 24)
  return `${days}d`
}

export default function CalendarAttentionPanel({
  items,
  account,
  authConfig,
  apiBase,
  onDismiss,
  onAct,
  onSelectEvent,
  loading = false,
}: CalendarAttentionPanelProps) {
  const [processingIds, setProcessingIds] = useState<Set<string>>(new Set())

  // Mark item as viewed when expanded
  const handleItemViewed = useCallback(async (eventId: string) => {
    try {
      await markCalendarAttentionViewed(account, eventId, authConfig, apiBase)
    } catch {
      // Ignore view tracking errors
    }
  }, [account, authConfig, apiBase])

  // Dismiss an attention item
  const handleDismiss = useCallback(async (eventId: string) => {
    setProcessingIds(prev => new Set(prev).add(eventId))
    try {
      await dismissCalendarAttention(account, eventId, authConfig, apiBase)
      onDismiss(eventId)
    } catch (err) {
      console.error('Failed to dismiss:', err)
    } finally {
      setProcessingIds(prev => {
        const next = new Set(prev)
        next.delete(eventId)
        return next
      })
    }
  }, [account, authConfig, apiBase, onDismiss])

  // Mark as acted upon
  const handleAct = useCallback(async (eventId: string, actionType: 'task_linked' | 'prep_started') => {
    setProcessingIds(prev => new Set(prev).add(eventId))
    try {
      await markCalendarAttentionActed(account, eventId, actionType, authConfig, apiBase)
      onAct(eventId, actionType)
    } catch (err) {
      console.error('Failed to mark acted:', err)
    } finally {
      setProcessingIds(prev => {
        const next = new Set(prev)
        next.delete(eventId)
        return next
      })
    }
  }, [account, authConfig, apiBase, onAct])

  if (loading) {
    return <div className="loading">Loading attention items...</div>
  }

  if (items.length === 0) {
    return (
      <div className="empty-state">
        <p>No calendar items need attention</p>
        <p className="text-muted">VIP meetings and events needing prep will appear here</p>
      </div>
    )
  }

  // Group items by attention type
  const groupedItems = items.reduce((acc, item) => {
    const type = item.attentionType
    if (!acc[type]) acc[type] = []
    acc[type].push(item)
    return acc
  }, {} as Record<string, CalendarAttentionItem[]>)

  return (
    <div className="calendar-attention-panel">
      {Object.entries(groupedItems).map(([type, typeItems]) => {
        const typeInfo = attentionTypeLabels[type] || { label: type, icon: '📌', color: '#6b7280' }
        return (
          <div key={type} className="attention-group">
            <h3 className="attention-group-header" style={{ borderLeftColor: typeInfo.color }}>
              <span className="icon">{typeInfo.icon}</span>
              {typeInfo.label}
              <span className="count">({typeItems.length})</span>
            </h3>
            <ul className="attention-list">
              {typeItems.map(item => {
                const isProcessing = processingIds.has(item.eventId)
                return (
                  <li
                    key={item.eventId}
                    className={`attention-item ${isProcessing ? 'processing' : ''}`}
                    onMouseEnter={() => handleItemViewed(item.eventId)}
                  >
                    <div className="attention-item-header">
                      <div
                        className="attention-item-title"
                        onClick={() => onSelectEvent?.(item.eventId)}
                        style={{ cursor: onSelectEvent ? 'pointer' : 'default' }}
                      >
                        {item.summary}
                      </div>
                      <div className="attention-item-time">
                        <span className="time-until">{getTimeUntil(item.start)}</span>
                      </div>
                    </div>

                    <div className="attention-item-details">
                      <span className="date">{formatEventDate(item.start)}</span>
                      <span className="time">{formatEventTime(item.start)}</span>
                      {item.attendees.length > 0 && (
                        <span className="attendees">
                          {item.attendees.length} attendee{item.attendees.length !== 1 ? 's' : ''}
                        </span>
                      )}
                    </div>

                    <div className="attention-item-reason">
                      {item.reason}
                      {item.matchedVip && (
                        <span className="vip-badge">VIP: {item.matchedVip}</span>
                      )}
                    </div>

                    <div className="attention-item-confidence">
                      <span
                        className={`confidence-badge ${item.confidence >= 0.7 ? 'high' : item.confidence >= 0.5 ? 'medium' : 'low'}`}
                      >
                        {Math.round(item.confidence * 100)}% confidence
                      </span>
                    </div>

                    <div className="attention-item-actions">
                      {type === 'prep_needed' && (
                        <button
                          className="btn btn-sm btn-primary"
                          onClick={() => handleAct(item.eventId, 'prep_started')}
                          disabled={isProcessing}
                        >
                          Start Prep
                        </button>
                      )}
                      {type === 'vip_meeting' && (
                        <button
                          className="btn btn-sm btn-primary"
                          onClick={() => handleAct(item.eventId, 'task_linked')}
                          disabled={isProcessing}
                        >
                          Link Task
                        </button>
                      )}
                      <button
                        className="btn btn-sm btn-secondary"
                        onClick={() => handleDismiss(item.eventId)}
                        disabled={isProcessing}
                      >
                        Dismiss
                      </button>
                    </div>
                  </li>
                )
              })}
            </ul>
          </div>
        )
      })}

      <style>{`
        .calendar-attention-panel {
          padding: 1rem;
        }

        .attention-group {
          margin-bottom: 1.5rem;
        }

        .attention-group-header {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.5rem;
          margin-bottom: 0.5rem;
          border-left: 4px solid;
          background: var(--bg-secondary, #f3f4f6);
          border-radius: 0 4px 4px 0;
          font-size: 0.9rem;
          font-weight: 600;
        }

        .attention-group-header .icon {
          font-size: 1rem;
        }

        .attention-group-header .count {
          color: var(--text-muted, #6b7280);
          font-weight: normal;
        }

        .attention-list {
          list-style: none;
          padding: 0;
          margin: 0;
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }

        .attention-item {
          padding: 0.75rem;
          background: var(--bg-primary, #fff);
          border: 1px solid var(--border-color, #e5e7eb);
          border-radius: 6px;
          transition: opacity 0.2s;
        }

        .attention-item.processing {
          opacity: 0.5;
          pointer-events: none;
        }

        .attention-item:hover {
          border-color: var(--accent-color, #3b82f6);
        }

        .attention-item-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 0.25rem;
        }

        .attention-item-title {
          font-weight: 500;
          color: var(--text-primary, #111827);
        }

        .attention-item-title:hover {
          color: var(--accent-color, #3b82f6);
        }

        .attention-item-time {
          font-size: 0.8rem;
          color: var(--text-muted, #6b7280);
        }

        .time-until {
          background: var(--bg-secondary, #f3f4f6);
          padding: 0.125rem 0.5rem;
          border-radius: 4px;
        }

        .attention-item-details {
          display: flex;
          gap: 0.75rem;
          font-size: 0.85rem;
          color: var(--text-secondary, #4b5563);
          margin-bottom: 0.5rem;
        }

        .attention-item-reason {
          font-size: 0.85rem;
          color: var(--text-secondary, #4b5563);
          margin-bottom: 0.5rem;
        }

        .vip-badge {
          display: inline-block;
          margin-left: 0.5rem;
          padding: 0.125rem 0.375rem;
          background: #fef3c7;
          color: #92400e;
          border-radius: 4px;
          font-size: 0.75rem;
          font-weight: 500;
        }

        .attention-item-confidence {
          margin-bottom: 0.5rem;
        }

        .confidence-badge {
          font-size: 0.75rem;
          padding: 0.125rem 0.375rem;
          border-radius: 4px;
        }

        .confidence-badge.high {
          background: #dcfce7;
          color: #166534;
        }

        .confidence-badge.medium {
          background: #fef3c7;
          color: #92400e;
        }

        .confidence-badge.low {
          background: #fee2e2;
          color: #991b1b;
        }

        .attention-item-actions {
          display: flex;
          gap: 0.5rem;
        }

        .btn {
          padding: 0.375rem 0.75rem;
          border-radius: 4px;
          border: none;
          cursor: pointer;
          font-size: 0.8rem;
          font-weight: 500;
          transition: background-color 0.2s;
        }

        .btn-sm {
          padding: 0.25rem 0.5rem;
        }

        .btn-primary {
          background: var(--accent-color, #3b82f6);
          color: white;
        }

        .btn-primary:hover:not(:disabled) {
          background: var(--accent-hover, #2563eb);
        }

        .btn-secondary {
          background: var(--bg-secondary, #f3f4f6);
          color: var(--text-secondary, #4b5563);
        }

        .btn-secondary:hover:not(:disabled) {
          background: var(--bg-tertiary, #e5e7eb);
        }

        .btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .empty-state {
          padding: 2rem;
          text-align: center;
          color: var(--text-muted, #6b7280);
        }

        .empty-state .text-muted {
          font-size: 0.85rem;
          margin-top: 0.5rem;
        }

        .loading {
          padding: 2rem;
          text-align: center;
          color: var(--text-muted, #6b7280);
        }
      `}</style>
    </div>
  )
}
