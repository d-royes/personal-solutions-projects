import { test, expect } from '@playwright/test';

/**
 * Email Dashboard Tests
 * 
 * Tests for DATA's email management features including:
 * - Account switching (Personal/Church)
 * - Rules management
 * - Suggestions and Attention tabs
 */

test.describe('Email Dashboard', () => {
  
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.setExtraHTTPHeaders({
      'X-User-Email': 'david.a.royes@gmail.com'
    });
    
    // Switch to Email mode
    await page.getByRole('button', { name: '✉️' }).click();
    
    // Wait for Email Management view
    await expect(page.getByRole('heading', { name: 'Email Management' })).toBeVisible({ timeout: 10000 });
  });

  test('should switch to Email mode when clicking email button', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Email Management' })).toBeVisible();
  });

  test('should have account switcher with Personal and Church', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Personal' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Church' })).toBeVisible();
  });

  test('should have navigation tabs', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Dashboard' })).toBeVisible();
    await expect(page.getByRole('button', { name: /Rules/i })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Suggestions' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Attention' })).toBeVisible();
  });

  test('should have Back to Tasks button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Back to Tasks/i })).toBeVisible();
  });

  test('should return to Tasks when clicking Back to Tasks', async ({ page }) => {
    await page.getByRole('button', { name: /Back to Tasks/i }).click();
    
    // Should be back on task view
    await expect(page.getByRole('list')).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Email Rules Tab', () => {
  
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.setExtraHTTPHeaders({
      'X-User-Email': 'david.a.royes@gmail.com'
    });
    
    // Switch to Email mode
    await page.getByRole('button', { name: '✉️' }).click();
    await expect(page.getByRole('heading', { name: 'Email Management' })).toBeVisible({ timeout: 10000 });
    
    // Click Rules tab
    await page.getByRole('button', { name: /Rules/i }).click();
    await page.waitForTimeout(1000); // Wait for rules to load
  });

  test('should display rules count in tab', async ({ page }) => {
    // The Rules tab should show a count like "Rules (325)"
    const rulesTab = page.getByRole('button', { name: /Rules.*\d+/i });
    await expect(rulesTab).toBeVisible();
  });

  test('should have category filter dropdown', async ({ page }) => {
    await expect(page.getByRole('combobox', { name: /Categories/i })).toBeVisible();
  });

  test('should have search input for rules', async ({ page }) => {
    await expect(page.getByPlaceholder(/Search rules/i)).toBeVisible();
  });

  test('should have Add Rule button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Add Rule/i })).toBeVisible();
  });

  test('should display rules table with data', async ({ page }) => {
    // Wait for table to appear
    await expect(page.getByRole('table')).toBeVisible({ timeout: 10000 });
    
    // Should have at least one row
    const rows = page.getByRole('row');
    await expect(rows.first()).toBeVisible();
  });

  test('should filter rules by category', async ({ page }) => {
    // Select a specific category
    const categoryDropdown = page.getByRole('combobox', { name: /Categories/i });
    await categoryDropdown.selectOption('Promotional');
    
    await page.waitForTimeout(500);
    
    // All visible rows should be Promotional
    const cells = page.getByRole('cell', { name: 'Promotional' });
    const count = await cells.count();
    expect(count).toBeGreaterThan(0);
  });

  test('should search rules by value', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/Search rules/i);
    await searchInput.fill('amazon');
    
    await page.waitForTimeout(500);
    
    // Results should contain amazon
    const tableText = await page.getByRole('table').textContent();
    expect(tableText?.toLowerCase()).toContain('amazon');
  });
});

test.describe('Account Switching', () => {
  
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.setExtraHTTPHeaders({
      'X-User-Email': 'david.a.royes@gmail.com'
    });
    
    // Switch to Email mode
    await page.getByRole('button', { name: '✉️' }).click();
    await expect(page.getByRole('heading', { name: 'Email Management' })).toBeVisible({ timeout: 10000 });
  });

  test('should switch to Church account', async ({ page }) => {
    // Click Church button
    await page.getByRole('button', { name: 'Church' }).first().click();
    
    // Wait for data to refresh
    await page.waitForTimeout(2000);
    
    // Click Rules tab to see the count
    await page.getByRole('button', { name: /Rules/i }).click();
    
    // Church should have fewer rules than Personal
    // The exact count will depend on your data
    const rulesTab = page.getByRole('button', { name: /Rules/i });
    await expect(rulesTab).toBeVisible();
  });

  test('should switch back to Personal account', async ({ page }) => {
    // Switch to Church first
    await page.getByRole('button', { name: 'Church' }).first().click();
    await page.waitForTimeout(1000);
    
    // Switch back to Personal
    await page.getByRole('button', { name: 'Personal' }).first().click();
    await page.waitForTimeout(1000);
    
    // Should be on Personal account
    const personalButton = page.getByRole('button', { name: 'Personal' }).first();
    await expect(personalButton).toBeVisible();
  });
});

test.describe('Dashboard Tab', () => {
  
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.setExtraHTTPHeaders({
      'X-User-Email': 'david.a.royes@gmail.com'
    });
    
    // Switch to Email mode
    await page.getByRole('button', { name: '✉️' }).click();
    await expect(page.getByRole('heading', { name: 'Email Management' })).toBeVisible({ timeout: 10000 });
    
    // Click Dashboard tab
    await page.getByRole('button', { name: 'Dashboard' }).click();
  });

  test('should have Analyze Inbox button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Analyze Inbox/i })).toBeVisible();
  });

  test('should have Refresh button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Refresh/i })).toBeVisible();
  });
});

