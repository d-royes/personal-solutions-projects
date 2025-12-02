"use client"
import { GoogleLogin, GoogleOAuthProvider } from '@react-oauth/google'
import { ReactNode, createContext, useContext, useEffect, useMemo, useState } from 'react'
import type { AuthConfig } from './types'

const AUTH_STORAGE_KEY = 'dta-auth-state'

interface AuthState {
  mode: 'google' | 'dev' | 'unauthenticated'
  userEmail: string | null
  idToken: string | null
}

interface AuthContextValue {
  state: AuthState
  authConfig: AuthConfig | null
  googleClientId?: string
  defaultDevEmail: string
  useDevAuth: (email: string) => void
  clearAuth: () => void
  setGoogleCredential: (token: string, email: string | null) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

/**
 * Check if a JWT token is expired
 */
function isTokenExpired(token: string): boolean {
  try {
    const payload = token.split('.')[1]
    const decoded = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')))
    const exp = decoded?.exp
    if (!exp) return true
    // Token is expired if exp is in the past (with 60s buffer)
    return Date.now() >= (exp * 1000) - 60000
  } catch {
    return true
  }
}

/**
 * Load auth state from localStorage, validating token expiry
 */
function loadAuthState(defaultDevEmail: string): AuthState {
  try {
    const stored = localStorage.getItem(AUTH_STORAGE_KEY)
    if (stored) {
      const parsed = JSON.parse(stored) as AuthState
      // Validate Google tokens haven't expired
      if (parsed.mode === 'google' && parsed.idToken) {
        if (isTokenExpired(parsed.idToken)) {
          // Token expired, clear it
          localStorage.removeItem(AUTH_STORAGE_KEY)
          return {
            mode: 'unauthenticated',
            userEmail: null,
            idToken: null,
          }
        }
        return parsed
      }
      // Dev mode auth is always valid
      if (parsed.mode === 'dev' && parsed.userEmail) {
        return parsed
      }
    }
  } catch {
    // Invalid stored state, ignore
  }
  
  // Default state
  return {
    mode: defaultDevEmail ? 'dev' : 'unauthenticated',
    userEmail: defaultDevEmail || null,
    idToken: null,
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID
  const defaultDevEmail = import.meta.env.VITE_DEV_USER_EMAIL ?? ''

  const [state, setState] = useState<AuthState>(() => loadAuthState(defaultDevEmail))

  // Persist auth state to localStorage whenever it changes
  useEffect(() => {
    if (state.mode === 'unauthenticated') {
      localStorage.removeItem(AUTH_STORAGE_KEY)
    } else {
      localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(state))
    }
  }, [state])

  // Periodically check for token expiry (every 5 minutes)
  useEffect(() => {
    if (state.mode !== 'google' || !state.idToken) return

    const checkExpiry = () => {
      if (state.idToken && isTokenExpired(state.idToken)) {
        console.log('Google token expired, clearing auth state')
        setState({
          mode: 'unauthenticated',
          userEmail: null,
          idToken: null,
        })
      }
    }

    const interval = setInterval(checkExpiry, 5 * 60 * 1000) // Check every 5 minutes
    return () => clearInterval(interval)
  }, [state.mode, state.idToken])

  const authConfig = useMemo<AuthConfig | null>(() => {
    if (state.mode === 'google' && state.idToken) {
      return { mode: 'idToken', idToken: state.idToken }
    }
    if (state.mode === 'dev' && state.userEmail) {
      return { mode: 'dev', userEmail: state.userEmail }
    }
    return null
  }, [state])

  const value: AuthContextValue = {
    state,
    authConfig,
    googleClientId: clientId,
    defaultDevEmail,
    useDevAuth: (email: string) =>
      setState({
        mode: 'dev',
        userEmail: email,
        idToken: null,
      }),
    clearAuth: () =>
      setState({
        mode: 'unauthenticated',
        userEmail: null,
        idToken: null,
      }),
    setGoogleCredential: (token, email) =>
      setState({
        mode: 'google',
        idToken: token,
        userEmail: email,
      }),
  }

  const content = (
    <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  )

  if (!clientId) {
    return content
  }

  return <GoogleOAuthProvider clientId={clientId}>{content}</GoogleOAuthProvider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return ctx
}

export function GoogleSignInButton({
  onSuccess,
  onError,
}: {
  onSuccess: (token: string, email: string | null) => void
  onError: () => void
}) {
  const { googleClientId } = useAuth()
  if (!googleClientId) return null
  return (
    <GoogleLogin
      onSuccess={(credentialResponse) => {
        const token = credentialResponse.credential
        if (!token) {
          onError()
          return
        }
        const email = decodeEmail(token)
        onSuccess(token, email)
      }}
      onError={onError}
      useOneTap
    />
  )
}

function decodeEmail(token: string): string | null {
  try {
    const payload = token.split('.')[1]
    const decoded = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')))
    return decoded?.email ?? null
  } catch {
    return null
  }
}

