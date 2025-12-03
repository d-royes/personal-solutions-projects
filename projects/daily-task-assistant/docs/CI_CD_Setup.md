# CI/CD Setup Guide

> **Last Updated**: December 2, 2025  
> **Status**: ✅ Staging environment fully operational  
> **First Successful Deployment**: December 2, 2025 (PR #8, 2m 32s)

This document describes how to set up the GitHub Actions CI/CD pipeline for the Daily Task Assistant.

## Deployment History

| Date | PR | Environment | Duration | Notes |
|------|-----|-------------|----------|-------|
| 2025-12-02 | #8 | Staging | 2m 32s | First CI/CD deployment - 9 commits including auth persistence, email allowlist, Research improvements |

## Quick Reference

| Environment | Frontend URL | Backend URL |
|-------------|--------------|-------------|
| **Dev** | http://localhost:5173 | http://localhost:8000 |
| **Staging** | https://daily-task-assistant-church.web.app | https://daily-task-assistant-staging-368257400464.us-central1.run.app |
| **Production** | TBD | TBD |

## Branch Strategy

```
develop     →  Local development, feature branches merge here
    ↓ PR
staging     →  Auto-deploys to Cloud Run staging + Firebase staging
    ↓ PR
main        →  Manual approval, deploys to production
```

## GitHub Secrets Required

Add these secrets in GitHub repo Settings > Secrets and variables > Actions:

| Secret | Description | How to Get |
|--------|-------------|------------|
| `GCP_SA_KEY` | Service account JSON key | GCP Console > IAM > Service Accounts > Create Key (JSON) |
| `GOOGLE_OAUTH_CLIENT_ID` | OAuth Client ID for token verification | GCP Console > APIs & Services > Credentials |

### Creating the Service Account

1. Go to [GCP Console > IAM > Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
2. Create a new service account: `github-actions-deployer`
3. Grant these roles:
   - `Cloud Run Admin`
   - `Artifact Registry Writer`
   - `Firebase Hosting Admin`
   - `Secret Manager Secret Accessor`
   - `Service Account User`
4. Create a JSON key and paste the entire contents as `GCP_SA_KEY` secret

## GCP Resources Required

### 1. Artifact Registry Repository

```bash
gcloud artifacts repositories create data-backend \
  --repository-format=docker \
  --location=us-central1 \
  --project=daily-task-assistant-church
```

### 2. Cloud Run Services

The workflows will create these automatically on first deploy:
- `daily-task-assistant-staging`
- `daily-task-assistant-prod`

### 3. Secret Manager Secrets

Ensure these secrets exist in Secret Manager (10 total):

| Secret | Purpose |
|--------|---------|
| `SMARTSHEET_API_TOKEN` | Smartsheet API access |
| `ANTHROPIC_API_KEY` | Claude AI API access |
| `CHURCH_GMAIL_CLIENT_ID` | Church Gmail OAuth Client ID |
| `CHURCH_GMAIL_CLIENT_SECRET` | Church Gmail OAuth Client Secret |
| `CHURCH_GMAIL_REFRESH_TOKEN` | Church Gmail OAuth Refresh Token |
| `CHURCH_GMAIL_ADDRESS` | Church Gmail email address (e.g., `user@southpointsda.org`) |
| `PERSONAL_GMAIL_CLIENT_ID` | Personal Gmail OAuth Client ID |
| `PERSONAL_GMAIL_CLIENT_SECRET` | Personal Gmail OAuth Client Secret |
| `PERSONAL_GMAIL_REFRESH_TOKEN` | Personal Gmail OAuth Refresh Token |
| `PERSONAL_GMAIL_ADDRESS` | Personal Gmail email address |

> ⚠️ **CRITICAL**: When creating secrets, ensure there are NO trailing whitespace or newline characters. Copy values carefully - trailing `\r\n` or spaces will cause authentication failures that are difficult to debug.

### 4. Firebase Hosting

Firebase Hosting should already be configured from the previous setup. The workflows use:
- Staging: `daily-task-assistant-church.web.app`
- Production: `daily-task-assistant-prod.web.app` (create when ready)

### 5. Current Staging URLs

| Service | URL |
|---------|-----|
| Frontend | https://daily-task-assistant-church.web.app |
| Backend | https://daily-task-assistant-staging-368257400464.us-central1.run.app |
| Health Check | https://daily-task-assistant-staging-368257400464.us-central1.run.app/health |

## Branch Protection Rules

Configure in GitHub repo Settings > Branches > Add rule:

### `main` branch
- [x] Require a pull request before merging
- [x] Require status checks to pass before merging
  - Select: `Backend Tests`, `Frontend Type Check`
- [x] Require approvals (1)
- [x] Do not allow bypassing the above settings

### `staging` branch
- [x] Require a pull request before merging
- [x] Require status checks to pass before merging
  - Select: `Backend Tests`, `Frontend Type Check`

### `develop` branch
- [x] Require status checks to pass before merging (optional)

## Workflow Triggers

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `test.yml` | PR to develop/staging/main, push to develop | Runs pytest + TypeScript check |
| `deploy-staging.yml` | Push to staging | Deploys to Cloud Run staging + Firebase |
| `deploy-prod.yml` | Push to main | Deploys to Cloud Run prod + Firebase (requires environment approval) |

## GitHub Environments

Create a `production` environment in GitHub repo Settings > Environments:
1. Click "New environment" > name it `production`
2. Add protection rule: "Required reviewers" > add yourself
3. This ensures production deploys require manual approval

## Testing the Pipeline

1. Create a feature branch from `develop`
2. Make a change and push
3. Create PR to `develop` → tests should run
4. Merge to `develop` → tests run again
5. Create PR from `develop` to `staging` → tests run
6. Merge to `staging` → auto-deploy to staging
7. Verify staging works
8. Create PR from `staging` to `main` → tests run
9. Merge to `main` → wait for approval → deploy to production

## Post-Deployment Verification

The deployment workflows include automatic health checks that verify:

1. **Backend Health** - Calls `/health` endpoint and checks:
   - Anthropic API configured
   - Smartsheet API configured
   - Church Gmail configured
   - Personal Gmail configured

2. **Frontend Accessibility** - Verifies the Firebase Hosting URL returns HTTP 200

If any critical service is not configured, the deployment will **fail** and alert you.

### Manual Health Check

You can manually verify the deployment by calling:
```bash
curl https://daily-task-assistant-staging-368257400464.us-central1.run.app/health | jq
```

Expected response:
```json
{
  "status": "ok",
  "environment": "staging",
  "services": {
    "anthropic": "configured",
    "smartsheet": "configured",
    "church_gmail": "configured",
    "personal_gmail": "configured"
  }
}
```

### Anthropic Connection Test

For deeper Anthropic debugging, use:
```bash
curl https://daily-task-assistant-staging-368257400464.us-central1.run.app/health/anthropic-test | jq
```

This makes an actual API call to verify the connection works end-to-end.

## Troubleshooting

### Tests fail
- Check the workflow logs in GitHub Actions tab
- Ensure all dependencies are in requirements.txt and package.json

### Deploy fails with permission error
- Verify the service account has all required roles
- Check that Secret Manager secrets are accessible

### Firebase deploy fails
- Ensure `firebase.json` exists in `projects/web-dashboard/`
- Verify the service account has Firebase Hosting Admin role

### Secrets not working after update
Cloud Run caches secrets. After updating a secret in Secret Manager:
1. Deploy a new revision: `gcloud run deploy daily-task-assistant-staging --region us-central1 --source .`
2. Or update the service to force a new revision

### "Illegal header value" or authentication errors
This usually means a secret has trailing whitespace or newline characters:
1. Go to Secret Manager in GCP Console
2. Create a **new version** of the affected secret with clean value
3. Redeploy to pick up the new version

### Gmail "invalid_client" error
The Gmail OAuth Client ID is incorrect or has trailing characters:
1. Verify the Client ID matches exactly what's in GCP Console > APIs & Services > Credentials
2. Recreate the secret with the exact value (no trailing spaces/newlines)

