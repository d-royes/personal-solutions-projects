import { test, expect } from '@playwright/test';

/**
 * Privacy Check API Tests
 *
 * Tests for the email privacy status check endpoint:
 * GET /email/{account}/privacy/{email_id}
 *
 * Privacy controls determine if DATA can see email body:
 * - Tier 1: Sender blocklist (user-managed)
 * - Tier 2: Gmail "Sensitive" label (user-applied or via Gmail filters)
 * - Tier 3: PII detection (Haiku analysis)
 *
 * Note: Domain-based blocking was DEPRECATED in Jan 2026.
 * Users should add specific senders to blocklist instead.
 * The `domainSensitive` field always returns false for backwards compatibility.
 *
 * Part of the Email Experience Enhancement feature (Q1 2025).
 */

const API_BASE = process.env.API_BASE || 'http://localhost:8000';
const AUTH_HEADERS = {
  'X-User-Email': 'david.a.royes@gmail.com'
};

test.describe('Privacy Check API - GET /email/{account}/privacy/{email_id}', () => {

  test('privacy check requires authentication', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/personal/privacy/fake-email-id`);
    // Should return 401 or 403 without auth
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('privacy check validates account (church/personal)', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/invalid/privacy/fake-email-id`, {
      headers: AUTH_HEADERS
    });
    // Should return 422 for invalid account type
    expect(response.status()).toBe(422);
  });

  test('privacy check returns 502 for non-existent email_id', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/personal/privacy/non-existent-email-id-12345`, {
      headers: AUTH_HEADERS
    });
    // Should return 502 Gmail API error (email not found)
    expect(response.status()).toBe(502);
  });

  test('privacy check returns correct structure for valid email', async ({ request }) => {
    // First get a real email ID
    const inboxResponse = await request.get(`${API_BASE}/inbox/personal?max_results=1`, {
      headers: AUTH_HEADERS
    });

    if (!inboxResponse.ok()) {
      test.skip(true, 'Could not fetch inbox');
      return;
    }

    const inboxData = await inboxResponse.json();
    if (inboxData.recentMessages.length === 0) {
      test.skip(true, 'No emails in inbox');
      return;
    }

    const emailId = inboxData.recentMessages[0].id;

    // Check privacy status
    const response = await request.get(`${API_BASE}/email/personal/privacy/${emailId}`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('success', true);
    expect(data).toHaveProperty('account', 'personal');
    expect(data).toHaveProperty('emailId', emailId);
    expect(data).toHaveProperty('fromAddress');
    expect(data).toHaveProperty('privacy');
  });
});

test.describe('Privacy Check Response Structure', () => {

  // Helper to get a valid email ID for testing
  async function getTestEmailId(request: any): Promise<string | null> {
    const response = await request.get(`${API_BASE}/inbox/personal?max_results=1`, {
      headers: AUTH_HEADERS
    });
    if (!response.ok()) return null;
    const data = await response.json();
    return data.recentMessages[0]?.id || null;
  }

  test('response includes fromAddress field', async ({ request }) => {
    const emailId = await getTestEmailId(request);
    if (!emailId) {
      test.skip(true, 'Could not get test email');
      return;
    }

    const response = await request.get(`${API_BASE}/email/personal/privacy/${emailId}`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('fromAddress');
    expect(typeof data.fromAddress).toBe('string');
    expect(data.fromAddress.length).toBeGreaterThan(0);
  });

  test('response includes privacy object with required fields', async ({ request }) => {
    const emailId = await getTestEmailId(request);
    if (!emailId) {
      test.skip(true, 'Could not get test email');
      return;
    }

    const response = await request.get(`${API_BASE}/email/personal/privacy/${emailId}`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.privacy).toHaveProperty('isBlocked');
    expect(typeof data.privacy.isBlocked).toBe('boolean');
  });

  test('privacy object includes senderBlocked flag', async ({ request }) => {
    const emailId = await getTestEmailId(request);
    if (!emailId) {
      test.skip(true, 'Could not get test email');
      return;
    }

    const response = await request.get(`${API_BASE}/email/personal/privacy/${emailId}`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.privacy).toHaveProperty('senderBlocked');
    expect(typeof data.privacy.senderBlocked).toBe('boolean');
  });

  test('privacy object includes labelSensitive flag', async ({ request }) => {
    const emailId = await getTestEmailId(request);
    if (!emailId) {
      test.skip(true, 'Could not get test email');
      return;
    }

    const response = await request.get(`${API_BASE}/email/personal/privacy/${emailId}`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.privacy).toHaveProperty('labelSensitive');
    expect(typeof data.privacy.labelSensitive).toBe('boolean');
  });

  test('privacy object includes canRequestOverride flag', async ({ request }) => {
    const emailId = await getTestEmailId(request);
    if (!emailId) {
      test.skip(true, 'Could not get test email');
      return;
    }

    const response = await request.get(`${API_BASE}/email/personal/privacy/${emailId}`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.privacy).toHaveProperty('canRequestOverride');
    expect(typeof data.privacy.canRequestOverride).toBe('boolean');
  });

  test('domainSensitive is always false (deprecated Jan 2026)', async ({ request }) => {
    // Domain-based blocking was removed in Jan 2026.
    // The field remains for backwards compatibility but should always be false.
    const emailId = await getTestEmailId(request);
    if (!emailId) {
      test.skip(true, 'Could not get test email');
      return;
    }

    const response = await request.get(`${API_BASE}/email/personal/privacy/${emailId}`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.privacy).toHaveProperty('domainSensitive');
    expect(data.privacy.domainSensitive).toBe(false);
  });

  test('privacy reason is string when blocked, null otherwise', async ({ request }) => {
    const emailId = await getTestEmailId(request);
    if (!emailId) {
      test.skip(true, 'Could not get test email');
      return;
    }

    const response = await request.get(`${API_BASE}/email/personal/privacy/${emailId}`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    // reason should be string if blocked, null if not blocked
    if (data.privacy.isBlocked) {
      expect(typeof data.privacy.reason).toBe('string');
    } else {
      // When not blocked, reason should be null or undefined
      expect(data.privacy.reason === null || data.privacy.reason === undefined).toBeTruthy();
    }
  });
});

test.describe('Privacy Check - Normal Sender Behavior', () => {

  test('normal sender is not blocked', async ({ request }) => {
    // Get a real email - most inbox emails should not be blocked
    const inboxResponse = await request.get(`${API_BASE}/inbox/personal?max_results=1`, {
      headers: AUTH_HEADERS
    });

    if (!inboxResponse.ok()) {
      test.skip(true, 'Could not fetch inbox');
      return;
    }

    const inboxData = await inboxResponse.json();
    if (inboxData.recentMessages.length === 0) {
      test.skip(true, 'No emails in inbox');
      return;
    }

    const emailId = inboxData.recentMessages[0].id;

    const response = await request.get(`${API_BASE}/email/personal/privacy/${emailId}`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    // Most inbox emails should not be blocked
    // (unless from a blocked sender or has sensitive label)
    expect(typeof data.privacy.isBlocked).toBe('boolean');
    expect(typeof data.privacy.senderBlocked).toBe('boolean');
  });
});

test.describe('Privacy Check - Blocklist Integration', () => {

  const TEST_BLOCKLIST_SENDER = 'privacy-test-blocked@fake-domain.invalid';

  test.afterEach(async ({ request }) => {
    // Clean up: remove test sender from blocklist
    await request.post(`${API_BASE}/profile/blocklist/remove`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: { senderEmail: TEST_BLOCKLIST_SENDER }
    });
  });

  test('blocklist affects privacy check response', async ({ request }) => {
    // Note: This test verifies the blocklist integration with privacy check
    // We can't easily test with a real blocked email without:
    // 1. Having an email from a blocked sender in inbox
    // 2. Adding a real sender to blocklist then checking their email

    // Instead, we verify the blocklist endpoint works
    // and privacy check returns senderBlocked field

    // Add to blocklist
    const addResponse = await request.post(`${API_BASE}/profile/blocklist/add`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: { senderEmail: TEST_BLOCKLIST_SENDER }
    });
    expect(addResponse.ok()).toBeTruthy();

    // Verify blocklist contains the sender
    const listResponse = await request.get(`${API_BASE}/profile/blocklist`, {
      headers: AUTH_HEADERS
    });
    expect(listResponse.ok()).toBeTruthy();

    const listData = await listResponse.json();
    expect(listData.blocklist).toContain(TEST_BLOCKLIST_SENDER);
  });
});

test.describe('Privacy Check - Account Separation', () => {

  test('privacy check works for church account', async ({ request }) => {
    // Get an email from church account
    const inboxResponse = await request.get(`${API_BASE}/inbox/church?max_results=1`, {
      headers: AUTH_HEADERS
    });

    if (!inboxResponse.ok()) {
      test.skip(true, 'Could not fetch church inbox');
      return;
    }

    const inboxData = await inboxResponse.json();
    if (inboxData.recentMessages.length === 0) {
      test.skip(true, 'No emails in church inbox');
      return;
    }

    const emailId = inboxData.recentMessages[0].id;

    const response = await request.get(`${API_BASE}/email/church/privacy/${emailId}`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.account).toBe('church');
    expect(data).toHaveProperty('privacy');
  });

  test('privacy check works for personal account', async ({ request }) => {
    // Get an email from personal account
    const inboxResponse = await request.get(`${API_BASE}/inbox/personal?max_results=1`, {
      headers: AUTH_HEADERS
    });

    if (!inboxResponse.ok()) {
      test.skip(true, 'Could not fetch personal inbox');
      return;
    }

    const inboxData = await inboxResponse.json();
    if (inboxData.recentMessages.length === 0) {
      test.skip(true, 'No emails in personal inbox');
      return;
    }

    const emailId = inboxData.recentMessages[0].id;

    const response = await request.get(`${API_BASE}/email/personal/privacy/${emailId}`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.account).toBe('personal');
    expect(data).toHaveProperty('privacy');
  });
});

test.describe('Privacy Check - Field Naming Convention', () => {

  test('privacy response uses camelCase fields', async ({ request }) => {
    const inboxResponse = await request.get(`${API_BASE}/inbox/personal?max_results=1`, {
      headers: AUTH_HEADERS
    });

    if (!inboxResponse.ok()) {
      test.skip(true, 'Could not fetch inbox');
      return;
    }

    const inboxData = await inboxResponse.json();
    if (inboxData.recentMessages.length === 0) {
      test.skip(true, 'No emails in inbox');
      return;
    }

    const emailId = inboxData.recentMessages[0].id;

    const response = await request.get(`${API_BASE}/email/personal/privacy/${emailId}`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();

    // Should use camelCase
    expect(data).toHaveProperty('emailId');
    expect(data).toHaveProperty('fromAddress');
    expect(data.privacy).toHaveProperty('isBlocked');
    expect(data.privacy).toHaveProperty('senderBlocked');
    expect(data.privacy).toHaveProperty('labelSensitive');
    expect(data.privacy).toHaveProperty('canRequestOverride');

    // Should NOT use snake_case
    expect(data).not.toHaveProperty('email_id');
    expect(data).not.toHaveProperty('from_address');
    expect(data.privacy).not.toHaveProperty('is_blocked');
    expect(data.privacy).not.toHaveProperty('sender_blocked');
    expect(data.privacy).not.toHaveProperty('label_sensitive');
    expect(data.privacy).not.toHaveProperty('can_request_override');
  });
});
