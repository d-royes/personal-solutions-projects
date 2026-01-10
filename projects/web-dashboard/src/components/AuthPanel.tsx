import { useEffect, useState } from 'react'
import { GoogleSignInButton, useAuth } from '../auth/AuthContext'

const devAuthEnabled = import.meta.env.VITE_DEV_AUTH_ENABLED !== '0'

interface AuthPanelProps {
  onLogin?: () => void
}

export function AuthPanel({ onLogin }: AuthPanelProps) {
  const {
    state,
    authConfig,
    googleClientId,
    useDevAuth,
    clearAuth,
    setGoogleCredential,
    defaultDevEmail,
    authError,
  } = useAuth()
  const [devEmail, setDevEmail] = useState(state.userEmail ?? defaultDevEmail)
  const [error, setError] = useState<string | null>(null)
  
  // Combine local error with auth context error
  const displayError = error || authError

  useEffect(() => {
    if (state.userEmail) {
      setDevEmail(state.userEmail)
      return
    }
    const stored =
      typeof window !== 'undefined'
        ? window.localStorage.getItem('dta-dev-email')
        : null
    if (stored) {
      setDevEmail(stored)
    } else if (defaultDevEmail) {
      setDevEmail(defaultDevEmail)
    }
  }, [state.userEmail, defaultDevEmail])

  return (
    <div className="menu-panel">
      <div className="menu-panel__header">
        <div>
          <h3>Authentication</h3>
          <p className="subtle">
            {authConfig
              ? `Signed in as ${state.userEmail ?? 'unknown'} via ${state.mode}`
              : 'Sign in to call the API'}
          </p>
        </div>
      </div>

      {displayError && <p className="warning">{displayError}</p>}

      {googleClientId ? (
        <GoogleSignInButton
          onSuccess={(token, email) => {
            const allowed = setGoogleCredential(token, email)
            if (allowed) {
              setError(null)
              onLogin?.()
            }
            // If not allowed, authError will be set by context
          }}
          onError={() => setError('Google sign-in failed')}
        />
      ) : (
        <p className="warning">
          Set VITE_GOOGLE_CLIENT_ID to enable Google Sign-In.
        </p>
      )}

      {devAuthEnabled && (
        <div className="dev-auth">
          <p className="subtle">Developer bypass</p>
          <div className="field">
            <label htmlFor="dev-email">User email</label>
            <input
              id="dev-email"
              type="email"
              placeholder="dev@example.com"
              value={devEmail}
              onChange={(e) => setDevEmail(e.target.value)}
            />
          </div>
          <button
            onClick={() => {
              if (devEmail) {
                const allowed = useDevAuth(devEmail)
                if (allowed) {
                  setError(null)
                  if (typeof window !== 'undefined') {
                    window.localStorage.setItem('dta-dev-email', devEmail)
                  }
                  onLogin?.()
                }
                // If not allowed, authError will be set by context
              } else {
                setError('Enter an email for dev auth')
              }
            }}
          >
            Use dev auth header
          </button>
        </div>
      )}

      {authConfig && (
        <button className="secondary" onClick={clearAuth}>
          Sign out
        </button>
      )}
    </div>
  )
}

