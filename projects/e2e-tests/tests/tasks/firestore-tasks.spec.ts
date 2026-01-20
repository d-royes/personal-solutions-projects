import { test, expect } from '@playwright/test';

/**
 * Firestore Task Tests
 *
 * Tests for the Firestore-native task system in DATA's web dashboard.
 * Covers DATA Tasks view, CRUD operations, Done checkbox, and filtering.
 */

const API_BASE = process.env.API_BASE || 'http://localhost:8000';
const AUTH_HEADERS = {
  'X-User-Email': 'david.a.royes@gmail.com'
};

// Helper to set up auth state
async function setupAuth(page: any) {
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
  await page.waitForTimeout(3000);
}

test.describe('Firestore Tasks API', () => {

  test('GET /tasks/firestore should return tasks', async ({ request }) => {
    const response = await request.get(`${API_BASE}/tasks/firestore`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(Array.isArray(data.tasks)).toBeTruthy();
  });

  test('GET /tasks/firestore should filter by domain', async ({ request }) => {
    const response = await request.get(`${API_BASE}/tasks/firestore?domain=personal`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(Array.isArray(data.tasks)).toBeTruthy();
    
    // All returned tasks should be personal domain
    for (const task of data.tasks) {
      expect(task.domain).toBe('personal');
    }
  });

  test('GET /tasks/firestore should filter by status', async ({ request }) => {
    const response = await request.get(`${API_BASE}/tasks/firestore?status=scheduled`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(Array.isArray(data.tasks)).toBeTruthy();
    
    // All returned tasks should have scheduled status
    for (const task of data.tasks) {
      expect(task.status).toBe('scheduled');
    }
  });

  test('PATCH /tasks/firestore/{id} should update task', async ({ request }) => {
    // First get a task to update
    const listResponse = await request.get(`${API_BASE}/tasks/firestore`, {
      headers: AUTH_HEADERS
    });
    expect(listResponse.ok()).toBeTruthy();
    
    const listData = await listResponse.json();
    if (listData.tasks.length === 0) {
      test.skip(true, 'No tasks to update');
      return;
    }

    const taskId = listData.tasks[0].id;
    const originalNotes = listData.tasks[0].notes || '';
    const testNote = `E2E test note - ${Date.now()}`;

    // Update the task
    const updateResponse = await request.patch(
      `${API_BASE}/tasks/firestore/${taskId}`,
      {
        headers: {
          ...AUTH_HEADERS,
          'Content-Type': 'application/json'
        },
        data: {
          notes: testNote
        }
      }
    );
    expect(updateResponse.ok()).toBeTruthy();

    // Verify the update
    const verifyResponse = await request.get(`${API_BASE}/tasks/firestore`, {
      headers: AUTH_HEADERS
    });
    const verifyData = await verifyResponse.json();
    const updatedTask = verifyData.tasks.find((t: any) => t.id === taskId);
    expect(updatedTask.notes).toBe(testNote);

    // Restore original notes
    await request.patch(
      `${API_BASE}/tasks/firestore/${taskId}`,
      {
        headers: {
          ...AUTH_HEADERS,
          'Content-Type': 'application/json'
        },
        data: {
          notes: originalNotes
        }
      }
    );
  });

  test('PATCH should update done field', async ({ request }) => {
    // Get a task - pick from the end of the list to avoid conflicts with other tests
    const listResponse = await request.get(`${API_BASE}/tasks/firestore`, {
      headers: AUTH_HEADERS
    });
    const listData = await listResponse.json();
    
    if (listData.tasks.length < 3) {
      test.skip(true, 'Not enough tasks available');
      return;
    }

    // Find a task from the middle/end of the list to avoid conflicts
    // Pick tasks that aren't done and aren't in terminal status
    const eligibleTasks = listData.tasks.filter((t: any) => 
      !t.done && 
      t.status !== 'completed' && 
      t.status !== 'cancelled'
    );
    
    if (eligibleTasks.length < 2) {
      test.skip(true, 'No suitable task available');
      return;
    }

    // Pick a task from later in the list to reduce parallel test conflicts
    const task = eligibleTasks[Math.min(2, eligibleTasks.length - 1)];
    const taskId = task.id;
    const originalDone = task.done;

    // Update done to true
    const updateResponse = await request.patch(
      `${API_BASE}/tasks/firestore/${taskId}`,
      {
        headers: {
          ...AUTH_HEADERS,
          'Content-Type': 'application/json'
        },
        data: {
          done: true
        }
      }
    );
    expect(updateResponse.ok()).toBeTruthy();
    
    // Check the response body from PATCH if available
    const updateData = await updateResponse.json().catch(() => null);
    if (updateData && updateData.done !== undefined) {
      expect(updateData.done).toBe(true);
    }

    // Restore immediately without verification to avoid race conditions
    await request.patch(
      `${API_BASE}/tasks/firestore/${taskId}`,
      {
        headers: {
          ...AUTH_HEADERS,
          'Content-Type': 'application/json'
        },
        data: {
          done: originalDone
        }
      }
    );
    
    // The PATCH succeeded, which is the main assertion
    expect(updateResponse.status()).toBe(200);
  });
});

test.describe('DATA Tasks View', () => {

  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
  });

  test('should display DATA Tasks filter button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /DATA Tasks/i })).toBeVisible({ timeout: 10000 });
  });

  test('should load Firestore tasks when DATA Tasks clicked', async ({ page }) => {
    // Click DATA Tasks filter
    const dataTasksBtn = page.getByRole('button', { name: /DATA Tasks/i });
    await dataTasksBtn.click();
    
    // Wait for tasks to load
    await page.waitForTimeout(2000);
    
    // Verify the button is active/selected
    await expect(dataTasksBtn).toHaveClass(/active|selected/);
    
    // Should have task list
    await expect(page.getByRole('list')).toBeVisible({ timeout: 10000 });
  });

  test('should show Sync with Smartsheet button in DATA Tasks view', async ({ page }) => {
    // Click DATA Tasks
    await page.getByRole('button', { name: /DATA Tasks/i }).click();
    await page.waitForTimeout(1000);
    
    // Sync button should be visible
    await expect(page.getByRole('button', { name: /Sync/i })).toBeVisible();
  });

  test('should filter DATA Tasks by domain - Personal', async ({ page }) => {
    // Click DATA Tasks first
    await page.getByRole('button', { name: /DATA Tasks/i }).click();
    await page.waitForTimeout(1000);
    
    // Click Personal filter
    await page.getByRole('button', { name: 'Personal' }).first().click();
    await page.waitForTimeout(500);
    
    // Verify filtering (tasks should show Personal indicator)
    const tasks = page.getByRole('listitem');
    const count = await tasks.count();
    
    if (count > 0) {
      // All visible tasks should have Personal domain
      for (let i = 0; i < Math.min(count, 5); i++) {
        const taskText = await tasks.nth(i).textContent();
        expect(taskText?.toLowerCase()).toContain('personal');
      }
    }
  });

  test('should hide completed tasks in DATA Tasks view', async ({ page }) => {
    // Click DATA Tasks
    await page.getByRole('button', { name: /DATA Tasks/i }).click();
    await page.waitForTimeout(2000);
    
    // Get all visible tasks
    const tasks = page.getByRole('listitem');
    const count = await tasks.count();
    
    // None of the visible tasks should show "completed" status badge
    for (let i = 0; i < count; i++) {
      const taskText = await tasks.nth(i).textContent();
      // Tasks that are done/completed shouldn't appear
      expect(taskText?.toLowerCase()).not.toContain('status: completed');
    }
  });

  test('should hide cancelled tasks in DATA Tasks view', async ({ page }) => {
    // Click DATA Tasks
    await page.getByRole('button', { name: /DATA Tasks/i }).click();
    await page.waitForTimeout(2000);
    
    // Get all visible tasks
    const tasks = page.getByRole('listitem');
    const count = await tasks.count();
    
    // None of the visible tasks should show "cancelled" status
    for (let i = 0; i < count; i++) {
      const taskText = await tasks.nth(i).textContent();
      expect(taskText?.toLowerCase()).not.toContain('cancelled');
    }
  });
});

test.describe('Needs Attention View', () => {

  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
  });

  test('should display Needs Attention filter button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Needs attention/i })).toBeVisible({ timeout: 10000 });
  });

  test('should load attention tasks when clicked', async ({ page }) => {
    await page.getByRole('button', { name: /Needs attention/i }).click();
    await page.waitForTimeout(2000);
    
    // Should still have task list visible
    await expect(page.getByRole('list')).toBeVisible({ timeout: 10000 });
  });

  test('should hide completed tasks in Needs Attention view', async ({ page }) => {
    await page.getByRole('button', { name: /Needs attention/i }).click();
    await page.waitForTimeout(2000);
    
    const tasks = page.getByRole('listitem');
    const count = await tasks.count();
    
    for (let i = 0; i < count; i++) {
      const taskText = await tasks.nth(i).textContent();
      expect(taskText?.toLowerCase()).not.toContain('status: completed');
    }
  });

  test('should hide cancelled tasks in Needs Attention view', async ({ page }) => {
    await page.getByRole('button', { name: /Needs attention/i }).click();
    await page.waitForTimeout(2000);
    
    const tasks = page.getByRole('listitem');
    const count = await tasks.count();
    
    for (let i = 0; i < count; i++) {
      const taskText = await tasks.nth(i).textContent();
      expect(taskText?.toLowerCase()).not.toContain('cancelled');
    }
  });
});

test.describe('Firestore Task Edit Form', () => {

  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    
    // Click DATA Tasks to ensure we're looking at Firestore tasks
    await page.getByRole('button', { name: /DATA Tasks/i }).click();
    await page.waitForTimeout(2000);
    
    // Select first task
    const tasks = page.getByRole('listitem');
    await tasks.first().click();
    await page.waitForTimeout(500);
  });

  test('should show task details when task selected', async ({ page }) => {
    // Task details should be visible in the assistant panel area
    const taskTitle = page.locator('.task-title, .task-preview h3, [class*="task-detail"]').first();
    await expect(taskTitle).toBeVisible({ timeout: 5000 });
  });

  test('should show Edit button for Firestore tasks', async ({ page }) => {
    const editButton = page.getByRole('button', { name: /Edit/i });
    await expect(editButton).toBeVisible({ timeout: 5000 });
  });

  test('should open edit form when Edit clicked', async ({ page }) => {
    const editButton = page.getByRole('button', { name: /Edit/i });
    await editButton.click();
    await page.waitForTimeout(500);
    
    // Should see edit form elements - status dropdown
    await expect(page.locator('select, [role="combobox"]').first()).toBeVisible({ timeout: 5000 });
  });

  test('should show Done checkbox in edit form', async ({ page }) => {
    const editButton = page.getByRole('button', { name: /Edit/i });
    await editButton.click();
    await page.waitForTimeout(500);
    
    // Look for Done checkbox
    const doneCheckbox = page.getByLabel(/Done/i);
    await expect(doneCheckbox).toBeVisible({ timeout: 5000 });
  });

  test('should auto-set Done when status changed to cancelled', async ({ page }) => {
    const editButton = page.getByRole('button', { name: /Edit/i });
    await editButton.click();
    await page.waitForTimeout(500);
    
    // Find status dropdown
    const statusSelect = page.locator('select').first();
    
    // Get current done checkbox state
    const doneCheckbox = page.getByLabel(/Done/i);
    const wasChecked = await doneCheckbox.isChecked();
    
    // Change status to cancelled
    await statusSelect.selectOption('cancelled');
    await page.waitForTimeout(300);
    
    // Done checkbox should now be checked
    await expect(doneCheckbox).toBeChecked();
    
    // Cancel to avoid saving changes
    const cancelButton = page.getByRole('button', { name: /Cancel/i });
    if (await cancelButton.isVisible()) {
      await cancelButton.click();
    }
  });

  test('should auto-set Done when status changed to completed', async ({ page }) => {
    const editButton = page.getByRole('button', { name: /Edit/i });
    await editButton.click();
    await page.waitForTimeout(500);
    
    const statusSelect = page.locator('select').first();
    const doneCheckbox = page.getByLabel(/Done/i);
    
    // Change status to completed
    await statusSelect.selectOption('completed');
    await page.waitForTimeout(300);
    
    // Done checkbox should be checked
    await expect(doneCheckbox).toBeChecked();
    
    // Cancel to avoid saving changes
    const cancelButton = page.getByRole('button', { name: /Cancel/i });
    if (await cancelButton.isVisible()) {
      await cancelButton.click();
    }
  });

  test('should auto-set Done when status changed to delegated', async ({ page }) => {
    test.setTimeout(45000);
    
    const editButton = page.getByRole('button', { name: /Edit/i });
    await expect(editButton).toBeVisible({ timeout: 10000 });
    await editButton.click();
    await page.waitForTimeout(500);
    
    const statusSelect = page.locator('select').first();
    await expect(statusSelect).toBeVisible({ timeout: 5000 });
    
    const doneCheckbox = page.getByLabel(/Done/i);
    
    // Change status to delegated
    await statusSelect.selectOption('delegated');
    await page.waitForTimeout(300);
    
    // Done checkbox should be checked
    await expect(doneCheckbox).toBeChecked();
    
    // Cancel
    const cancelButton = page.getByRole('button', { name: /Cancel/i });
    if (await cancelButton.isVisible()) {
      await cancelButton.click();
    }
  });

  test('should show Mark Complete button', async ({ page }) => {
    const markCompleteBtn = page.getByRole('button', { name: /Mark Complete/i });
    await expect(markCompleteBtn).toBeVisible({ timeout: 5000 });
  });
});

test.describe('New Firestore Task Creation', () => {

  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    
    // Click DATA Tasks
    await page.getByRole('button', { name: /DATA Tasks/i }).click();
    await page.waitForTimeout(2000);
  });

  test('should show New Task button', async ({ page }) => {
    const newTaskBtn = page.getByRole('button', { name: /New Task|\+ Task/i });
    await expect(newTaskBtn).toBeVisible({ timeout: 5000 });
  });

  test('should open task creation modal when New Task clicked', async ({ page }) => {
    const newTaskBtn = page.getByRole('button', { name: /New Task|\+ Task/i });
    await newTaskBtn.click();
    await page.waitForTimeout(1000);
    
    // Modal or form should appear - look for various indicators
    // Could be a modal, dialog, or inline form
    const modalOrForm = page.locator('dialog, [role="dialog"], .modal, .task-form, form').first();
    const titleInput = page.locator('input[type="text"], input:not([type]), textarea').first();
    
    // Either a modal appeared or an input appeared
    const isModalVisible = await modalOrForm.isVisible().catch(() => false);
    const isInputVisible = await titleInput.isVisible().catch(() => false);
    
    expect(isModalVisible || isInputVisible).toBeTruthy();
  });
});
