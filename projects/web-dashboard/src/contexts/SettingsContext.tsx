import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react'
import type { AuthConfig } from '../auth/types'
import {
  fetchSettings as apiFetchSettings,
  updateSettings as apiUpdateSettings,
  triggerSyncNow as apiTriggerSyncNow,
  type GlobalSettings,
  type SyncSettings,
  type SyncResult,
  type AttentionSignals,
} from '../api'

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

/** Sync interval options in minutes */
export type SyncIntervalOption = 5 | 15 | 30 | 60

export const SYNC_INTERVAL_OPTIONS: { value: SyncIntervalOption; label: string }[] = [
  { value: 5, label: '5 minutes' },
  { value: 15, label: '15 minutes' },
  { value: 30, label: '30 minutes' },
  { value: 60, label: '1 hour' },
]

export interface AppSettings {
  /** Inactivity timeout in minutes (0 = disabled) */
  inactivityTimeoutMinutes: InactivityTimeoutOption
  /** Sync configuration */
  sync: SyncSettings
  /** Attention signal thresholds for Needs Attention filter */
  attentionSignals: AttentionSignals
}

const DEFAULT_SYNC_SETTINGS: SyncSettings = {
  enabled: true,
  intervalMinutes: 30,
  lastSyncAt: null,
  lastSyncResult: null,
}

const DEFAULT_ATTENTION_SIGNALS: AttentionSignals = {
  slippageThreshold: 3,
  hardDeadlineDays: 2,
  staleDays: 7,
}

const DEFAULT_SETTINGS: AppSettings = {
  inactivityTimeoutMinutes: 15,
  sync: DEFAULT_SYNC_SETTINGS,
  attentionSignals: DEFAULT_ATTENTION_SIGNALS,
}

interface SettingsContextValue {
  settings: AppSettings
  settingsLoading: boolean
  settingsError: string | null
  updateSettings: (updates: Partial<AppSettings>) => void
  resetSettings: () => void
  /** Load settings from API (call when authenticated) */
  loadFromApi: (auth: AuthConfig, baseUrl?: string) => Promise<void>
  /** Save current settings to API */
  saveToApi: (auth: AuthConfig, updates: Partial<AppSettings>, baseUrl?: string) => Promise<void>
  /** Trigger manual sync */
  triggerSync: (auth: AuthConfig, baseUrl?: string) => Promise<SyncResult>
}

const SettingsContext = createContext<SettingsContextValue | null>(null)

/**
 * Load settings from localStorage (cache)
 */
function loadSettings(): AppSettings {
  try {
    const stored = localStorage.getItem(SETTINGS_STORAGE_KEY)
    if (stored) {
      const parsed = JSON.parse(stored) as Partial<AppSettings>
      return {
        ...DEFAULT_SETTINGS,
        ...parsed,
        sync: {
          ...DEFAULT_SYNC_SETTINGS,
          ...(parsed.sync || {}),
        },
        attentionSignals: {
          ...DEFAULT_ATTENTION_SIGNALS,
          ...(parsed.attentionSignals || {}),
        },
      }
    }
  } catch {
    // Invalid stored settings, use defaults
  }
  return DEFAULT_SETTINGS
}

/**
 * Save settings to localStorage (cache)
 */
function saveSettingsLocal(settings: AppSettings): void {
  try {
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings))
  } catch {
    // Storage error, ignore
  }
}

/**
 * Convert API response to AppSettings
 */
function apiToAppSettings(apiSettings: GlobalSettings): AppSettings {
  return {
    inactivityTimeoutMinutes: apiSettings.inactivityTimeoutMinutes as InactivityTimeoutOption,
    sync: apiSettings.sync,
    attentionSignals: apiSettings.attentionSignals || DEFAULT_ATTENTION_SIGNALS,
  }
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<AppSettings>(() => loadSettings())
  const [settingsLoading, setSettingsLoading] = useState(false)
  const [settingsError, setSettingsError] = useState<string | null>(null)

  // Persist settings to localStorage whenever they change
  useEffect(() => {
    saveSettingsLocal(settings)
  }, [settings])

  const updateSettings = useCallback((updates: Partial<AppSettings>) => {
    setSettings((prev) => {
      const newSettings = { ...prev }
      if (updates.inactivityTimeoutMinutes !== undefined) {
        newSettings.inactivityTimeoutMinutes = updates.inactivityTimeoutMinutes
      }
      if (updates.sync) {
        newSettings.sync = { ...prev.sync, ...updates.sync }
      }
      if (updates.attentionSignals) {
        newSettings.attentionSignals = { ...prev.attentionSignals, ...updates.attentionSignals }
      }
      return newSettings
    })
  }, [])

  const resetSettings = useCallback(() => {
    setSettings(DEFAULT_SETTINGS)
  }, [])

  const loadFromApi = useCallback(async (auth: AuthConfig, baseUrl?: string) => {
    setSettingsLoading(true)
    setSettingsError(null)
    try {
      const apiSettings = await apiFetchSettings(auth, baseUrl)
      const appSettings = apiToAppSettings(apiSettings)
      setSettings(appSettings)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load settings'
      setSettingsError(message)
      console.error('Failed to load settings from API:', err)
      // Keep using local settings on error
    } finally {
      setSettingsLoading(false)
    }
  }, [])

  const saveToApi = useCallback(async (
    auth: AuthConfig,
    updates: Partial<AppSettings>,
    baseUrl?: string
  ) => {
    setSettingsError(null)
    try {
      // Convert to API format
      const apiUpdates: {
        inactivityTimeoutMinutes?: number
        sync?: { enabled?: boolean; intervalMinutes?: number }
        attentionSignals?: { slippageThreshold?: number; hardDeadlineDays?: number; staleDays?: number }
      } = {}
      
      if (updates.inactivityTimeoutMinutes !== undefined) {
        apiUpdates.inactivityTimeoutMinutes = updates.inactivityTimeoutMinutes
      }
      
      if (updates.sync) {
        apiUpdates.sync = {}
        if (updates.sync.enabled !== undefined) {
          apiUpdates.sync.enabled = updates.sync.enabled
        }
        if (updates.sync.intervalMinutes !== undefined) {
          apiUpdates.sync.intervalMinutes = updates.sync.intervalMinutes
        }
      }
      
      if (updates.attentionSignals) {
        apiUpdates.attentionSignals = {}
        if (updates.attentionSignals.slippageThreshold !== undefined) {
          apiUpdates.attentionSignals.slippageThreshold = updates.attentionSignals.slippageThreshold
        }
        if (updates.attentionSignals.hardDeadlineDays !== undefined) {
          apiUpdates.attentionSignals.hardDeadlineDays = updates.attentionSignals.hardDeadlineDays
        }
        if (updates.attentionSignals.staleDays !== undefined) {
          apiUpdates.attentionSignals.staleDays = updates.attentionSignals.staleDays
        }
      }
      
      const apiSettings = await apiUpdateSettings(apiUpdates, auth, baseUrl)
      const appSettings = apiToAppSettings(apiSettings)
      setSettings(appSettings)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save settings'
      setSettingsError(message)
      console.error('Failed to save settings to API:', err)
      throw err
    }
  }, [])

  const triggerSync = useCallback(async (auth: AuthConfig, baseUrl?: string): Promise<SyncResult> => {
    try {
      const result = await apiTriggerSyncNow(auth, baseUrl)
      
      // Update last sync info in local state if sync ran
      if (result.syncedAt) {
        setSettings(prev => ({
          ...prev,
          sync: {
            ...prev.sync,
            lastSyncAt: result.syncedAt ?? null,
            lastSyncResult: result.success !== undefined ? {
              created: result.created ?? 0,
              updated: result.updated ?? 0,
              unchanged: result.unchanged ?? 0,
              conflicts: result.conflicts ?? 0,
              errors: result.errors ?? 0,
              totalProcessed: result.totalProcessed ?? 0,
              success: result.success,
            } : null,
          },
        }))
      }
      
      return result
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Sync failed'
      setSettingsError(message)
      throw err
    }
  }, [])

  return (
    <SettingsContext.Provider value={{
      settings,
      settingsLoading,
      settingsError,
      updateSettings,
      resetSettings,
      loadFromApi,
      saveToApi,
      triggerSync,
    }}>
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

// Re-export types for convenience
export type { SyncSettings, SyncResult, AttentionSignals }
