import { defineConfig, devices } from '@playwright/test';

/**
 * DATA - End-to-End Test Configuration
 * 
 * This configuration sets up Playwright for testing the Daily Task Assistant
 * web dashboard and API endpoints.
 */

export default defineConfig({
  testDir: './tests',
  
  /* Run tests in parallel */
  fullyParallel: true,
  
  /* Fail the build on CI if you accidentally left test.only in the source code */
  forbidOnly: !!process.env.CI,
  
  /* Retry failed tests on CI */
  retries: process.env.CI ? 2 : 0,
  
  /* Use fewer workers on CI */
  workers: process.env.CI ? 1 : undefined,
  
  /* Reporter configuration */
  reporter: [
    ['html', { open: 'never' }],
    ['list'],
  ],
  
  /* Shared settings for all projects */
  use: {
    /* Base URL for the DATA web dashboard */
    baseURL: 'http://localhost:5173',
    
    /* Collect trace on first retry */
    trace: 'on-first-retry',
    
    /* Screenshot on failure */
    screenshot: 'only-on-failure',
    
    /* Video on failure */
    video: 'on-first-retry',
  },

  /* Configure projects for different test scenarios */
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    /* Test against mobile viewports */
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
  ],

  /* Run local dev servers before starting tests */
  webServer: [
    {
      command: 'cd ../daily-task-assistant && python -m uvicorn api.main:app --port 8000',
      url: 'http://localhost:8000/health',
      reuseExistingServer: !process.env.CI,
      timeout: 120 * 1000,
      env: {
        DTA_DEV_AUTH_BYPASS: '1',
      },
    },
    {
      command: 'cd ../web-dashboard && npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 120 * 1000,
    },
  ],
});

