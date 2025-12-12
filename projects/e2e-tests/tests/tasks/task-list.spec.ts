import { test, expect } from '@playwright/test';

/**
 * Task List Tests
 * 
 * Tests for the main task list view in DATA's web dashboard.
 * Verifies that tasks load correctly, filters work, and basic interactions function.
 */

test.describe('Task List', () => {
  
  test.beforeEach(async ({ page }) => {
    // Navigate to the app and wait for tasks to load
    await page.goto('/');
    
    // Set dev auth header for local testing
    await page.setExtraHTTPHeaders({
      'X-User-Email': 'david.a.royes@gmail.com'
    });
  });

  test('should display the task list on load', async ({ page }) => {
    // Wait for the task list to appear
    await expect(page.getByRole('list')).toBeVisible({ timeout: 10000 });
    
    // Verify we have at least one task
    const tasks = page.getByRole('listitem');
    await expect(tasks.first()).toBeVisible();
  });

  test('should show mode switcher with Tasks and Email buttons', async ({ page }) => {
    // Check for mode switcher buttons
    await expect(page.getByRole('button', { name: '📋' })).toBeVisible();
    await expect(page.getByRole('button', { name: '✉️' })).toBeVisible();
  });

  test('should have filter buttons', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'All' })).toBeVisible();
    await expect(page.getByRole('button', { name: /Needs attention/i })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Blocked' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Personal' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Church' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Work' })).toBeVisible();
  });

  test('should filter tasks by category when clicking Personal', async ({ page }) => {
    // Wait for tasks to load
    await expect(page.getByRole('list')).toBeVisible({ timeout: 10000 });
    
    // Click Personal filter
    await page.getByRole('button', { name: 'Personal' }).click();
    
    // Wait for filter to apply
    await page.waitForTimeout(500);
    
    // All visible tasks should be Personal category
    const tasks = page.getByRole('listitem');
    const count = await tasks.count();
    
    for (let i = 0; i < Math.min(count, 5); i++) {
      const taskText = await tasks.nth(i).textContent();
      expect(taskText).toContain('Personal');
    }
  });

  test('should filter tasks by category when clicking Church', async ({ page }) => {
    // Wait for tasks to load
    await expect(page.getByRole('list')).toBeVisible({ timeout: 10000 });
    
    // Click Church filter
    await page.getByRole('button', { name: 'Church' }).click();
    
    // Wait for filter to apply
    await page.waitForTimeout(500);
    
    // All visible tasks should be Church category
    const tasks = page.getByRole('listitem');
    const count = await tasks.count();
    
    for (let i = 0; i < Math.min(count, 5); i++) {
      const taskText = await tasks.nth(i).textContent();
      expect(taskText).toContain('Church');
    }
  });

  test('should have search input', async ({ page }) => {
    await expect(page.getByPlaceholder('Search...')).toBeVisible();
  });

  test('should have refresh button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Refresh/i })).toBeVisible();
  });

  test('should have portfolio button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Portfolio/i })).toBeVisible();
  });
});

test.describe('Portfolio View', () => {
  
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.setExtraHTTPHeaders({
      'X-User-Email': 'david.a.royes@gmail.com'
    });
  });

  test('should display portfolio section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /Portfolio/i })).toBeVisible();
  });

  test('should have portfolio category tabs', async ({ page }) => {
    // Look for portfolio-specific buttons (in the right panel)
    const portfolioSection = page.locator('section').filter({ hasText: 'Portfolio' });
    await expect(portfolioSection.getByRole('button', { name: 'Personal' })).toBeVisible();
    await expect(portfolioSection.getByRole('button', { name: 'Church' })).toBeVisible();
    await expect(portfolioSection.getByRole('button', { name: 'Work' })).toBeVisible();
    await expect(portfolioSection.getByRole('button', { name: 'Holistic' })).toBeVisible();
  });

  test('should have Quick Question button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Quick Question/i })).toBeVisible();
  });

  test('should have chat input', async ({ page }) => {
    await expect(page.getByRole('textbox', { name: /Ask about/i })).toBeVisible();
  });
});

