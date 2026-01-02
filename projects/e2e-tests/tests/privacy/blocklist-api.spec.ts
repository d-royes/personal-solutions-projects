import { test, expect } from '@playwright/test';

/**
 * Blocklist API Tests
 *
 * Tests for the sender blocklist CRUD endpoints.
 * Part of the Email Experience Enhancement feature (Q1 2025 - Sprint 2)
 *
 * The blocklist is stored at the GLOBAL level (not per-account),
 * so it's shared across login identities (personal and church).
 */

// Run all blocklist tests serially to avoid race conditions on shared profile
test.describe.configure({ mode: 'serial' });

const API_BASE = process.env.API_BASE || 'http://localhost:8000';
const AUTH_HEADERS = {
  'X-User-Email': 'david.a.royes@gmail.com'
};

// Test sender emails (using clearly fake domains to avoid accidental real use)
const TEST_SENDER = 'test-blocklist-e2e@fake-domain-for-testing.invalid';
const TEST_SENDER_2 = 'another-test@fake-domain-for-testing.invalid';

test.describe('Blocklist API - GET /profile/blocklist', () => {

  test('blocklist endpoint requires authentication', async ({ request }) => {
    const response = await request.get(`${API_BASE}/profile/blocklist`);
    // Should return 401 or 403 without auth
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('blocklist endpoint returns correct structure', async ({ request }) => {
    const response = await request.get(`${API_BASE}/profile/blocklist`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('blocklist');
    expect(Array.isArray(data.blocklist)).toBeTruthy();
  });

  test('blocklist returns array of sender emails', async ({ request }) => {
    const response = await request.get(`${API_BASE}/profile/blocklist`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    // All items should be strings (email addresses)
    for (const item of data.blocklist) {
      expect(typeof item).toBe('string');
    }
  });
});

test.describe('Blocklist API - POST /profile/blocklist/add', () => {

  // Clean up test sender before and after tests
  test.beforeEach(async ({ request }) => {
    // Try to remove test sender if it exists
    await request.post(`${API_BASE}/profile/blocklist/remove`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: { senderEmail: TEST_SENDER }
    });
  });

  test.afterEach(async ({ request }) => {
    // Clean up test sender
    await request.post(`${API_BASE}/profile/blocklist/remove`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: { senderEmail: TEST_SENDER }
    });
  });

  test('add endpoint requires authentication', async ({ request }) => {
    const response = await request.post(`${API_BASE}/profile/blocklist/add`, {
      headers: {
        'Content-Type': 'application/json'
      },
      data: { senderEmail: TEST_SENDER }
    });
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('add endpoint requires senderEmail field', async ({ request }) => {
    const response = await request.post(`${API_BASE}/profile/blocklist/add`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {}
    });
    // Should fail validation - 422 Unprocessable Entity
    expect(response.status()).toBe(422);
  });

  test('add endpoint validates email format (min 3 chars)', async ({ request }) => {
    const response = await request.post(`${API_BASE}/profile/blocklist/add`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: { senderEmail: 'ab' } // Only 2 chars
    });
    // Should fail validation - 422 Unprocessable Entity
    expect(response.status()).toBe(422);
  });

  test('add endpoint returns success for new sender', async ({ request }) => {
    const response = await request.post(`${API_BASE}/profile/blocklist/add`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: { senderEmail: TEST_SENDER }
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.success).toBe(true);
    expect(data.senderEmail).toBe(TEST_SENDER);
  });

  test('add endpoint returns success=false for duplicate', async ({ request }) => {
    // Add sender first time
    await request.post(`${API_BASE}/profile/blocklist/add`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: { senderEmail: TEST_SENDER }
    });

    // Try to add again - should indicate duplicate
    const response = await request.post(`${API_BASE}/profile/blocklist/add`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: { senderEmail: TEST_SENDER }
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.success).toBe(false);
    expect(data.message).toContain('already');
  });

  test('added sender appears in GET /profile/blocklist', async ({ request }) => {
    // Add sender
    const addResponse = await request.post(`${API_BASE}/profile/blocklist/add`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: { senderEmail: TEST_SENDER }
    });
    expect(addResponse.ok()).toBeTruthy();

    // Verify it appears in blocklist
    const getResponse = await request.get(`${API_BASE}/profile/blocklist`, {
      headers: AUTH_HEADERS
    });
    expect(getResponse.ok()).toBeTruthy();

    const data = await getResponse.json();
    expect(data.blocklist).toContain(TEST_SENDER);
  });
});

test.describe('Blocklist API - POST /profile/blocklist/remove', () => {

  // Ensure test sender exists before each test
  test.beforeEach(async ({ request }) => {
    await request.post(`${API_BASE}/profile/blocklist/add`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: { senderEmail: TEST_SENDER }
    });
  });

  test.afterEach(async ({ request }) => {
    // Clean up
    await request.post(`${API_BASE}/profile/blocklist/remove`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: { senderEmail: TEST_SENDER }
    });
  });

  test('remove endpoint requires authentication', async ({ request }) => {
    const response = await request.post(`${API_BASE}/profile/blocklist/remove`, {
      headers: {
        'Content-Type': 'application/json'
      },
      data: { senderEmail: TEST_SENDER }
    });
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('remove endpoint requires senderEmail field', async ({ request }) => {
    const response = await request.post(`${API_BASE}/profile/blocklist/remove`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {}
    });
    // Should fail validation - 422 Unprocessable Entity
    expect(response.status()).toBe(422);
  });

  test('remove endpoint returns success for existing sender', async ({ request }) => {
    const response = await request.post(`${API_BASE}/profile/blocklist/remove`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: { senderEmail: TEST_SENDER }
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.success).toBe(true);
    expect(data.senderEmail).toBe(TEST_SENDER);
  });

  test('remove endpoint returns success=false for non-existent', async ({ request }) => {
    // First remove it
    await request.post(`${API_BASE}/profile/blocklist/remove`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: { senderEmail: TEST_SENDER }
    });

    // Try to remove again - should indicate not found
    const response = await request.post(`${API_BASE}/profile/blocklist/remove`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: { senderEmail: TEST_SENDER }
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.success).toBe(false);
    expect(data.message).toContain('not found');
  });

  test('removed sender no longer in GET /profile/blocklist', async ({ request }) => {
    // Remove sender
    const removeResponse = await request.post(`${API_BASE}/profile/blocklist/remove`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: { senderEmail: TEST_SENDER }
    });
    expect(removeResponse.ok()).toBeTruthy();

    // Verify it's gone from blocklist
    const getResponse = await request.get(`${API_BASE}/profile/blocklist`, {
      headers: AUTH_HEADERS
    });
    expect(getResponse.ok()).toBeTruthy();

    const data = await getResponse.json();
    expect(data.blocklist).not.toContain(TEST_SENDER);
  });
});

test.describe('Blocklist API - GLOBAL Storage', () => {
  // Blocklist is GLOBAL - shared across all login identities
  const PERSONAL_USER = 'david.a.royes@gmail.com';
  const CHURCH_USER = 'davidroyes@southpointsda.org';

  test('blocklist visible from both login identities', async ({ request }) => {
    // Use unique sender per test run to avoid race conditions
    const testSender = `cross-login-${Date.now()}-${Math.random().toString(36).substr(2, 9)}@fake-domain-for-testing.invalid`;

    // Add sender as personal user
    const addResponse = await request.post(`${API_BASE}/profile/blocklist/add`, {
      headers: {
        'X-User-Email': PERSONAL_USER,
        'Content-Type': 'application/json'
      },
      data: { senderEmail: testSender }
    });
    expect(addResponse.ok()).toBeTruthy();
    const addData = await addResponse.json();
    expect(addData.success).toBe(true);

    // Get blocklist as personal user
    const response1 = await request.get(`${API_BASE}/profile/blocklist`, {
      headers: { 'X-User-Email': PERSONAL_USER }
    });
    expect(response1.ok()).toBeTruthy();
    const data1 = await response1.json();

    // Get blocklist as church user
    const response2 = await request.get(`${API_BASE}/profile/blocklist`, {
      headers: { 'X-User-Email': CHURCH_USER }
    });
    expect(response2.ok()).toBeTruthy();
    const data2 = await response2.json();

    // Should be identical (including the test sender)
    expect(data1.blocklist).toContain(testSender);
    expect(data2.blocklist).toContain(testSender);
    expect(data1.blocklist).toEqual(data2.blocklist);

    // Cleanup
    await request.post(`${API_BASE}/profile/blocklist/remove`, {
      headers: {
        'X-User-Email': PERSONAL_USER,
        'Content-Type': 'application/json'
      },
      data: { senderEmail: testSender }
    });
  });

  test('blocklist changes from personal visible from church', async ({ request }) => {
    // Use unique sender per test run
    const testSender = `personal-to-church-${Date.now()}-${Math.random().toString(36).substr(2, 9)}@fake-domain-for-testing.invalid`;

    // Add sender as personal user
    const addResponse = await request.post(`${API_BASE}/profile/blocklist/add`, {
      headers: {
        'X-User-Email': PERSONAL_USER,
        'Content-Type': 'application/json'
      },
      data: { senderEmail: testSender }
    });
    expect(addResponse.ok()).toBeTruthy();

    // Verify as church user
    const getResponse = await request.get(`${API_BASE}/profile/blocklist`, {
      headers: { 'X-User-Email': CHURCH_USER }
    });
    expect(getResponse.ok()).toBeTruthy();

    const data = await getResponse.json();
    expect(data.blocklist).toContain(testSender);

    // Cleanup
    await request.post(`${API_BASE}/profile/blocklist/remove`, {
      headers: {
        'X-User-Email': PERSONAL_USER,
        'Content-Type': 'application/json'
      },
      data: { senderEmail: testSender }
    });
  });

  test('blocklist changes from church visible from personal', async ({ request }) => {
    // Use unique sender per test run
    const testSender = `church-to-personal-${Date.now()}-${Math.random().toString(36).substr(2, 9)}@fake-domain-for-testing.invalid`;

    // Add sender as church user
    const addResponse = await request.post(`${API_BASE}/profile/blocklist/add`, {
      headers: {
        'X-User-Email': CHURCH_USER,
        'Content-Type': 'application/json'
      },
      data: { senderEmail: testSender }
    });
    expect(addResponse.ok()).toBeTruthy();

    // Verify as personal user
    const getResponse = await request.get(`${API_BASE}/profile/blocklist`, {
      headers: { 'X-User-Email': PERSONAL_USER }
    });
    expect(getResponse.ok()).toBeTruthy();

    const data = await getResponse.json();
    expect(data.blocklist).toContain(testSender);

    // Cleanup
    await request.post(`${API_BASE}/profile/blocklist/remove`, {
      headers: {
        'X-User-Email': CHURCH_USER,
        'Content-Type': 'application/json'
      },
      data: { senderEmail: testSender }
    });
  });
});
