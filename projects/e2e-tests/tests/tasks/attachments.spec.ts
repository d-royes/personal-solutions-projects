import { test, expect } from '@playwright/test';

/**
 * Task Attachments E2E Tests
 *
 * Tests for the attachments gallery feature including:
 * - API endpoints (list, detail, chat with attachments)
 * - UI components (gallery, thumbnails, selection, preview)
 * - Integration (chat with images via Vision, chat with PDFs via text extraction)
 *
 * Test Task: 1924683243917188 (DATA - Task Attachments)
 * Test Image: 408031116431236 (Screenshot 2025-12-07 134419.png)
 * Test PDF: 4750884418391940 (Release for Pump Outs .pdf)
 */

const TEST_TASK_ID = '1924683243917188';
const TEST_IMAGE_ID = '408031116431236';
const TEST_PDF_ID = '4750884418391940';
const API_BASE = 'http://localhost:8000';

test.describe('Attachments API', () => {

  test('should list attachments for a task', async ({ request }) => {
    const response = await request.get(`${API_BASE}/assist/${TEST_TASK_ID}/attachments?source=personal`, {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com'
      }
    });

    expect(response.ok()).toBeTruthy();
    const data = await response.json();

    // Should return object with taskId and attachments array
    expect(data).toHaveProperty('taskId', TEST_TASK_ID);
    expect(data).toHaveProperty('attachments');
    expect(Array.isArray(data.attachments)).toBeTruthy();
    expect(data.attachments.length).toBeGreaterThan(0);

    // Each attachment should have required fields
    const attachment = data.attachments[0];
    expect(attachment).toHaveProperty('attachmentId');
    expect(attachment).toHaveProperty('name');
    expect(attachment).toHaveProperty('mimeType');
    expect(attachment).toHaveProperty('downloadUrl');
    expect(attachment).toHaveProperty('isImage');
    expect(attachment).toHaveProperty('isPdf');
  });

  test('should get attachment detail with download URL', async ({ request }) => {
    const response = await request.get(`${API_BASE}/assist/${TEST_TASK_ID}/attachment/${TEST_IMAGE_ID}?source=personal`, {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com'
      }
    });

    expect(response.ok()).toBeTruthy();
    const data = await response.json();

    // Should have full attachment details
    expect(data).toHaveProperty('attachmentId', TEST_IMAGE_ID);
    expect(data).toHaveProperty('name');
    expect(data).toHaveProperty('mimeType');
    expect(data).toHaveProperty('downloadUrl');
    expect(data.downloadUrl).toContain('https://');
  });

  test('should include image in chat context via Vision', async ({ request }) => {
    const response = await request.post(`${API_BASE}/assist/${TEST_TASK_ID}/chat?source=personal`, {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com',
        'Content-Type': 'application/json'
      },
      data: {
        message: 'Please describe what you see in the attached image.',
        selected_attachments: [TEST_IMAGE_ID]
      }
    });

    expect(response.ok()).toBeTruthy();
    const data = await response.json();

    // Should return a response that references the image content
    expect(data).toHaveProperty('response');
    expect(data.response.length).toBeGreaterThan(50);
    // The response should indicate DATA analyzed the image
    // (Not checking specific content as it varies)
  });

  test('should include PDF text in chat context', async ({ request }) => {
    // PDF extraction + LLM processing takes longer
    test.setTimeout(60000);

    const response = await request.post(`${API_BASE}/assist/${TEST_TASK_ID}/chat?source=personal`, {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com',
        'Content-Type': 'application/json'
      },
      data: {
        message: 'What are the key points in this PDF document?',
        selected_attachments: [TEST_PDF_ID]
      }
    });

    expect(response.ok()).toBeTruthy();
    const data = await response.json();

    // Should return a response analyzing the PDF content
    expect(data).toHaveProperty('response');
    expect(data.response.length).toBeGreaterThan(50);
  });

  test('should handle chat with both image and PDF attachments', async ({ request }) => {
    // Multi-attachment processing takes longer
    test.setTimeout(90000);

    const response = await request.post(`${API_BASE}/assist/${TEST_TASK_ID}/chat?source=personal`, {
      headers: {
        'X-User-Email': 'david.a.royes@gmail.com',
        'Content-Type': 'application/json'
      },
      data: {
        message: 'Please summarize both attachments.',
        selected_attachments: [TEST_IMAGE_ID, TEST_PDF_ID]
      }
    });

    expect(response.ok()).toBeTruthy();
    const data = await response.json();

    expect(data).toHaveProperty('response');
    expect(data.response.length).toBeGreaterThan(50);
  });
});

test.describe('Attachments Gallery UI', () => {

  test.beforeEach(async ({ page }) => {
    // Set dev auth header for API requests
    await page.setExtraHTTPHeaders({
      'X-User-Email': 'david.a.royes@gmail.com'
    });

    // Navigate to set up localStorage first
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

    // Reload to pick up the auth state
    await page.reload();

    // Wait for task list to load
    await expect(page.locator('.task-list')).toBeVisible({ timeout: 10000 });

    // Find and click the test task (DATA - Task Attachments)
    const taskItem = page.locator('li.task-item').filter({ hasText: 'Task Attachments' });
    await expect(taskItem.first()).toBeVisible({ timeout: 5000 });
    await taskItem.first().click();

    // Click "Engage DATA" to load the full assistant panel
    const engageButton = page.getByRole('button', { name: /Engage DATA/i });
    await expect(engageButton).toBeVisible({ timeout: 5000 });
    await engageButton.click();

    // Wait for assistant panel and attachments to load
    await expect(page.locator('.planning-zone')).toBeVisible({ timeout: 15000 });
    // Wait extra time for attachments to load
    await page.waitForTimeout(2000);
  });

  test('should display attachments gallery with correct count', async ({ page }) => {
    // The attachments gallery should be visible
    const gallery = page.locator('.attachments-gallery');
    await expect(gallery).toBeVisible({ timeout: 10000 });

    // Header should show attachment count
    const header = gallery.locator('.attachments-header');
    await expect(header).toBeVisible();
    await expect(header).toContainText('Attachments');
    await expect(header).toContainText(/\(\d+\)/); // Should show count like "(3)"
  });

  test('should display thumbnails for each attachment', async ({ page }) => {
    const gallery = page.locator('.attachments-gallery');
    await expect(gallery).toBeVisible({ timeout: 10000 });

    // Thumbnails container should have items
    const thumbnails = gallery.locator('.attachments-thumbnails');
    await expect(thumbnails).toBeVisible();

    // Should have at least one thumbnail
    const thumbItems = thumbnails.locator('.attachment-thumb');
    await expect(thumbItems.first()).toBeVisible();

    // Each thumbnail should have filename
    const firstThumb = thumbItems.first();
    const filename = firstThumb.locator('.attachment-filename');
    await expect(filename).toBeVisible();
  });

  test('should show checkbox on each thumbnail', async ({ page }) => {
    const gallery = page.locator('.attachments-gallery');
    await expect(gallery).toBeVisible({ timeout: 10000 });

    const thumbItems = gallery.locator('.attachment-thumb');
    const firstThumb = thumbItems.first();

    // Checkbox should be visible
    const checkbox = firstThumb.locator('.attachment-checkbox');
    await expect(checkbox).toBeVisible();
  });

  test('should toggle selection when checkbox is clicked', async ({ page }) => {
    const gallery = page.locator('.attachments-gallery');
    await expect(gallery).toBeVisible({ timeout: 10000 });

    const thumbItems = gallery.locator('.attachment-thumb');
    const firstThumb = thumbItems.first();
    const checkbox = firstThumb.locator('.attachment-checkbox');

    // Initially unchecked
    await expect(checkbox).not.toBeChecked();
    await expect(firstThumb).not.toHaveClass(/selected/);

    // Click to select
    await checkbox.click();

    // Should now be selected
    await expect(checkbox).toBeChecked();
    await expect(firstThumb).toHaveClass(/selected/);

    // Click again to deselect
    await checkbox.click();

    // Should be deselected
    await expect(checkbox).not.toBeChecked();
    await expect(firstThumb).not.toHaveClass(/selected/);
  });

  test('should show selection count when items are selected', async ({ page }) => {
    const gallery = page.locator('.attachments-gallery');
    await expect(gallery).toBeVisible({ timeout: 10000 });

    const thumbItems = gallery.locator('.attachment-thumb');
    const firstThumb = thumbItems.first();
    const checkbox = firstThumb.locator('.attachment-checkbox');

    // Select an item
    await checkbox.click();

    // Header should show selection count
    const header = gallery.locator('.attachments-header');
    const selectedCount = header.locator('.attachments-selected-count');
    await expect(selectedCount).toBeVisible();
    await expect(selectedCount).toContainText(/1 selected/);
  });

  test('should show hover preview for images', async ({ page }) => {
    const gallery = page.locator('.attachments-gallery');
    await expect(gallery).toBeVisible({ timeout: 10000 });

    // Find an image thumbnail (has attachment-thumb-image class)
    const imageThumbs = gallery.locator('.attachment-thumb').filter({
      has: page.locator('.attachment-thumb-image')
    });

    // Skip if no images in attachments
    const count = await imageThumbs.count();
    if (count === 0) {
      test.skip();
      return;
    }

    const firstImage = imageThumbs.first();

    // Hover over the thumbnail
    await firstImage.hover();

    // Preview should appear
    const preview = page.locator('.attachment-preview');
    await expect(preview).toBeVisible({ timeout: 3000 });

    // Preview should contain an image
    const previewImage = preview.locator('.attachment-preview-image');
    await expect(previewImage).toBeVisible();

    // Move mouse away
    await page.mouse.move(0, 0);

    // Preview should disappear
    await expect(preview).not.toBeVisible({ timeout: 3000 });
  });

  test('should show PDF icon for PDF attachments', async ({ page }) => {
    const gallery = page.locator('.attachments-gallery');
    await expect(gallery).toBeVisible({ timeout: 10000 });

    // Find a PDF thumbnail
    const pdfThumbs = gallery.locator('.attachment-thumb').filter({
      has: page.locator('.attachment-thumb-pdf')
    });

    // Skip if no PDFs in attachments
    const count = await pdfThumbs.count();
    if (count === 0) {
      test.skip();
      return;
    }

    const firstPdf = pdfThumbs.first();

    // Should show PDF icon and label
    const pdfIcon = firstPdf.locator('.pdf-icon');
    await expect(pdfIcon).toBeVisible();

    const pdfLabel = firstPdf.locator('.pdf-label');
    await expect(pdfLabel).toBeVisible();
    await expect(pdfLabel).toHaveText('PDF');
  });

  test('should collapse and expand gallery', async ({ page }) => {
    const gallery = page.locator('.attachments-gallery');
    await expect(gallery).toBeVisible({ timeout: 10000 });

    const header = gallery.locator('.attachments-header');
    const thumbnails = gallery.locator('.attachments-thumbnails');

    // Initially expanded
    await expect(thumbnails).toBeVisible();

    // Check toggle shows expanded state
    const toggle = header.locator('.attachments-toggle');
    await expect(toggle).toHaveText('▼');

    // Click header to collapse
    await header.click();

    // Thumbnails should be hidden
    await expect(thumbnails).not.toBeVisible();

    // Toggle should show collapsed state
    await expect(toggle).toHaveText('▶');

    // Click header to expand again
    await header.click();

    // Thumbnails should be visible again
    await expect(thumbnails).toBeVisible();
    await expect(toggle).toHaveText('▼');
  });
});

test.describe('Attachments Integration with Chat', () => {

  test.beforeEach(async ({ page }) => {
    // Set dev auth header for API requests
    await page.setExtraHTTPHeaders({
      'X-User-Email': 'david.a.royes@gmail.com'
    });

    // Navigate to set up localStorage first
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

    // Reload to pick up the auth state
    await page.reload();

    // Wait for task list to load
    await expect(page.locator('.task-list')).toBeVisible({ timeout: 10000 });

    // Find and click the test task
    const taskItem = page.locator('li.task-item').filter({ hasText: 'Task Attachments' });
    await expect(taskItem.first()).toBeVisible({ timeout: 5000 });
    await taskItem.first().click();

    // Click "Engage DATA" to load the full assistant panel
    const engageButton = page.getByRole('button', { name: /Engage DATA/i });
    await expect(engageButton).toBeVisible({ timeout: 5000 });
    await engageButton.click();

    // Wait for assistant panel and attachments to load
    await expect(page.locator('.planning-zone')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('.attachments-gallery')).toBeVisible({ timeout: 15000 });
  });

  test('should send selected attachments with chat message', async ({ page }) => {
    // Chat with attachments takes longer due to LLM processing
    test.setTimeout(90000);

    const gallery = page.locator('.attachments-gallery');

    // Select the first attachment
    const thumbItems = gallery.locator('.attachment-thumb');
    const firstThumb = thumbItems.first();
    const checkbox = firstThumb.locator('.attachment-checkbox');
    await checkbox.click();

    // Verify selection
    await expect(firstThumb).toHaveClass(/selected/);

    // Send a message asking about the attachment
    const chatInput = page.locator('.chat-input-bottom textarea');
    await chatInput.fill('What can you tell me about the selected attachment?');

    const sendButton = page.locator('.chat-input-bottom .send-btn');
    await sendButton.click();

    // Wait for response
    const assistantMessage = page.locator('.chat-bubble.assistant');
    await expect(assistantMessage.first()).toBeVisible({ timeout: 60000 });

    // Response should exist (content varies based on attachment type)
    const responseText = await assistantMessage.first().textContent();
    expect(responseText).toBeTruthy();
    expect(responseText!.length).toBeGreaterThan(20);
  });

  test('should analyze image attachment with Vision', async ({ page }) => {
    // Vision analysis takes longer
    test.setTimeout(90000);

    const gallery = page.locator('.attachments-gallery');

    // Find and select an image attachment
    const imageThumbs = gallery.locator('.attachment-thumb').filter({
      has: page.locator('.attachment-thumb-image')
    });

    const count = await imageThumbs.count();
    if (count === 0) {
      test.skip();
      return;
    }

    const imageThumb = imageThumbs.first();
    const checkbox = imageThumb.locator('.attachment-checkbox');
    await checkbox.click();

    // Send a message specifically about the image
    const chatInput = page.locator('.chat-input-bottom textarea');
    await chatInput.fill('Please describe what you see in this image.');

    const sendButton = page.locator('.chat-input-bottom .send-btn');
    await sendButton.click();

    // Wait for response
    const assistantMessage = page.locator('.chat-bubble.assistant');
    await expect(assistantMessage.first()).toBeVisible({ timeout: 60000 });

    // Response should describe visual content
    const responseText = await assistantMessage.first().textContent();
    expect(responseText).toBeTruthy();
    expect(responseText!.length).toBeGreaterThan(50);
  });

  test('should analyze PDF attachment with text extraction', async ({ page }) => {
    // PDF extraction + LLM takes longer
    test.setTimeout(90000);

    const gallery = page.locator('.attachments-gallery');

    // Find and select a PDF attachment
    const pdfThumbs = gallery.locator('.attachment-thumb').filter({
      has: page.locator('.attachment-thumb-pdf')
    });

    const count = await pdfThumbs.count();
    if (count === 0) {
      test.skip();
      return;
    }

    const pdfThumb = pdfThumbs.first();
    const checkbox = pdfThumb.locator('.attachment-checkbox');
    await checkbox.click();

    // Send a message specifically about the PDF
    const chatInput = page.locator('.chat-input-bottom textarea');
    await chatInput.fill('What are the main points in this PDF document?');

    const sendButton = page.locator('.chat-input-bottom .send-btn');
    await sendButton.click();

    // Wait for response
    const assistantMessage = page.locator('.chat-bubble.assistant');
    await expect(assistantMessage.first()).toBeVisible({ timeout: 60000 });

    // Response should reference PDF content
    const responseText = await assistantMessage.first().textContent();
    expect(responseText).toBeTruthy();
    expect(responseText!.length).toBeGreaterThan(50);
  });

  test('should handle multiple selected attachments', async ({ page }) => {
    // Multi-attachment processing takes even longer
    test.setTimeout(120000);

    const gallery = page.locator('.attachments-gallery');

    // Select multiple attachments
    const thumbItems = gallery.locator('.attachment-thumb');
    const thumbCount = await thumbItems.count();

    if (thumbCount < 2) {
      test.skip();
      return;
    }

    // Select first two attachments
    await thumbItems.nth(0).locator('.attachment-checkbox').click();
    await thumbItems.nth(1).locator('.attachment-checkbox').click();

    // Verify selection count
    const selectedCount = gallery.locator('.attachments-selected-count');
    await expect(selectedCount).toContainText(/2 selected/);

    // Send a message about both
    const chatInput = page.locator('.chat-input-bottom textarea');
    await chatInput.fill('Please summarize both of the selected attachments.');

    const sendButton = page.locator('.chat-input-bottom .send-btn');
    await sendButton.click();

    // Wait for response
    const assistantMessage = page.locator('.chat-bubble.assistant');
    await expect(assistantMessage.first()).toBeVisible({ timeout: 90000 });

    // Response should exist
    const responseText = await assistantMessage.first().textContent();
    expect(responseText).toBeTruthy();
  });
});
