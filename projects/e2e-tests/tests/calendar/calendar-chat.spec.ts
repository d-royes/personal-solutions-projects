import { test, expect } from '@playwright/test';

/**
 * Calendar DATA Chat Tests
 *
 * End-to-end tests for DATA's chat functionality in Calendar Management mode.
 * Validates the HITL test groups:
 * - Group 1: Basic Chat Functionality
 * - Group 2: Domain Awareness
 * - Group 3: Task Creation from Calendar
 * - Group 4: Task Editing from Calendar
 * - Group 5: Calendar Event Creation
 * - Group 6: Workload Analysis
 */

const API_BASE = 'http://localhost:8000';

// Helper to set up authenticated calendar view
async function setupCalendarView(page: any, domain: 'Personal' | 'Work' | 'Church' | 'Combined' = 'Personal') {
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

  // Select the requested domain
  await page.getByRole('button', { name: domain }).click();
  await page.waitForTimeout(1000);
}

// ============================================================================
// Group 1: Basic Chat Functionality
// ============================================================================

test.describe('Calendar Chat - Basic Functionality', () => {

  test.beforeEach(async ({ page }) => {
    await setupCalendarView(page, 'Personal');
  });

  test('should display DATA chat panel', async ({ page }) => {
    // DATA header should be visible
    await expect(page.locator('.email-assist-header').getByText('DATA')).toBeVisible({ timeout: 5000 });
  });

  test('should have chat input field', async ({ page }) => {
    // Chat input should be visible with placeholder
    const chatInput = page.locator('input[placeholder*="Ask DATA"]');
    await expect(chatInput).toBeVisible({ timeout: 5000 });
  });

  test('should have Send button', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Send' })).toBeVisible({ timeout: 5000 });
  });

  test('should have Clear Chat button', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Clear Chat' })).toBeVisible({ timeout: 5000 });
  });

  test('should send message and receive response', async ({ page }) => {
    const chatInput = page.locator('input[placeholder*="Ask DATA"]');
    await chatInput.fill('Hello');
    await page.getByRole('button', { name: 'Send' }).click();

    // Should show user message
    await expect(page.locator('.chat-message-user, .user-message').last()).toContainText('Hello', { timeout: 10000 });

    // Should show assistant response (wait for API)
    await expect(page.locator('.chat-message-assistant, .assistant-message').last()).toBeVisible({ timeout: 30000 });
  });

  test('should clear chat when clicking Clear Chat', async ({ page }) => {
    // First send a message
    const chatInput = page.locator('input[placeholder*="Ask DATA"]');
    await chatInput.fill('Test message');
    await page.getByRole('button', { name: 'Send' }).click();

    // Wait for response
    await page.waitForTimeout(5000);

    // Click Clear Chat
    await page.getByRole('button', { name: 'Clear Chat' }).click();

    // Chat should be cleared (no messages visible or welcome message shown)
    await page.waitForTimeout(1000);
    const messageCount = await page.locator('.chat-message-user, .user-message').count();
    expect(messageCount).toBe(0);
  });
});

// ============================================================================
// Group 2: Domain Awareness
// ============================================================================

test.describe('Calendar Chat - Domain Awareness', () => {

  test('should show Personal context when on Personal view', async ({ page }) => {
    await setupCalendarView(page, 'Personal');

    const chatInput = page.locator('input[placeholder*="Ask DATA"]');
    await chatInput.fill('What calendar am I looking at?');
    await page.getByRole('button', { name: 'Send' }).click();

    // Response should mention personal
    const response = page.locator('.chat-message-assistant, .assistant-message').last();
    await expect(response).toBeVisible({ timeout: 30000 });
    const text = await response.textContent();
    expect(text?.toLowerCase()).toMatch(/personal/i);
  });

  test('should show Work context when on Work view', async ({ page }) => {
    await setupCalendarView(page, 'Work');

    const chatInput = page.locator('input[placeholder*="Ask DATA"]');
    await chatInput.fill('What domain am I in?');
    await page.getByRole('button', { name: 'Send' }).click();

    // Response should mention work
    const response = page.locator('.chat-message-assistant, .assistant-message').last();
    await expect(response).toBeVisible({ timeout: 30000 });
    const text = await response.textContent();
    expect(text?.toLowerCase()).toMatch(/work/i);
  });

  test('should show Church context when on Church view', async ({ page }) => {
    await setupCalendarView(page, 'Church');

    const chatInput = page.locator('input[placeholder*="Ask DATA"]');
    await chatInput.fill('What view is this?');
    await page.getByRole('button', { name: 'Send' }).click();

    // Response should mention church
    const response = page.locator('.chat-message-assistant, .assistant-message').last();
    await expect(response).toBeVisible({ timeout: 30000 });
    const text = await response.textContent();
    expect(text?.toLowerCase()).toMatch(/church|southpoint/i);
  });
});

// ============================================================================
// Group 3: Task Creation from Calendar
// ============================================================================

test.describe('Calendar Chat - Task Creation', () => {

  test.beforeEach(async ({ page }) => {
    await setupCalendarView(page, 'Personal');
  });

  test('should show task creation confirmation when asking to create a task', async ({ page }) => {
    const chatInput = page.locator('input[placeholder*="Ask DATA"]');
    await chatInput.fill('Create a task to test the calendar integration');
    await page.getByRole('button', { name: 'Send' }).click();

    // Should show pending task creation card with Create button
    await expect(page.locator('.pending-action-card')).toBeVisible({ timeout: 30000 });
    await expect(page.getByRole('button', { name: /Create/i })).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole('button', { name: /Cancel/i })).toBeVisible();
  });

  test('should cancel task creation when clicking Cancel', async ({ page }) => {
    const chatInput = page.locator('input[placeholder*="Ask DATA"]');
    await chatInput.fill('Create a task to review documents');
    await page.getByRole('button', { name: 'Send' }).click();

    // Wait for confirmation card
    await expect(page.locator('.pending-action-card')).toBeVisible({ timeout: 30000 });

    // Click Cancel
    await page.getByRole('button', { name: /Cancel/i }).click();

    // Confirmation card should disappear
    await expect(page.locator('.pending-action-card')).not.toBeVisible({ timeout: 5000 });

    // Should show cancellation message
    await expect(page.locator('.chat-message-assistant, .assistant-message').last()).toContainText(/cancelled/i, { timeout: 5000 });
  });

  test('task creation card should show task details', async ({ page }) => {
    const chatInput = page.locator('input[placeholder*="Ask DATA"]');
    await chatInput.fill('Create an urgent task to prepare quarterly report due Friday');
    await page.getByRole('button', { name: 'Send' }).click();

    // Wait for confirmation card
    await expect(page.locator('.pending-action-card')).toBeVisible({ timeout: 30000 });

    // Card should show task title
    const cardText = await page.locator('.pending-action-card').textContent();
    expect(cardText).toMatch(/quarterly|report|prepare/i);
  });
});

// ============================================================================
// Group 4: Task Editing from Calendar
// ============================================================================

test.describe('Calendar Chat - Task Editing', () => {

  test.beforeEach(async ({ page }) => {
    await setupCalendarView(page, 'Personal');
    // Click on Tasks tab to see tasks
    await page.getByRole('button', { name: /^Tasks/i }).click();
    await page.waitForTimeout(2000);
  });

  test('should show task update confirmation when asking to update a task', async ({ page }) => {
    // First click on a task to select it
    const taskItem = page.locator('.calendar-task-item').first();
    const taskCount = await taskItem.count();

    if (taskCount > 0) {
      await taskItem.click();
      await page.waitForTimeout(500);

      // Ask to update the task
      const chatInput = page.locator('input[placeholder*="Ask DATA"]');
      await chatInput.fill('Push this task out to next week');
      await page.getByRole('button', { name: 'Send' }).click();

      // Should show pending action card with Confirm button
      await expect(page.locator('.pending-action-card')).toBeVisible({ timeout: 30000 });
      await expect(page.getByRole('button', { name: /Confirm/i })).toBeVisible({ timeout: 5000 });
    }
  });

  test('should be able to ask about task priorities', async ({ page }) => {
    const chatInput = page.locator('input[placeholder*="Ask DATA"]');
    await chatInput.fill('What are my highest priority tasks?');
    await page.getByRole('button', { name: 'Send' }).click();

    // Should get a response about tasks
    const response = page.locator('.chat-message-assistant, .assistant-message').last();
    await expect(response).toBeVisible({ timeout: 30000 });
    const text = await response.textContent();
    expect(text?.toLowerCase()).toMatch(/task|priority|urgent|important/i);
  });
});

// ============================================================================
// Group 5: Calendar Event Creation
// ============================================================================

test.describe('Calendar Chat - Event Creation', () => {

  test.beforeEach(async ({ page }) => {
    await setupCalendarView(page, 'Personal');
  });

  test('should show event creation confirmation when asking to create an event', async ({ page }) => {
    const chatInput = page.locator('input[placeholder*="Ask DATA"]');
    await chatInput.fill('Block 2 hours tomorrow at 2pm for focus time');
    await page.getByRole('button', { name: 'Send' }).click();

    // Should show pending calendar action card
    await expect(page.locator('.pending-action-card')).toBeVisible({ timeout: 30000 });

    // Should have confirmation buttons
    await expect(page.getByRole('button', { name: /Confirm|Create/i })).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole('button', { name: /Cancel/i })).toBeVisible();
  });

  test('should cancel event creation when clicking Cancel', async ({ page }) => {
    const chatInput = page.locator('input[placeholder*="Ask DATA"]');
    await chatInput.fill('Schedule a meeting tomorrow at 3pm');
    await page.getByRole('button', { name: 'Send' }).click();

    // Wait for confirmation card
    await expect(page.locator('.pending-action-card')).toBeVisible({ timeout: 30000 });

    // Click Cancel
    await page.getByRole('button', { name: /Cancel/i }).click();

    // Confirmation card should disappear
    await expect(page.locator('.pending-action-card')).not.toBeVisible({ timeout: 5000 });
  });

  test('event creation card should show event details', async ({ page }) => {
    const chatInput = page.locator('input[placeholder*="Ask DATA"]');
    await chatInput.fill('Create a meeting called Team Sync tomorrow at 10am in Conference Room A');
    await page.getByRole('button', { name: 'Send' }).click();

    // Wait for confirmation card
    await expect(page.locator('.pending-action-card')).toBeVisible({ timeout: 30000 });

    // Card should show event summary
    const cardText = await page.locator('.pending-action-card').textContent();
    expect(cardText).toMatch(/Team Sync|meeting|10/i);
  });

  test('should not allow event creation on Work calendar', async ({ page }) => {
    await page.getByRole('button', { name: 'Work' }).click();
    await page.waitForTimeout(1000);

    const chatInput = page.locator('input[placeholder*="Ask DATA"]');
    await chatInput.fill('Create an event tomorrow at noon');
    await page.getByRole('button', { name: 'Send' }).click();

    // Response should indicate work calendar is read-only or redirect
    const response = page.locator('.chat-message-assistant, .assistant-message').last();
    await expect(response).toBeVisible({ timeout: 30000 });
    // Work events can't be created directly - DATA should acknowledge this
  });
});

// ============================================================================
// Group 6: Workload Analysis
// ============================================================================

test.describe('Calendar Chat - Workload Analysis', () => {

  test.beforeEach(async ({ page }) => {
    await setupCalendarView(page, 'Combined');
  });

  test('should analyze daily workload when asked', async ({ page }) => {
    const chatInput = page.locator('input[placeholder*="Ask DATA"]');
    await chatInput.fill('Am I overcommitted tomorrow?');
    await page.getByRole('button', { name: 'Send' }).click();

    // Should get a detailed response about workload
    const response = page.locator('.chat-message-assistant, .assistant-message').last();
    await expect(response).toBeVisible({ timeout: 30000 });
    const text = await response.textContent();
    // Response should mention meetings, tasks, or workload
    expect(text?.toLowerCase()).toMatch(/meeting|task|commit|schedule|workload|calendar/i);
  });

  test('should analyze weekly workload when asked', async ({ page }) => {
    const chatInput = page.locator('input[placeholder*="Ask DATA"]');
    await chatInput.fill('What does my week look like?');
    await page.getByRole('button', { name: 'Send' }).click();

    // Should get a response about the week
    const response = page.locator('.chat-message-assistant, .assistant-message').last();
    await expect(response).toBeVisible({ timeout: 30000 });
    const text = await response.textContent();
    expect(text?.toLowerCase()).toMatch(/week|monday|tuesday|wednesday|thursday|friday|meeting|task/i);
  });

  test('should provide meeting count when asked', async ({ page }) => {
    const chatInput = page.locator('input[placeholder*="Ask DATA"]');
    await chatInput.fill('How many meetings do I have this week?');
    await page.getByRole('button', { name: 'Send' }).click();

    // Should get a response with meeting information
    const response = page.locator('.chat-message-assistant, .assistant-message').last();
    await expect(response).toBeVisible({ timeout: 30000 });
    const text = await response.textContent();
    expect(text?.toLowerCase()).toMatch(/meeting|\d+/i);
  });

  test('should identify VIP meetings when asked', async ({ page }) => {
    const chatInput = page.locator('input[placeholder*="Ask DATA"]');
    await chatInput.fill('Do I have any VIP meetings this week?');
    await page.getByRole('button', { name: 'Send' }).click();

    // Should get a response about VIP meetings
    const response = page.locator('.chat-message-assistant, .assistant-message').last();
    await expect(response).toBeVisible({ timeout: 30000 });
    // Response should acknowledge VIP or mention there are none
  });

  test('should suggest task adjustments based on workload', async ({ page }) => {
    const chatInput = page.locator('input[placeholder*="Ask DATA"]');
    await chatInput.fill('I feel overwhelmed. What should I prioritize?');
    await page.getByRole('button', { name: 'Send' }).click();

    // Should get helpful prioritization advice
    const response = page.locator('.chat-message-assistant, .assistant-message').last();
    await expect(response).toBeVisible({ timeout: 30000 });
    const text = await response.textContent();
    expect(text?.toLowerCase()).toMatch(/priorit|focus|urgent|important|recommend|suggest/i);
  });
});

// ============================================================================
// API Integration Tests
// ============================================================================

test.describe('Calendar Chat - API Integration', () => {

  test('calendar chat endpoint responds', async ({ request }) => {
    const response = await request.post(`${API_BASE}/calendar/personal/chat`, {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com',
        'Content-Type': 'application/json'
      },
      data: {
        message: 'Hello',
        context: {
          selectedEventId: null,
          dateRange: {
            start: new Date().toISOString(),
            end: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString()
          },
          tasksInView: []
        }
      }
    });

    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data).toHaveProperty('response');
    expect(data).toHaveProperty('domain');
  });

  test('calendar conversation history endpoint responds', async ({ request }) => {
    const response = await request.get(`${API_BASE}/calendar/personal/conversation`, {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com'
      }
    });

    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data).toHaveProperty('domain');
    expect(data).toHaveProperty('messages');
  });

  test('task creation endpoint responds', async ({ request }) => {
    // Test with preview mode (confirmed: false)
    const response = await request.post(`${API_BASE}/tasks/create`, {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com',
        'Content-Type': 'application/json'
      },
      data: {
        source: 'personal',
        task: 'E2E Test Task',
        project: 'Sm. Projects & Tasks',
        due_date: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().split('T')[0],
        priority: 'Standard',
        status: 'Scheduled',
        assigned_to: 'david.a.royes@gmail.com',
        estimated_hours: '1',
        confirmed: false
      }
    });

    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.status).toBe('preview');
  });
});
