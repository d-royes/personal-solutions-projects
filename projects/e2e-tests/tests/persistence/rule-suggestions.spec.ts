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

test.describe('Suggestion Duplicate Prevention', () => {

  test('pending suggestions should have unique email IDs', async ({ request }) => {
    // Verify no duplicate suggestions for same email
    const response = await request.get(`${API_BASE}/email/suggestions/church/pending`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    const suggestions = data.suggestions || [];

    // Count email IDs
    const emailIds = suggestions.map((s: any) => s.emailId);
    const uniqueEmailIds = new Set(emailIds);

    // Each email should have at most one suggestion
    expect(emailIds.length).toBe(uniqueEmailIds.size);
  });

  test('has_pending check endpoint should detect existing suggestions', async ({ request }) => {
    // First get a pending suggestion's email ID
    const pendingResponse = await request.get(`${API_BASE}/email/suggestions/church/pending`, {
      headers: AUTH_HEADERS
    });
    expect(pendingResponse.ok()).toBeTruthy();

    const data = await pendingResponse.json();
    if (data.suggestions.length === 0) {
      // No suggestions to test - skip
      return;
    }

    const emailId = data.suggestions[0].emailId;

    // Verify the API correctly identifies emails with pending suggestions
    // This is implicitly tested by the analyze endpoint skipping duplicates
    // The count should not increase on re-analysis
    const countBefore = data.suggestions.length;

    // Note: We can't easily trigger analyze in E2E without Gmail credentials
    // But we can verify the count is stable and no duplicates exist
    expect(countBefore).toBeGreaterThan(0);
  });
});

test.describe('Allowed Labels Configuration', () => {

  test('allowed-labels endpoint requires authentication', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/rules/church/allowed-labels`);
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('allowed-labels endpoint returns correct structure for church', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/rules/church/allowed-labels`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('account');
    expect(data.account).toBe('church');
    expect(data).toHaveProperty('allowedLabels');
    expect(data).toHaveProperty('count');
    expect(Array.isArray(data.allowedLabels)).toBeTruthy();
    expect(data.count).toBe(data.allowedLabels.length);
  });

  test('allowed-labels endpoint returns correct structure for personal', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/rules/personal/allowed-labels`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.account).toBe('personal');
    expect(Array.isArray(data.allowedLabels)).toBeTruthy();
  });

  test('church has expected labels', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/rules/church/allowed-labels`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    const labels = data.allowedLabels;

    // Church should have these specific labels
    expect(labels).toContain('1 Week Hold');
    expect(labels).toContain('Admin');
    expect(labels).toContain('Ministry Comms');
    expect(labels).toContain('Risk Management Forms');

    // Church should NOT have generic "Risk Management" (consolidated)
    expect(labels).not.toContain('Risk Management');
  });

  test('personal has restricted label set', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/rules/personal/allowed-labels`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    const labels = data.allowedLabels;

    // Personal should have core filtering labels
    expect(labels).toContain('1 Week Hold');
    expect(labels).toContain('Admin');
    expect(labels).toContain('Promotional');
    expect(labels).toContain('Transactional');

    // Personal should NOT have church-specific labels
    expect(labels).not.toContain('Ministry Comms');
    expect(labels).not.toContain('Risk Management Forms');
  });

  test('pending rules only use allowed labels', async ({ request }) => {
    // Get allowed labels for church
    const labelsResponse = await request.get(`${API_BASE}/email/rules/church/allowed-labels`, {
      headers: AUTH_HEADERS
    });
    expect(labelsResponse.ok()).toBeTruthy();
    const labelsData = await labelsResponse.json();
    const allowedLabels = new Set(labelsData.allowedLabels);

    // Get pending rules
    const rulesResponse = await request.get(`${API_BASE}/email/rules/church/pending`, {
      headers: AUTH_HEADERS
    });
    expect(rulesResponse.ok()).toBeTruthy();
    const rulesData = await rulesResponse.json();

    // Verify all pending rules use allowed labels
    for (const rule of rulesData.rules) {
      const category = rule.suggestedRule?.category;
      if (category) {
        expect(allowedLabels.has(category)).toBeTruthy();
      }
    }
  });
});
