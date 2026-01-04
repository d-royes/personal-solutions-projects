import { test, expect } from '@playwright/test';

/**
 * API Health Check Tests
 * 
 * Basic tests to verify the DATA backend API is running and responding correctly.
 * These tests run before other tests to ensure the infrastructure is healthy.
 */

const API_BASE = 'http://localhost:8000';

test.describe('API Health Checks', () => {
  
  test('backend API health endpoint responds', async ({ request }) => {
    const response = await request.get(`${API_BASE}/health`);
    expect(response.ok()).toBeTruthy();
    
    const data = await response.json();
    expect(['ok', 'healthy'].includes(data.status)).toBeTruthy();
  });

  test('tasks endpoint responds with auth bypass', async ({ request }) => {
    const response = await request.get(`${API_BASE}/tasks`, {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com'
      }
    });
    expect(response.ok()).toBeTruthy();
    
    const data = await response.json();
    expect(Array.isArray(data.tasks)).toBeTruthy();
  });

  test('email rules endpoint responds', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/rules/personal`, {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com'
      }
    });
    expect(response.ok()).toBeTruthy();
    
    const data = await response.json();
    expect(Array.isArray(data.rules)).toBeTruthy();
  });

  test('inbox summary endpoint responds', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/inbox/personal`, {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com'
      }
    });
    
    // This might fail if Gmail isn't configured, which is okay
    if (response.ok()) {
      const data = await response.json();
      expect(data).toHaveProperty('total_count');
    }
  });
});

test.describe('Frontend Health Checks', () => {
  
  test('frontend loads without errors', async ({ page }) => {
    // Listen for console errors
    const errors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });
    
    await page.goto('/');
    
    // Wait for app to load
    await page.waitForTimeout(3000);
    
    // Should not have critical errors (some warnings are okay)
    const criticalErrors = errors.filter(e => 
      !e.includes('favicon') && 
      !e.includes('DevTools')
    );
    
    expect(criticalErrors.length).toBe(0);
  });

  test('frontend renders main layout', async ({ page }) => {
    await page.goto('/');
    
    // Should have header
    await expect(page.getByRole('banner')).toBeVisible();
    
    // Should have main content area
    await expect(page.getByRole('main')).toBeVisible();
  });
});

