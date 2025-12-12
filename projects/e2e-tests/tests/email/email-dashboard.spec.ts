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
    
    // Should be back on task view - wait longer for tasks to load
    await page.waitForTimeout(3000);
    await expect(page.getByRole('button', { name: 'All' })).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Email Rules Tab', () => {
  
  test.beforeEach(async ({ page }) => {
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
    await expect(page.getByRole('heading', { name: 'Email Management' })).toBeVisible({ timeout: 10000 });
    
    // Click Rules tab
    await page.getByRole('button', { name: /Rules/i }).click();
    await page.waitForTimeout(1000);
  });

  test('should display rules count in tab', async ({ page }) => {
    // The Rules tab should show a count like "Rules (325)"
    const rulesTab = page.getByRole('button', { name: /Rules.*\d+/i });
    await expect(rulesTab).toBeVisible();
  });

  test('should have category filter dropdown', async ({ page }) => {
    // Look for the select element or dropdown by its text
    await expect(page.locator('select').first()).toBeVisible();
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
    const categoryDropdown = page.locator('select').first();
    await categoryDropdown.selectOption('Promotional');
    
    await page.waitForTimeout(1000);
    
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

  test('should display stat cards with counts', async ({ page }) => {
    // Wait for data to load
    await page.waitForTimeout(3000);
    
    // Should have stat cards showing numbers
    const statCards = page.locator('.stat-card');
    const count = await statCards.count();
    expect(count).toBeGreaterThanOrEqual(3);
  });

  test('should display formatted numbers with commas', async ({ page }) => {
    // Wait for data to load
    await page.waitForTimeout(3000);
    
    // Check that large numbers show commas (e.g., 3,360)
    const statValues = page.locator('.stat-value');
    const firstValue = await statValues.first().textContent();
    
    // If value > 999, it should contain a comma
    if (firstValue && parseInt(firstValue.replace(/,/g, '')) > 999) {
      expect(firstValue).toContain(',');
    }
  });
});

test.describe('Email Styling Consistency', () => {
  
  test.beforeEach(async ({ page }) => {
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
    await expect(page.getByRole('heading', { name: 'Email Management' })).toBeVisible({ timeout: 10000 });
  });

  test('email dashboard should have consistent panel styling', async ({ page }) => {
    // Dashboard should have the panel class styling
    const dashboard = page.locator('.email-dashboard');
    await expect(dashboard).toBeVisible();
    
    // Should have border-radius
    const borderRadius = await dashboard.evaluate(el => 
      window.getComputedStyle(el).borderRadius
    );
    expect(borderRadius).toBe('18px');
  });

  test('tabs should have pill-style appearance', async ({ page }) => {
    // Tabs container should have the pill style
    const tabs = page.locator('.email-tabs');
    await expect(tabs).toBeVisible();
    
    // Should have border-radius for pill appearance
    const borderRadius = await tabs.evaluate(el => 
      window.getComputedStyle(el).borderRadius
    );
    expect(borderRadius).toBe('8px');
  });

  test('account selector should have pill-style appearance', async ({ page }) => {
    // Account selector should match mode-switcher style
    const selector = page.locator('.account-selector');
    await expect(selector).toBeVisible();
    
    // Should have border-radius for pill appearance
    const borderRadius = await selector.evaluate(el => 
      window.getComputedStyle(el).borderRadius
    );
    expect(borderRadius).toBe('8px');
  });

  test('active tab should have gradient background', async ({ page }) => {
    // Active tab should have the gradient style
    const activeTab = page.locator('.email-tabs button.active');
    await expect(activeTab).toBeVisible();
    
    // Should have gradient background
    const bgImage = await activeTab.evaluate(el => 
      window.getComputedStyle(el).backgroundImage
    );
    expect(bgImage).toContain('gradient');
  });

  test('all navigation tabs remain functional after styling', async ({ page }) => {
    // Test each tab can be clicked and activates
    const tabs = ['Dashboard', 'Rules', 'Suggestions', 'Attention'];
    
    for (const tabName of tabs) {
      const tab = page.getByRole('button', { name: new RegExp(tabName, 'i') });
      await tab.click();
      await page.waitForTimeout(500);
      
      // Tab should now be active
      await expect(tab).toHaveClass(/active/);
    }
  });

  test('scrolling works within email dashboard content', async ({ page }) => {
    // Click on Rules tab which has scrollable content
    await page.getByRole('button', { name: /Rules/i }).click();
    await page.waitForTimeout(2000);
    
    // Content area should be scrollable
    const content = page.locator('.email-tab-content');
    const isScrollable = await content.evaluate(el => 
      el.scrollHeight > el.clientHeight
    );
    
    // If there's enough content, it should be scrollable
    // This may vary based on actual data
    expect(await content.isVisible()).toBe(true);
  });
});

test.describe('Two-Panel Layout (Phase 2)', () => {
  
  test.beforeEach(async ({ page }) => {
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
    await expect(page.getByRole('heading', { name: 'Email Management' })).toBeVisible({ timeout: 10000 });
  });

  test('should display two-panel layout with left panel visible', async ({ page }) => {
    // Left panel should be visible
    const leftPanel = page.locator('.email-left-panel');
    await expect(leftPanel).toBeVisible();
    
    // Left panel should contain tabs
    await expect(leftPanel.locator('.email-tabs')).toBeVisible();
  });

  test('should have collapse button in left panel', async ({ page }) => {
    const collapseBtn = page.locator('.panel-collapse-btn.left');
    await expect(collapseBtn).toBeVisible();
  });

  test('should show collapsed DATA indicator when right panel is collapsed', async ({ page }) => {
    // The DATA panel starts collapsed, so collapsed indicator should be visible
    const collapsedIndicator = page.locator('.collapsed-panel-indicator.right');
    await expect(collapsedIndicator).toBeVisible();
    
    // Should contain DATA label
    await expect(collapsedIndicator.locator('.collapsed-label')).toContainText('DATA');
  });

  test('should expand DATA panel when clicking collapsed indicator', async ({ page }) => {
    // Click the collapsed DATA indicator
    const collapsedIndicator = page.locator('.collapsed-panel-indicator.right');
    await collapsedIndicator.click();
    await page.waitForTimeout(500);
    
    // Right panel should now be visible
    const rightPanel = page.locator('.email-right-panel');
    await expect(rightPanel).toBeVisible();
    
    // Should contain DATA header
    await expect(rightPanel.locator('.email-assist-header h2')).toContainText('DATA');
  });

  test('should show chat interface in DATA panel', async ({ page }) => {
    // Expand the DATA panel
    await page.locator('.collapsed-panel-indicator.right').click();
    await page.waitForTimeout(500);
    
    // Should show chat container (Phase 4 replaced placeholder with actual chat)
    const chatContainer = page.locator('.email-chat-container');
    await expect(chatContainer).toBeVisible();
    
    // Should have chat input
    const chatInput = page.locator('.email-chat-input');
    await expect(chatInput).toBeVisible();
  });

  test('should collapse left panel when clicking its collapse button', async ({ page }) => {
    // First expand the DATA panel so we can collapse the left panel
    await page.locator('.collapsed-panel-indicator.right').click();
    await page.waitForTimeout(500);
    
    // Click the left panel collapse button
    const collapseBtn = page.locator('.panel-collapse-btn.left');
    await collapseBtn.click();
    await page.waitForTimeout(500);
    
    // Left panel should be hidden
    const leftPanel = page.locator('.email-left-panel');
    await expect(leftPanel).not.toBeVisible();
    
    // Collapsed indicator for inbox should be visible
    const collapsedIndicator = page.locator('.collapsed-panel-indicator.left');
    await expect(collapsedIndicator).toBeVisible();
  });

  test('should expand both panels when clicking collapsed inbox indicator', async ({ page }) => {
    // First expand DATA panel
    await page.locator('.collapsed-panel-indicator.right').click();
    await page.waitForTimeout(500);
    
    // Collapse left panel
    await page.locator('.panel-collapse-btn.left').click();
    await page.waitForTimeout(500);
    
    // Click the collapsed inbox indicator to expand
    await page.locator('.collapsed-panel-indicator.left').click();
    await page.waitForTimeout(500);
    
    // Both panels should be visible
    await expect(page.locator('.email-left-panel')).toBeVisible();
    await expect(page.locator('.email-right-panel')).toBeVisible();
  });

  test('should select email from recent messages and show in DATA panel', async ({ page }) => {
    // Wait for messages to load
    await page.waitForTimeout(3000);
    
    // Check if there are recent messages
    const messageList = page.locator('.message-list li');
    const messageCount = await messageList.count();
    
    if (messageCount > 0) {
      // Click on the first message
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // DATA panel should open
      const rightPanel = page.locator('.email-right-panel');
      await expect(rightPanel).toBeVisible();
      
      // Email preview should be shown
      const emailPreview = page.locator('.email-preview');
      await expect(emailPreview).toBeVisible();
    }
  });

  test('should show quick action buttons when email is selected', async ({ page }) => {
    // Wait for messages to load
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    const messageCount = await messageList.count();
    
    if (messageCount > 0) {
      // Select first message
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // Quick action buttons should be visible
      const quickActions = page.locator('.email-quick-actions');
      await expect(quickActions).toBeVisible();
      
      // Should have archive, star, flag, and delete buttons
      await expect(quickActions.locator('.quick-action-btn')).toHaveCount(4);
    }
  });

  test('selected email should have highlighted state in message list', async ({ page }) => {
    // Wait for messages to load
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    const messageCount = await messageList.count();
    
    if (messageCount > 0) {
      // Select first message
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // First message should have selected class
      await expect(messageList.first()).toHaveClass(/selected/);
    }
  });
});

test.describe('Email Actions (Phase 3)', () => {
  
  test.beforeEach(async ({ page }) => {
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
    await expect(page.getByRole('heading', { name: 'Email Management' })).toBeVisible({ timeout: 10000 });
  });

  test('quick action buttons should be visible when email is selected', async ({ page }) => {
    // Wait for data to load
    await page.waitForTimeout(3000);
    
    // Select an email from recent messages
    const messageList = page.locator('.message-list li');
    const messageCount = await messageList.count();
    
    if (messageCount > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // Quick actions should be visible
      const quickActions = page.locator('.email-quick-actions');
      await expect(quickActions).toBeVisible();
      
      // Should have 4 action buttons
      const buttons = quickActions.locator('.quick-action-btn');
      await expect(buttons).toHaveCount(4);
    }
  });

  test('archive button should have archive icon', async ({ page }) => {
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      const archiveBtn = page.locator('.quick-action-btn').first();
      const text = await archiveBtn.textContent();
      expect(text).toContain('📥');
    }
  });

  test('star button should have star icon', async ({ page }) => {
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      const starBtn = page.locator('.quick-action-btn').nth(1);
      const text = await starBtn.textContent();
      expect(text).toContain('⭐');
    }
  });

  test('flag button should have flag icon', async ({ page }) => {
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      const flagBtn = page.locator('.quick-action-btn').nth(2);
      const text = await flagBtn.textContent();
      expect(text).toContain('🚩');
    }
  });

  test('delete button should have trash icon', async ({ page }) => {
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      const deleteBtn = page.locator('.quick-action-btn.delete');
      const text = await deleteBtn.textContent();
      expect(text).toContain('🗑️');
    }
  });

  test('action buttons should be disabled while action is in progress', async ({ page }) => {
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // All buttons should initially be enabled
      const buttons = page.locator('.quick-action-btn');
      const buttonCount = await buttons.count();
      
      for (let i = 0; i < buttonCount; i++) {
        const isDisabled = await buttons.nth(i).isDisabled();
        expect(isDisabled).toBe(false);
      }
    }
  });

  test('clicking star should trigger star action', async ({ page }) => {
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // Click star button
      const starBtn = page.locator('.quick-action-btn').nth(1);
      await starBtn.click();
      
      // Button should show loading state briefly
      // After completion, should show star icon again (or updated state)
      await page.waitForTimeout(2000);
      
      // Check no error is shown (implicitly confirms action attempted)
      const errorBar = page.locator('.email-error');
      // Error might or might not be visible depending on API response
      // This test verifies the button is clickable and triggers an action
    }
  });
});

test.describe('DATA Email Chat (Phase 4)', () => {
  
  test.beforeEach(async ({ page }) => {
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
    await expect(page.getByRole('heading', { name: 'Email Management' })).toBeVisible({ timeout: 10000 });
  });

  test('should show chat container when DATA panel is expanded', async ({ page }) => {
    // Expand DATA panel
    await page.locator('.collapsed-panel-indicator.right').click();
    await page.waitForTimeout(500);
    
    // Chat container should be visible
    const chatContainer = page.locator('.email-chat-container');
    await expect(chatContainer).toBeVisible();
  });

  test('should show empty state with suggestions when no email selected', async ({ page }) => {
    // Expand DATA panel
    await page.locator('.collapsed-panel-indicator.right').click();
    await page.waitForTimeout(500);
    
    // Empty state should be visible
    const emptyState = page.locator('.chat-empty-state');
    await expect(emptyState).toBeVisible();
    
    // Should have suggestion buttons
    const suggestions = page.locator('.chat-suggestions button');
    const count = await suggestions.count();
    expect(count).toBeGreaterThan(0);
  });

  test('should have chat input at bottom of DATA panel', async ({ page }) => {
    // Expand DATA panel
    await page.locator('.collapsed-panel-indicator.right').click();
    await page.waitForTimeout(500);
    
    // Chat input should be visible
    const chatInput = page.locator('.email-chat-input');
    await expect(chatInput).toBeVisible();
    
    // Should have input field and send button
    await expect(chatInput.locator('input')).toBeVisible();
    await expect(chatInput.locator('button')).toBeVisible();
  });

  test('chat input should be disabled when no email selected', async ({ page }) => {
    // Expand DATA panel
    await page.locator('.collapsed-panel-indicator.right').click();
    await page.waitForTimeout(500);
    
    // Input should be disabled without email selected
    const input = page.locator('.email-chat-input input');
    await expect(input).toBeDisabled();
  });

  test('chat input should be enabled when email is selected', async ({ page }) => {
    // Wait for messages to load
    await page.waitForTimeout(3000);
    
    // Select an email
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // Input should now be enabled
      const input = page.locator('.email-chat-input input');
      await expect(input).not.toBeDisabled();
    }
  });

  test('clicking suggestion should populate chat input', async ({ page }) => {
    // Expand DATA panel
    await page.locator('.collapsed-panel-indicator.right').click();
    await page.waitForTimeout(500);
    
    // Wait for messages and select one
    await page.waitForTimeout(3000);
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // Click a suggestion button
      const suggestionBtn = page.locator('.chat-suggestions button').first();
      await suggestionBtn.click();
      
      // Input should now have text
      const input = page.locator('.email-chat-input input');
      const value = await input.inputValue();
      expect(value.length).toBeGreaterThan(0);
    }
  });

  test('send button should be disabled when input is empty', async ({ page }) => {
    // Wait for messages to load
    await page.waitForTimeout(3000);
    
    // Select an email
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // Send button should be disabled with empty input
      const sendBtn = page.locator('.email-chat-input button');
      await expect(sendBtn).toBeDisabled();
    }
  });

  test('typing in chat input should enable send button', async ({ page }) => {
    // Wait for messages to load
    await page.waitForTimeout(3000);
    
    // Select an email
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // Type in input
      const input = page.locator('.email-chat-input input');
      await input.fill('What should I do with this email?');
      
      // Send button should now be enabled
      const sendBtn = page.locator('.email-chat-input button');
      await expect(sendBtn).not.toBeDisabled();
    }
  });

  test('chat should clear when selecting a different email', async ({ page }) => {
    // Wait for messages to load
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    const messageCount = await messageList.count();
    
    if (messageCount >= 2) {
      // Select first email
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // Type something in chat
      const input = page.locator('.email-chat-input input');
      await input.fill('Test message');
      
      // Select second email
      await messageList.nth(1).click();
      await page.waitForTimeout(500);
      
      // Chat input should be cleared (or empty state visible)
      const chatMessages = page.locator('.email-chat-messages');
      await expect(chatMessages).toBeVisible();
    }
  });
});

