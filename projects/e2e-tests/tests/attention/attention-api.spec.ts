import { test, expect } from '@playwright/test';

/**
 * Attention Persistence API Tests
 *
 * Tests for the attention item persistence system.
 * Sprint 2: E2E tests for attention persistence (dismiss, snooze, reload)
 */

const API_BASE = process.env.API_BASE || 'http://localhost:8000';
const AUTH_HEADERS = {
  'X-User-Email': 'david.a.royes@gmail.com'
};

test.describe('Attention API - GET /email/attention/{account}', () => {

  test('attention endpoint responds with authenticated user', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/attention/personal`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('account', 'personal');
    expect(data).toHaveProperty('attentionItems');
    expect(data).toHaveProperty('count');
    expect(Array.isArray(data.attentionItems)).toBeTruthy();
  });

  test('attention endpoint returns correct structure for items', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/attention/church`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.account).toBe('church');

    // If there are any attention items, verify structure
    if (data.attentionItems.length > 0) {
      const item = data.attentionItems[0];
      expect(item).toHaveProperty('emailId');
      expect(item).toHaveProperty('emailAccount');
      expect(item).toHaveProperty('subject');
      expect(item).toHaveProperty('fromAddress');
      expect(item).toHaveProperty('date');
      expect(item).toHaveProperty('reason');
      expect(item).toHaveProperty('urgency');
      expect(item).toHaveProperty('status');
    }
  });

  test('attention endpoint requires authentication', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/attention/personal`);
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });
});

test.describe('Attention API - Analyze with Persistence', () => {

  test('analyze endpoint returns persistence counts when Gmail configured', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/analyze/personal`, {
      headers: AUTH_HEADERS
    });

    // If Gmail isn't configured, we expect a 400 error - skip this test
    if (response.status() === 400) {
      const data = await response.json();
      if (data.detail && data.detail.includes('Gmail config error')) {
        test.skip(true, 'Gmail credentials not configured');
        return;
      }
    }

    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('account', 'personal');
    expect(data).toHaveProperty('attentionItems');
    expect(data).toHaveProperty('persistedCount');
    expect(data).toHaveProperty('newCount');
    expect(typeof data.persistedCount).toBe('number');
    expect(typeof data.newCount).toBe('number');
  });

  test('analyze endpoint includes persisted items in response when Gmail configured', async ({ request }) => {
    // This test makes two sequential analyze calls, each ~20s, so we need longer timeout
    test.setTimeout(60000);
    // First call to populate persistence
    const response1 = await request.get(`${API_BASE}/email/analyze/personal`, {
      headers: AUTH_HEADERS
    });

    // If Gmail isn't configured, skip this test
    if (response1.status() === 400) {
      const data = await response1.json();
      if (data.detail && data.detail.includes('Gmail config error')) {
        test.skip(true, 'Gmail credentials not configured');
        return;
      }
    }

    expect(response1.ok()).toBeTruthy();
    const data1 = await response1.json();

    // Second call should see persisted items
    const response2 = await request.get(`${API_BASE}/email/analyze/personal`, {
      headers: AUTH_HEADERS
    });
    expect(response2.ok()).toBeTruthy();
    const data2 = await response2.json();

    // If first call had attention items, they should be persisted
    if (data1.attentionItems.length > 0) {
      expect(data2.persistedCount).toBeGreaterThan(0);
    }
  });
});

test.describe('Attention API - Dismiss', () => {

  test('dismiss endpoint requires valid reason', async ({ request }) => {
    // Test with invalid reason - should fail validation
    const response = await request.post(
      `${API_BASE}/email/attention/personal/test-email-id/dismiss`,
      {
        headers: {
          ...AUTH_HEADERS,
          'Content-Type': 'application/json'
        },
        data: {
          reason: 'invalid_reason'
        }
      }
    );
    // Should reject invalid reason (422 validation error)
    expect(response.status()).toBe(422);
  });

  test('dismiss endpoint returns 404 for non-existent item', async ({ request }) => {
    const response = await request.post(
      `${API_BASE}/email/attention/personal/non-existent-email-id/dismiss`,
      {
        headers: {
          ...AUTH_HEADERS,
          'Content-Type': 'application/json'
        },
        data: {
          reason: 'not_actionable'
        }
      }
    );
    expect(response.status()).toBe(404);
  });

  test('dismiss endpoint requires authentication', async ({ request }) => {
    const response = await request.post(
      `${API_BASE}/email/attention/personal/test-id/dismiss`,
      {
        headers: {
          'Content-Type': 'application/json'
        },
        data: {
          reason: 'handled'
        }
      }
    );
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });
});

test.describe('Attention API - Snooze', () => {

  test('snooze endpoint requires valid datetime', async ({ request }) => {
    const response = await request.post(
      `${API_BASE}/email/attention/personal/test-email-id/snooze`,
      {
        headers: {
          ...AUTH_HEADERS,
          'Content-Type': 'application/json'
        },
        data: {
          until: 'not-a-datetime'
        }
      }
    );
    // Should reject invalid datetime (422 validation error)
    expect(response.status()).toBe(422);
  });

  test('snooze endpoint returns 404 for non-existent item', async ({ request }) => {
    const futureDate = new Date();
    futureDate.setDate(futureDate.getDate() + 1);

    const response = await request.post(
      `${API_BASE}/email/attention/personal/non-existent-email-id/snooze`,
      {
        headers: {
          ...AUTH_HEADERS,
          'Content-Type': 'application/json'
        },
        data: {
          until: futureDate.toISOString()
        }
      }
    );
    expect(response.status()).toBe(404);
  });

  test('snooze endpoint requires authentication', async ({ request }) => {
    const futureDate = new Date();
    futureDate.setDate(futureDate.getDate() + 1);

    const response = await request.post(
      `${API_BASE}/email/attention/personal/test-id/snooze`,
      {
        headers: {
          'Content-Type': 'application/json'
        },
        data: {
          until: futureDate.toISOString()
        }
      }
    );
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });
});

test.describe('Attention API - Field Naming Convention', () => {

  test('API returns camelCase field names', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/attention/personal`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('attentionItems');
    expect(data).not.toHaveProperty('attention_items');

    // If there are items, verify camelCase
    if (data.attentionItems.length > 0) {
      const item = data.attentionItems[0];
      expect(item).toHaveProperty('emailId');
      expect(item).toHaveProperty('emailAccount');
      expect(item).toHaveProperty('fromAddress');
      expect(item).toHaveProperty('suggestedAction');

      // Verify NOT snake_case
      expect(item).not.toHaveProperty('email_id');
      expect(item).not.toHaveProperty('email_account');
      expect(item).not.toHaveProperty('from_address');
    }
  });

  test('analyze endpoint returns camelCase persistence counts when Gmail configured', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/analyze/personal`, {
      headers: AUTH_HEADERS
    });

    // If Gmail isn't configured, skip this test
    if (response.status() === 400) {
      const data = await response.json();
      if (data.detail && data.detail.includes('Gmail config error')) {
        test.skip(true, 'Gmail credentials not configured');
        return;
      }
    }

    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('persistedCount');
    expect(data).toHaveProperty('newCount');
    expect(data).toHaveProperty('attentionItems');

    // Verify NOT snake_case
    expect(data).not.toHaveProperty('persisted_count');
    expect(data).not.toHaveProperty('new_count');
    expect(data).not.toHaveProperty('attention_items');
  });
});
