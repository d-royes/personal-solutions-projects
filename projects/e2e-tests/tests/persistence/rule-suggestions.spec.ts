import { test, expect } from '@playwright/test';

/**
 * Rule Suggestions Persistence E2E Tests
 *
 * Tests for F1 Persistence Layer: Rule Suggestions
 * - Pending rule suggestions API
 * - Rule decision tracking (approve/reject)
 * - Rule statistics for Trust Gradient
 */

const API_BASE = process.env.API_BASE || 'http://localhost:8000';
const AUTH_HEADERS = {
  'X-User-Email': 'david.a.royes@gmail.com'
};

test.describe('Pending Rules API - GET /email/rules/{account}/pending', () => {

  test('pending rules endpoint requires authentication', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/rules/church/pending`);
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('pending rules endpoint returns list structure for church', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/rules/church/pending`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('rules');
    expect(data).toHaveProperty('count');
    expect(data).toHaveProperty('account');
    expect(data.account).toBe('church');
    expect(Array.isArray(data.rules)).toBeTruthy();
    expect(typeof data.count).toBe('number');
  });

  test('pending rules endpoint returns list structure for personal', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/rules/personal/pending`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('account');
    expect(data.account).toBe('personal');
  });

  test('pending rules endpoint validates account', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/rules/invalid/pending`, {
      headers: AUTH_HEADERS
    });
    expect(response.status()).toBe(422);
  });

  test('pending rules include required fields when present', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/rules/church/pending`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    // If there are rules, verify structure
    if (data.rules.length > 0) {
      const rule = data.rules[0];
      expect(rule).toHaveProperty('ruleId');
      expect(rule).toHaveProperty('emailAccount');
      expect(rule).toHaveProperty('suggestionType');
      expect(rule).toHaveProperty('suggestedRule');
      expect(rule).toHaveProperty('reason');
      expect(rule).toHaveProperty('confidence');
      expect(rule).toHaveProperty('status');
    }
  });
});

test.describe('Rule Decision API - POST /email/rules/{account}/{rule_id}/decide', () => {

  test('decide endpoint requires authentication', async ({ request }) => {
    const response = await request.post(`${API_BASE}/email/rules/church/test-rule-id/decide`, {
      headers: {
        'Content-Type': 'application/json'
      },
      data: {
        approved: true
      }
    });
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('decide endpoint returns 404 for non-existent rule', async ({ request }) => {
    const response = await request.post(`${API_BASE}/email/rules/church/non-existent-rule-id/decide`, {
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
    const response = await request.post(`${API_BASE}/email/rules/church/test-rule-id/decide`, {
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
    const response = await request.post(`${API_BASE}/email/rules/invalid-account/test-rule-id/decide`, {
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

test.describe('Rule Statistics API - GET /email/rules/{account}/stats', () => {

  test('stats endpoint requires authentication', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/rules/church/stats`);
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('stats endpoint returns correct structure', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/rules/church/stats`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('days');
    expect(data).toHaveProperty('total');
    expect(data).toHaveProperty('approved');
    expect(data).toHaveProperty('rejected');
    expect(data).toHaveProperty('pending');
    expect(data).toHaveProperty('approvalRate');

    // Validate types
    expect(typeof data.total).toBe('number');
    expect(typeof data.approvalRate).toBe('number');
    expect(data.approvalRate).toBeGreaterThanOrEqual(0);
    expect(data.approvalRate).toBeLessThanOrEqual(1);
  });

  test('stats endpoint accepts days parameter', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/rules/church/stats?days=7`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.days).toBe(7);
  });

  test('stats endpoint validates account', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/rules/invalid/stats`, {
      headers: AUTH_HEADERS
    });
    expect(response.status()).toBe(422);
  });
});

test.describe('Rule API Response Format', () => {

  test('pending rules use camelCase field names', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/rules/church/pending`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    if (data.rules.length > 0) {
      const rule = data.rules[0];
      // Verify camelCase
      expect(rule).toHaveProperty('ruleId');
      expect(rule).toHaveProperty('emailAccount');
      expect(rule).toHaveProperty('suggestionType');
      expect(rule).toHaveProperty('suggestedRule');

      // Verify NOT snake_case
      expect(rule).not.toHaveProperty('rule_id');
      expect(rule).not.toHaveProperty('email_account');
      expect(rule).not.toHaveProperty('suggestion_type');
      expect(rule).not.toHaveProperty('suggested_rule');
    }
  });

  test('stats use camelCase field names', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/rules/church/stats`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('approvalRate');
    expect(data).not.toHaveProperty('approval_rate');
  });
});

test.describe('Rule Suggestions - Cross-Login Access', () => {
  const PERSONAL_USER = 'david.a.royes@gmail.com';
  const CHURCH_USER = 'davidroyes@southpointsda.org';

  test('church rules visible from personal login', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/rules/church/pending`, {
      headers: { 'X-User-Email': PERSONAL_USER }
    });
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.account).toBe('church');
  });

  test('personal rules visible from church login', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/rules/personal/pending`, {
      headers: { 'X-User-Email': CHURCH_USER }
    });
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.account).toBe('personal');
  });
});
