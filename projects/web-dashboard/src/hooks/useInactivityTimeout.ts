import { useCallback, useEffect, useRef, useState } from 'react'

interface UseInactivityTimeoutOptions {
  /** Time in ms before showing warning (default: 15 minutes) */
  warningTimeout?: number
  /** Time in ms after warning before logout (default: 2 minutes) */
  logoutTimeout?: number
  /** Whether the timeout is enabled (e.g., only when authenticated) */
  enabled?: boolean
  /** Callback when logout should occur */
  onLogout: () => void
}

interface UseInactivityTimeoutReturn {
  /** Whether the warning modal should be shown */
  showWarning: boolean
  /** Seconds remaining before auto-logout (only valid when showWarning is true) */
  secondsRemaining: number
  /** Manually reset the inactivity timer (e.g., when user clicks "Stay Logged In") */
  resetInactivity: () => void
}

const DEFAULT_WARNING_TIMEOUT = 15 * 60 * 1000 // 15 minutes
const DEFAULT_LOGOUT_TIMEOUT = 2 * 60 * 1000 // 2 minutes
const THROTTLE_MS = 1000 // Throttle activity events to once per second

/**
 * Hook to track user inactivity and trigger logout after a warning period.
 * 
 * Activity events tracked: mousemove, mousedown, keydown, touchstart, scroll, click
 * 
 * Flow:
 * 1. User is active -> timer resets
 * 2. User inactive for warningTimeout -> showWarning becomes true
 * 3. User continues inactive for logoutTimeout -> onLogout is called
 * 4. If user clicks "Stay Logged In" -> resetInactivity() is called, back to step 1
 */
export function useInactivityTimeout({
  warningTimeout = DEFAULT_WARNING_TIMEOUT,
  logoutTimeout = DEFAULT_LOGOUT_TIMEOUT,
  enabled = true,
  onLogout,
}: UseInactivityTimeoutOptions): UseInactivityTimeoutReturn {
  const [showWarning, setShowWarning] = useState(false)
  const [secondsRemaining, setSecondsRemaining] = useState(Math.floor(logoutTimeout / 1000))

  // Refs to persist timer IDs across renders
  const warningTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const logoutTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const countdownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const lastActivityRef = useRef<number>(Date.now())

  // Clear all timers
  const clearAllTimers = useCallback(() => {
    if (warningTimerRef.current) {
      clearTimeout(warningTimerRef.current)
      warningTimerRef.current = null
    }
    if (logoutTimerRef.current) {
      clearTimeout(logoutTimerRef.current)
      logoutTimerRef.current = null
    }
    if (countdownIntervalRef.current) {
      clearInterval(countdownIntervalRef.current)
      countdownIntervalRef.current = null
    }
  }, [])

  // Start the logout countdown (after warning is shown)
  const startLogoutCountdown = useCallback(() => {
    const logoutTimeoutSeconds = Math.floor(logoutTimeout / 1000)
    setSecondsRemaining(logoutTimeoutSeconds)

    // Update countdown every second
    countdownIntervalRef.current = setInterval(() => {
      setSecondsRemaining((prev) => {
        if (prev <= 1) {
          // Time's up, trigger logout
          clearAllTimers()
          setShowWarning(false)
          onLogout()
          return 0
        }
        return prev - 1
      })
    }, 1000)

    // Backup timeout in case interval drifts
    logoutTimerRef.current = setTimeout(() => {
      clearAllTimers()
      setShowWarning(false)
      onLogout()
    }, logoutTimeout)
  }, [logoutTimeout, onLogout, clearAllTimers])

  // Start the warning timer
  const startWarningTimer = useCallback(() => {
    clearAllTimers()
    setShowWarning(false)

    warningTimerRef.current = setTimeout(() => {
      setShowWarning(true)
      startLogoutCountdown()
    }, warningTimeout)
  }, [warningTimeout, startLogoutCountdown, clearAllTimers])

  // Reset inactivity - call this when user confirms they're still there
  const resetInactivity = useCallback(() => {
    lastActivityRef.current = Date.now()
    setShowWarning(false)
    setSecondsRemaining(Math.floor(logoutTimeout / 1000))
    startWarningTimer()
  }, [logoutTimeout, startWarningTimer])

  // Handle activity events (throttled)
  useEffect(() => {
    if (!enabled) {
      clearAllTimers()
      setShowWarning(false)
      return
    }

    let throttleTimer: ReturnType<typeof setTimeout> | null = null

    const handleActivity = () => {
      // Don't reset if warning is already showing - user must click button
      if (showWarning) return

      const now = Date.now()
      if (now - lastActivityRef.current < THROTTLE_MS) return

      lastActivityRef.current = now

      // Throttle the timer reset
      if (throttleTimer) return
      throttleTimer = setTimeout(() => {
        throttleTimer = null
        startWarningTimer()
      }, THROTTLE_MS)
    }

    // Events to track
    const events = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll', 'click']

    // Add listeners
    events.forEach((event) => {
      window.addEventListener(event, handleActivity, { passive: true })
    })

    // Start initial timer
    startWarningTimer()

    // Cleanup
    return () => {
      events.forEach((event) => {
        window.removeEventListener(event, handleActivity)
      })
      if (throttleTimer) {
        clearTimeout(throttleTimer)
      }
      clearAllTimers()
    }
  }, [enabled, showWarning, startWarningTimer, clearAllTimers])

  return {
    showWarning,
    secondsRemaining,
    resetInactivity,
  }
}
