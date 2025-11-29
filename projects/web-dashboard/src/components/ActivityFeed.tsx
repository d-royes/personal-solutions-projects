import { useState } from 'react'
import type { ActivityEntry } from '../types'

interface ActivityFeedProps {
  entries: ActivityEntry[]
  onRefresh?: () => void
  error?: string | null
  variant?: 'panel' | 'inline'
}

export function ActivityFeed({
  entries,
  onRefresh,
  error,
  variant = 'panel',
}: ActivityFeedProps) {
  const inline = variant === 'inline'
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null)

  const sortedEntries = [...entries].sort(
    (a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime(),
  )

  const toggleEntry = (index: number) => {
    setExpandedIndex((prev) => (prev === index ? null : index))
  }
  return (
    <section className={inline ? 'menu-activity' : 'panel activity-panel'}>
      <header>
        <h2>Activity</h2>
        {onRefresh && (
          <button
            className={inline ? 'link-button' : 'secondary'}
            onClick={onRefresh}
          >
            Refresh
          </button>
        )}
      </header>
      {error && <p className="warning">{error}</p>}
      {sortedEntries.length === 0 ? (
        <p>No recent activity.</p>
      ) : (
        <ul className="activity-list">
          {sortedEntries.map((entry, idx) => {
            const expanded = expandedIndex === idx
            return (
              <li key={`${entry.ts}-${idx}`}>
                <button
                  className="activity-entry"
                  onClick={() => toggleEntry(idx)}
                  aria-expanded={expanded}
                >
                  <div className="activity-meta">
                    <strong>{entry.task_title}</strong>
                    <span>{new Date(entry.ts).toLocaleString()}</span>
                  </div>
                  <p>
                    Account: {entry.account || 'n/a'} | Model:{' '}
                    {entry.anthropic_model || 'n/a'} | Source:{' '}
                    {entry.source || 'n/a'}
                  </p>
                </button>
                {expanded && (
                  <div className="activity-detail">
                    {entry.message_id && <p>Message ID: {entry.message_id}</p>}
                    {entry.recipient && <p>Recipient: {entry.recipient}</p>}
                    <p>Task ID: {entry.task_id}</p>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

