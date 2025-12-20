import { useCallback, useEffect, useState } from 'react'
import type { AuthConfig } from '../auth/types'
import type { HaikuSettings, HaikuUsage } from '../api'
import { getHaikuSettings, updateHaikuSettings, getHaikuUsage } from '../api'
import './HaikuSettingsPanel.css'

interface HaikuSettingsPanelProps {
  authConfig: AuthConfig
  apiBase: string
}

export function HaikuSettingsPanel({ authConfig, apiBase }: HaikuSettingsPanelProps) {
  const [settings, setSettings] = useState<HaikuSettings | null>(null)
  const [usage, setUsage] = useState<HaikuUsage | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Edit state
  const [editEnabled, setEditEnabled] = useState(true)
  const [editDailyLimit, setEditDailyLimit] = useState(50)
  const [editWeeklyLimit, setEditWeeklyLimit] = useState(200)
  const [hasChanges, setHasChanges] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [settingsRes, usageRes] = await Promise.all([
        getHaikuSettings(authConfig, apiBase),
        getHaikuUsage(authConfig, apiBase),
      ])
      setSettings(settingsRes.settings)
      setUsage(usageRes.usage)

      // Initialize edit state from loaded settings
      setEditEnabled(settingsRes.settings.enabled)
      setEditDailyLimit(settingsRes.settings.dailyLimit)
      setEditWeeklyLimit(settingsRes.settings.weeklyLimit)
      setHasChanges(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load Haiku settings')
    } finally {
      setLoading(false)
    }
  }, [authConfig, apiBase])

  useEffect(() => {
    loadData()
  }, [loadData])

  // Track changes
  useEffect(() => {
    if (settings) {
      const changed =
        editEnabled !== settings.enabled ||
        editDailyLimit !== settings.dailyLimit ||
        editWeeklyLimit !== settings.weeklyLimit
      setHasChanges(changed)
    }
  }, [editEnabled, editDailyLimit, editWeeklyLimit, settings])

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    setSuccessMessage(null)

    try {
      const response = await updateHaikuSettings(
        {
          enabled: editEnabled,
          daily_limit: editDailyLimit,
          weekly_limit: editWeeklyLimit,
        },
        authConfig,
        apiBase
      )
      setSettings(response.settings)
      setHasChanges(false)
      setSuccessMessage('Settings saved successfully')
      setTimeout(() => setSuccessMessage(null), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  const handleReset = () => {
    if (settings) {
      setEditEnabled(settings.enabled)
      setEditDailyLimit(settings.dailyLimit)
      setEditWeeklyLimit(settings.weeklyLimit)
      setHasChanges(false)
    }
  }

  // Calculate progress percentage
  const getProgressPercent = (current: number, limit: number): number => {
    if (limit === 0) return 0
    return Math.min(100, (current / limit) * 100)
  }

  // Get progress bar color class
  const getProgressClass = (percent: number): string => {
    if (percent >= 90) return 'progress-critical'
    if (percent >= 70) return 'progress-warning'
    return 'progress-normal'
  }

  if (loading) {
    return (
      <div className="haiku-settings">
        <h3>AI Email Analysis (Haiku)</h3>
        <p className="loading">Loading settings...</p>
      </div>
    )
  }

  return (
    <div className="haiku-settings">
      <h3>AI Email Analysis (Haiku)</h3>
      <p className="haiku-description">
        Use Claude Haiku for intelligent email analysis. Haiku provides semantic understanding
        to better identify emails that need your attention and suggest appropriate actions.
      </p>

      {error && <p className="error">{error}</p>}
      {successMessage && <p className="success">{successMessage}</p>}

      {/* Settings Section */}
      <section className="haiku-section">
        <h4>Settings</h4>

        <div className="setting-row">
          <label htmlFor="haiku-enabled">Enable Haiku Analysis</label>
          <button
            id="haiku-enabled"
            className={`toggle-btn ${editEnabled ? 'active' : ''}`}
            onClick={() => setEditEnabled(!editEnabled)}
            aria-pressed={editEnabled}
          >
            {editEnabled ? 'ON' : 'OFF'}
          </button>
        </div>

        <div className="setting-row">
          <label htmlFor="daily-limit">Daily Limit</label>
          <div className="limit-input-group">
            <input
              id="daily-limit"
              type="number"
              min={0}
              max={500}
              value={editDailyLimit}
              onChange={(e) => setEditDailyLimit(Math.max(0, Math.min(500, parseInt(e.target.value) || 0)))}
              disabled={!editEnabled}
            />
            <span className="limit-unit">emails/day</span>
          </div>
        </div>

        <div className="setting-row">
          <label htmlFor="weekly-limit">Weekly Limit</label>
          <div className="limit-input-group">
            <input
              id="weekly-limit"
              type="number"
              min={0}
              max={2000}
              value={editWeeklyLimit}
              onChange={(e) => setEditWeeklyLimit(Math.max(0, Math.min(2000, parseInt(e.target.value) || 0)))}
              disabled={!editEnabled}
            />
            <span className="limit-unit">emails/week</span>
          </div>
        </div>

        <div className="setting-actions">
          <button
            className="reset-btn"
            onClick={handleReset}
            disabled={!hasChanges || saving}
          >
            Reset
          </button>
          <button
            className="save-btn"
            onClick={handleSave}
            disabled={!hasChanges || saving}
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </section>

      {/* Usage Section */}
      {usage && (
        <section className="haiku-section usage-section">
          <h4>Current Usage</h4>

          <div className="usage-row">
            <div className="usage-label">
              <span>Daily</span>
              <span className="usage-numbers">
                {usage.dailyCount}/{usage.dailyLimit}
                <span className="remaining">({usage.dailyRemaining} remaining)</span>
              </span>
            </div>
            <div className="progress-bar">
              <div
                className={`progress-fill ${getProgressClass(getProgressPercent(usage.dailyCount, usage.dailyLimit))}`}
                style={{ width: `${getProgressPercent(usage.dailyCount, usage.dailyLimit)}%` }}
              />
            </div>
          </div>

          <div className="usage-row">
            <div className="usage-label">
              <span>Weekly</span>
              <span className="usage-numbers">
                {usage.weeklyCount}/{usage.weeklyLimit}
                <span className="remaining">({usage.weeklyRemaining} remaining)</span>
              </span>
            </div>
            <div className="progress-bar">
              <div
                className={`progress-fill ${getProgressClass(getProgressPercent(usage.weeklyCount, usage.weeklyLimit))}`}
                style={{ width: `${getProgressPercent(usage.weeklyCount, usage.weeklyLimit)}%` }}
              />
            </div>
          </div>

          <div className="usage-status">
            {usage.canAnalyze ? (
              <span className="status-ok">Haiku analysis available</span>
            ) : (
              <span className="status-limit">Limit reached - using regex fallback</span>
            )}
          </div>
        </section>
      )}

      {/* Info Section */}
      <section className="haiku-section info-section">
        <h4>About Haiku Analysis</h4>
        <ul className="info-list">
          <li>Haiku runs in parallel with profile-based detection for best results</li>
          <li>When limits are reached, analysis falls back to regex patterns</li>
          <li>Daily limits reset at midnight, weekly limits reset on Monday</li>
          <li>Sensitive domains (banks, healthcare) are automatically excluded</li>
        </ul>
      </section>
    </div>
  )
}
