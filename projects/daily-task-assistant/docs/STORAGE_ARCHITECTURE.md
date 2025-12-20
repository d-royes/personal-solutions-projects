# Storage Key Architecture

> **Status:** Implemented (December 2025)
> **Priority:** CRITICAL - Data integrity depends on correct implementation
> **Quick Reference:** See `.claude/CLAUDE.md` for summary table

---

## Problem Statement

David uses TWO Gmail login identities but is ONE user:

| Identity | Email | Use Case |
|----------|-------|----------|
| Personal | `david.a.royes@gmail.com` | Personal Gmail inbox |
| Church | `davidroyes@southpointsda.org` | Church Gmail inbox |

**The naive approach** of keying storage by login email causes:

1. **Data Fragmentation** - Profile settings saved under one login invisible from other
2. **Limit Bypass** - Daily Haiku usage limits (50/day) become 100/day by switching logins
3. **Lost Context** - Email suggestions created in one session invisible in another
4. **Inconsistent Experience** - Settings tab shows different data depending on login

---

## Solution: Two Storage Categories

### GLOBAL Storage

Data that belongs to David as a person, regardless of which email account he's viewing.

**Key:** Fixed identifier `"david"`

**Firestore Path:** `global/david/{collection}/{document}`

**File Path (dev):** `{store}/global/{file}`

**Examples:**
- User profile (church roles, personal contexts, VIP senders)
- Haiku usage limits and counters
- Application settings and preferences

### ACCOUNT Storage

Data that belongs to a specific email account (church inbox vs personal inbox).

**Key:** Account identifier `"church"` or `"personal"`

**Firestore Path:** `email_accounts/{account}/{collection}/{document}`

**File Path (dev):** `{store}/{account}/{file}`

**Examples:**
- Email attention items (needs-attention emails for that inbox)
- Email suggestions (AI-generated action suggestions for that inbox)
- Email memory (sender profiles, category patterns for that inbox)

---

## Module Classification

| Module | Location | Category | Storage Key | Rationale |
|--------|----------|----------|-------------|-----------|
| `profile.py` | `memory/` | GLOBAL | `"david"` | User identity shared across logins |
| `haiku_usage.py` | `email/` | GLOBAL | `"david"` | Prevents limit bypass via login switching |
| `attention_store.py` | `email/` | ACCOUNT | `"church"/"personal"` | Emails are account-specific |
| `suggestion_store.py` | `email/` | ACCOUNT | `"church"/"personal"` | Suggestions are for specific emails |
| `memory.py` | `email/` | ACCOUNT | `"church"/"personal"` | Learning patterns are inbox-specific |

---

## Implementation Patterns

### GLOBAL Module Pattern

```python
# File: daily_task_assistant/memory/profile.py

GLOBAL_USER_ID = "david"

def _get_firestore_path():
    """Fixed path for global data."""
    db = get_firestore_client()
    return (
        db.collection("global")
        .document(GLOBAL_USER_ID)
        .collection("profile")
        .document("current")
    )

def _get_file_path() -> Path:
    """Fixed file path for dev mode."""
    return _storage_dir() / "global" / "profile.json"

# Functions take NO user_id parameter
def get_profile() -> Optional[DavidProfile]:
    ...

def save_profile(profile: DavidProfile) -> bool:
    ...
```

### ACCOUNT Module Pattern

```python
# File: daily_task_assistant/email/attention_store.py

def _validate_account(account: str) -> Literal["church", "personal"]:
    """Validate and normalize account identifier."""
    if account not in ("church", "personal"):
        raise ValueError(f"Invalid account: {account}")
    return account

def _get_firestore_path(account: str):
    """Account-specific Firestore path."""
    account = _validate_account(account)
    db = get_firestore_client()
    return (
        db.collection("email_accounts")
        .document(account)
        .collection("attention")
    )

def _get_file_path(account: str) -> Path:
    """Account-specific file path for dev mode."""
    account = _validate_account(account)
    return _storage_dir() / account

# Functions take account as FIRST parameter (not user_id)
def get_attention_items(account: str) -> List[AttentionItem]:
    ...

def save_attention_item(account: str, item: AttentionItem) -> None:
    ...
```

---

## API Endpoint Patterns

### GLOBAL Endpoints

No account in URL path:

```
GET  /profile
PUT  /profile
GET  /email/haiku/settings
PUT  /email/haiku/settings
GET  /email/haiku/usage
```

### ACCOUNT Endpoints

Account as URL path parameter:

```
GET  /email/attention/{account}
POST /email/attention/{account}/{email_id}/dismiss
GET  /email/suggestions/{account}/pending
POST /email/suggestions/{account}/{suggestion_id}/decide
GET  /email/{account}/memory/sender-profiles
```

---

## Cross-Login Verification

Tests must verify that data is accessible regardless of login identity:

```typescript
// E2E Test Example
test('profile returns same data regardless of login identity', async ({ request }) => {
  const PERSONAL_USER = 'david.a.royes@gmail.com';
  const CHURCH_USER = 'davidroyes@southpointsda.org';

  // Get profile as personal user
  const response1 = await request.get(`${API_BASE}/profile`, {
    headers: { 'X-User-Email': PERSONAL_USER }
  });
  const data1 = await response1.json();

  // Get profile as church user
  const response2 = await request.get(`${API_BASE}/profile`, {
    headers: { 'X-User-Email': CHURCH_USER }
  });
  const data2 = await response2.json();

  // Should be identical
  expect(data1.profile.churchRoles).toEqual(data2.profile.churchRoles);
});

test('church suggestions visible from personal login', async ({ request }) => {
  const response = await request.get(`${API_BASE}/email/suggestions/church/pending`, {
    headers: { 'X-User-Email': 'david.a.royes@gmail.com' }  // Personal login
  });
  expect(response.ok()).toBeTruthy();
  expect((await response.json()).account).toBe('church');
});
```

---

## Adding New Storage Modules

When creating a new storage module, ask:

1. **Is this data about David as a person?** → GLOBAL
   - Settings, preferences, identity, limits

2. **Is this data about a specific email inbox?** → ACCOUNT
   - Emails, suggestions, patterns, learning

3. **Could bypassing limits be a concern?** → GLOBAL
   - Usage counters, rate limits, quotas

### Checklist for New Modules

- [ ] Determine category (GLOBAL vs ACCOUNT)
- [ ] Use correct path pattern (see examples above)
- [ ] NO `user_id` parameter in function signatures
- [ ] ACCOUNT modules: `account` as first parameter
- [ ] Add cross-login E2E tests
- [ ] Update this document's module table

---

## Historical Context

This architecture was established in December 2025 after discovering that early modules incorrectly used login email as storage key, causing:

- Haiku daily limits effectively doubled (50 per login = 100 total)
- Profile changes invisible when switching logins
- Email suggestions scattered across login-specific storage

The fix involved updating all storage modules to use the correct key strategy and adding E2E tests to prevent regression.

---

## Related Files

- `.claude/CLAUDE.md` - Quick reference table for Claude Code sessions
- `attention_store.py` - Reference implementation for ACCOUNT pattern
- `profile.py` - Reference implementation for GLOBAL pattern
- `e2e-tests/tests/profile/profile-api.spec.ts` - Cross-login profile tests
- `e2e-tests/tests/suggestions/suggestion-tracking.spec.ts` - Cross-login suggestion tests
