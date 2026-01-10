import { useState } from 'react'
import {
  useSettings,
  INACTIVITY_TIMEOUT_OPTIONS,
  type InactivityTimeoutOption,
} from '../contexts/SettingsContext'

interface SettingsPanelProps {
  onClose: () => void
}

/**
 * Settings Panel - Slide-out panel for global app settings
 */
export function SettingsPanel({ onClose }: SettingsPanelProps) {
  const { settings, updateSettings, resetSettings } = useSettings()
  
  // Local state for editing (allows cancel without saving)
  const [localTimeout, setLocalTimeout] = useState<InactivityTimeoutOption>(
    settings.inactivityTimeoutMinutes
  )
  const [hasChanges, setHasChanges] = useState(false)
  const [showSaved, setShowSaved] = useState(false)

  const handleTimeoutChange = (value: InactivityTimeoutOption) => {
    setLocalTimeout(value)
    setHasChanges(value !== settings.inactivityTimeoutMinutes)
    setShowSaved(false)
  }

  const handleSave = () => {
    updateSettings({ inactivityTimeoutMinutes: localTimeout })
    setHasChanges(false)
    setShowSaved(true)
    setTimeout(() => setShowSaved(false), 2000)
  }

  const handleReset = () => {
    resetSettings()
    setLocalTimeout(15) // Default value
    setHasChanges(false)
    setShowSaved(true)
    setTimeout(() => setShowSaved(false), 2000)
  }

  const handleCancel = () => {
    if (hasChanges) {
      // Reset local state to saved settings
      setLocalTimeout(settings.inactivityTimeoutMinutes)
      setHasChanges(false)
    }
    onClose()
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
        <button className="settings-close-btn" onClick={handleCancel} aria-label="Close settings">
          ×
        </button>
      </div>

      <div className="settings-content">
        {/* Inactivity Timeout Setting */}
        <div className="settings-section">
          <h3 className="settings-section-title">Security</h3>
          
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

        {/* Future settings sections can be added here */}
        <div className="settings-section settings-section-future">
          <p className="settings-future-hint">
            More settings coming soon...
          </p>
        </div>
      </div>

      <div className="settings-footer">
        <button
          className="settings-btn settings-btn-secondary"
          onClick={handleReset}
          title="Reset all settings to defaults"
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
          >
            {hasChanges ? 'Cancel' : 'Close'}
          </button>
          <button
            className="settings-btn settings-btn-primary"
            onClick={handleSave}
            disabled={!hasChanges}
          >
            Save Changes
          </button>
        </div>
      </div>
    </div>
  )
}
