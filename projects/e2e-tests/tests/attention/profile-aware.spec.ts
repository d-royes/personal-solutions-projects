import { test, expect } from '@playwright/test';

/**
 * Profile-Aware Analysis E2E Tests
 *
 * Tests for role-aware email attention detection using user profiles.
 * Sprint 3: Profile-aware analysis with VIP, role patterns, and not-actionable filtering.
 */

const API_BASE = process.env.API_BASE || 'http://localhost:8000';
const AUTH_HEADERS = {
  'X-User-Email': 'david.a.royes@gmail.com'
};

test.describe('Profile API - CRUD Operations', () => {

  test('GET /profile returns user profile with roles and patterns', async ({ request }) => {
    const response = await request.get(`${API_BASE}/profile`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('profile');

    const profile = data.profile;
    expect(profile).toHaveProperty('userId');
    expect(profile).toHaveProperty('churchRoles');
    expect(profile).toHaveProperty('personalContexts');
    expect(profile).toHaveProperty('vipSenders');
    expect(profile).toHaveProperty('churchAttentionPatterns');
    expect(profile).toHaveProperty('personalAttentionPatterns');
    expect(profile).toHaveProperty('notActionablePatterns');

    // Verify arrays are present
    expect(Array.isArray(profile.churchRoles)).toBeTruthy();
    expect(Array.isArray(profile.personalContexts)).toBeTruthy();
  });

  test('profile contains expected church roles', async ({ request }) => {
    const response = await request.get(`${API_BASE}/profile`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    const profile = data.profile;
    // Default profile should have these roles
    const expectedRoles = ['Treasurer', 'IT Lead'];
    for (const role of expectedRoles) {
      expect(profile.churchRoles).toContain(role);
    }
  });

  test('profile contains expected personal contexts', async ({ request }) => {
    const response = await request.get(`${API_BASE}/profile`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    const profile = data.profile;
    // Default profile should have these contexts
    const expectedContexts = ['Parent', 'Homeowner'];
    for (const context of expectedContexts) {
      expect(profile.personalContexts).toContain(context);
    }
  });

  test('profile contains VIP senders by account', async ({ request }) => {
    const response = await request.get(`${API_BASE}/profile`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    const profile = data.profile;
    expect(profile.vipSenders).toHaveProperty('personal');
    expect(profile.vipSenders).toHaveProperty('church');
    expect(Array.isArray(profile.vipSenders.personal)).toBeTruthy();
    expect(Array.isArray(profile.vipSenders.church)).toBeTruthy();
  });

  test('profile requires authentication', async ({ request }) => {
    const response = await request.get(`${API_BASE}/profile`);
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });
});

test.describe('Profile-Aware Attention Analysis', () => {

  test('analyze endpoint returns profile analysis fields when Gmail configured', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/analyze/personal`, {
      headers: AUTH_HEADERS
    });

    // Skip if Gmail not configured or other backend error
    if (!response.ok()) {
      const data = await response.json();
      if (data.detail && (data.detail.includes('Gmail') || data.detail.includes('config'))) {
        test.skip(true, 'Gmail credentials not configured');
        return;
      }
    }

    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('attentionItems');

    // If there are attention items, verify profile fields are present
    if (data.attentionItems.length > 0) {
      const item = data.attentionItems[0];
      // New profile-aware fields
      expect(item).toHaveProperty('matchedRole');
      expect(item).toHaveProperty('confidence');
      expect(item).toHaveProperty('analysisMethod');

      // Confidence should be a number between 0 and 1
      expect(typeof item.confidence).toBe('number');
      expect(item.confidence).toBeGreaterThanOrEqual(0);
      expect(item.confidence).toBeLessThanOrEqual(1);

      // Analysis method should be one of the valid values (includes 'haiku' for AI analysis)
      expect(['regex', 'profile', 'vip', 'haiku']).toContain(item.analysisMethod);
    }
  });

  test('attention endpoint returns items with profile fields', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/attention/personal`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('attentionItems');
    expect(data).toHaveProperty('count');

    // If there are attention items, verify profile fields are present
    if (data.attentionItems.length > 0) {
      const item = data.attentionItems[0];
      // New profile-aware fields should be present
      expect(item).toHaveProperty('matchedRole');
      expect(item).toHaveProperty('confidence');
      expect(item).toHaveProperty('analysisMethod');
    }
  });

  test('attention items have valid confidence values', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/attention/personal`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();

    // Check all items have valid confidence
    for (const item of data.attentionItems) {
      expect(typeof item.confidence).toBe('number');
      expect(item.confidence).toBeGreaterThanOrEqual(0);
      expect(item.confidence).toBeLessThanOrEqual(1);
    }
  });

  test('attention items have valid analysis method', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/attention/personal`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();

    // Check all items have valid analysis method (includes 'haiku' for AI analysis)
    for (const item of data.attentionItems) {
      expect(['regex', 'profile', 'vip', 'haiku']).toContain(item.analysisMethod);
    }
  });

  test('VIP items have high confidence and urgency', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/attention/personal`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();

    // Check VIP items have high confidence
    const vipItems = data.attentionItems.filter(
      (item: any) => item.analysisMethod === 'vip'
    );

    for (const item of vipItems) {
      expect(item.confidence).toBeGreaterThanOrEqual(0.9);
      expect(item.matchedRole).toBe('VIP');
      expect(item.urgency).toBe('high');
    }
  });

  test('profile pattern matches have matched role', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/attention/personal`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();

    // Check profile matches have appropriate data
    const profileItems = data.attentionItems.filter(
      (item: any) => item.analysisMethod === 'profile'
    );

    for (const item of profileItems) {
      expect(item.confidence).toBeGreaterThanOrEqual(0.8);
      expect(item.matchedRole).not.toBeNull();
    }
  });
});

test.describe('Profile Update API', () => {

  test('PUT /profile updates church roles', async ({ request }) => {
    // Get current profile
    const getResponse = await request.get(`${API_BASE}/profile`, {
      headers: AUTH_HEADERS
    });
    expect(getResponse.ok()).toBeTruthy();
    const getData = await getResponse.json();
    const originalProfile = getData.profile;

    // Update with a test role added
    const testRole = 'Test Role';
    const updatedRoles = [...originalProfile.churchRoles];
    if (!updatedRoles.includes(testRole)) {
      updatedRoles.push(testRole);
    }

    const updateResponse = await request.put(`${API_BASE}/profile`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        churchRoles: updatedRoles
      }
    });
    expect(updateResponse.ok()).toBeTruthy();

    // Verify the update
    const verifyResponse = await request.get(`${API_BASE}/profile`, {
      headers: AUTH_HEADERS
    });
    const verifyData = await verifyResponse.json();
    expect(verifyData.profile.churchRoles).toContain(testRole);

    // Restore original profile
    await request.put(`${API_BASE}/profile`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        churchRoles: originalProfile.churchRoles
      }
    });
  });

  test('PUT /profile updates VIP senders', async ({ request }) => {
    // Get current profile
    const getResponse = await request.get(`${API_BASE}/profile`, {
      headers: AUTH_HEADERS
    });
    expect(getResponse.ok()).toBeTruthy();
    const getData = await getResponse.json();
    const originalProfile = getData.profile;

    // Update with a test VIP added
    const testVip = 'test-vip-sender';
    const updatedVips = {
      ...originalProfile.vipSenders,
      personal: [...(originalProfile.vipSenders.personal || []), testVip]
    };

    const updateResponse = await request.put(`${API_BASE}/profile`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        vipSenders: updatedVips
      }
    });
    expect(updateResponse.ok()).toBeTruthy();

    // Verify the update
    const verifyResponse = await request.get(`${API_BASE}/profile`, {
      headers: AUTH_HEADERS
    });
    const verifyData = await verifyResponse.json();
    expect(verifyData.profile.vipSenders.personal).toContain(testVip);

    // Restore original profile
    await request.put(`${API_BASE}/profile`, {
      headers: {
        ...AUTH_HEADERS,
        'Content-Type': 'application/json'
      },
      data: {
        vipSenders: originalProfile.vipSenders
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
    expect(response.status()).toBeGreaterThanOrEqual(400);
  });
});

test.describe('Attention Response Structure', () => {

  test('attention items use camelCase for profile fields', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/attention/personal`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('attentionItems');

    if (data.attentionItems.length > 0) {
      const item = data.attentionItems[0];

      // Verify camelCase field names
      expect(item).toHaveProperty('matchedRole');
      expect(item).toHaveProperty('analysisMethod');

      // Verify NOT snake_case
      expect(item).not.toHaveProperty('matched_role');
      expect(item).not.toHaveProperty('analysis_method');
    }
  });

  test('church attention endpoint returns valid structure', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/attention/church`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('account', 'church');
    expect(data).toHaveProperty('attentionItems');
    expect(data).toHaveProperty('count');
    expect(Array.isArray(data.attentionItems)).toBeTruthy();
  });

  test('personal attention endpoint returns valid structure', async ({ request }) => {
    const response = await request.get(`${API_BASE}/email/attention/personal`, {
      headers: AUTH_HEADERS
    });
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('account', 'personal');
    expect(data).toHaveProperty('attentionItems');
    expect(data).toHaveProperty('count');
    expect(Array.isArray(data.attentionItems)).toBeTruthy();
  });
});
