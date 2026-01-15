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

  // Refs to persist values across renders without causing effect re-runs
  const warningTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const logoutTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const countdownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const lastActivityRef = useRef<number>(Date.now())
  const showWarningRef = useRef(showWarning)
  const onLogoutRef = useRef(onLogout)
  const warningTimeoutRef = useRef(warningTimeout)
  const logoutTimeoutRef = useRef(logoutTimeout)

  // Keep refs in sync with props/state
  useEffect(() => {
    showWarningRef.current = showWarning
  }, [showWarning])

  useEffect(() => {
    onLogoutRef.current = onLogout
  }, [onLogout])

  useEffect(() => {
    warningTimeoutRef.current = warningTimeout
  }, [warningTimeout])

  useEffect(() => {
    logoutTimeoutRef.current = logoutTimeout
  }, [logoutTimeout])

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
    const timeoutSeconds = Math.floor(logoutTimeoutRef.current / 1000)
    setSecondsRemaining(timeoutSeconds)

    // Clear any existing countdown
    if (countdownIntervalRef.current) {
      clearInterval(countdownIntervalRef.current)
    }
    if (logoutTimerRef.current) {
      clearTimeout(logoutTimerRef.current)
    }

    // Update countdown every second
    countdownIntervalRef.current = setInterval(() => {
      setSecondsRemaining((prev) => {
        if (prev <= 1) {
          // Time's up, trigger logout
          clearAllTimers()
          setShowWarning(false)
          onLogoutRef.current()
          return 0
        }
        return prev - 1
      })
    }, 1000)

    // Backup timeout in case interval drifts
    logoutTimerRef.current = setTimeout(() => {
      clearAllTimers()
      setShowWarning(false)
      onLogoutRef.current()
    }, logoutTimeoutRef.current)
  }, [clearAllTimers])

  // Start the warning timer
  const startWarningTimer = useCallback(() => {
    // Clear existing warning timer only (not logout countdown if active)
    if (warningTimerRef.current) {
      clearTimeout(warningTimerRef.current)
      warningTimerRef.current = null
    }

    warningTimerRef.current = setTimeout(() => {
      setShowWarning(true)
      startLogoutCountdown()
    }, warningTimeoutRef.current)
  }, [startLogoutCountdown])

  // Reset inactivity - call this when user confirms they're still there
  const resetInactivity = useCallback(() => {
    lastActivityRef.current = Date.now()
    clearAllTimers()
    setShowWarning(false)
    setSecondsRemaining(Math.floor(logoutTimeoutRef.current / 1000))
    startWarningTimer()
  }, [clearAllTimers, startWarningTimer])

  // Main effect for activity tracking - runs once on mount/enable change
  useEffect(() => {
    if (!enabled) {
      clearAllTimers()
      setShowWarning(false)
      return
    }

    let throttleTimer: ReturnType<typeof setTimeout> | null = null

    const handleActivity = () => {
      // Don't reset if warning is already showing - user must click button
      if (showWarningRef.current) return

      const now = Date.now()
      if (now - lastActivityRef.current < THROTTLE_MS) return

      lastActivityRef.current = now

      // Throttle the timer reset
      if (throttleTimer) return
      throttleTimer = setTimeout(() => {
        throttleTimer = null
        // Only restart if warning isn't showing
        if (!showWarningRef.current) {
          startWarningTimer()
        }
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
  }, [enabled, startWarningTimer, clearAllTimers])

  // Effect to handle timeout changes while running
  useEffect(() => {
    if (!enabled || showWarningRef.current) return
    
    // Restart warning timer with new timeout value
    startWarningTimer()
  }, [warningTimeout, enabled, startWarningTimer])

  return {
    showWarning,
    secondsRemaining,
    resetInactivity,
  }
}
