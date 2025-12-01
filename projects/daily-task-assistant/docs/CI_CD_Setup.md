# CI/CD Setup Guide

This document describes how to set up the GitHub Actions CI/CD pipeline for the Daily Task Assistant.

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

Ensure these secrets exist in Secret Manager:
- `SMARTSHEET_API_TOKEN`
- `ANTHROPIC_API_KEY`
- `CHURCH_GMAIL_CLIENT_ID`
- `CHURCH_GMAIL_CLIENT_SECRET`
- `CHURCH_GMAIL_REFRESH_TOKEN`
- `PERSONAL_GMAIL_CLIENT_ID`
- `PERSONAL_GMAIL_CLIENT_SECRET`
- `PERSONAL_GMAIL_REFRESH_TOKEN`

### 4. Firebase Hosting

Firebase Hosting should already be configured from the previous setup. The workflows use:
- Staging: `daily-task-assistant-church.web.app`
- Production: `daily-task-assistant-prod.web.app` (create when ready)

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

