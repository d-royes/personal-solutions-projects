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
      {entries.length === 0 ? (
        <p>No recent activity.</p>
      ) : (
        <ul className="activity-list">
          {entries.map((entry, idx) => (
            <li key={`${entry.ts}-${idx}`}>
              <div className="activity-meta">
                <strong>{entry.task_title}</strong>
                <span>{new Date(entry.ts).toLocaleString()}</span>
              </div>
              <p>
                Account: {entry.account || 'n/a'} | Model:{' '}
                {entry.anthropic_model || 'n/a'} | Source:{' '}
                {entry.source || 'n/a'}
              </p>
              {entry.message_id && (
                <p className="success">Message ID: {entry.message_id}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

