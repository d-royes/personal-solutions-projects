import { test, expect } from '@playwright/test';

/**
 * Profile API Tests
 *
 * Tests for the user profile CRUD endpoints.
 * Sprint 1.7: E2E tests for Profile CRUD + regression check
 */

const API_BASE = process.env.API_BASE || 'http://localhost:8000';
const AUTH_HEADERS = {
  'X-User-Email': 'david.a.royes@gmail.com'
};

test.describe('Profile API - GET /profile', () => {

  test('profile endpoint responds with authenticated user', async ({ request }) => {
    const response = await request.get(`${API_BASE}/profile`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('profile');
    expect(data.profile).toHaveProperty('userId');
    expect(data.profile).toHaveProperty('churchRoles');
    expect(data.profile).toHaveProperty('personalContexts');
  });

  test('profile endpoint returns correct structure', async ({ request }) => {
    const response = await request.get(`${API_BASE}/profile`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    const profile = data.profile;

    // Check all required fields
    expect(profile).toHaveProperty('userId');
    expect(profile).toHaveProperty('churchRoles');
    expect(profile).toHaveProperty('personalContexts');
    expect(profile).toHaveProperty('vipSenders');
    expect(profile).toHaveProperty('churchAttentionPatterns');
    expect(profile).toHaveProperty('personalAttentionPatterns');
    expect(profile).toHaveProperty('notActionablePatterns');
    expect(profile).toHaveProperty('version');
    expect(profile).toHaveProperty('createdAt');
    expect(profile).toHaveProperty('updatedAt');

    // Check types
    expect(Array.isArray(profile.churchRoles)).toBeTruthy();
    expect(Array.isArray(profile.personalContexts)).toBeTruthy();
    expect(typeof profile.vipSenders).toBe('object');
    expect(typeof profile.churchAttentionPatterns).toBe('object');
    expect(typeof profile.personalAttentionPatterns).toBe('object');
    expect(typeof profile.notActionablePatterns).toBe('object');
  });

  test('profile endpoint requires authentication', async ({ request }) => {
    const response = await request.get(`${API_BASE}/profile`);
    // Should return 401 or 403 without auth
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });

  test('profile returns default seed data for new user', async ({ request }) => {
    const response = await request.get(`${API_BASE}/profile`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    const profile = data.profile;

    // Check that default seed data exists
    expect(profile.churchRoles.length).toBeGreaterThan(0);
    expect(profile.personalContexts.length).toBeGreaterThan(0);

    // Verify expected default roles
    expect(profile.churchRoles).toContain('Treasurer');
    expect(profile.churchRoles).toContain('Head Elder');

    // Verify expected default contexts
    expect(profile.personalContexts).toContain('Parent');
    expect(profile.personalContexts).toContain('Homeowner');
  });
});

test.describe('Profile API - PUT /profile', () => {

  test('profile update endpoint accepts partial updates', async ({ request }) => {
    // First, get current profile
    const getResponse = await request.get(`${API_BASE}/profile`, {
      headers: AUTH_HEADERS
    });
    expect(getResponse.ok()).toBeTruthy();
    const originalData = await getResponse.json();

    // Update only churchRoles
    const newRoles = [...originalData.profile.churchRoles];
    if (!newRoles.includes('Test Role')) {
      newRoles.push('Test Role');
    }

    const updateResponse = await request.put(`${API_BASE}/profile`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        churchRoles: newRoles
      }
    });
    expect(updateResponse.ok()).toBeTruthy();

    const updatedData = await updateResponse.json();
    expect(updatedData.profile.churchRoles).toContain('Test Role');

    // Clean up - remove the test role
    const cleanRoles = updatedData.profile.churchRoles.filter((r: string) => r !== 'Test Role');
    await request.put(`${API_BASE}/profile`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        churchRoles: cleanRoles
      }
    });
  });

  test('profile update preserves non-updated fields', async ({ request }) => {
    // Get current profile
    const getResponse = await request.get(`${API_BASE}/profile`, {
      headers: AUTH_HEADERS
    });
    expect(getResponse.ok()).toBeTruthy();
    const originalData = await getResponse.json();

    // Update only personalContexts
    const updateResponse = await request.put(`${API_BASE}/profile`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        personalContexts: originalData.profile.personalContexts
      }
    });
    expect(updateResponse.ok()).toBeTruthy();

    const updatedData = await updateResponse.json();

    // churchRoles should be preserved
    expect(updatedData.profile.churchRoles).toEqual(originalData.profile.churchRoles);

    // vipSenders should be preserved
    expect(updatedData.profile.vipSenders).toEqual(originalData.profile.vipSenders);
  });

  test('profile update accepts VIP senders', async ({ request }) => {
    const getResponse = await request.get(`${API_BASE}/profile`, {
      headers: AUTH_HEADERS
    });
    expect(getResponse.ok()).toBeTruthy();
    const originalData = await getResponse.json();

    // Update VIP senders with test data
    const newVipSenders = {
      ...originalData.profile.vipSenders,
      test_account: ['test@example.com']
    };

    const updateResponse = await request.put(`${API_BASE}/profile`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        vipSenders: newVipSenders
      }
    });
    expect(updateResponse.ok()).toBeTruthy();

    const updatedData = await updateResponse.json();
    expect(updatedData.profile.vipSenders).toHaveProperty('test_account');

    // Clean up - remove test account
    const cleanVipSenders = { ...updatedData.profile.vipSenders };
    delete cleanVipSenders.test_account;
    await request.put(`${API_BASE}/profile`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        vipSenders: cleanVipSenders
      }
    });
  });

  test('profile update accepts attention patterns', async ({ request }) => {
    const getResponse = await request.get(`${API_BASE}/profile`, {
      headers: AUTH_HEADERS
    });
    expect(getResponse.ok()).toBeTruthy();
    const originalData = await getResponse.json();

    // Update church attention patterns
    const newPatterns = {
      ...originalData.profile.churchAttentionPatterns,
      'Test Role': ['test pattern']
    };

    const updateResponse = await request.put(`${API_BASE}/profile`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        churchAttentionPatterns: newPatterns
      }
    });
    expect(updateResponse.ok()).toBeTruthy();

    const updatedData = await updateResponse.json();
    expect(updatedData.profile.churchAttentionPatterns).toHaveProperty('Test Role');
    expect(updatedData.profile.churchAttentionPatterns['Test Role']).toContain('test pattern');

    // Clean up
    const cleanPatterns = { ...updatedData.profile.churchAttentionPatterns };
    delete cleanPatterns['Test Role'];
    await request.put(`${API_BASE}/profile`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        churchAttentionPatterns: cleanPatterns
      }
    });
  });

  test('profile update requires authentication', async ({ request }) => {
    const response = await request.put(`${API_BASE}/profile`, {
      headers: {
        'Content-Type': 'application/json'
      },
      data: {
        churchRoles: ['Test']
      }
    });
    // Should return 401 or 403 without auth
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });
});

test.describe('Profile API - Cross-Login Access (GLOBAL Profile)', () => {
  // Profile is GLOBAL - shared across all login identities
  const PERSONAL_USER = 'david.a.royes@gmail.com';
  const CHURCH_USER = 'davidroyes@southpointsda.org';

  test('profile returns same data regardless of login identity', async ({ request }) => {
    // Get profile as personal user
    const response1 = await request.get(`${API_BASE}/profile`, {
      headers: { 'X-User-Email': PERSONAL_USER }
    });
    expect(response1.ok()).toBeTruthy();
    const data1 = await response1.json();

    // Get profile as church user
    const response2 = await request.get(`${API_BASE}/profile`, {
      headers: { 'X-User-Email': CHURCH_USER }
    });
    expect(response2.ok()).toBeTruthy();
    const data2 = await response2.json();

    // Should be identical
    expect(data1.profile.churchRoles).toEqual(data2.profile.churchRoles);
    expect(data1.profile.personalContexts).toEqual(data2.profile.personalContexts);
    expect(data1.profile.vipSenders).toEqual(data2.profile.vipSenders);
  });

  test('profile update visible from other login identity', async ({ request }) => {
    // Get original profile
    const originalResponse = await request.get(`${API_BASE}/profile`, {
      headers: { 'X-User-Email': PERSONAL_USER }
    });
    const originalData = await originalResponse.json();

    // Update as personal user
    const testRole = 'E2E Cross-Login Test';
    const newRoles = [...originalData.profile.churchRoles, testRole];

    await request.put(`${API_BASE}/profile`, {
      headers: {
        'X-User-Email': PERSONAL_USER,
        'Content-Type': 'application/json'
      },
      data: { churchRoles: newRoles }
    });

    // Read as church user - should see the update
    const response = await request.get(`${API_BASE}/profile`, {
      headers: { 'X-User-Email': CHURCH_USER }
    });
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.profile.churchRoles).toContain(testRole);

    // Clean up - restore original
    await request.put(`${API_BASE}/profile`, {
      headers: {
        'X-User-Email': PERSONAL_USER,
        'Content-Type': 'application/json'
      },
      data: { churchRoles: originalData.profile.churchRoles }
    });
  });
});

test.describe('Profile API - Camel Case Conversion', () => {

  test('API returns camelCase field names', async ({ request }) => {
    const response = await request.get(`${API_BASE}/profile`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    const profile = data.profile;

    // Verify camelCase (not snake_case)
    expect(profile).toHaveProperty('userId');
    expect(profile).toHaveProperty('churchRoles');
    expect(profile).toHaveProperty('personalContexts');
    expect(profile).toHaveProperty('vipSenders');
    expect(profile).toHaveProperty('churchAttentionPatterns');
    expect(profile).toHaveProperty('personalAttentionPatterns');
    expect(profile).toHaveProperty('notActionablePatterns');
    expect(profile).toHaveProperty('createdAt');
    expect(profile).toHaveProperty('updatedAt');

    // Verify NOT snake_case
    expect(profile).not.toHaveProperty('user_id');
    expect(profile).not.toHaveProperty('church_roles');
    expect(profile).not.toHaveProperty('personal_contexts');
  });

  test('API accepts camelCase field names in updates', async ({ request }) => {
    const getResponse = await request.get(`${API_BASE}/profile`, {
      headers: AUTH_HEADERS
    });
    expect(getResponse.ok()).toBeTruthy();
    const originalData = await getResponse.json();

    // Send update with camelCase names
    const updateResponse = await request.put(`${API_BASE}/profile`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        churchRoles: originalData.profile.churchRoles,
        personalContexts: originalData.profile.personalContexts
      }
    });
    expect(updateResponse.ok()).toBeTruthy();

    // Response should also be camelCase
    const updatedData = await updateResponse.json();
    expect(updatedData.profile).toHaveProperty('churchRoles');
    expect(updatedData.profile).toHaveProperty('personalContexts');
  });
});
