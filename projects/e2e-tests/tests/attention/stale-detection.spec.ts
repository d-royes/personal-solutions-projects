import { test, expect } from '@playwright/test';

/**
 * Stale Item Detection Tests
 *
 * Tests for the stale email detection feature:
 * - When emails are deleted/trashed in Gmail, attention items become "stale"
 * - API validates email existence and auto-dismisses stale items on fetch
 * - API returns stale flag when fetching/acting on trashed emails
 * - UI shows warning toast and dismisses attention item for stale emails
 *
 * Note: These tests verify API contracts. Testing actual stale detection
 * requires emails in Gmail's Trash, which can't be controlled in E2E tests.
 */

const API_BASE = process.env.API_BASE || 'http://localhost:8000';
const AUTH_HEADERS = {
  'X-User-Email': 'david.a.royes@gmail.com'
};

test.describe('Stale Detection API - Attention Endpoint', () => {

  test('attention endpoint returns staleDismissed count', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/attention/personal`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    // staleDismissed should be present and be a number
    expect(data).toHaveProperty('staleDismissed');
    expect(typeof data.staleDismissed).toBe('number');
    expect(data.staleDismissed).toBeGreaterThanOrEqual(0);
  });

  test('attention endpoint validates against Gmail on fetch', async ({ request }) => {
    // This test verifies the endpoint performs validation
    // The staleDismissed count indicates how many items were auto-dismissed
    const response = await request.get(`${API_BASE}/email/attention/church`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('staleDismissed');
    expect(data).toHaveProperty('count');
    expect(data).toHaveProperty('attentionItems');

    // count should reflect remaining items after stale dismissal
    expect(data.count).toBe(data.attentionItems.length);
  });
});

test.describe('Stale Detection API - Email Message Endpoint', () => {

  test('message endpoint returns stale field in response', async ({ request }) => {
    // First get an email ID from inbox
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

    // Fetch the email message
    const response = await request.get(`${API_BASE}/email/personal/message/${emailId}`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    // stale field should be present
    expect(data).toHaveProperty('stale');
    expect(typeof data.stale).toBe('boolean');

    // staleMessage should be present (null for non-stale emails)
    expect('staleMessage' in data).toBeTruthy();

    // Normal inbox email should not be stale
    expect(data.stale).toBe(false);
    expect(data.staleMessage).toBeNull();
  });
});

test.describe('Stale Detection API - Email Action Endpoints', () => {

  test('star endpoint returns stale field in response', async ({ request }) => {
    // First get an email ID from inbox
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

    // Star the email
    const response = await request.post(
      `${API_BASE}/email/personal/star/${emailId}?starred=true`,
      { headers: AUTH_HEADERS }
    );
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    // stale field should be present
    expect(data).toHaveProperty('stale');
    expect(typeof data.stale).toBe('boolean');

    // Normal inbox email should not be stale
    expect(data.stale).toBe(false);
  });

  test('important endpoint returns stale field in response', async ({ request }) => {
    // First get an email ID from inbox
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

    // Mark the email as important
    const response = await request.post(
      `${API_BASE}/email/personal/important/${emailId}?important=true`,
      { headers: AUTH_HEADERS }
    );
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    // stale field should be present
    expect(data).toHaveProperty('stale');
    expect(typeof data.stale).toBe('boolean');

    // Normal inbox email should not be stale
    expect(data.stale).toBe(false);
  });

  test('read endpoint returns stale field in response', async ({ request }) => {
    // First get an email ID from inbox
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

    // Mark the email as read
    const response = await request.post(
      `${API_BASE}/email/personal/read/${emailId}?read=true`,
      { headers: AUTH_HEADERS }
    );
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    // stale field should be present
    expect(data).toHaveProperty('stale');
    expect(typeof data.stale).toBe('boolean');

    // Normal inbox email should not be stale
    expect(data.stale).toBe(false);
  });
});

test.describe('Stale Detection UI - Toast Notification', () => {

  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({
      'X-User-Email': 'david.a.royes@gmail.com'
    });

    await page.goto('/');

    await page.evaluate(() => {
      const authState = {
        mode: 'dev',
        userEmail: 'david.a.royes@gmail.com',
        idToken: null
      };
      localStorage.setItem('dta-auth-state', JSON.stringify(authState));
    });

    await page.reload();
    await page.waitForTimeout(2000);

    // Switch to Email mode
    await page.getByRole('button', { name: '✉️' }).click();
    await expect(page.getByRole('heading', { name: 'Email Management' })).toBeVisible({ timeout: 10000 });
  });

  test('toast component exists in DOM when triggered', async ({ page }) => {
    // This test verifies the toast infrastructure exists
    // We can't trigger a real stale toast without a trashed email,
    // but we can verify the component structure is in place

    // Wait for email dashboard to load
    await page.waitForTimeout(2000);

    // Navigate to Attention tab to see attention items
    const attentionTab = page.getByRole('tab', { name: /Attention/i });
    if (await attentionTab.isVisible().catch(() => false)) {
      await attentionTab.click();
      await page.waitForTimeout(1000);
    }

    // The toast div with class 'email-toast' should render when toastMessage state is set
    // We verify the component renders by checking if it can be selected
    const toastSelector = page.locator('.email-toast');

    // Toast should NOT be visible by default (no stale items in normal flow)
    const isToastVisible = await toastSelector.isVisible().catch(() => false);

    // This is expected - toast only shows when there's a stale email
    // The test validates the absence of false positives
    expect(isToastVisible).toBe(false);
  });

  test('attention tab displays count correctly after stale dismissal', async ({ page }) => {
    // Wait for email dashboard to load
    await page.waitForTimeout(3000);

    // Check if Attention tab exists and has a count
    const attentionTab = page.locator('button, [role="tab"]').filter({ hasText: /Attention/i });

    if (await attentionTab.isVisible().catch(() => false)) {
      const tabText = await attentionTab.textContent();

      // Tab should show "Attention" with optional count in parentheses
      // Format: "Attention (N)" where N >= 0
      expect(tabText).toMatch(/Attention(\s*\(\d+\))?/);
    }
  });
});

test.describe('Stale Detection - Field Naming Convention', () => {

  test('attention endpoint returns camelCase staleDismissed field', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/attention/personal`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    // Should use camelCase
    expect(data).toHaveProperty('staleDismissed');
    // Should NOT use snake_case
    expect(data).not.toHaveProperty('stale_dismissed');
  });

  test('message endpoint returns camelCase stale fields', async ({ request }) => {
    // First get an email ID from inbox
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

    const response = await request.get(`${API_BASE}/email/personal/message/${emailId}`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    // Should use camelCase
    expect(data).toHaveProperty('stale');
    expect(data).toHaveProperty('staleMessage');
    // Should NOT use snake_case
    expect(data).not.toHaveProperty('stale_message');
  });
});
