interface InactivityWarningModalProps {
  /** Seconds remaining before auto-logout */
  secondsRemaining: number
  /** Callback when user clicks "Stay Logged In" */
  onStayLoggedIn: () => void
}

/**
 * Modal displayed when user has been inactive for too long.
 * Shows a countdown and allows user to stay logged in.
 */
export function InactivityWarningModal({
  secondsRemaining,
  onStayLoggedIn,
}: InactivityWarningModalProps) {
  // Format seconds as M:SS
  const minutes = Math.floor(secondsRemaining / 60)
  const seconds = secondsRemaining % 60
  const formattedTime = `${minutes}:${seconds.toString().padStart(2, '0')}`

  // Determine urgency level for styling
  const isUrgent = secondsRemaining <= 30

  return (
    <div className="inactivity-modal-overlay">
      <div className={`inactivity-modal ${isUrgent ? 'urgent' : ''}`}>
        <div className="inactivity-modal-icon">
          <svg
            width="48"
            height="48"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
        </div>

        <h2 className="inactivity-modal-title">Session Timeout Warning</h2>

        <p className="inactivity-modal-message">
          You've been inactive for a while. For your security, you'll be
          automatically logged out in:
        </p>

        <div className={`inactivity-countdown ${isUrgent ? 'urgent' : ''}`}>
          {formattedTime}
        </div>

        <button
          className="inactivity-stay-btn"
          onClick={onStayLoggedIn}
          autoFocus
        >
          Stay Logged In
        </button>

        <p className="inactivity-modal-hint">
          Click the button or press Enter to continue your session
        </p>
      </div>
    </div>
  )
}
