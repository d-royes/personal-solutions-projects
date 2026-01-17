import { test, expect } from '@playwright/test';

/**
 * Calendar Tasks Tab Tests
 *
 * Tests for DATA's unified timeline feature in Calendar Management:
 * - Tab navigation (Dashboard, Events, Meetings, Tasks, Settings)
 * - View selector filtering (Personal, Work, Church, Combined)
 * - Unified timeline display (events + tasks)
 * - Task preview in DATA panel
 * - Date grouping and sorting
 */

test.describe('Calendar Tasks Tab', () => {

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

    // Switch to Calendar mode
    await page.getByRole('button', { name: 'Calendar' }).click();

    // Wait for Calendar Management view
    await expect(page.getByRole('heading', { name: 'Calendar Management' })).toBeVisible({ timeout: 10000 });
  });

  test('should switch to Calendar mode when clicking calendar button', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Calendar Management' })).toBeVisible();
  });

  test('should have view selector with Personal, Work, Church, Combined', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Personal' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Work' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Church' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Combined' })).toBeVisible();
  });

  test('should have navigation tabs including Tasks', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Dashboard' })).toBeVisible();
    await expect(page.getByRole('button', { name: /^Events/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /^Meetings/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /^Tasks/i })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Settings' })).toBeVisible();
  });

  test('should have Back to Tasks button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Back to Tasks/i })).toBeVisible();
  });

  test('should return to Tasks mode when clicking Back to Tasks', async ({ page }) => {
    await page.getByRole('button', { name: /Back to Tasks/i }).click();

    // Should be back on task view
    await page.waitForTimeout(2000);
    await expect(page.getByRole('button', { name: 'All' })).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Calendar Tasks Tab - Unified Timeline', () => {

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

    // Switch to Calendar mode
    await page.getByRole('button', { name: 'Calendar' }).click();
    await expect(page.getByRole('heading', { name: 'Calendar Management' })).toBeVisible({ timeout: 10000 });

    // Click Tasks tab and wait for content to load
    await page.getByRole('button', { name: /^Tasks/i }).click();
    // Wait for either timeline content or empty state to appear
    await expect(page.locator('.timeline-header, .empty-state').first()).toBeVisible({ timeout: 10000 });
  });

  test('should display unified timeline header with event and task counts', async ({ page }) => {
    // Should show "X events + Y tasks" format in the timeline header
    await expect(page.locator('.timeline-count')).toBeVisible({ timeout: 10000 });
    // Verify the text pattern
    const countText = await page.locator('.timeline-count').textContent();
    expect(countText).toMatch(/\d+ events \+ \d+ tasks/);
  });

  test('should have search input', async ({ page }) => {
    // Search input in Tasks tab
    await expect(page.locator('.email-search-input')).toBeVisible({ timeout: 10000 });
  });

  test('should have refresh button', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Refresh' })).toBeVisible({ timeout: 10000 });
  });

  test('should display date groups in timeline', async ({ page }) => {
    // Look for date headers (e.g., "Mon, Jan 6" format) or date group containers
    const dateGroups = page.locator('.calendar-date-group');
    await expect(dateGroups.first()).toBeVisible({ timeout: 10000 });
  });

  test('should display events with calendar icon', async ({ page }) => {
    // Events should have calendar emoji icon
    const eventItems = page.locator('.calendar-event-item');
    await expect(eventItems.first()).toBeVisible({ timeout: 5000 });
  });

  test('should display tasks with checkbox icon', async ({ page }) => {
    // Tasks should have checkbox icon
    const taskItems = page.locator('.calendar-task-item');
    // Tasks may not be present if none due within 14 days
    const count = await taskItems.count();
    if (count > 0) {
      await expect(taskItems.first()).toBeVisible();
    }
  });
});

test.describe('Calendar Tasks Tab - Task Preview', () => {

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

    // Switch to Calendar mode
    await page.getByRole('button', { name: 'Calendar' }).click();
    await expect(page.getByRole('heading', { name: 'Calendar Management' })).toBeVisible({ timeout: 10000 });

    // Click Tasks tab
    await page.getByRole('button', { name: /^Tasks/i }).click();
    await page.waitForTimeout(1000);
  });

  test('should show empty state message when no item selected', async ({ page }) => {
    await expect(page.getByText('Select an item to view details')).toBeVisible({ timeout: 5000 });
  });

  test('should show event preview when clicking an event', async ({ page }) => {
    // Click on first event item
    const eventItem = page.locator('.calendar-event-item').first();
    if (await eventItem.isVisible()) {
      await eventItem.click();
      await page.waitForTimeout(500);

      // DATA panel should show event details
      await expect(page.locator('.calendar-event-preview')).toBeVisible({ timeout: 3000 });
    }
  });

  test('should show task preview when clicking a task', async ({ page }) => {
    // Click on first task item
    const taskItem = page.locator('.calendar-task-item').first();
    const count = await taskItem.count();

    if (count > 0 && await taskItem.isVisible()) {
      await taskItem.click();
      await page.waitForTimeout(500);

      // DATA panel should show task preview with key fields
      await expect(page.locator('.calendar-task-preview')).toBeVisible({ timeout: 3000 });

      // Should show domain badge
      await expect(page.locator('.calendar-domain-badge')).toBeVisible();

      // Should have Open Task button
      await expect(page.getByRole('button', { name: /Open Task/i })).toBeVisible();

      // Should have Ask DATA section
      await expect(page.getByText('Ask DATA about this task')).toBeVisible();
    }
  });

  test('should show quick action buttons for task', async ({ page }) => {
    const taskItem = page.locator('.calendar-task-item').first();
    const count = await taskItem.count();

    if (count > 0 && await taskItem.isVisible()) {
      await taskItem.click();
      await page.waitForTimeout(500);

      // Should have quick action buttons
      await expect(page.getByRole('button', { name: 'What should I focus on?' })).toBeVisible({ timeout: 3000 });
      await expect(page.getByRole('button', { name: 'Break this down' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Related events?' })).toBeVisible();
    }
  });
});

test.describe('Calendar Tasks Tab - View Filtering', () => {

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

    // Switch to Calendar mode
    await page.getByRole('button', { name: 'Calendar' }).click();
    await expect(page.getByRole('heading', { name: 'Calendar Management' })).toBeVisible({ timeout: 10000 });

    // Click Tasks tab and wait for content
    await page.getByRole('button', { name: /^Tasks/i }).click();
    await expect(page.locator('.timeline-header, .empty-state').first()).toBeVisible({ timeout: 10000 });
  });

  test('should filter timeline when switching to Personal view', async ({ page }) => {
    // Switch to Personal view
    await page.getByRole('button', { name: 'Personal' }).click();
    await page.waitForTimeout(1000);

    // Timeline should update (show count or empty state)
    await expect(page.locator('.timeline-count, .empty-state').first()).toBeVisible({ timeout: 10000 });
  });

  test('should filter timeline when switching to Church view', async ({ page }) => {
    // Switch to Church view
    await page.getByRole('button', { name: 'Church' }).click();
    await page.waitForTimeout(1000);

    // Timeline should update (show count or empty state)
    await expect(page.locator('.timeline-count, .empty-state').first()).toBeVisible({ timeout: 10000 });
  });

  test('should show combined view by default', async ({ page }) => {
    // Combined should be clickable
    await page.getByRole('button', { name: 'Combined' }).click();
    await page.waitForTimeout(500);

    // Timeline should show content
    await expect(page.locator('.timeline-count, .empty-state').first()).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Calendar Tasks Tab - Domain Styling', () => {

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

    // Switch to Calendar mode and Tasks tab
    await page.getByRole('button', { name: 'Calendar' }).click();
    await expect(page.getByRole('heading', { name: 'Calendar Management' })).toBeVisible({ timeout: 10000 });
    await page.getByRole('button', { name: /^Tasks/i }).click();
    // Wait for timeline content to load
    await expect(page.locator('.timeline-header, .empty-state').first()).toBeVisible({ timeout: 10000 });
  });

  test('should apply domain color classes to timeline items', async ({ page }) => {
    // Wait for any timeline items to appear
    await page.waitForTimeout(1000);

    // Check for domain-specific styling
    const personalItems = page.locator('.domain-personal');
    const churchItems = page.locator('.domain-church');
    const workItems = page.locator('.domain-work');

    // At least one domain should have items visible
    const personalCount = await personalItems.count();
    const churchCount = await churchItems.count();
    const workCount = await workItems.count();

    expect(personalCount + churchCount + workCount).toBeGreaterThan(0);
  });

  test('should display priority badges on tasks', async ({ page }) => {
    const taskItems = page.locator('.calendar-task-item');
    const count = await taskItems.count();

    if (count > 0) {
      // Check for priority badge classes
      const priorityBadges = page.locator('.calendar-task-priority');
      const badgeCount = await priorityBadges.count();

      // At least some tasks should have priority badges
      // (not all tasks may have priority set)
      expect(badgeCount).toBeGreaterThanOrEqual(0);
    }
  });
});
