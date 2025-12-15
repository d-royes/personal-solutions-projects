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

  test('decide endpoint requires authentication', async ({ request }) => {
    const response = await request.post(`${API_BASE}/email/suggestions/test-id/decide`, {
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
    const response = await request.post(`${API_BASE}/email/suggestions/non-existent-suggestion-id/decide`, {
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
    const response = await request.post(`${API_BASE}/email/suggestions/test-id/decide`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {}
    });
    // Should return 422 for validation error
    expect(response.status()).toBe(422);
  });
});

test.describe('Pending Suggestions API', () => {

  test('pending endpoint requires authentication', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/suggestions/pending`);
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('pending endpoint returns list structure', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/suggestions/pending`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('suggestions');
    expect(data).toHaveProperty('count');
    expect(Array.isArray(data.suggestions)).toBeTruthy();
    expect(typeof data.count).toBe('number');
  });

  test('pending endpoint filters by account', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/suggestions/pending?account=church`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.account).toBe('church');
  });
});

test.describe('Suggestion Statistics API', () => {

  test('stats endpoint requires authentication', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/suggestions/stats`);
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('stats endpoint returns correct structure', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/suggestions/stats`, {
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
    const response = await request.get(`${API_BASE}/email/suggestions/stats?days=7`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.days).toBe(7);
  });

  test('stats endpoint validates days parameter range', async ({ request }) => {
    // Days too low
    const response1 = await request.get(`${API_BASE}/email/suggestions/stats?days=0`, {
      headers: AUTH_HEADERS
    });
    expect(response1.status()).toBe(422);

    // Days too high
    const response2 = await request.get(`${API_BASE}/email/suggestions/stats?days=500`, {
      headers: AUTH_HEADERS
    });
    expect(response2.status()).toBe(422);
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
    const response = await request.get(`${API_BASE}/email/suggestions/stats`, {
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
    const response = await request.get(`${API_BASE}/email/suggestions/pending`, {
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
