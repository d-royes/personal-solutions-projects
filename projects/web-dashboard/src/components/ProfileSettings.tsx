import { useCallback, useEffect, useState } from 'react'
import type { UserProfile } from '../types'
import type { AuthConfig } from '../auth/types'
import { getProfile, updateProfile } from '../api'
import './ProfileSettings.css'

interface ProfileSettingsProps {
  authConfig: AuthConfig
  apiBase: string
}

type EditableSection =
  | 'churchRoles'
  | 'personalContexts'
  | 'vipSenders'
  | 'churchAttentionPatterns'
  | 'personalAttentionPatterns'
  | 'notActionablePatterns'

export function ProfileSettings({ authConfig, apiBase }: ProfileSettingsProps) {
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [editingSection, setEditingSection] = useState<EditableSection | null>(null)

  // Edit state for each section
  const [editChurchRoles, setEditChurchRoles] = useState<string[]>([])
  const [editPersonalContexts, setEditPersonalContexts] = useState<string[]>([])
  const [editVipSenders, setEditVipSenders] = useState<Record<string, string[]>>({})
  const [editChurchPatterns, setEditChurchPatterns] = useState<Record<string, string[]>>({})
  const [editPersonalPatterns, setEditPersonalPatterns] = useState<Record<string, string[]>>({})
  const [editNotActionable, setEditNotActionable] = useState<Record<string, string[]>>({})

  const loadProfile = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await getProfile(authConfig, apiBase)
      setProfile(response.profile)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load profile')
    } finally {
      setLoading(false)
    }
  }, [authConfig, apiBase])

  useEffect(() => {
    loadProfile()
  }, [loadProfile])

  const startEditing = (section: EditableSection) => {
    if (!profile) return

    setEditingSection(section)
    setSuccessMessage(null)

    switch (section) {
      case 'churchRoles':
        setEditChurchRoles([...profile.churchRoles])
        break
      case 'personalContexts':
        setEditPersonalContexts([...profile.personalContexts])
        break
      case 'vipSenders':
        setEditVipSenders(JSON.parse(JSON.stringify(profile.vipSenders)))
        break
      case 'churchAttentionPatterns':
        setEditChurchPatterns(JSON.parse(JSON.stringify(profile.churchAttentionPatterns)))
        break
      case 'personalAttentionPatterns':
        setEditPersonalPatterns(JSON.parse(JSON.stringify(profile.personalAttentionPatterns)))
        break
      case 'notActionablePatterns':
        setEditNotActionable(JSON.parse(JSON.stringify(profile.notActionablePatterns)))
        break
    }
  }

  const cancelEditing = () => {
    setEditingSection(null)
  }

  const saveSection = async (section: EditableSection) => {
    setSaving(true)
    setError(null)

    try {
      let updateData: Partial<UserProfile> = {}

      switch (section) {
        case 'churchRoles':
          updateData = { churchRoles: editChurchRoles.filter(r => r.trim()) }
          break
        case 'personalContexts':
          updateData = { personalContexts: editPersonalContexts.filter(c => c.trim()) }
          break
        case 'vipSenders':
          updateData = { vipSenders: editVipSenders }
          break
        case 'churchAttentionPatterns':
          updateData = { churchAttentionPatterns: editChurchPatterns }
          break
        case 'personalAttentionPatterns':
          updateData = { personalAttentionPatterns: editPersonalPatterns }
          break
        case 'notActionablePatterns':
          updateData = { notActionablePatterns: editNotActionable }
          break
      }

      const response = await updateProfile(updateData, authConfig, apiBase)
      setProfile(response.profile)
      setEditingSection(null)
      setSuccessMessage('Profile updated successfully')
      setTimeout(() => setSuccessMessage(null), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save profile')
    } finally {
      setSaving(false)
    }
  }

  // Array item handlers
  const addArrayItem = (
    setter: React.Dispatch<React.SetStateAction<string[]>>,
    items: string[]
  ) => {
    setter([...items, ''])
  }

  const updateArrayItem = (
    setter: React.Dispatch<React.SetStateAction<string[]>>,
    items: string[],
    index: number,
    value: string
  ) => {
    const newItems = [...items]
    newItems[index] = value
    setter(newItems)
  }

  const removeArrayItem = (
    setter: React.Dispatch<React.SetStateAction<string[]>>,
    items: string[],
    index: number
  ) => {
    setter(items.filter((_, i) => i !== index))
  }

  // Dict handlers for VIP senders and patterns
  const addDictItem = (
    setter: React.Dispatch<React.SetStateAction<Record<string, string[]>>>,
    dict: Record<string, string[]>,
    key: string
  ) => {
    setter({ ...dict, [key]: [...(dict[key] || []), ''] })
  }

  const updateDictItem = (
    setter: React.Dispatch<React.SetStateAction<Record<string, string[]>>>,
    dict: Record<string, string[]>,
    key: string,
    index: number,
    value: string
  ) => {
    const newDict = { ...dict }
    const items = [...(newDict[key] || [])]
    items[index] = value
    newDict[key] = items
    setter(newDict)
  }

  const removeDictItem = (
    setter: React.Dispatch<React.SetStateAction<Record<string, string[]>>>,
    dict: Record<string, string[]>,
    key: string,
    index: number
  ) => {
    const newDict = { ...dict }
    newDict[key] = (newDict[key] || []).filter((_, i) => i !== index)
    setter(newDict)
  }

  const addDictKey = (
    setter: React.Dispatch<React.SetStateAction<Record<string, string[]>>>,
    dict: Record<string, string[]>,
    newKey: string
  ) => {
    if (newKey.trim() && !dict[newKey]) {
      setter({ ...dict, [newKey]: [] })
    }
  }

  const removeDictKey = (
    setter: React.Dispatch<React.SetStateAction<Record<string, string[]>>>,
    dict: Record<string, string[]>,
    key: string
  ) => {
    const newDict = { ...dict }
    delete newDict[key]
    setter(newDict)
  }

  if (loading) {
    return (
      <div className="profile-settings">
        <h3>Profile Settings</h3>
        <p className="loading">Loading profile...</p>
      </div>
    )
  }

  if (!profile) {
    return (
      <div className="profile-settings">
        <h3>Profile Settings</h3>
        {error && <p className="error">{error}</p>}
        <button onClick={loadProfile}>Retry</button>
      </div>
    )
  }

  return (
    <div className="profile-settings">
      <h3>Profile Settings</h3>
      <p className="profile-description">
        Configure your roles and contexts for intelligent email detection.
        DATA uses this information to identify emails that need your attention.
      </p>

      {error && <p className="error">{error}</p>}
      {successMessage && <p className="success">{successMessage}</p>}

      {/* Church Roles Section */}
      <section className="profile-section">
        <div className="section-header">
          <h4>Church Roles</h4>
          {editingSection !== 'churchRoles' && (
            <button className="edit-btn" onClick={() => startEditing('churchRoles')}>
              Edit
            </button>
          )}
        </div>

        {editingSection === 'churchRoles' ? (
          <div className="edit-form">
            {editChurchRoles.map((role, i) => (
              <div key={i} className="edit-row">
                <input
                  type="text"
                  value={role}
                  onChange={(e) => updateArrayItem(setEditChurchRoles, editChurchRoles, i, e.target.value)}
                  placeholder="Role name"
                />
                <button className="remove-btn" onClick={() => removeArrayItem(setEditChurchRoles, editChurchRoles, i)}>
                  ×
                </button>
              </div>
            ))}
            <button className="add-btn" onClick={() => addArrayItem(setEditChurchRoles, editChurchRoles)}>
              + Add Role
            </button>
            <div className="edit-actions">
              <button onClick={cancelEditing} disabled={saving}>Cancel</button>
              <button
                className="save-btn"
                onClick={() => saveSection('churchRoles')}
                disabled={saving}
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        ) : (
          <ul className="item-list">
            {profile.churchRoles.map((role, i) => (
              <li key={i}>{role}</li>
            ))}
            {profile.churchRoles.length === 0 && <li className="empty">No roles defined</li>}
          </ul>
        )}
      </section>

      {/* Personal Contexts Section */}
      <section className="profile-section">
        <div className="section-header">
          <h4>Personal Contexts</h4>
          {editingSection !== 'personalContexts' && (
            <button className="edit-btn" onClick={() => startEditing('personalContexts')}>
              Edit
            </button>
          )}
        </div>

        {editingSection === 'personalContexts' ? (
          <div className="edit-form">
            {editPersonalContexts.map((ctx, i) => (
              <div key={i} className="edit-row">
                <input
                  type="text"
                  value={ctx}
                  onChange={(e) => updateArrayItem(setEditPersonalContexts, editPersonalContexts, i, e.target.value)}
                  placeholder="Context name"
                />
                <button className="remove-btn" onClick={() => removeArrayItem(setEditPersonalContexts, editPersonalContexts, i)}>
                  ×
                </button>
              </div>
            ))}
            <button className="add-btn" onClick={() => addArrayItem(setEditPersonalContexts, editPersonalContexts)}>
              + Add Context
            </button>
            <div className="edit-actions">
              <button onClick={cancelEditing} disabled={saving}>Cancel</button>
              <button
                className="save-btn"
                onClick={() => saveSection('personalContexts')}
                disabled={saving}
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        ) : (
          <ul className="item-list">
            {profile.personalContexts.map((ctx, i) => (
              <li key={i}>{ctx}</li>
            ))}
            {profile.personalContexts.length === 0 && <li className="empty">No contexts defined</li>}
          </ul>
        )}
      </section>

      {/* VIP Senders Section */}
      <section className="profile-section">
        <div className="section-header">
          <h4>VIP Senders</h4>
          {editingSection !== 'vipSenders' && (
            <button className="edit-btn" onClick={() => startEditing('vipSenders')}>
              Edit
            </button>
          )}
        </div>
        <p className="section-hint">High priority senders - emails from these people always surface.</p>

        {editingSection === 'vipSenders' ? (
          <div className="edit-form">
            {Object.entries(editVipSenders).map(([account, senders]) => (
              <div key={account} className="dict-group">
                <div className="dict-header">
                  <strong>{account}</strong>
                  <button
                    className="remove-btn"
                    onClick={() => removeDictKey(setEditVipSenders, editVipSenders, account)}
                    title="Remove account"
                  >
                    ×
                  </button>
                </div>
                {senders.map((sender, i) => (
                  <div key={i} className="edit-row indent">
                    <input
                      type="text"
                      value={sender}
                      onChange={(e) => updateDictItem(setEditVipSenders, editVipSenders, account, i, e.target.value)}
                      placeholder="Sender name or email"
                    />
                    <button
                      className="remove-btn"
                      onClick={() => removeDictItem(setEditVipSenders, editVipSenders, account, i)}
                    >
                      ×
                    </button>
                  </div>
                ))}
                <button
                  className="add-btn indent"
                  onClick={() => addDictItem(setEditVipSenders, editVipSenders, account)}
                >
                  + Add Sender
                </button>
              </div>
            ))}
            <div className="add-key-row">
              <input
                type="text"
                id="new-vip-account"
                placeholder="New account (e.g., church)"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    const input = e.target as HTMLInputElement
                    addDictKey(setEditVipSenders, editVipSenders, input.value)
                    input.value = ''
                  }
                }}
              />
              <button
                className="add-btn"
                onClick={() => {
                  const input = document.getElementById('new-vip-account') as HTMLInputElement
                  if (input) {
                    addDictKey(setEditVipSenders, editVipSenders, input.value)
                    input.value = ''
                  }
                }}
              >
                + Add Account
              </button>
            </div>
            <div className="edit-actions">
              <button onClick={cancelEditing} disabled={saving}>Cancel</button>
              <button
                className="save-btn"
                onClick={() => saveSection('vipSenders')}
                disabled={saving}
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        ) : (
          <div className="dict-display">
            {Object.entries(profile.vipSenders).map(([account, senders]) => (
              <div key={account} className="dict-group-display">
                <strong>{account}:</strong>
                <ul>
                  {senders.map((sender, i) => (
                    <li key={i}>{sender}</li>
                  ))}
                </ul>
              </div>
            ))}
            {Object.keys(profile.vipSenders).length === 0 && (
              <p className="empty">No VIP senders defined</p>
            )}
          </div>
        )}
      </section>

      {/* Church Attention Patterns Section */}
      <section className="profile-section">
        <div className="section-header">
          <h4>Church Attention Patterns</h4>
          {editingSection !== 'churchAttentionPatterns' && (
            <button className="edit-btn" onClick={() => startEditing('churchAttentionPatterns')}>
              Edit
            </button>
          )}
        </div>
        <p className="section-hint">Keywords that trigger attention for each church role.</p>

        {editingSection === 'churchAttentionPatterns' ? (
          <div className="edit-form">
            {Object.entries(editChurchPatterns).map(([role, patterns]) => (
              <div key={role} className="dict-group">
                <div className="dict-header">
                  <strong>{role}</strong>
                  <button
                    className="remove-btn"
                    onClick={() => removeDictKey(setEditChurchPatterns, editChurchPatterns, role)}
                    title="Remove role"
                  >
                    ×
                  </button>
                </div>
                {patterns.map((pattern, i) => (
                  <div key={i} className="edit-row indent">
                    <input
                      type="text"
                      value={pattern}
                      onChange={(e) => updateDictItem(setEditChurchPatterns, editChurchPatterns, role, i, e.target.value)}
                      placeholder="Pattern keyword"
                    />
                    <button
                      className="remove-btn"
                      onClick={() => removeDictItem(setEditChurchPatterns, editChurchPatterns, role, i)}
                    >
                      ×
                    </button>
                  </div>
                ))}
                <button
                  className="add-btn indent"
                  onClick={() => addDictItem(setEditChurchPatterns, editChurchPatterns, role)}
                >
                  + Add Pattern
                </button>
              </div>
            ))}
            <div className="add-key-row">
              <input
                type="text"
                id="new-church-role"
                placeholder="New role"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    const input = e.target as HTMLInputElement
                    addDictKey(setEditChurchPatterns, editChurchPatterns, input.value)
                    input.value = ''
                  }
                }}
              />
              <button
                className="add-btn"
                onClick={() => {
                  const input = document.getElementById('new-church-role') as HTMLInputElement
                  if (input) {
                    addDictKey(setEditChurchPatterns, editChurchPatterns, input.value)
                    input.value = ''
                  }
                }}
              >
                + Add Role
              </button>
            </div>
            <div className="edit-actions">
              <button onClick={cancelEditing} disabled={saving}>Cancel</button>
              <button
                className="save-btn"
                onClick={() => saveSection('churchAttentionPatterns')}
                disabled={saving}
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        ) : (
          <div className="dict-display">
            {Object.entries(profile.churchAttentionPatterns).map(([role, patterns]) => (
              <div key={role} className="dict-group-display">
                <strong>{role}:</strong>
                <ul className="pattern-list">
                  {patterns.map((pattern, i) => (
                    <li key={i}>{pattern}</li>
                  ))}
                </ul>
              </div>
            ))}
            {Object.keys(profile.churchAttentionPatterns).length === 0 && (
              <p className="empty">No church patterns defined</p>
            )}
          </div>
        )}
      </section>

      {/* Personal Attention Patterns Section */}
      <section className="profile-section">
        <div className="section-header">
          <h4>Personal Attention Patterns</h4>
          {editingSection !== 'personalAttentionPatterns' && (
            <button className="edit-btn" onClick={() => startEditing('personalAttentionPatterns')}>
              Edit
            </button>
          )}
        </div>
        <p className="section-hint">Keywords that trigger attention for each personal context.</p>

        {editingSection === 'personalAttentionPatterns' ? (
          <div className="edit-form">
            {Object.entries(editPersonalPatterns).map(([context, patterns]) => (
              <div key={context} className="dict-group">
                <div className="dict-header">
                  <strong>{context}</strong>
                  <button
                    className="remove-btn"
                    onClick={() => removeDictKey(setEditPersonalPatterns, editPersonalPatterns, context)}
                    title="Remove context"
                  >
                    ×
                  </button>
                </div>
                {patterns.map((pattern, i) => (
                  <div key={i} className="edit-row indent">
                    <input
                      type="text"
                      value={pattern}
                      onChange={(e) => updateDictItem(setEditPersonalPatterns, editPersonalPatterns, context, i, e.target.value)}
                      placeholder="Pattern keyword"
                    />
                    <button
                      className="remove-btn"
                      onClick={() => removeDictItem(setEditPersonalPatterns, editPersonalPatterns, context, i)}
                    >
                      ×
                    </button>
                  </div>
                ))}
                <button
                  className="add-btn indent"
                  onClick={() => addDictItem(setEditPersonalPatterns, editPersonalPatterns, context)}
                >
                  + Add Pattern
                </button>
              </div>
            ))}
            <div className="add-key-row">
              <input
                type="text"
                id="new-personal-context"
                placeholder="New context"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    const input = e.target as HTMLInputElement
                    addDictKey(setEditPersonalPatterns, editPersonalPatterns, input.value)
                    input.value = ''
                  }
                }}
              />
              <button
                className="add-btn"
                onClick={() => {
                  const input = document.getElementById('new-personal-context') as HTMLInputElement
                  if (input) {
                    addDictKey(setEditPersonalPatterns, editPersonalPatterns, input.value)
                    input.value = ''
                  }
                }}
              >
                + Add Context
              </button>
            </div>
            <div className="edit-actions">
              <button onClick={cancelEditing} disabled={saving}>Cancel</button>
              <button
                className="save-btn"
                onClick={() => saveSection('personalAttentionPatterns')}
                disabled={saving}
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        ) : (
          <div className="dict-display">
            {Object.entries(profile.personalAttentionPatterns).map(([context, patterns]) => (
              <div key={context} className="dict-group-display">
                <strong>{context}:</strong>
                <ul className="pattern-list">
                  {patterns.map((pattern, i) => (
                    <li key={i}>{pattern}</li>
                  ))}
                </ul>
              </div>
            ))}
            {Object.keys(profile.personalAttentionPatterns).length === 0 && (
              <p className="empty">No personal patterns defined</p>
            )}
          </div>
        )}
      </section>

      {/* Not Actionable Patterns Section */}
      <section className="profile-section">
        <div className="section-header">
          <h4>Not Actionable Patterns</h4>
          {editingSection !== 'notActionablePatterns' && (
            <button className="edit-btn" onClick={() => startEditing('notActionablePatterns')}>
              Edit
            </button>
          )}
        </div>
        <p className="section-hint">Patterns to skip - emails matching these won't surface as attention items.</p>

        {editingSection === 'notActionablePatterns' ? (
          <div className="edit-form">
            {Object.entries(editNotActionable).map(([account, patterns]) => (
              <div key={account} className="dict-group">
                <div className="dict-header">
                  <strong>{account}</strong>
                  <button
                    className="remove-btn"
                    onClick={() => removeDictKey(setEditNotActionable, editNotActionable, account)}
                    title="Remove account"
                  >
                    ×
                  </button>
                </div>
                {patterns.map((pattern, i) => (
                  <div key={i} className="edit-row indent">
                    <input
                      type="text"
                      value={pattern}
                      onChange={(e) => updateDictItem(setEditNotActionable, editNotActionable, account, i, e.target.value)}
                      placeholder="Pattern to skip"
                    />
                    <button
                      className="remove-btn"
                      onClick={() => removeDictItem(setEditNotActionable, editNotActionable, account, i)}
                    >
                      ×
                    </button>
                  </div>
                ))}
                <button
                  className="add-btn indent"
                  onClick={() => addDictItem(setEditNotActionable, editNotActionable, account)}
                >
                  + Add Pattern
                </button>
              </div>
            ))}
            <div className="add-key-row">
              <input
                type="text"
                id="new-not-actionable-account"
                placeholder="New account"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    const input = e.target as HTMLInputElement
                    addDictKey(setEditNotActionable, editNotActionable, input.value)
                    input.value = ''
                  }
                }}
              />
              <button
                className="add-btn"
                onClick={() => {
                  const input = document.getElementById('new-not-actionable-account') as HTMLInputElement
                  if (input) {
                    addDictKey(setEditNotActionable, editNotActionable, input.value)
                    input.value = ''
                  }
                }}
              >
                + Add Account
              </button>
            </div>
            <div className="edit-actions">
              <button onClick={cancelEditing} disabled={saving}>Cancel</button>
              <button
                className="save-btn"
                onClick={() => saveSection('notActionablePatterns')}
                disabled={saving}
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        ) : (
          <div className="dict-display">
            {Object.entries(profile.notActionablePatterns).map(([account, patterns]) => (
              <div key={account} className="dict-group-display">
                <strong>{account}:</strong>
                <ul className="pattern-list">
                  {patterns.map((pattern, i) => (
                    <li key={i}>{pattern}</li>
                  ))}
                </ul>
              </div>
            ))}
            {Object.keys(profile.notActionablePatterns).length === 0 && (
              <p className="empty">No skip patterns defined</p>
            )}
          </div>
        )}
      </section>

      {/* Profile Metadata */}
      <section className="profile-section profile-metadata">
        <h4>Profile Info</h4>
        <p><strong>User ID:</strong> {profile.userId}</p>
        <p><strong>Version:</strong> {profile.version}</p>
        <p><strong>Last Updated:</strong> {new Date(profile.updatedAt).toLocaleString()}</p>
      </section>
    </div>
  )
}
