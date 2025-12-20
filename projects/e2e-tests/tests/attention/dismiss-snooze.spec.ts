import { test, expect } from '@playwright/test';

/**
 * Dismiss/Snooze E2E Tests
 *
 * Tests for attention item dismiss and snooze functionality.
 * Sprint 4: User controls for attention items.
 */

const API_BASE = process.env.API_BASE || 'http://localhost:8000';
const AUTH_HEADERS = {
  'X-User-Email': 'david.a.royes@gmail.com'
};

test.describe('Dismiss API', () => {

  test('dismiss endpoint requires valid email ID', async ({ request }) => {
    const response = await request.post(`${API_BASE}/email/attention/personal/non-existent-id/dismiss`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        reason: 'handled'
      }
    });
    // Should return 404 for non-existent email
    expect(response.status()).toBe(404);
  });

  test('dismiss endpoint requires authentication', async ({ request }) => {
    const response = await request.post(`${API_BASE}/email/attention/personal/test-id/dismiss`, {
      headers: {
        'Content-Type': 'application/json'
      },
      data: {
        reason: 'handled'
      }
    });
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('dismiss endpoint validates reason', async ({ request }) => {
    const response = await request.post(`${API_BASE}/email/attention/personal/test-id/dismiss`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        reason: 'invalid_reason'
      }
    });
    // Should return 422 for validation error
    expect(response.status()).toBe(422);
  });

  test('dismiss endpoint accepts valid reasons', async ({ request }) => {
    const validReasons = ['handled', 'not_actionable', 'false_positive'];

    for (const reason of validReasons) {
      const response = await request.post(`${API_BASE}/email/attention/personal/test-id-${reason}/dismiss`, {
        headers: {
          ...AUTH_HEADERS,
          'Content-Type': 'application/json'
        },
        data: {
          reason
        }
      });
      // Should return 404 (not found) not 422 (validation error)
      // The endpoint accepts the reason but the email doesn't exist
      expect(response.status()).toBe(404);
    }
  });
});

test.describe('Snooze API', () => {

  test('snooze endpoint requires valid email ID', async ({ request }) => {
    const until = new Date();
    until.setHours(until.getHours() + 4);

    const response = await request.post(`${API_BASE}/email/attention/personal/non-existent-id/snooze`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        until: until.toISOString()
      }
    });
    // Should return 404 for non-existent email
    expect(response.status()).toBe(404);
  });

  test('snooze endpoint requires authentication', async ({ request }) => {
    const until = new Date();
    until.setHours(until.getHours() + 4);

    const response = await request.post(`${API_BASE}/email/attention/personal/test-id/snooze`, {
      headers: {
        'Content-Type': 'application/json'
      },
      data: {
        until: until.toISOString()
      }
    });
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('snooze endpoint requires valid datetime', async ({ request }) => {
    const response = await request.post(`${API_BASE}/email/attention/personal/test-id/snooze`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        until: 'not-a-valid-date'
      }
    });
    // Should return 422 for validation error
    expect(response.status()).toBe(422);
  });

  test('snooze endpoint accepts valid ISO datetime', async ({ request }) => {
    const until = new Date();
    until.setHours(until.getHours() + 24);

    const response = await request.post(`${API_BASE}/email/attention/personal/test-snooze-id/snooze`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        until: until.toISOString()
      }
    });
    // Should return 404 (not found) not 422 (validation error)
    // The endpoint accepts the datetime but the email doesn't exist
    expect(response.status()).toBe(404);
  });
});

test.describe('Attention List API', () => {

  test('attention list returns empty array when no items', async ({ request }) => {
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

  test('attention list works for church account', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/attention/church`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('account', 'church');
    expect(data).toHaveProperty('attentionItems');
    expect(Array.isArray(data.attentionItems)).toBeTruthy();
  });

  test('attention list requires authentication', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/attention/personal`);
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });
});

test.describe('Profile-Aware Response Fields', () => {

  test('analyze response includes profile fields on attention items', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/analyze/personal`, {
      headers: AUTH_HEADERS
    });

    // Skip if Gmail not configured
    if (!response.ok()) {
      const data = await response.json();
      if (data.detail && (data.detail.includes('Gmail') || data.detail.includes('config'))) {
        test.skip(true, 'Gmail credentials not configured');
        return;
      }
    }

    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('attentionItems');

    // If there are attention items, verify profile fields
    if (data.attentionItems.length > 0) {
      const item = data.attentionItems[0];

      // Sprint 3/4 fields should be present
      expect(item).toHaveProperty('matchedRole');
      expect(item).toHaveProperty('confidence');
      expect(item).toHaveProperty('analysisMethod');

      // Validate confidence is a number between 0 and 1
      expect(typeof item.confidence).toBe('number');
      expect(item.confidence).toBeGreaterThanOrEqual(0);
      expect(item.confidence).toBeLessThanOrEqual(1);

      // Validate analysisMethod is one of the valid values (includes 'haiku' for AI analysis)
      expect(['regex', 'profile', 'vip', 'haiku']).toContain(item.analysisMethod);
    }
  });
});
