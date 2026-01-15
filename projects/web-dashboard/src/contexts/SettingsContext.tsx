import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

const SETTINGS_STORAGE_KEY = 'dta-app-settings'

/** Inactivity timeout options in minutes (0 = disabled) */
export type InactivityTimeoutOption = 0 | 5 | 10 | 15 | 30

export const INACTIVITY_TIMEOUT_OPTIONS: { value: InactivityTimeoutOption; label: string }[] = [
  { value: 0, label: 'Disabled' },
  { value: 5, label: '5 minutes' },
  { value: 10, label: '10 minutes' },
  { value: 15, label: '15 minutes' },
  { value: 30, label: '30 minutes' },
]

export interface AppSettings {
  /** Inactivity timeout in minutes (0 = disabled) */
  inactivityTimeoutMinutes: InactivityTimeoutOption
}

const DEFAULT_SETTINGS: AppSettings = {
  inactivityTimeoutMinutes: 15,
}

interface SettingsContextValue {
  settings: AppSettings
  updateSettings: (updates: Partial<AppSettings>) => void
  resetSettings: () => void
}

const SettingsContext = createContext<SettingsContextValue | null>(null)

/**
 * Load settings from localStorage
 */
function loadSettings(): AppSettings {
  try {
    const stored = localStorage.getItem(SETTINGS_STORAGE_KEY)
    if (stored) {
      const parsed = JSON.parse(stored) as Partial<AppSettings>
      return {
        ...DEFAULT_SETTINGS,
        ...parsed,
      }
    }
  } catch {
    // Invalid stored settings, use defaults
  }
  return DEFAULT_SETTINGS
}

/**
 * Save settings to localStorage
 */
function saveSettings(settings: AppSettings): void {
  try {
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings))
  } catch {
    // Storage error, ignore
  }
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<AppSettings>(() => loadSettings())

  // Persist settings to localStorage whenever they change
  useEffect(() => {
    saveSettings(settings)
  }, [settings])

  const updateSettings = (updates: Partial<AppSettings>) => {
    setSettings((prev) => ({
      ...prev,
      ...updates,
    }))
  }

  const resetSettings = () => {
    setSettings(DEFAULT_SETTINGS)
  }

  return (
    <SettingsContext.Provider value={{ settings, updateSettings, resetSettings }}>
      {children}
    </SettingsContext.Provider>
  )
}

export function useSettings() {
  const ctx = useContext(SettingsContext)
  if (!ctx) {
    throw new Error('useSettings must be used within SettingsProvider')
  }
  return ctx
}
