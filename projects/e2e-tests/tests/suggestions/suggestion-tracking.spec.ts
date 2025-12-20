import { test, expect } from '@playwright/test';

/**
 * Suggestion Tracking E2E Tests
 *
 * Tests for Sprint 5: Learning Foundation
 * - Suggestion approval/rejection tracking
 * - Approval statistics
 * - Profile feedback loop
 */

const API_BASE = process.env.API_BASE || 'http://localhost:8000';
const AUTH_HEADERS = {
  'X-User-Email': 'david.a.royes@gmail.com'
};

test.describe('Suggestion Decision API', () => {
  // Note: URL now includes account in path: /email/suggestions/{account}/{id}/decide

  test('decide endpoint requires authentication', async ({ request }) => {
    const response = await request.post(`${API_BASE}/email/suggestions/church/test-id/decide`, {
      headers: {
        'Content-Type': 'application/json'
      },
      data: {
        approved: true
      }
    });
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('decide endpoint returns 404 for non-existent suggestion', async ({ request }) => {
    const response = await request.post(`${API_BASE}/email/suggestions/church/non-existent-suggestion-id/decide`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        approved: true
      }
    });
    expect(response.status()).toBe(404);
  });

  test('decide endpoint requires approved field', async ({ request }) => {
    const response = await request.post(`${API_BASE}/email/suggestions/church/test-id/decide`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {}
    });
    // Should return 422 for validation error
    expect(response.status()).toBe(422);
  });

  test('decide endpoint validates account', async ({ request }) => {
    const response = await request.post(`${API_BASE}/email/suggestions/invalid-account/test-id/decide`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        approved: true
      }
    });
    expect(response.status()).toBe(422);
  });
});

test.describe('Pending Suggestions API', () => {
  // Note: URL now requires account in path: /email/suggestions/{account}/pending

  test('pending endpoint requires authentication', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/suggestions/church/pending`);
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('pending endpoint returns list structure for church', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/suggestions/church/pending`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('suggestions');
    expect(data).toHaveProperty('count');
    expect(data).toHaveProperty('account');
    expect(data.account).toBe('church');
    expect(Array.isArray(data.suggestions)).toBeTruthy();
    expect(typeof data.count).toBe('number');
  });

  test('pending endpoint returns list structure for personal', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/suggestions/personal/pending`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('account');
    expect(data.account).toBe('personal');
  });

  test('pending endpoint validates account', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/suggestions/invalid/pending`, {
      headers: AUTH_HEADERS
    });
    expect(response.status()).toBe(422);
  });
});

test.describe('Suggestion Statistics API', () => {
  // Note: URL now requires account in path: /email/suggestions/{account}/stats

  test('stats endpoint requires authentication', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/suggestions/church/stats`);
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('stats endpoint returns correct structure', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/suggestions/church/stats`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('days');
    expect(data).toHaveProperty('total');
    expect(data).toHaveProperty('approved');
    expect(data).toHaveProperty('rejected');
    expect(data).toHaveProperty('expired');
    expect(data).toHaveProperty('pending');
    expect(data).toHaveProperty('approvalRate');
    expect(data).toHaveProperty('byAction');
    expect(data).toHaveProperty('byMethod');

    // Validate types
    expect(typeof data.total).toBe('number');
    expect(typeof data.approvalRate).toBe('number');
    expect(data.approvalRate).toBeGreaterThanOrEqual(0);
    expect(data.approvalRate).toBeLessThanOrEqual(1);
  });

  test('stats endpoint accepts days parameter', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/suggestions/church/stats?days=7`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.days).toBe(7);
  });

  test('stats endpoint validates days parameter range', async ({ request }) => {
    // Days too low
    const response1 = await request.get(`${API_BASE}/email/suggestions/church/stats?days=0`, {
      headers: AUTH_HEADERS
    });
    expect(response1.status()).toBe(422);

    // Days too high
    const response2 = await request.get(`${API_BASE}/email/suggestions/church/stats?days=500`, {
      headers: AUTH_HEADERS
    });
    expect(response2.status()).toBe(422);
  });

  test('stats endpoint validates account', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/suggestions/invalid/stats`, {
      headers: AUTH_HEADERS
    });
    expect(response.status()).toBe(422);
  });
});

test.describe('Rejection Patterns API', () => {

  test('rejection patterns endpoint requires authentication', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/suggestions/rejection-patterns`);
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('rejection patterns endpoint returns correct structure', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/suggestions/rejection-patterns`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('days');
    expect(data).toHaveProperty('minRejections');
    expect(data).toHaveProperty('candidates');
    expect(data.candidates).toHaveProperty('church');
    expect(data.candidates).toHaveProperty('personal');
    expect(Array.isArray(data.candidates.church)).toBeTruthy();
    expect(Array.isArray(data.candidates.personal)).toBeTruthy();
  });

  test('rejection patterns endpoint accepts parameters', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/suggestions/rejection-patterns?days=14&min_rejections=2`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.days).toBe(14);
    expect(data.minRejections).toBe(2);
  });
});

test.describe('Profile Pattern Management API', () => {

  test('add pattern endpoint requires authentication', async ({ request }) => {
    const response = await request.post(`${API_BASE}/profile/not-actionable/add`, {
      headers: {
        'Content-Type': 'application/json'
      },
      data: {
        account: 'personal',
        pattern: 'test pattern'
      }
    });
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('add pattern endpoint requires valid account', async ({ request }) => {
    const response = await request.post(`${API_BASE}/profile/not-actionable/add`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        account: 'invalid',
        pattern: 'test pattern'
      }
    });
    expect(response.status()).toBe(422);
  });

  test('add pattern endpoint requires minimum pattern length', async ({ request }) => {
    const response = await request.post(`${API_BASE}/profile/not-actionable/add`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        account: 'personal',
        pattern: 'ab'  // Too short
      }
    });
    expect(response.status()).toBe(422);
  });

  test('remove pattern endpoint requires authentication', async ({ request }) => {
    const response = await request.post(`${API_BASE}/profile/not-actionable/remove`, {
      headers: {
        'Content-Type': 'application/json'
      },
      data: {
        account: 'personal',
        pattern: 'test pattern'
      }
    });
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('remove pattern returns not found for non-existent pattern', async ({ request }) => {
    const response = await request.post(`${API_BASE}/profile/not-actionable/remove`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        account: 'personal',
        pattern: 'non-existent-pattern-xyz-123'
      }
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.success).toBe(false);
    expect(data.message).toContain('not found');
  });
});

test.describe('Suggestion API Response Format', () => {

  test('suggestions endpoint returns camelCase field names', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/suggestions/church/stats`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    // Verify camelCase
    expect(data).toHaveProperty('approvalRate');
    expect(data).toHaveProperty('byAction');
    expect(data).toHaveProperty('byMethod');

    // Verify NOT snake_case
    expect(data).not.toHaveProperty('approval_rate');
    expect(data).not.toHaveProperty('by_action');
    expect(data).not.toHaveProperty('by_method');
  });

  test('pending suggestions include required fields', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/suggestions/church/pending`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    // If there are suggestions, verify structure
    if (data.suggestions.length > 0) {
      const suggestion = data.suggestions[0];
      expect(suggestion).toHaveProperty('suggestionId');
      expect(suggestion).toHaveProperty('emailId');
      expect(suggestion).toHaveProperty('emailAccount');
      expect(suggestion).toHaveProperty('action');
      expect(suggestion).toHaveProperty('rationale');
      expect(suggestion).toHaveProperty('confidence');
      expect(suggestion).toHaveProperty('status');
    }
  });
});

test.describe('Cross-Login Suggestion Access', () => {
  // Verify suggestions are accessible regardless of login identity
  const PERSONAL_USER = 'david.a.royes@gmail.com';
  const CHURCH_USER = 'davidroyes@southpointsda.org';

  test('church suggestions visible from personal login', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/suggestions/church/pending`, {
      headers: { 'X-User-Email': PERSONAL_USER }
    });
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.account).toBe('church');
  });

  test('personal suggestions visible from church login', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/suggestions/personal/pending`, {
      headers: { 'X-User-Email': CHURCH_USER }
    });
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.account).toBe('personal');
  });
});
