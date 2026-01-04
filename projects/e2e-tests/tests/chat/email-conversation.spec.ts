import { test, expect } from '@playwright/test';

/**
 * Email Conversation Persistence Tests
 *
 * Tests for the email conversation persistence feature:
 * - GET /email/{account}/conversation/{thread_id} - Retrieve conversation history
 * - DELETE /email/{account}/conversation/{thread_id} - Clear conversation history
 * - POST /email/{account}/chat - Chat with DATA (persists messages)
 *
 * Conversations are persisted by thread_id with 90-day TTL.
 * Part of the Email Experience Enhancement feature (Q1 2025).
 */

const API_BASE = process.env.API_BASE || 'http://localhost:8000';
const AUTH_HEADERS = {
  'X-User-Email': 'david.a.royes@gmail.com'
};

// Test thread ID - using a fake one for API structure tests
const TEST_THREAD_ID = 'test-thread-e2e-12345';

test.describe('Conversation API - GET /email/{account}/conversation/{thread_id}', () => {

  test('conversation endpoint requires authentication', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/personal/conversation/${TEST_THREAD_ID}`);
    // Should return 401 or 403 without auth
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('conversation endpoint validates account (rejects invalid)', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/invalid/conversation/${TEST_THREAD_ID}`, {
      headers: AUTH_HEADERS
    });
    // Should return 422 for invalid account type
    expect(response.status()).toBe(422);
  });

  test('conversation endpoint returns correct structure for new thread', async ({ request }) => {
    // Use a guaranteed-new thread ID
    const newThreadId = `new-thread-${Date.now()}`;
    const response = await request.get(`${API_BASE}/email/personal/conversation/${newThreadId}`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('success', true);
    expect(data).toHaveProperty('account', 'personal');
    expect(data).toHaveProperty('threadId', newThreadId);
    expect(data).toHaveProperty('messages');
    expect(data).toHaveProperty('count');
    expect(Array.isArray(data.messages)).toBeTruthy();
    // New thread should have empty messages
    expect(data.count).toBe(0);
    expect(data.messages.length).toBe(0);
  });

  test('conversation endpoint returns metadata when available', async ({ request }) => {
    // Get any existing conversation to check metadata structure
    const response = await request.get(`${API_BASE}/email/personal/conversation/${TEST_THREAD_ID}`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    // Metadata may be null for threads without history
    expect('metadata' in data).toBeTruthy();
    // If metadata exists, check structure
    if (data.metadata) {
      expect(data.metadata).toHaveProperty('subject');
      expect(data.metadata).toHaveProperty('fromEmail');
      expect(data.metadata).toHaveProperty('fromName');
      expect(data.metadata).toHaveProperty('lastEmailDate');
      expect(data.metadata).toHaveProperty('sensitivity');
      expect(data.metadata).toHaveProperty('messageCount');
    }
  });

  test('conversation endpoint respects limit parameter', async ({ request }) => {
    const response = await request.get(
      `${API_BASE}/email/personal/conversation/${TEST_THREAD_ID}?limit=5`,
      { headers: AUTH_HEADERS }
    );
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    // Limit should be respected (messages.length <= 5)
    expect(data.messages.length).toBeLessThanOrEqual(5);
  });

  test('conversation endpoint validates limit range (1-100)', async ({ request }) => {
    // Test limit < 1
    const response1 = await request.get(
      `${API_BASE}/email/personal/conversation/${TEST_THREAD_ID}?limit=0`,
      { headers: AUTH_HEADERS }
    );
    expect(response1.status()).toBe(422);

    // Test limit > 100
    const response2 = await request.get(
      `${API_BASE}/email/personal/conversation/${TEST_THREAD_ID}?limit=101`,
      { headers: AUTH_HEADERS }
    );
    expect(response2.status()).toBe(422);
  });
});

test.describe('Conversation API - DELETE /email/{account}/conversation/{thread_id}', () => {

  test('clear conversation requires authentication', async ({ request }) => {
    const response = await request.delete(`${API_BASE}/email/personal/conversation/${TEST_THREAD_ID}`);
    // Should return 401 or 403 without auth
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('clear conversation validates account', async ({ request }) => {
    const response = await request.delete(`${API_BASE}/email/invalid/conversation/${TEST_THREAD_ID}`, {
      headers: AUTH_HEADERS
    });
    expect(response.status()).toBe(422);
  });

  test('clear conversation returns correct structure', async ({ request }) => {
    const threadId = `clear-test-${Date.now()}`;
    const response = await request.delete(`${API_BASE}/email/personal/conversation/${threadId}`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('success', true);
    expect(data).toHaveProperty('account', 'personal');
    expect(data).toHaveProperty('threadId', threadId);
    expect(data).toHaveProperty('messagesCleared');
    // messagesCleared is a boolean (true if found and cleared, false otherwise)
    expect(typeof data.messagesCleared).toBe('boolean');
  });

  test('cleared conversation returns empty on subsequent GET', async ({ request }) => {
    const threadId = `clear-verify-${Date.now()}`;

    // Clear the conversation
    await request.delete(`${API_BASE}/email/personal/conversation/${threadId}`, {
      headers: AUTH_HEADERS
    });

    // Get should return empty
    const getResponse = await request.get(`${API_BASE}/email/personal/conversation/${threadId}`, {
      headers: AUTH_HEADERS
    });
    expect(getResponse.ok()).toBeTruthy();

    const data = await getResponse.json();
    expect(data.count).toBe(0);
    expect(data.messages.length).toBe(0);
  });
});

test.describe('Chat API - POST /email/{account}/chat', () => {

  test('chat endpoint requires authentication', async ({ request }) => {
    const response = await request.post(`${API_BASE}/email/personal/chat`, {
      headers: { 'Content-Type': 'application/json' },
      data: { email_id: 'test', message: 'test' }
    });
    // Should return 401 or 403 without auth
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('chat endpoint validates account', async ({ request }) => {
    const response = await request.post(`${API_BASE}/email/invalid/chat`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: { email_id: 'test', message: 'test' }
    });
    expect(response.status()).toBe(422);
  });

  test('chat endpoint requires email_id field', async ({ request }) => {
    const response = await request.post(`${API_BASE}/email/personal/chat`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: { message: 'test message' }
    });
    // Should fail validation
    expect(response.status()).toBe(422);
  });

  test('chat endpoint requires message field', async ({ request }) => {
    const response = await request.post(`${API_BASE}/email/personal/chat`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: { email_id: 'test-email-id' }
    });
    // Should fail validation
    expect(response.status()).toBe(422);
  });
});

test.describe('Conversation Persistence - Integration', () => {

  test('conversation uses thread_id for grouping (not email_id)', async ({ request }) => {
    // First, get a real email to use for testing
    const inboxResponse = await request.get(`${API_BASE}/inbox/personal?max_results=1`, {
      headers: AUTH_HEADERS
    });

    if (!inboxResponse.ok()) {
      test.skip(true, 'Could not fetch inbox');
      return;
    }

    const inboxData = await inboxResponse.json();
    if (inboxData.recentMessages.length === 0) {
      test.skip(true, 'No emails in inbox');
      return;
    }

    const email = inboxData.recentMessages[0];

    // Thread ID should be used for conversation storage
    // Fetch conversation by thread ID
    const response = await request.get(
      `${API_BASE}/email/personal/conversation/${email.threadId}`,
      { headers: AUTH_HEADERS }
    );
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.threadId).toBe(email.threadId);
  });

  test('conversation persists across account in correct storage', async ({ request }) => {
    // Conversations should be stored per account (ACCOUNT-based keying)
    const threadId = `cross-account-test-${Date.now()}`;

    // Check personal account
    const personalResponse = await request.get(
      `${API_BASE}/email/personal/conversation/${threadId}`,
      { headers: AUTH_HEADERS }
    );
    expect(personalResponse.ok()).toBeTruthy();

    // Check church account
    const churchResponse = await request.get(
      `${API_BASE}/email/church/conversation/${threadId}`,
      { headers: AUTH_HEADERS }
    );
    expect(churchResponse.ok()).toBeTruthy();

    // Both should return valid responses (separate storage)
    const personalData = await personalResponse.json();
    const churchData = await churchResponse.json();

    expect(personalData.account).toBe('personal');
    expect(churchData.account).toBe('church');
  });
});

test.describe('Conversation Response - Field Naming Convention', () => {

  test('conversation endpoint returns camelCase fields', async ({ request }) => {
    const response = await request.get(
      `${API_BASE}/email/personal/conversation/${TEST_THREAD_ID}`,
      { headers: AUTH_HEADERS }
    );
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    // Should use camelCase
    expect(data).toHaveProperty('threadId');
    // Should NOT use snake_case
    expect(data).not.toHaveProperty('thread_id');
  });

  test('clear endpoint returns camelCase messagesCleared', async ({ request }) => {
    const response = await request.delete(
      `${API_BASE}/email/personal/conversation/${TEST_THREAD_ID}`,
      { headers: AUTH_HEADERS }
    );
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    // Should use camelCase
    expect(data).toHaveProperty('messagesCleared');
    // Should NOT use snake_case
    expect(data).not.toHaveProperty('messages_cleared');
  });
});
