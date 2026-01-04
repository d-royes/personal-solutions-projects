import { test, expect } from '@playwright/test';

/**
 * Assistant Panel Tests
 *
 * Tests for the DATA assistant panel features including:
 * - Workspace management (add cards, check items)
 * - Plan generation and clearing
 * - Workspace context integration with chat
 */

test.describe('Assistant Panel', () => {

  test.beforeEach(async ({ page }) => {
    // Set dev auth header for API requests
    await page.setExtraHTTPHeaders({
      'X-User-Email': 'david.a.royes@gmail.com'
    });

    // Navigate to set up localStorage first
    await page.goto('/');

    // Inject dev auth into localStorage (must match AuthState format)
    await page.evaluate(() => {
      const authState = {
        mode: 'dev',
        userEmail: 'david.a.royes@gmail.com',
        idToken: null
      };
      localStorage.setItem('dta-auth-state', JSON.stringify(authState));
    });

    // Reload to pick up the auth state
    await page.reload();

    // Wait for tasks to load
    await page.waitForTimeout(3000);

    // Select the first task to open the task preview
    const tasks = page.getByRole('listitem');
    await tasks.first().click();

    // Click "Engage DATA" to load the full assistant panel
    const engageButton = page.getByRole('button', { name: /Engage DATA/i });
    await expect(engageButton).toBeVisible({ timeout: 5000 });
    await engageButton.click();

    // Wait for assistant panel to fully load (Planning zone container)
    await expect(page.locator('.planning-zone')).toBeVisible({ timeout: 15000 });
  });

  test.describe('Workspace Management', () => {

    test('should display workspace header with add button', async ({ page }) => {
      // The "+" button should always be visible in workspace header
      const workspaceHeader = page.locator('.zone-header').filter({ hasText: 'Workspace' });
      await expect(workspaceHeader).toBeVisible();

      const addButton = workspaceHeader.locator('.add-btn');
      await expect(addButton).toBeVisible();
      await expect(addButton).toHaveText('+');
    });

    test('should add a new empty card when clicking + button', async ({ page }) => {
      const workspaceHeader = page.locator('.zone-header').filter({ hasText: 'Workspace' });
      const addButton = workspaceHeader.locator('.add-btn');

      // Count existing workspace items
      const workspaceContent = page.locator('.workspace-content');
      const initialItems = await workspaceContent.locator('.workspace-item-simple').count();

      // Click add button
      await addButton.click();

      // Verify a new item was added
      await expect(workspaceContent.locator('.workspace-item-simple')).toHaveCount(initialItems + 1);

      // The new item should have an empty/editable textarea
      const newItem = workspaceContent.locator('.workspace-item-simple').last();
      const editor = newItem.locator('.workspace-editor');
      await expect(editor).toBeVisible();
    });

    test('should show copy and clear buttons when workspace has items', async ({ page }) => {
      const workspaceHeader = page.locator('.zone-header').filter({ hasText: 'Workspace' });
      const addButton = workspaceHeader.locator('.add-btn');

      // Add an item first
      await addButton.click();

      // Now copy and clear buttons should be visible
      const copyButton = workspaceHeader.locator('.copy-btn');
      const clearButton = workspaceHeader.locator('.clear-btn');

      await expect(copyButton).toBeVisible();
      await expect(clearButton).toBeVisible();
    });

    test('should clear all workspace items when clicking clear button', async ({ page }) => {
      const workspaceHeader = page.locator('.zone-header').filter({ hasText: 'Workspace' });
      const addButton = workspaceHeader.locator('.add-btn');
      const workspaceContent = page.locator('.workspace-content');

      // Get initial count (may have items from task context)
      const initialCount = await workspaceContent.locator('.workspace-item-simple').count();

      // Add two items
      await addButton.click();
      await addButton.click();
      await expect(workspaceContent.locator('.workspace-item-simple')).toHaveCount(initialCount + 2);

      // Click clear button
      const clearButton = workspaceHeader.locator('.clear-btn');
      await clearButton.click();

      // All items should be removed
      await expect(workspaceContent.locator('.workspace-item-simple')).toHaveCount(0);
    });

    test('should show checkbox on workspace item hover', async ({ page }) => {
      const workspaceHeader = page.locator('.zone-header').filter({ hasText: 'Workspace' });
      const addButton = workspaceHeader.locator('.add-btn');

      // Add an item
      await addButton.click();

      // Get the workspace item (outer container)
      const workspaceContent = page.locator('.workspace-content');
      const item = workspaceContent.locator('.workspace-item-simple').first();

      // Wait for the item to be stable before hovering
      await expect(item).toBeVisible();

      // Hover over the item
      await item.hover();

      // Checkbox should become visible (it's inside workspace-item-controls)
      const checkbox = item.locator('.workspace-item-checkbox');
      await expect(checkbox).toBeVisible();
    });

    test('should mark item as selected when checkbox is checked', async ({ page }) => {
      const workspaceHeader = page.locator('.zone-header').filter({ hasText: 'Workspace' });
      const addButton = workspaceHeader.locator('.add-btn');

      // Add an item and type some content
      await addButton.click();
      const workspaceContent = page.locator('.workspace-content');
      const item = workspaceContent.locator('.workspace-item-simple').first();

      // Wait for item to be visible and stable
      await expect(item).toBeVisible();

      const editor = item.locator('.workspace-editor');
      await editor.fill('Test workspace content');

      // Hover and check the checkbox
      await item.hover();
      const checkbox = item.locator('.workspace-item-checkbox');
      await checkbox.check();

      // Item (workspace-item-simple) should have selected class
      await expect(item).toHaveClass(/selected/);
    });

    test('should show selection hint when items are checked', async ({ page }) => {
      const workspaceHeader = page.locator('.zone-header').filter({ hasText: 'Workspace' });
      const addButton = workspaceHeader.locator('.add-btn');

      // Add an item
      await addButton.click();
      const workspaceContent = page.locator('.workspace-content');
      const item = workspaceContent.locator('.workspace-item-simple').first();

      // Wait for item to be visible
      await expect(item).toBeVisible();

      // Check the checkbox
      await item.hover();
      const checkbox = item.locator('.workspace-item-checkbox');
      await checkbox.check();

      // Selection hint should appear
      const hint = workspaceContent.locator('.workspace-selection-hint');
      await expect(hint).toBeVisible();
      await expect(hint).toContainText(/selected for context/i);
    });
  });

  test.describe('Plan Management', () => {

    test('should display Plan button in action bar', async ({ page }) => {
      const planButton = page.getByRole('button', { name: /Plan/i });
      await expect(planButton).toBeVisible();
    });

    test('should generate a plan when Plan button is clicked', async ({ page }) => {
      // Click Plan button
      const planButton = page.getByRole('button', { name: /Plan/i });
      await planButton.click();

      // Wait for plan to generate (may take a while due to API call)
      const planningZone = page.locator('.planning-zone');

      // Should show "Current Plan" section when complete
      await expect(planningZone.locator('h5').filter({ hasText: 'Current Plan' }))
        .toBeVisible({ timeout: 30000 });
    });

    test('should show push and clear buttons on plan card', async ({ page }) => {
      // Generate a plan first
      const planButton = page.getByRole('button', { name: /Plan/i });
      await planButton.click();

      // Wait for plan to appear
      const planSection = page.locator('.plan-section').first();
      await expect(planSection).toBeVisible({ timeout: 30000 });

      // Check for push button (arrow emoji)
      const pushButton = planSection.locator('.push-btn');
      await expect(pushButton).toBeVisible();

      // Check for clear button (x)
      const clearButton = planSection.locator('.clear-plan-btn');
      await expect(clearButton).toBeVisible();
    });

    test('should clear plan when clear button is clicked', async ({ page }) => {
      // Generate a plan first
      const planButton = page.getByRole('button', { name: /Plan/i });
      await planButton.click();

      // Wait for plan to appear
      const planSection = page.locator('.plan-section').first();
      await expect(planSection).toBeVisible({ timeout: 30000 });

      // Click clear button
      const clearPlanBtn = planSection.locator('.clear-plan-btn');
      await clearPlanBtn.click();

      // Plan should be cleared - no more "Current Plan" visible
      await expect(page.locator('h5').filter({ hasText: 'Current Plan' }))
        .not.toBeVisible({ timeout: 5000 });
    });

    test('should push plan to workspace when push button is clicked', async ({ page }) => {
      // Generate a plan first
      const planButton = page.getByRole('button', { name: /Plan/i });
      await planButton.click();

      // Wait for plan to appear
      const planSection = page.locator('.plan-section').first();
      await expect(planSection).toBeVisible({ timeout: 30000 });

      // Count initial workspace items
      const workspaceContent = page.locator('.workspace-content');
      const initialCount = await workspaceContent.locator('.workspace-item-simple').count();

      // Click push button
      const pushButton = planSection.locator('.push-btn');
      await pushButton.click();

      // Workspace should have one more item
      await expect(workspaceContent.locator('.workspace-item-simple'))
        .toHaveCount(initialCount + 1);
    });
  });

  test.describe('Workspace Context in Chat', () => {

    test('should have chat input in assistant panel', async ({ page }) => {
      const chatInput = page.locator('.chat-input-bottom textarea');
      await expect(chatInput).toBeVisible();
      await expect(chatInput).toHaveAttribute('placeholder', /Message DATA/i);
    });

    test('should be able to send message with workspace context', async ({ page }) => {
      // Add a workspace item with content
      const workspaceHeader = page.locator('.zone-header').filter({ hasText: 'Workspace' });
      const addButton = workspaceHeader.locator('.add-btn');
      await addButton.click();

      // Fill in workspace content
      const workspaceContent = page.locator('.workspace-content');
      const item = workspaceContent.locator('.workspace-item-simple').first();

      // Wait for item to be visible
      await expect(item).toBeVisible();

      const editor = item.locator('.workspace-editor');
      await editor.fill('Important context for DATA to consider');

      // Check the item to include in context
      await item.hover();
      const checkbox = item.locator('.workspace-item-checkbox');
      await checkbox.check();

      // Verify item is selected
      await expect(item).toHaveClass(/selected/);

      // Send a message
      const chatInput = page.locator('.chat-input-bottom textarea');
      await chatInput.fill('What do you think about the context I provided?');

      const sendButton = page.locator('.chat-input-bottom .send-btn');
      await sendButton.click();

      // Wait for response (an assistant message should appear)
      const assistantMessage = page.locator('.chat-bubble.assistant');
      await expect(assistantMessage.first()).toBeVisible({ timeout: 30000 });
    });
  });

  test.describe('Conversation Actions', () => {

    test('should show push and strike buttons on assistant messages', async ({ page }) => {
      // Send a message to get a response
      const chatInput = page.locator('.chat-input-bottom textarea');
      await chatInput.fill('Hello DATA');

      const sendButton = page.locator('.chat-input-bottom .send-btn');
      await sendButton.click();

      // Wait for response
      await page.waitForTimeout(5000);

      // Find an assistant message
      const assistantBubble = page.locator('.chat-bubble.assistant').first();
      await expect(assistantBubble).toBeVisible({ timeout: 30000 });

      // Check for push button in chat-meta
      const chatMeta = assistantBubble.locator('.chat-meta');
      const pushButton = chatMeta.locator('.push-btn-inline');
      await expect(pushButton).toBeVisible();

      // Check for strike button
      const strikeButton = chatMeta.locator('.strike-btn');
      await expect(strikeButton).toBeVisible();
    });

    test('conversation buttons should have proper spacing', async ({ page }) => {
      // This test verifies the CSS fix for button spacing
      // Send a message to get a response
      const chatInput = page.locator('.chat-input-bottom textarea');
      await chatInput.fill('Test message');

      const sendButton = page.locator('.chat-input-bottom .send-btn');
      await sendButton.click();

      // Wait for response
      const assistantBubble = page.locator('.chat-bubble.assistant').first();
      await expect(assistantBubble).toBeVisible({ timeout: 30000 });

      // Get the chat-meta container
      const chatMeta = assistantBubble.locator('.chat-meta');

      // Verify it uses flex layout with gap
      const display = await chatMeta.evaluate(el => getComputedStyle(el).display);
      expect(display).toBe('flex');

      const gap = await chatMeta.evaluate(el => getComputedStyle(el).gap);
      expect(gap).toBe('6px');
    });
  });
});
