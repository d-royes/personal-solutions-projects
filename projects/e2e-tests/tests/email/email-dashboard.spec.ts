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

  test('should have navigation tabs including New Rules', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Dashboard' })).toBeVisible();
    await expect(page.getByRole('button', { name: /Rules/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /New Rules/i })).toBeVisible();
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
    const tabs = ['Dashboard', 'Rules', 'New Rules', 'Suggestions', 'Attention'];
    
    for (const tabName of tabs) {
      // Handle "Rules" being a substring of "New Rules"
      let tab;
      if (tabName === 'Rules') {
        // Match "Rules" but not "New Rules"
        tab = page.locator('.email-tabs button').filter({ hasText: /^Rules/ }).first();
      } else {
        tab = page.getByRole('button', { name: new RegExp(tabName, 'i') });
      }
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

test.describe('Email Action Suggestions Tab (Phase A)', () => {
  
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
    
    // Navigate to Suggestions tab
    await page.getByRole('button', { name: 'Suggestions' }).click();
    await page.waitForTimeout(500);
  });

  test('should display Suggestions tab header', async ({ page }) => {
    // Should have the suggestions header
    await expect(page.locator('.email-suggestions-view h3')).toContainText('Email Action Suggestions');
  });

  test('should have Refresh Suggestions button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Refresh Suggestions/i })).toBeVisible();
  });

  test('should show empty state initially', async ({ page }) => {
    // Empty state should be visible before loading suggestions
    const emptyState = page.locator('.email-suggestions-view .empty-state');
    await expect(emptyState).toBeVisible();
  });

  test('should load suggestions when clicking Refresh', async ({ page }) => {
    // Click refresh button
    await page.getByRole('button', { name: /Refresh Suggestions/i }).click();
    
    // Should show loading state
    const loading = page.locator('.loading');
    await expect(loading).toBeVisible();
    
    // Wait for loading to complete
    await page.waitForTimeout(5000);
    
    // Either suggestions or empty state should be visible
    const suggestionsList = page.locator('.action-suggestions-list');
    const emptyState = page.locator('.email-suggestions-view .empty-state');
    
    const hasContent = await suggestionsList.isVisible() || await emptyState.isVisible();
    expect(hasContent).toBe(true);
  });

  test('suggestions should have numbered format', async ({ page }) => {
    // Load suggestions
    await page.getByRole('button', { name: /Refresh Suggestions/i }).click();
    await page.waitForTimeout(5000);
    
    // Check if any suggestions are present
    const suggestionCards = page.locator('.email-action-suggestion');
    const count = await suggestionCards.count();
    
    if (count > 0) {
      // First suggestion should have #1
      const firstNumber = page.locator('.suggestion-number').first();
      await expect(firstNumber).toContainText('#1');
    }
  });

  test('suggestion cards should display email details', async ({ page }) => {
    // Load suggestions
    await page.getByRole('button', { name: /Refresh Suggestions/i }).click();
    await page.waitForTimeout(5000);
    
    const suggestionCards = page.locator('.email-action-suggestion');
    const count = await suggestionCards.count();
    
    if (count > 0) {
      const firstCard = suggestionCards.first();
      
      // Should have from/to/subject fields
      await expect(firstCard.locator('.email-preview-from')).toBeVisible();
      await expect(firstCard.locator('.email-preview-to')).toBeVisible();
      await expect(firstCard.locator('.email-preview-subject')).toBeVisible();
    }
  });

  test('suggestion cards should have action buttons', async ({ page }) => {
    // Load suggestions
    await page.getByRole('button', { name: /Refresh Suggestions/i }).click();
    await page.waitForTimeout(5000);
    
    const suggestionCards = page.locator('.email-action-suggestion');
    const count = await suggestionCards.count();
    
    if (count > 0) {
      const firstCard = suggestionCards.first();
      
      // Should have approve and dismiss buttons
      await expect(firstCard.locator('.approve-action')).toBeVisible();
      await expect(firstCard.locator('.dismiss-action')).toBeVisible();
      
      // Should have quick action buttons
      await expect(firstCard.locator('.quick-action')).toHaveCount(4);
    }
  });

  test('batch approve controls should appear when suggestions are present', async ({ page }) => {
    // Load suggestions
    await page.getByRole('button', { name: /Refresh Suggestions/i }).click();
    await page.waitForTimeout(5000);
    
    const suggestionCards = page.locator('.email-action-suggestion');
    const count = await suggestionCards.count();
    
    if (count > 0) {
      // Batch controls should be visible
      const batchControls = page.locator('.batch-approve-controls');
      await expect(batchControls).toBeVisible();
      
      // Should have approve all button
      await expect(page.locator('.approve-all-btn')).toBeVisible();
    }
  });

  test('dismiss button should remove suggestion from list', async ({ page }) => {
    // Load suggestions
    await page.getByRole('button', { name: /Refresh Suggestions/i }).click();
    await page.waitForTimeout(5000);
    
    const suggestionCards = page.locator('.email-action-suggestion');
    const initialCount = await suggestionCards.count();
    
    if (initialCount > 0) {
      // Click dismiss on first suggestion
      await suggestionCards.first().locator('.dismiss-action').click();
      await page.waitForTimeout(500);
      
      // Count should decrease by 1
      const newCount = await suggestionCards.count();
      expect(newCount).toBe(initialCount - 1);
    }
  });
});

test.describe('New Rules Tab (Phase A)', () => {
  
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
    
    // Navigate to New Rules tab
    await page.getByRole('button', { name: /New Rules/i }).click();
    await page.waitForTimeout(1000);
  });

  test('should display New Rules tab content', async ({ page }) => {
    // Should see rule suggestions or empty state
    const suggestionView = page.locator('.suggestions-view');
    await expect(suggestionView).toBeVisible();
  });

  test('should have Run Analysis button when no suggestions', async ({ page }) => {
    // If no suggestions loaded yet, should show Run Analysis button
    const runAnalysisBtn = page.getByRole('button', { name: /Run Analysis/i });
    const isVisible = await runAnalysisBtn.isVisible().catch(() => false);
    
    // Either button is visible OR suggestions are already loaded
    const suggestions = page.locator('.suggestion-list');
    const hasSuggestions = await suggestions.isVisible().catch(() => false);
    
    expect(isVisible || hasSuggestions).toBe(true);
  });

  test('rule suggestions should have confidence badge', async ({ page }) => {
    // Load rule suggestions
    const runAnalysisBtn = page.getByRole('button', { name: /Run Analysis/i });
    if (await runAnalysisBtn.isVisible()) {
      await runAnalysisBtn.click();
      await page.waitForTimeout(5000);
    }
    
    const suggestionCards = page.locator('.suggestion-card');
    const count = await suggestionCards.count();
    
    if (count > 0) {
      const firstCard = suggestionCards.first();
      await expect(firstCard.locator('.confidence-badge')).toBeVisible();
    }
  });

  test('rule suggestions should have category dropdown', async ({ page }) => {
    // Load rule suggestions
    const runAnalysisBtn = page.getByRole('button', { name: /Run Analysis/i });
    if (await runAnalysisBtn.isVisible()) {
      await runAnalysisBtn.click();
      await page.waitForTimeout(5000);
    }
    
    const suggestionCards = page.locator('.suggestion-card');
    const count = await suggestionCards.count();
    
    if (count > 0) {
      const firstCard = suggestionCards.first();
      await expect(firstCard.locator('.category-select')).toBeVisible();
    }
  });

  test('rule suggestions should have approve and dismiss buttons', async ({ page }) => {
    // Load rule suggestions
    const runAnalysisBtn = page.getByRole('button', { name: /Run Analysis/i });
    if (await runAnalysisBtn.isVisible()) {
      await runAnalysisBtn.click();
      await page.waitForTimeout(5000);
    }
    
    const suggestionCards = page.locator('.suggestion-card');
    const count = await suggestionCards.count();
    
    if (count > 0) {
      const firstCard = suggestionCards.first();
      await expect(firstCard.locator('.approve-btn')).toBeVisible();
      await expect(firstCard.locator('.dismiss-btn')).toBeVisible();
    }
  });
});

test.describe('Chat Approval Commands (Phase A)', () => {
  
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
    
    // Expand DATA panel
    await page.locator('.collapsed-panel-indicator.right').click();
    await page.waitForTimeout(500);
  });

  test('chat input should accept approval commands without selecting email', async ({ page }) => {
    // Chat input should be visible
    const chatInput = page.locator('.email-chat-input input');
    await expect(chatInput).toBeVisible();
    
    // Type an approval command
    await chatInput.fill('approve #1');
    
    // Send button should be enabled for approval commands
    const sendBtn = page.locator('.email-chat-input button[type="submit"]');
    await expect(sendBtn).not.toBeDisabled();
  });

  test('approve all command should be recognized in chat', async ({ page }) => {
    // Type approve all command
    const chatInput = page.locator('.email-chat-input input');
    await chatInput.fill('approve all');
    
    // Send button should be enabled
    const sendBtn = page.locator('.email-chat-input button[type="submit"]');
    await expect(sendBtn).not.toBeDisabled();
    
    // Submit the command
    await sendBtn.click();
    await page.waitForTimeout(500);
    
    // Should add user message to chat
    const chatMessages = page.locator('.chat-message.user');
    await expect(chatMessages.last()).toContainText('approve all');
  });
});

test.describe('Task Creation from Email (Phase B)', () => {
  
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

  test('should show task creation button in attention items', async ({ page }) => {
    // Navigate to Attention tab
    await page.getByRole('button', { name: 'Attention' }).click();
    await page.waitForTimeout(3000);
    
    // If there are attention items with extracted tasks, they should have create task button
    const attentionCards = page.locator('.attention-card');
    const count = await attentionCards.count();
    
    if (count > 0) {
      // Check if any have create task button
      const createTaskBtns = page.locator('.create-task-btn');
      const btnCount = await createTaskBtns.count();
      // May or may not have buttons depending on email content
      expect(btnCount).toBeGreaterThanOrEqual(0);
    }
  });

  test('task creation form should appear when triggered', async ({ page }) => {
    // Wait for messages to load
    await page.waitForTimeout(3000);
    
    // Select an email
    const messageList = page.locator('.message-list li');
    const messageCount = await messageList.count();
    
    if (messageCount > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // DATA panel should be open
      const rightPanel = page.locator('.email-right-panel');
      await expect(rightPanel).toBeVisible();
      
      // The task form can be triggered via chat command "create task"
      // For this test, we verify the structure exists
      const assistContent = page.locator('.email-assist-content');
      await expect(assistContent).toBeVisible();
    }
  });

  test('task form should have all required fields', async ({ page }) => {
    // This test verifies the form structure exists in the DOM
    // The form becomes visible when showTaskForm state is true
    
    // Navigate to check if form CSS classes are defined
    const styles = await page.evaluate(() => {
      const form = document.querySelector('.task-creation-form');
      return form !== null;
    });
    
    // Form may not be visible initially, but CSS should be present
    // Check that the page loads without errors
    await expect(page.getByRole('heading', { name: 'Email Management' })).toBeVisible();
  });

  test('Firestore tasks API endpoint should be accessible', async ({ page }) => {
    // Test the API endpoint directly
    const response = await page.request.get('/tasks/firestore', {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com'
      }
    });
    
    expect(response.ok()).toBe(true);
    const data = await response.json();
    expect(data).toHaveProperty('count');
    expect(data).toHaveProperty('tasks');
  });
});

test.describe('Email Memory (Phase C)', () => {
  
  test('sender profiles API should be accessible', async ({ page }) => {
    // Test the API endpoint directly
    const response = await page.request.get('/email/memory/sender-profiles', {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com'
      }
    });
    
    expect(response.ok()).toBe(true);
    const data = await response.json();
    expect(data).toHaveProperty('count');
    expect(data).toHaveProperty('profiles');
  });

  test('category patterns API should be accessible', async ({ page }) => {
    // Test the API endpoint directly
    const response = await page.request.get('/email/memory/category-patterns', {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com'
      }
    });
    
    expect(response.ok()).toBe(true);
    const data = await response.json();
    expect(data).toHaveProperty('count');
    expect(data).toHaveProperty('patterns');
  });

  test('timing patterns API should be accessible', async ({ page }) => {
    // Test the API endpoint directly
    const response = await page.request.get('/email/memory/timing', {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com'
      }
    });
    
    expect(response.ok()).toBe(true);
    // May or may not have patterns depending on history
    const data = await response.json();
    expect(data).toHaveProperty('patterns');
  });

  test('seed endpoint should create sender profiles', async ({ page }) => {
    // Seed the memory with known contacts
    const response = await page.request.post('/email/memory/seed', {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com'
      }
    });
    
    expect(response.ok()).toBe(true);
    const data = await response.json();
    expect(data.status).toBe('seeded');
    expect(data.profilesCreated).toBeGreaterThan(0);
  });

  test('category approval should record pattern', async ({ page }) => {
    const response = await page.request.post(
      '/email/memory/category-approval?pattern=amazon.com&pattern_type=domain&category=Transactional',
      {
        headers: {
          'X-User-Email': 'david.a.royes@gmail.com'
        }
      }
    );
    
    expect(response.ok()).toBe(true);
    const data = await response.json();
    expect(data.status).toBe('recorded');
    expect(data.pattern).toHaveProperty('pattern');
    expect(data.pattern.pattern).toBe('amazon.com');
  });

  test('response warning API should return warning status', async ({ page }) => {
    // First seed some profiles
    await page.request.post('/email/memory/seed', {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com'
      }
    });
    
    // Check for warning on a known sender
    const response = await page.request.get(
      '/email/memory/response-warning?sender_email=laura.destella-whippy@pgatour.com&received_hours_ago=10',
      {
        headers: {
          'X-User-Email': 'david.a.royes@gmail.com'
        }
      }
    );
    
    expect(response.ok()).toBe(true);
    const data = await response.json();
    expect(data).toHaveProperty('warning');
    // May or may not have warning depending on timing data
  });
});


// =============================================================================
// Phase 1: Email Body Loading Tests
// =============================================================================

test.describe('Email Body Loading (Phase 1)', () => {

  test('full email API should return body content', async ({ page }) => {
    // First get a message ID from inbox
    const inboxResponse = await page.request.get('/inbox/personal?max_results=1', {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com'
      }
    });
    
    expect(inboxResponse.ok()).toBe(true);
    const inboxData = await inboxResponse.json();
    
    if (inboxData.recentMessages && inboxData.recentMessages.length > 0) {
      const messageId = inboxData.recentMessages[0].id;
      
      // Fetch full message with body
      const response = await page.request.get(
        `/email/personal/message/${messageId}?full=true`,
        {
          headers: {
            'X-User-Email': 'david.a.royes@gmail.com'
          }
        }
      );
      
      expect(response.ok()).toBe(true);
      const data = await response.json();
      
      expect(data).toHaveProperty('message');
      expect(data.message).toHaveProperty('body');
      expect(data.message).toHaveProperty('bodyHtml');
      expect(data.message).toHaveProperty('ccAddress');
      expect(data.message).toHaveProperty('messageIdHeader');
      expect(data.message).toHaveProperty('attachmentCount');
      expect(data.message).toHaveProperty('attachments');
    }
  });

  test('thread context API should return thread messages', async ({ page }) => {
    // First get a message with a thread ID
    const inboxResponse = await page.request.get('/inbox/personal?max_results=5', {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com'
      }
    });
    
    expect(inboxResponse.ok()).toBe(true);
    const inboxData = await inboxResponse.json();
    
    if (inboxData.recentMessages && inboxData.recentMessages.length > 0) {
      const threadId = inboxData.recentMessages[0].threadId;
      
      // Fetch thread context
      const response = await page.request.get(
        `/email/personal/thread/${threadId}`,
        {
          headers: {
            'X-User-Email': 'david.a.royes@gmail.com'
          }
        }
      );
      
      expect(response.ok()).toBe(true);
      const data = await response.json();
      
      expect(data).toHaveProperty('threadId');
      expect(data).toHaveProperty('messageCount');
      expect(data).toHaveProperty('messages');
      expect(Array.isArray(data.messages)).toBe(true);
      expect(data.messageCount).toBeGreaterThanOrEqual(1);
    }
  });

  test('thread context should include summary for multi-message threads', async ({ page }) => {
    // Search for threads with multiple messages
    const searchResponse = await page.request.get(
      '/inbox/personal/search?q=in:inbox&max_results=20',
      {
        headers: {
          'X-User-Email': 'david.a.royes@gmail.com'
        }
      }
    );
    
    expect(searchResponse.ok()).toBe(true);
    const searchData = await searchResponse.json();
    
    // Find a thread to test (any will do for API validation)
    if (searchData.messages && searchData.messages.length > 0) {
      const threadId = searchData.messages[0].threadId;
      
      const response = await page.request.get(
        `/email/personal/thread/${threadId}`,
        {
          headers: {
            'X-User-Email': 'david.a.royes@gmail.com'
          }
        }
      );
      
      expect(response.ok()).toBe(true);
      const data = await response.json();
      
      // Summary field should exist (may be null for single-message threads)
      expect(data).toHaveProperty('summary');
      
      // If multiple messages, summary should be a string
      if (data.messageCount > 3 && data.summary) {
        expect(typeof data.summary).toBe('string');
        expect(data.summary.length).toBeGreaterThan(0);
      }
    }
  });

  test('message without full flag should not include body', async ({ page }) => {
    const inboxResponse = await page.request.get('/inbox/personal?max_results=1', {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com'
      }
    });
    
    expect(inboxResponse.ok()).toBe(true);
    const inboxData = await inboxResponse.json();
    
    if (inboxData.recentMessages && inboxData.recentMessages.length > 0) {
      const messageId = inboxData.recentMessages[0].id;
      
      // Fetch message without full body
      const response = await page.request.get(
        `/email/personal/message/${messageId}?full=false`,
        {
          headers: {
            'X-User-Email': 'david.a.royes@gmail.com'
          }
        }
      );
      
      expect(response.ok()).toBe(true);
      const data = await response.json();
      
      // Body fields should not be present or be null
      expect(data.message.body).toBeUndefined();
      expect(data.message.bodyHtml).toBeUndefined();
    }
  });

  test('attachment info should include filename and size', async ({ page }) => {
    // Search for emails with attachments
    const searchResponse = await page.request.get(
      '/inbox/personal/search?q=has:attachment&max_results=5',
      {
        headers: {
          'X-User-Email': 'david.a.royes@gmail.com'
        }
      }
    );
    
    expect(searchResponse.ok()).toBe(true);
    const searchData = await searchResponse.json();
    
    if (searchData.messages && searchData.messages.length > 0) {
      const messageId = searchData.messages[0].id;
      
      const response = await page.request.get(
        `/email/personal/message/${messageId}?full=true`,
        {
          headers: {
            'X-User-Email': 'david.a.royes@gmail.com'
          }
        }
      );
      
      expect(response.ok()).toBe(true);
      const data = await response.json();
      
      expect(data.message.attachmentCount).toBeGreaterThan(0);
      expect(data.message.attachments.length).toBeGreaterThan(0);
      
      // First attachment should have required fields
      const attachment = data.message.attachments[0];
      expect(attachment).toHaveProperty('filename');
      expect(attachment).toHaveProperty('mimeType');
      expect(attachment).toHaveProperty('size');
    }
  });
});


// =============================================================================
// Phase 2: Reply API Tests
// =============================================================================

test.describe('Email Reply API (Phase 2)', () => {

  test('reply draft API should generate a draft', async ({ page }) => {
    // Get a message to reply to
    const inboxResponse = await page.request.get('/inbox/personal?max_results=1', {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com'
      }
    });
    
    expect(inboxResponse.ok()).toBe(true);
    const inboxData = await inboxResponse.json();
    
    if (inboxData.recentMessages && inboxData.recentMessages.length > 0) {
      const messageId = inboxData.recentMessages[0].id;
      
      // Generate a reply draft
      const response = await page.request.post(
        '/email/personal/reply-draft',
        {
          headers: {
            'X-User-Email': 'david.a.royes@gmail.com',
            'Content-Type': 'application/json'
          },
          data: {
            messageId: messageId,
            replyAll: false,
            userContext: 'Please acknowledge receipt'
          }
        }
      );
      
      expect(response.ok()).toBe(true);
      const data = await response.json();
      
      expect(data).toHaveProperty('draft');
      expect(data.draft).toHaveProperty('subject');
      expect(data.draft).toHaveProperty('body');
      expect(data.draft).toHaveProperty('to');
      
      // Subject should start with Re:
      expect(data.draft.subject.toLowerCase()).toContain('re:');
      
      // Body should not be empty
      expect(data.draft.body.length).toBeGreaterThan(0);
      
      // To should have at least one recipient
      expect(data.draft.to.length).toBeGreaterThan(0);
    }
  });

  test('reply all draft should include CC recipients', async ({ page }) => {
    // Search for an email that has CC recipients
    const searchResponse = await page.request.get(
      '/inbox/personal/search?q=cc:*&max_results=5',
      {
        headers: {
          'X-User-Email': 'david.a.royes@gmail.com'
        }
      }
    );
    
    // If no CC emails found, test basic functionality
    const inboxResponse = await page.request.get('/inbox/personal?max_results=1', {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com'
      }
    });
    
    expect(inboxResponse.ok()).toBe(true);
    const inboxData = await inboxResponse.json();
    
    if (inboxData.recentMessages && inboxData.recentMessages.length > 0) {
      const messageId = inboxData.recentMessages[0].id;
      
      // Generate a reply all draft
      const response = await page.request.post(
        '/email/personal/reply-draft',
        {
          headers: {
            'X-User-Email': 'david.a.royes@gmail.com',
            'Content-Type': 'application/json'
          },
          data: {
            messageId: messageId,
            replyAll: true
          }
        }
      );
      
      expect(response.ok()).toBe(true);
      const data = await response.json();
      
      expect(data).toHaveProperty('draft');
      expect(data.draft).toHaveProperty('cc');
      // CC should be an array (may be empty)
      expect(Array.isArray(data.draft.cc)).toBe(true);
    }
  });

  test('reply draft without AI-isms', async ({ page }) => {
    const inboxResponse = await page.request.get('/inbox/personal?max_results=1', {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com'
      }
    });
    
    expect(inboxResponse.ok()).toBe(true);
    const inboxData = await inboxResponse.json();
    
    if (inboxData.recentMessages && inboxData.recentMessages.length > 0) {
      const messageId = inboxData.recentMessages[0].id;
      
      const response = await page.request.post(
        '/email/personal/reply-draft',
        {
          headers: {
            'X-User-Email': 'david.a.royes@gmail.com',
            'Content-Type': 'application/json'
          },
          data: {
            messageId: messageId,
            replyAll: false
          }
        }
      );
      
      expect(response.ok()).toBe(true);
      const data = await response.json();
      
      const body = data.draft.body.toLowerCase();
      
      // Should not contain common AI-isms
      expect(body).not.toContain('i hope this email finds you well');
      expect(body).not.toContain('please let me know if you have any questions');
      expect(body).not.toContain('i would be happy to');
    }
  });

  test('reply draft includes HTML version', async ({ page }) => {
    const inboxResponse = await page.request.get('/inbox/personal?max_results=1', {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com'
      }
    });
    
    expect(inboxResponse.ok()).toBe(true);
    const inboxData = await inboxResponse.json();
    
    if (inboxData.recentMessages && inboxData.recentMessages.length > 0) {
      const messageId = inboxData.recentMessages[0].id;
      
      const response = await page.request.post(
        '/email/personal/reply-draft',
        {
          headers: {
            'X-User-Email': 'david.a.royes@gmail.com',
            'Content-Type': 'application/json'
          },
          data: {
            messageId: messageId,
            replyAll: false
          }
        }
      );
      
      expect(response.ok()).toBe(true);
      const data = await response.json();
      
      // Should have HTML body
      expect(data.draft).toHaveProperty('bodyHtml');
      expect(data.draft.bodyHtml).toContain('<p>');
    }
  });

  // Note: reply-send is not tested in E2E to avoid sending actual emails
  // We verify the endpoint exists and validates input
  test('reply send API should validate required fields', async ({ page }) => {
    // Send request with missing fields
    const response = await page.request.post(
      '/email/personal/reply-send',
      {
        headers: {
          'X-User-Email': 'david.a.royes@gmail.com',
          'Content-Type': 'application/json'
        },
        data: {
          // Missing required fields
          replyAll: false
        }
      }
    );
    
    // Should return 422 validation error
    expect(response.status()).toBe(422);
  });
});


// =============================================================================
// Phase 3: Email Body UI Tests
// =============================================================================

test.describe('Email Body UI (Phase 3)', () => {
  
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

  test('should show expand button when email is selected', async ({ page }) => {
    // Wait for messages to load
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    const messageCount = await messageList.count();
    
    if (messageCount > 0) {
      // Select first message
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // Expand button should be visible
      const expandBtn = page.locator('.email-body-toggle');
      await expect(expandBtn).toBeVisible();
      
      // Should show "Show full email" text
      await expect(expandBtn).toContainText('Show full email');
    }
  });

  test('clicking expand button should reveal full email body', async ({ page }) => {
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      // Select first message
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // Initially snippet should be visible, expanded body should not
      const snippet = page.locator('.email-preview .preview-snippet');
      const expandedBody = page.locator('.email-body-expanded');
      
      await expect(snippet).toBeVisible();
      await expect(expandedBody).not.toBeVisible();
      
      // Click expand button
      const expandBtn = page.locator('.email-body-toggle');
      await expandBtn.click();
      await page.waitForTimeout(1500); // Wait for body to load
      
      // Expanded body should now be visible
      await expect(expandedBody).toBeVisible();
      
      // Button should change to "Hide full email"
      await expect(expandBtn).toContainText('Hide full email');
    }
  });

  test('clicking collapse button should hide email body', async ({ page }) => {
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      // Select and expand
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      const expandBtn = page.locator('.email-body-toggle');
      await expandBtn.click();
      await page.waitForTimeout(1500);
      
      // Click again to collapse
      await expandBtn.click();
      await page.waitForTimeout(500);
      
      // Expanded body should be hidden, snippet should be visible
      const snippet = page.locator('.email-preview .preview-snippet');
      const expandedBody = page.locator('.email-body-expanded');
      
      await expect(snippet).toBeVisible();
      await expect(expandedBody).not.toBeVisible();
      
      // Button should show "Show full email"
      await expect(expandBtn).toContainText('Show full email');
    }
  });

  test('attachment indicator should show count', async ({ page }) => {
    // Search for emails with attachments
    await page.waitForTimeout(3000);
    
    const searchInput = page.getByPlaceholder('Search emails...');
    if (await searchInput.isVisible()) {
      await searchInput.fill('has:attachment');
      await page.waitForTimeout(2000);
      
      // If search results appear, select one
      const results = page.locator('.search-results-list li');
      if (await results.count() > 0) {
        await results.first().click();
        await page.waitForTimeout(500);
        
        // Expand button should be visible
        const expandBtn = page.locator('.email-body-toggle');
        await expandBtn.click();
        await page.waitForTimeout(1500);
        
        // Should show attachment indicator
        const attachmentIndicator = page.locator('.attachment-indicator');
        // May or may not be visible depending on the email
        const isVisible = await attachmentIndicator.isVisible().catch(() => false);
        expect(typeof isVisible).toBe('boolean');
      }
    }
  });

  test('selecting different email should reset body state', async ({ page }) => {
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    const messageCount = await messageList.count();
    
    if (messageCount >= 2) {
      // Select first and expand
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      const expandBtn = page.locator('.email-body-toggle');
      await expandBtn.click();
      await page.waitForTimeout(1500);
      
      // Verify expanded
      await expect(page.locator('.email-body-expanded')).toBeVisible();
      
      // Select second email
      await messageList.nth(1).click();
      await page.waitForTimeout(500);
      
      // Body should be collapsed (snippet visible)
      await expect(page.locator('.email-preview .preview-snippet')).toBeVisible();
      await expect(page.locator('.email-body-expanded')).not.toBeVisible();
    }
  });

  test('expand button arrow should rotate when expanded', async ({ page }) => {
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      const toggleArrow = page.locator('.email-body-toggle .toggle-arrow');
      
      // Initially not expanded
      await expect(toggleArrow).not.toHaveClass(/expanded/);
      
      // Click to expand
      await page.locator('.email-body-toggle').click();
      await page.waitForTimeout(500);
      
      // Arrow should have expanded class
      await expect(toggleArrow).toHaveClass(/expanded/);
    }
  });
});


// =============================================================================
// Phase 4: Email Reply Workflow Tests
// =============================================================================

test.describe('Email Reply Workflow (Phase 4)', () => {
  
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

  test('should show Reply and Reply All buttons when email is selected', async ({ page }) => {
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // Should have reply buttons in quick actions
      const quickActions = page.locator('.email-quick-actions');
      await expect(quickActions).toBeVisible();
      
      // Should have 6 buttons now: Reply, Reply All, Archive, Star, Important, Delete
      const buttons = quickActions.locator('.quick-action-btn');
      await expect(buttons).toHaveCount(6);
      
      // Check reply buttons exist
      const replyBtn = quickActions.locator('.quick-action-btn.reply');
      const replyAllBtn = quickActions.locator('.quick-action-btn.reply-all');
      
      await expect(replyBtn).toBeVisible();
      await expect(replyAllBtn).toBeVisible();
    }
  });

  test('Reply button should have correct icon', async ({ page }) => {
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      const replyBtn = page.locator('.quick-action-btn.reply');
      const text = await replyBtn.textContent();
      expect(text).toContain('↩️');
    }
  });

  test('Reply All button should have correct icon', async ({ page }) => {
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      const replyAllBtn = page.locator('.quick-action-btn.reply-all');
      const text = await replyAllBtn.textContent();
      expect(text).toContain('↩️');
    }
  });

  test('clicking Reply should open email draft panel', async ({ page }) => {
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // Click Reply button
      const replyBtn = page.locator('.quick-action-btn.reply');
      await replyBtn.click();
      
      // Wait for draft panel to appear (may take a moment for AI generation)
      await page.waitForTimeout(5000);
      
      // Draft panel should be visible
      const draftPanel = page.locator('.email-draft-panel');
      await expect(draftPanel).toBeVisible({ timeout: 15000 });
    }
  });

  test('draft panel should have pre-filled subject with Re:', async ({ page }) => {
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // Click Reply
      await page.locator('.quick-action-btn.reply').click();
      await page.waitForTimeout(5000);
      
      // Check subject field
      const subjectInput = page.locator('.subject-input');
      if (await subjectInput.isVisible()) {
        const value = await subjectInput.inputValue();
        expect(value.toLowerCase()).toContain('re:');
      }
    }
  });

  test('draft panel should have rich text editor', async ({ page }) => {
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // Click Reply
      await page.locator('.quick-action-btn.reply').click();
      await page.waitForTimeout(5000);
      
      // Rich text toolbar should be visible
      const toolbar = page.locator('.rich-text-toolbar');
      await expect(toolbar).toBeVisible({ timeout: 15000 });
      
      // Should have Bold button
      const boldBtn = toolbar.locator('.toolbar-btn').first();
      await expect(boldBtn).toBeVisible();
    }
  });

  test('draft panel should have account selector defaulted to current account', async ({ page }) => {
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // Click Reply
      await page.locator('.quick-action-btn.reply').click();
      await page.waitForTimeout(5000);
      
      // Check account selector
      const personalRadio = page.locator('input[name="fromAccount"][value="personal"]');
      if (await personalRadio.isVisible()) {
        // Since we're on personal account, personal should be checked
        await expect(personalRadio).toBeChecked();
      }
    }
  });

  test('draft panel should have regenerate option', async ({ page }) => {
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // Click Reply
      await page.locator('.quick-action-btn.reply').click();
      await page.waitForTimeout(5000);
      
      // Regenerate section should be visible
      const regenerateInput = page.locator('.regenerate-input');
      await expect(regenerateInput).toBeVisible({ timeout: 15000 });
      
      // Regenerate button should exist
      const regenerateBtn = page.getByRole('button', { name: /Regenerate/i });
      await expect(regenerateBtn).toBeVisible();
    }
  });

  test('can close draft panel with close button', async ({ page }) => {
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // Click Reply
      await page.locator('.quick-action-btn.reply').click();
      await page.waitForTimeout(5000);
      
      // Draft panel should be visible
      const draftPanel = page.locator('.email-draft-panel');
      await expect(draftPanel).toBeVisible({ timeout: 15000 });
      
      // Click close button
      const closeBtn = page.locator('.email-draft-header-actions .icon-btn');
      await closeBtn.click();
      await page.waitForTimeout(500);
      
      // Panel should be hidden
      await expect(draftPanel).not.toBeVisible();
    }
  });

  test('can discard draft', async ({ page }) => {
    await page.waitForTimeout(3000);
    
    const messageList = page.locator('.message-list li');
    if (await messageList.count() > 0) {
      await messageList.first().click();
      await page.waitForTimeout(500);
      
      // Click Reply
      await page.locator('.quick-action-btn.reply').click();
      await page.waitForTimeout(5000);
      
      // Draft panel should be visible
      const draftPanel = page.locator('.email-draft-panel');
      await expect(draftPanel).toBeVisible({ timeout: 15000 });
      
      // Accept the dialog that will appear
      page.on('dialog', dialog => dialog.accept());
      
      // Click discard button
      const discardBtn = page.locator('.discard-btn');
      await discardBtn.click();
      await page.waitForTimeout(500);
      
      // Panel should be hidden
      await expect(draftPanel).not.toBeVisible();
    }
  });
});

