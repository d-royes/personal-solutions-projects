import { useEffect, useState } from 'react'
import {
  useSettings,
  INACTIVITY_TIMEOUT_OPTIONS,
  SYNC_INTERVAL_OPTIONS,
  type InactivityTimeoutOption,
  type SyncIntervalOption,
} from '../contexts/SettingsContext'
import type { AuthConfig } from '../auth/types'

interface SettingsPanelProps {
  onClose: () => void
  authConfig: AuthConfig | null
  apiBase: string
}

/**
 * Settings Panel - Slide-out panel for global app settings
 * 
 * Includes:
 * - Inactivity timeout configuration
 * - Sync settings (enable/disable, interval, manual trigger)
 */
export function SettingsPanel({ onClose, authConfig, apiBase }: SettingsPanelProps) {
  const {
    settings,
    settingsLoading,
    settingsError,
    updateSettings,
    resetSettings,
    loadFromApi,
    saveToApi,
    triggerSync,
  } = useSettings()
  
  // Local state for editing (allows cancel without saving)
  const [localTimeout, setLocalTimeout] = useState<InactivityTimeoutOption>(
    settings.inactivityTimeoutMinutes
  )
  const [localSyncEnabled, setLocalSyncEnabled] = useState(settings.sync.enabled)
  const [localSyncInterval, setLocalSyncInterval] = useState<SyncIntervalOption>(
    settings.sync.intervalMinutes as SyncIntervalOption
  )
  const [hasChanges, setHasChanges] = useState(false)
  const [showSaved, setShowSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [syncMessage, setSyncMessage] = useState<string | null>(null)

  // Load settings from API on mount when authenticated
  useEffect(() => {
    if (authConfig) {
      loadFromApi(authConfig, apiBase)
    }
  }, [authConfig, apiBase, loadFromApi])

  // Update local state when settings change (e.g., after API load)
  useEffect(() => {
    setLocalTimeout(settings.inactivityTimeoutMinutes)
    setLocalSyncEnabled(settings.sync.enabled)
    setLocalSyncInterval(settings.sync.intervalMinutes as SyncIntervalOption)
  }, [settings])

  // Check for changes
  useEffect(() => {
    const timeoutChanged = localTimeout !== settings.inactivityTimeoutMinutes
    const syncEnabledChanged = localSyncEnabled !== settings.sync.enabled
    const syncIntervalChanged = localSyncInterval !== settings.sync.intervalMinutes
    setHasChanges(timeoutChanged || syncEnabledChanged || syncIntervalChanged)
  }, [localTimeout, localSyncEnabled, localSyncInterval, settings])

  const handleTimeoutChange = (value: InactivityTimeoutOption) => {
    setLocalTimeout(value)
    setShowSaved(false)
  }

  const handleSyncEnabledChange = (enabled: boolean) => {
    setLocalSyncEnabled(enabled)
    setShowSaved(false)
  }

  const handleSyncIntervalChange = (interval: SyncIntervalOption) => {
    setLocalSyncInterval(interval)
    setShowSaved(false)
  }

  const handleSave = async () => {
    // Build updates object
    const updates: {
      inactivityTimeoutMinutes?: InactivityTimeoutOption
      sync?: { enabled?: boolean; intervalMinutes?: number }
    } = {}
    
    if (localTimeout !== settings.inactivityTimeoutMinutes) {
      updates.inactivityTimeoutMinutes = localTimeout
    }
    
    const syncUpdates: { enabled?: boolean; intervalMinutes?: number } = {}
    if (localSyncEnabled !== settings.sync.enabled) {
      syncUpdates.enabled = localSyncEnabled
    }
    if (localSyncInterval !== settings.sync.intervalMinutes) {
      syncUpdates.intervalMinutes = localSyncInterval
    }
    if (Object.keys(syncUpdates).length > 0) {
      updates.sync = syncUpdates
    }

    // Update local state immediately
    updateSettings(updates)
    
    // Save to API if authenticated
    if (authConfig && Object.keys(updates).length > 0) {
      setSaving(true)
      try {
        await saveToApi(authConfig, updates, apiBase)
        setShowSaved(true)
        setTimeout(() => setShowSaved(false), 2000)
      } catch (err) {
        console.error('Failed to save settings:', err)
        // Local state already updated, API will sync next time
      } finally {
        setSaving(false)
      }
    } else {
      setShowSaved(true)
      setTimeout(() => setShowSaved(false), 2000)
    }
    
    setHasChanges(false)
  }

  const handleReset = async () => {
    resetSettings()
    setLocalTimeout(15)
    setLocalSyncEnabled(true)
    setLocalSyncInterval(30)
    setHasChanges(false)
    
    // Save defaults to API
    if (authConfig) {
      setSaving(true)
      try {
        await saveToApi(authConfig, {
          inactivityTimeoutMinutes: 15,
          sync: { enabled: true, intervalMinutes: 30 },
        }, apiBase)
      } catch (err) {
        console.error('Failed to reset settings:', err)
      } finally {
        setSaving(false)
      }
    }
    
    setShowSaved(true)
    setTimeout(() => setShowSaved(false), 2000)
  }

  const handleSyncNow = async () => {
    if (!authConfig) return
    
    setSyncing(true)
    setSyncMessage(null)
    
    try {
      const result = await triggerSync(authConfig, apiBase)
      if (result.success) {
        setSyncMessage(`Synced: ${result.created ?? 0} created, ${result.updated ?? 0} updated`)
      } else {
        setSyncMessage('Sync completed with errors')
      }
    } catch (err) {
      setSyncMessage(err instanceof Error ? err.message : 'Sync failed')
    } finally {
      setSyncing(false)
      // Clear message after 5 seconds
      setTimeout(() => setSyncMessage(null), 5000)
    }
  }

  const handleCancel = () => {
    if (hasChanges) {
      // Reset local state to saved settings
      setLocalTimeout(settings.inactivityTimeoutMinutes)
      setLocalSyncEnabled(settings.sync.enabled)
      setLocalSyncInterval(settings.sync.intervalMinutes as SyncIntervalOption)
      setHasChanges(false)
    }
    onClose()
  }

  // Format last sync time for display
  const formatLastSync = (isoString: string | null): string => {
    if (!isoString) return 'Never'
    try {
      const date = new Date(isoString)
      return date.toLocaleString()
    } catch {
      return 'Unknown'
    }
  }

  return (
    <div className="settings-panel">
      <div className="settings-header">
        <h2 className="settings-title">
          <svg
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
          Settings
        </h2>
      </div>

      <div className="settings-content">
        {settingsLoading && (
          <div className="settings-loading">Loading settings...</div>
        )}
        
        {settingsError && (
          <div className="settings-error">{settingsError}</div>
        )}

        {/* Session Settings */}
        <div className="settings-section">
          <h3 className="settings-section-title">Session</h3>
          
          <div className="settings-item">
            <div className="settings-item-info">
              <label htmlFor="inactivity-timeout" className="settings-label">
                Inactivity Timeout
              </label>
              <p className="settings-description">
                Automatically log out after a period of inactivity. A warning will appear 
                2 minutes before logout.
              </p>
            </div>
            
            <select
              id="inactivity-timeout"
              className="settings-select"
              value={localTimeout}
              onChange={(e) => handleTimeoutChange(Number(e.target.value) as InactivityTimeoutOption)}
            >
              {INACTIVITY_TIMEOUT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Sync Settings Section */}
        <div className="settings-section">
          <h3 className="settings-section-title">Smartsheet Sync</h3>
          
          {/* Enable/Disable Toggle */}
          <div className="settings-item">
            <div className="settings-item-info">
              <label htmlFor="sync-enabled" className="settings-label">
                Automatic Sync
              </label>
              <p className="settings-description">
                Automatically synchronize tasks between Firestore and Smartsheet.
              </p>
            </div>
            
            <label className="settings-toggle">
              <input
                type="checkbox"
                id="sync-enabled"
                checked={localSyncEnabled}
                onChange={(e) => handleSyncEnabledChange(e.target.checked)}
              />
              <span className="settings-toggle-slider"></span>
            </label>
          </div>

          {/* Sync Interval */}
          <div className="settings-item">
            <div className="settings-item-info">
              <label htmlFor="sync-interval" className="settings-label">
                Sync Interval
              </label>
              <p className="settings-description">
                How often to synchronize when automatic sync is enabled.
              </p>
            </div>
            
            <select
              id="sync-interval"
              className="settings-select"
              value={localSyncInterval}
              onChange={(e) => handleSyncIntervalChange(Number(e.target.value) as SyncIntervalOption)}
              disabled={!localSyncEnabled}
            >
              {SYNC_INTERVAL_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          {/* Last Sync Info & Manual Trigger */}
          <div className="settings-item settings-item-sync-status">
            <div className="settings-item-info">
              <span className="settings-label">Last Sync</span>
              <p className="settings-sync-time">
                {formatLastSync(settings.sync.lastSyncAt)}
              </p>
              {settings.sync.lastSyncResult && (
                <p className="settings-sync-result">
                  {settings.sync.lastSyncResult.success ? '✓' : '⚠'}{' '}
                  {settings.sync.lastSyncResult.created} created,{' '}
                  {settings.sync.lastSyncResult.updated} updated
                  {settings.sync.lastSyncResult.errors > 0 && (
                    <span className="settings-sync-errors">
                      , {settings.sync.lastSyncResult.errors} errors
                    </span>
                  )}
                </p>
              )}
            </div>
            
            <button
              className="settings-btn settings-btn-sync"
              onClick={handleSyncNow}
              disabled={!authConfig || syncing}
            >
              {syncing ? 'Syncing...' : 'Sync Now'}
            </button>
          </div>

          {syncMessage && (
            <div className={`settings-sync-message ${syncMessage.includes('failed') || syncMessage.includes('error') ? 'error' : 'success'}`}>
              {syncMessage}
            </div>
          )}
        </div>
      </div>

      <div className="settings-footer">
        <button
          className="settings-btn settings-btn-secondary"
          onClick={handleReset}
          title="Reset all settings to defaults"
          disabled={saving}
        >
          Reset to Defaults
        </button>
        
        <div className="settings-footer-right">
          {showSaved && (
            <span className="settings-saved-indicator">✓ Saved</span>
          )}
          <button
            className="settings-btn settings-btn-secondary"
            onClick={handleCancel}
            disabled={saving}
          >
            {hasChanges ? 'Cancel' : 'Close'}
          </button>
          <button
            className="settings-btn settings-btn-primary"
            onClick={handleSave}
            disabled={!hasChanges || saving}
          >
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  )
}
