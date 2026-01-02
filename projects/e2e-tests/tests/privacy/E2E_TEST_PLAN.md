# E2E Test Plan: Email Experience Enhancement

> **Created**: December 31, 2025
> **Updated**: January 1, 2026
> **Status**: IMPLEMENTED
> **Sprint**: Q1 2025 - Sprint 2

---

## Overview

This document outlines the E2E tests needed to validate the Email Experience Enhancement feature set:

1. **Email Conversation Persistence** - Chat history by thread_id
2. **Privacy Controls (3-tier)** - Sender blocklist, Gmail labels, PII detection
3. **Stale Item Validation** - Auto-dismiss when emails are deleted/archived
4. **Blocklist Management** - CRUD for sender blocklist

---

## Test Files to Create

### 1. `privacy/blocklist-api.spec.ts`

Tests for the sender blocklist CRUD endpoints.

```typescript
// Planned Tests:

describe('Blocklist API - GET /profile/blocklist', () => {
  test('blocklist endpoint requires authentication');
  test('blocklist endpoint returns correct structure');
  test('blocklist returns array of sender emails');
});

describe('Blocklist API - POST /profile/blocklist/add', () => {
  test('add endpoint requires authentication');
  test('add endpoint requires senderEmail field');
  test('add endpoint validates email format (min 3 chars)');
  test('add endpoint returns success for new sender');
  test('add endpoint returns success=false for duplicate');
  test('added sender appears in GET /profile/blocklist');
});

describe('Blocklist API - POST /profile/blocklist/remove', () => {
  test('remove endpoint requires authentication');
  test('remove endpoint requires senderEmail field');
  test('remove endpoint returns success for existing sender');
  test('remove endpoint returns success=false for non-existent');
  test('removed sender no longer in GET /profile/blocklist');
});

describe('Blocklist API - GLOBAL Storage', () => {
  test('blocklist visible from both login identities');
  test('blocklist changes from personal visible from church');
  test('blocklist changes from church visible from personal');
});
```

**Dependencies**: Backend only (no frontend integration needed)

---

### 2. `privacy/privacy-check.spec.ts`

Tests for the email privacy status check endpoint.

```typescript
// Planned Tests:

describe('Privacy Check API - GET /email/{account}/privacy/{email_id}', () => {
  test('privacy check requires authentication');
  test('privacy check validates account (church/personal)');
  test('privacy check returns 502 for invalid email_id');
  test('privacy check returns correct structure');
  test('privacy check returns isBlocked: false for normal sender');
});

describe('Privacy Check Response Structure', () => {
  test('response includes fromAddress');
  test('response includes privacy.isBlocked');
  test('response includes privacy.reason (when blocked)');
  test('response includes privacy.senderBlocked');
  test('response includes privacy.domainSensitive');
  test('response includes privacy.labelSensitive');
  test('response includes privacy.canRequestOverride');
});
```

**Dependencies**: Backend + Gmail API (needs real email_id for testing)

**Note**: Privacy check tests require actual Gmail messages. Consider using known test emails or mocking.

---

### 3. `chat/email-conversation.spec.ts`

Tests for email conversation persistence.

```typescript
// Planned Tests:

describe('Conversation API - GET /email/{account}/conversation/{thread_id}', () => {
  test('conversation endpoint requires authentication');
  test('conversation endpoint validates account');
  test('conversation endpoint returns empty for new thread');
  test('conversation endpoint returns messages array');
  test('conversation endpoint respects limit parameter');
  test('conversation endpoint returns metadata when available');
});

describe('Conversation API - DELETE /email/{account}/conversation/{thread_id}', () => {
  test('clear conversation requires authentication');
  test('clear conversation returns messagesCleared count');
  test('cleared conversation returns empty on subsequent GET');
});

describe('Chat Persistence - POST /email/{account}/chat', () => {
  test('chat requires authentication');
  test('chat validates account');
  test('chat response includes threadId');
  test('chat response includes privacyStatus');
  test('chat persists user message to conversation');
  test('chat persists assistant response to conversation');
  test('subsequent GET returns both messages');
  test('chat with override_privacy=true includes body');
});

describe('Chat Privacy Integration', () => {
  test('chat response includes canSeeBody in privacyStatus');
  test('chat response includes blockedReason when blocked');
  test('chat with blocked sender does not include body in context');
});
```

**Dependencies**: Backend + Gmail API + Anthropic API

**Note**: Chat tests require:
- Real email_id and thread_id
- Working Anthropic API key
- Consider mocking LLM responses for faster tests

---

### 4. `suggestions/stale-detection.spec.ts`

Tests for stale item detection in suggestion decisions.

```typescript
// Planned Tests:

describe('Stale Detection - POST /email/suggestions/{account}/{suggestion_id}/decide', () => {
  test('decide response includes stale: false for valid email');
  test('decide response structure includes stale field');
  // Note: Testing stale=true requires deleting an email after creating suggestion
  // This is difficult to test without mocking Gmail API
});
```

**Dependencies**: Backend + Gmail API + Suggestion with valid email

**Note**: Full stale detection testing requires:
1. Create a suggestion for an email
2. Delete/archive the email in Gmail
3. Call decide endpoint
4. Verify stale: true response

This is challenging to automate without:
- Test Gmail account with disposable emails
- Gmail API access for email deletion
- Time for email deletion to propagate

---

## Test Priority

| Test File | Priority | Complexity | Dependencies |
|-----------|----------|------------|--------------|
| `blocklist-api.spec.ts` | **High** | Low | Backend only |
| `privacy-check.spec.ts` | Medium | Medium | Backend + Gmail |
| `email-conversation.spec.ts` | Medium | High | Backend + Gmail + Anthropic |
| `stale-detection.spec.ts` | Low | High | Requires email deletion |

---

## Recommended Testing Strategy

### Phase 1: Backend API Tests (Can Test Now)

Create `blocklist-api.spec.ts` immediately - no external dependencies:

```bash
# Create and run blocklist tests
cd projects/e2e-tests
npm test -- tests/privacy/blocklist-api.spec.ts
```

### Phase 2: Integration Tests (After Frontend)

After frontend updates:
1. Create conversation persistence tests
2. Add privacy indicator UI tests
3. Test "Share with DATA" button flow

### Phase 3: Manual Validation

Some scenarios are better tested manually:
- Stale email detection (requires email deletion)
- PII detection accuracy
- Privacy override UX flow

---

## Blockers for Full E2E Testing

1. **Gmail API Mocking**: Tests that check email existence need either:
   - Mock Gmail responses
   - Dedicated test Gmail account
   - Known stable email IDs

2. **Anthropic API Costs**: Chat tests call real LLM, consider:
   - Mocking LLM responses for unit tests
   - Limiting E2E chat tests to critical paths

3. **Frontend Pending**: UI tests blocked until components updated

---

## Files to Create

```
e2e-tests/tests/
├── privacy/
│   ├── blocklist-api.spec.ts      # High priority - ready now
│   ├── privacy-check.spec.ts      # Medium priority - needs email IDs
│   └── E2E_TEST_PLAN.md           # This document
├── chat/
│   └── email-conversation.spec.ts # Medium priority - needs frontend
└── suggestions/
    └── stale-detection.spec.ts    # Low priority - complex setup
```

---

## Success Criteria

| Feature | Passing Tests | Coverage |
|---------|--------------|----------|
| Blocklist CRUD | All 12 tests | 100% |
| Privacy Check | 8+ tests | 80% |
| Conversation Persistence | 10+ tests | 80% |
| Stale Detection | 2+ tests | Manual validation |

---

## Completed Tests

| Test File | Location | Tests |
|-----------|----------|-------|
| `blocklist-api.spec.ts` | `privacy/` | 16 tests - Blocklist CRUD + GLOBAL storage |
| `privacy-check.spec.ts` | `privacy/` | 12 tests - Privacy status endpoint |
| `email-conversation.spec.ts` | `chat/` | 14 tests - Conversation persistence |
| `stale-detection.spec.ts` | `attention/` | 10 tests - Stale item detection |

## Next Steps

1. **Run**: Execute all new tests to validate implementation
2. **Monitor**: Watch for regressions in CI pipeline
3. **Extend**: Add integration tests for chat with LLM (requires mock or staging)
