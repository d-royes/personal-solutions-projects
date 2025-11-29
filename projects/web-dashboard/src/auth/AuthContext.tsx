"use client"
import { GoogleLogin, GoogleOAuthProvider } from '@react-oauth/google'
import { ReactNode, createContext, useContext, useMemo, useState } from 'react'
import type { AuthConfig } from './types'

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

export function AuthProvider({ children }: { children: ReactNode }) {
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID
  const defaultDevEmail = import.meta.env.VITE_DEV_USER_EMAIL ?? ''

  const [state, setState] = useState<AuthState>({
    mode: defaultDevEmail ? 'dev' : 'unauthenticated',
    userEmail: defaultDevEmail || null,
    idToken: null,
  })

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

