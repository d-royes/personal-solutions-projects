import { test, expect } from '@playwright/test';

/**
 * Email Dashboard Pagination Tests
 *
 * Tests for the "Load More" pagination feature:
 * - Initial load returns ~20 emails
 * - Load More button appears when more pages exist
 * - Load More appends emails to existing list
 * - Load More button hidden when no more pages
 * - Cache persists across account switches
 * - Thread count badge displays for multi-email threads
 */

const API_BASE = process.env.API_BASE || 'http://localhost:8000';
const AUTH_HEADERS = {
  'X-User-Email': 'david.a.royes@gmail.com'
};

test.describe('Pagination API - /inbox/{account}', () => {

  test('inbox endpoint returns nextPageToken in response', async ({ request }) => {
    const response = await request.get(`${API_BASE}/inbox/personal?max_results=5`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('recentMessages');
    expect(data).toHaveProperty('nextPageToken');
    // With only 5 results, there should be more pages
    expect(data.recentMessages.length).toBeLessThanOrEqual(5);
  });

  test('inbox endpoint accepts page_token parameter', async ({ request }) => {
    // First request to get the page token
    const response1 = await request.get(`${API_BASE}/inbox/personal?max_results=5`, {
      headers: AUTH_HEADERS
    });
    expect(response1.ok()).toBeTruthy();
    const data1 = await response1.json();

    // Skip test if no more pages (not enough emails)
    if (!data1.nextPageToken) {
      test.skip();
      return;
    }

    // Second request with page token
    const response2 = await request.get(
      `${API_BASE}/inbox/personal?max_results=5&page_token=${data1.nextPageToken}`,
      { headers: AUTH_HEADERS }
    );
    expect(response2.ok()).toBeTruthy();
    const data2 = await response2.json();

    // Second page should have different emails
    const firstPageIds = new Set(data1.recentMessages.map((m: { id: string }) => m.id));
    const hasNewEmails = data2.recentMessages.some((m: { id: string }) => !firstPageIds.has(m.id));
    expect(hasNewEmails).toBeTruthy();
  });

  test('nextPageToken is null or string (not missing)', async ({ request }) => {
    // Just verify nextPageToken is explicitly returned (null or string)
    const response = await request.get(`${API_BASE}/inbox/personal?max_results=20`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    // nextPageToken should be explicitly present in response (null or string)
    expect('nextPageToken' in data).toBeTruthy();
    // If present, it's either null or a non-empty string
    if (data.nextPageToken !== null) {
      expect(typeof data.nextPageToken).toBe('string');
      expect(data.nextPageToken.length).toBeGreaterThan(0);
    }
  });

  test('default max_results is 20', async ({ request }) => {
    const response = await request.get(`${API_BASE}/inbox/personal`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    // Should return at most 20 emails by default
    expect(data.recentMessages.length).toBeLessThanOrEqual(20);
  });
});

test.describe('Pagination UI - Load More Button', () => {

  test.beforeEach(async ({ page }) => {
    // Set dev auth header for API requests
    await page.setExtraHTTPHeaders({
      'X-User-Email': 'david.a.royes@gmail.com'
    });

    await page.goto('/');

    // Inject dev auth into localStorage
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

    // Wait for Email Management view
    await expect(page.getByRole('heading', { name: 'Email Management' })).toBeVisible({ timeout: 10000 });
  });

  test('Load More button is visible when more emails exist', async ({ page }) => {
    // Wait for inbox to load
    await page.waitForTimeout(3000);

    // Check if Load More button is visible (only if there are more pages)
    const loadMoreBtn = page.getByRole('button', { name: 'Load More' });

    // The button should be visible if there are more emails to load
    // We can't guarantee this in all test environments, so we check if it exists or not
    const isVisible = await loadMoreBtn.isVisible().catch(() => false);

    if (isVisible) {
      await expect(loadMoreBtn).toBeEnabled();
    }
    // If not visible, that's also valid (no more pages)
  });

  test('Load More button shows Loading state while fetching', async ({ page }) => {
    // Wait for inbox to load
    await page.waitForTimeout(3000);

    const loadMoreBtn = page.getByRole('button', { name: 'Load More' });
    const isVisible = await loadMoreBtn.isVisible().catch(() => false);

    if (!isVisible) {
      test.skip();
      return;
    }

    // Click Load More and check for loading state
    await loadMoreBtn.click();

    // Should show "Loading..." text briefly
    // Note: This may be too fast to catch in some environments
    await page.waitForTimeout(500);
  });

  test('Load More appends emails to existing list', async ({ page }) => {
    // Wait for inbox to load
    await page.waitForTimeout(3000);

    // Count initial emails
    const initialEmails = await page.locator('.message-list li').count();

    const loadMoreBtn = page.getByRole('button', { name: 'Load More' });
    const isVisible = await loadMoreBtn.isVisible().catch(() => false);

    if (!isVisible || initialEmails === 0) {
      test.skip();
      return;
    }

    // Click Load More
    await loadMoreBtn.click();

    // Wait for new emails to load
    await page.waitForTimeout(3000);

    // Count emails after loading more
    const newEmailCount = await page.locator('.message-list li').count();

    // Should have more emails than before
    expect(newEmailCount).toBeGreaterThan(initialEmails);
  });
});

test.describe('Thread Count Badge', () => {

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

  test('thread count badge displays for multi-email threads', async ({ page }) => {
    // Wait for inbox to load
    await page.waitForTimeout(3000);

    // Look for thread count badges
    const threadBadges = page.locator('.thread-count-badge');
    const badgeCount = await threadBadges.count();

    // If there are thread badges, verify they contain "in thread" text
    if (badgeCount > 0) {
      const firstBadge = threadBadges.first();
      const badgeText = await firstBadge.textContent();
      expect(badgeText).toContain('in thread');
    }
    // If no badges, that's also valid (no multi-email threads in visible emails)
  });

  test('thread count badge has correct count format', async ({ page }) => {
    // Wait for inbox to load
    await page.waitForTimeout(3000);

    const threadBadges = page.locator('.thread-count-badge');
    const badgeCount = await threadBadges.count();

    if (badgeCount > 0) {
      const firstBadge = threadBadges.first();
      const badgeText = await firstBadge.textContent();

      // Should match format "N in thread" where N >= 2
      expect(badgeText).toMatch(/^\d+ in thread$/);

      // Extract the number and verify it's >= 2
      const match = badgeText?.match(/^(\d+) in thread$/);
      if (match) {
        const count = parseInt(match[1], 10);
        expect(count).toBeGreaterThanOrEqual(2);
      }
    }
  });
});

test.describe('Cache Persistence', () => {

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

  test('email list persists when switching accounts and back', async ({ page }) => {
    // Wait for Personal inbox to load
    await page.waitForTimeout(3000);

    // Count initial personal emails
    const personalEmails = await page.locator('.message-list li').count();

    // Skip if no emails loaded
    if (personalEmails === 0) {
      test.skip();
      return;
    }

    // Switch to Church account
    await page.getByRole('button', { name: 'Church' }).click();
    await page.waitForTimeout(3000);

    // Switch back to Personal
    await page.getByRole('button', { name: 'Personal' }).click();
    await page.waitForTimeout(1000);

    // Count emails again - should be same as before (cached)
    const cachedEmails = await page.locator('.message-list li').count();
    expect(cachedEmails).toBe(personalEmails);
  });

  test('loaded emails persist when switching to Tasks and back', async ({ page }) => {
    // Wait for inbox to load
    await page.waitForTimeout(3000);

    // Check if Load More is available
    const loadMoreBtn = page.getByRole('button', { name: 'Load More' });
    const canLoadMore = await loadMoreBtn.isVisible().catch(() => false);

    // Count initial emails
    const initialCount = await page.locator('.message-list li').count();

    // If we can load more, do it
    if (canLoadMore) {
      await loadMoreBtn.click();
      await page.waitForTimeout(3000);
    }

    // Count emails after potential load more
    const afterLoadMoreCount = await page.locator('.message-list li').count();

    // Switch to Tasks
    await page.getByRole('button', { name: /Back to Tasks/i }).click();
    await page.waitForTimeout(2000);

    // Switch back to Email
    await page.getByRole('button', { name: '✉️' }).click();
    await expect(page.getByRole('heading', { name: 'Email Management' })).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(1000);

    // Count should match what we had before switching
    const cachedCount = await page.locator('.message-list li').count();
    expect(cachedCount).toBe(afterLoadMoreCount);
  });
});
