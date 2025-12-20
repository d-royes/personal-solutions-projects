import { test, expect } from '@playwright/test';

/**
 * Last Analysis Audit E2E Tests
 *
 * Tests for F1 Persistence Layer: Analysis Audit
 * - Cross-machine visibility of analysis results
 * - Account-based storage (church vs personal)
 */

const API_BASE = process.env.API_BASE || 'http://localhost:8000';
const AUTH_HEADERS = {
  'X-User-Email': 'david.a.royes@gmail.com'
};

test.describe('Last Analysis API - GET /email/last-analysis/{account}', () => {

  test('last-analysis endpoint requires authentication', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/last-analysis/church`);
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('last-analysis endpoint returns correct structure for church', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/last-analysis/church`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('account');
    expect(data.account).toBe('church');
    expect(data).toHaveProperty('lastAnalysis');

    // lastAnalysis can be null if never analyzed
    if (data.lastAnalysis !== null) {
      expect(data.lastAnalysis).toHaveProperty('timestamp');
      expect(data.lastAnalysis).toHaveProperty('emailsFetched');
      expect(data.lastAnalysis).toHaveProperty('emailsAnalyzed');
      expect(data.lastAnalysis).toHaveProperty('alreadyTracked');
      expect(data.lastAnalysis).toHaveProperty('dismissed');
      expect(data.lastAnalysis).toHaveProperty('suggestionsGenerated');
      expect(data.lastAnalysis).toHaveProperty('rulesGenerated');
      expect(data.lastAnalysis).toHaveProperty('attentionItems');
      expect(data.lastAnalysis).toHaveProperty('haikuAnalyzed');
    }
  });

  test('last-analysis endpoint returns correct structure for personal', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/last-analysis/personal`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('account');
    expect(data.account).toBe('personal');
  });

  test('last-analysis endpoint validates account', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/last-analysis/invalid-account`, {
      headers: AUTH_HEADERS
    });
    expect(response.status()).toBe(422);
  });

  test('last-analysis uses camelCase field names', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/last-analysis/church`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    if (data.lastAnalysis !== null) {
      // Verify camelCase
      expect(data.lastAnalysis).toHaveProperty('emailsFetched');
      expect(data.lastAnalysis).toHaveProperty('emailsAnalyzed');
      expect(data.lastAnalysis).toHaveProperty('alreadyTracked');
      expect(data.lastAnalysis).toHaveProperty('suggestionsGenerated');
      expect(data.lastAnalysis).toHaveProperty('rulesGenerated');
      expect(data.lastAnalysis).toHaveProperty('attentionItems');
      expect(data.lastAnalysis).toHaveProperty('haikuAnalyzed');

      // Verify NOT snake_case
      expect(data.lastAnalysis).not.toHaveProperty('emails_fetched');
      expect(data.lastAnalysis).not.toHaveProperty('emails_analyzed');
      expect(data.lastAnalysis).not.toHaveProperty('already_tracked');
    }
  });
});

test.describe('Last Analysis - Cross-Login Access', () => {
  const PERSONAL_USER = 'david.a.royes@gmail.com';
  const CHURCH_USER = 'davidroyes@southpointsda.org';

  test('church analysis visible from personal login', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/last-analysis/church`, {
      headers: { 'X-User-Email': PERSONAL_USER }
    });
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.account).toBe('church');
  });

  test('personal analysis visible from church login', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/last-analysis/personal`, {
      headers: { 'X-User-Email': CHURCH_USER }
    });
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.account).toBe('personal');
  });
});
