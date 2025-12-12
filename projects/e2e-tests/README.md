# DATA E2E Tests

End-to-end regression tests for the Daily Task Assistant (DATA) application using Playwright.

## Overview

This test suite provides automated regression testing for DATA's web dashboard and API endpoints. It helps ensure that new features don't break existing functionality.

## Test Structure

```
tests/
├── api-health.spec.ts      # Backend API health checks
├── tasks/
│   └── task-list.spec.ts   # Task list and filtering tests
├── email/
│   └── email-dashboard.spec.ts  # Email management tests
├── auth/                   # Authentication tests (future)
└── chat/                   # Chat/AI interaction tests (future)
```

## Prerequisites

1. **Backend running**: The FastAPI backend should be available at `http://localhost:8000`
2. **Frontend running**: The React dashboard should be available at `http://localhost:5173`
3. **Dev auth bypass**: Set `DTA_DEV_AUTH_BYPASS=1` in the backend environment

The Playwright config can auto-start these servers, but it's often faster to have them running already.

## Running Tests

### Quick Start

```bash
# Run all tests
npm test

# Run with UI (interactive mode)
npm run test:ui

# Run headed (see the browser)
npm run test:headed

# Debug mode (step through)
npm run test:debug
```

### Targeted Tests

```bash
# API health checks only
npm run test:api

# Task-related tests
npm run test:tasks

# Email management tests
npm run test:email

# Chrome only (faster)
npm run test:chrome
```

### Generate Tests

Use Playwright's codegen to record new tests:

```bash
npm run codegen
```

### View Test Report

After running tests:

```bash
npm run report
```

## Test Coverage

### Current Coverage

| Feature | Tests | Status |
|---------|-------|--------|
| API Health | 4 | ✅ |
| Task List | 9 | ✅ |
| Portfolio View | 5 | ✅ |
| Email Dashboard | 5 | ✅ |
| Email Rules | 7 | ✅ |
| Account Switching | 2 | ✅ |

### Future Coverage (TODO)

- [ ] Chat interactions with DATA
- [ ] Task creation/editing
- [ ] Plan generation
- [ ] Research functionality
- [ ] Feedback submission
- [ ] Google OAuth flow (mocked)

## CI/CD Integration

Tests are configured to run in GitHub Actions. See `.github/workflows/playwright.yml` for the workflow configuration.

## Writing New Tests

1. Create a new `.spec.ts` file in the appropriate directory
2. Use the `test.describe` and `test` structure
3. Set up auth headers in `beforeEach`:

```typescript
test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await page.setExtraHTTPHeaders({
    'X-User-Email': 'david.a.royes@gmail.com'
  });
});
```

4. Use Playwright's locators and assertions:

```typescript
test('should do something', async ({ page }) => {
  await expect(page.getByRole('button', { name: 'Click me' })).toBeVisible();
  await page.getByRole('button', { name: 'Click me' }).click();
  await expect(page.getByText('Success!')).toBeVisible();
});
```

## Debugging Failed Tests

1. **Screenshots**: Automatically captured on failure in `test-results/`
2. **Videos**: Captured on first retry
3. **Traces**: Use `npx playwright show-trace trace.zip` to view
4. **Debug mode**: `npm run test:debug` to step through

## Notes

- Tests run in parallel by default
- Mobile viewports are tested via the "Mobile Chrome" project
- The backend must have `DTA_DEV_AUTH_BYPASS=1` set for tests to authenticate

