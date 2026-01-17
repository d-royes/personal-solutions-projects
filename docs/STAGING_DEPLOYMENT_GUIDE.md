# DATA Staging Deployment Guide

This guide covers deploying the Daily Task Assistant (DATA) to the staging environment and setting up the automated sync infrastructure.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Backend Deployment (Cloud Run)](#backend-deployment-cloud-run)
3. [Frontend Deployment](#frontend-deployment)
4. [Cloud Scheduler Setup (Automated Sync)](#cloud-scheduler-setup-automated-sync)
5. [Verification Steps](#verification-steps)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Tools
- Google Cloud SDK (`gcloud`) installed and configured
- Docker installed (for local builds)
- Node.js 18+ and npm (for frontend builds)
- Access to GCP project: `daily-task-assistant-church`

### Required Permissions
- Cloud Run Admin
- Cloud Build Editor
- Cloud Scheduler Admin
- Service Account User

### Environment Variables Reference

**Backend (Cloud Run):**
```
SMARTSHEET_API_TOKEN       # Smartsheet API token
GOOGLE_CLIENT_ID           # OAuth client ID
DTA_ALLOWED_EMAILS         # Comma-separated allowed emails
ANTHROPIC_API_KEY          # Claude API key (optional)
GEMINI_API_KEY             # Gemini API key (optional)
```

**Frontend (.env.production):**
```
VITE_API_BASE_URL          # Backend API URL (e.g., https://staging.dailytaskassistant.ai)
VITE_GOOGLE_CLIENT_ID      # OAuth client ID
VITE_ENVIRONMENT           # STAGING or PROD
```

---

## Backend Deployment (Cloud Run)

### Step 1: Build and Push Docker Image

From the `projects/daily-task-assistant` directory:

```bash
# Set variables
PROJECT_ID="daily-task-assistant-church"
REGION="us-central1"
SERVICE_NAME="data-api-staging"
IMAGE_TAG="gcr.io/$PROJECT_ID/$SERVICE_NAME:latest"

# Build the image
docker build -t $IMAGE_TAG .

# Push to Container Registry
docker push $IMAGE_TAG
```

### Step 2: Deploy to Cloud Run

```bash
gcloud run deploy $SERVICE_NAME \
  --image=$IMAGE_TAG \
  --platform=managed \
  --region=$REGION \
  --allow-unauthenticated \
  --memory=1Gi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=5 \
  --set-env-vars="SMARTSHEET_API_TOKEN=$SMARTSHEET_API_TOKEN" \
  --set-env-vars="GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID" \
  --set-env-vars="DTA_ALLOWED_EMAILS=davidroyes@southpointsda.org,david.a.royes@gmail.com"
```

### Step 3: Verify Deployment

```bash
# Get the service URL
gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)'

# Test health endpoint
curl https://your-staging-url.run.app/health
```

---

## Frontend Deployment

### Option A: Firebase Hosting (Recommended)

#### Initial Setup (One-time)

```bash
# Install Firebase CLI
npm install -g firebase-tools

# Login and initialize
firebase login
firebase init hosting

# Select:
# - Project: daily-task-assistant-church
# - Public directory: dist
# - Single-page app: Yes
# - Automatic builds: No
```

#### Deploy

From the `projects/web-dashboard` directory:

```bash
# Create .env.production with staging values
echo "VITE_API_BASE_URL=https://data-api-staging-xxxxx.run.app" > .env.production
echo "VITE_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com" >> .env.production
echo "VITE_ENVIRONMENT=STAGING" >> .env.production

# Build
npm run build

# Deploy to staging
firebase deploy --only hosting:staging
```

### Option B: Cloud Run (Static Files)

```bash
# Build the frontend
npm run build

# Deploy as static site to Cloud Run
gcloud run deploy data-web-staging \
  --source=dist \
  --region=us-central1 \
  --allow-unauthenticated
```

---

## Cloud Scheduler Setup (Automated Sync)

The automated sync system uses Cloud Scheduler to trigger bidirectional sync between Firestore and Smartsheet at user-configured intervals.

### Architecture

```
Cloud Scheduler (every 5 min)
        |
        v
POST /sync/scheduled
        |
        v
Check settings/preferences in Firestore
  - Is sync enabled?
  - Has interval_minutes passed since last_sync_at?
        |
        v
If conditions met: Run sync_bidirectional()
        |
        v
Record result to Firestore
```

### Step 1: Create Service Account (If Needed)

```bash
# Create service account for Cloud Scheduler
gcloud iam service-accounts create cloud-scheduler-invoker \
  --display-name="Cloud Scheduler Invoker"

# Grant invoker role for Cloud Run
gcloud run services add-iam-policy-binding data-api-staging \
  --region=us-central1 \
  --member="serviceAccount:cloud-scheduler-invoker@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

### Step 2: Create Cloud Scheduler Job

#### Via GCP Console

1. Navigate to: https://console.cloud.google.com/cloudscheduler
2. Click "Create Job"
3. Configure:
   - **Name:** `data-bidirectional-sync-staging`
   - **Region:** `us-central1`
   - **Frequency:** `*/5 * * * *` (every 5 minutes)
   - **Timezone:** `America/New_York`
4. Configure Target:
   - **Target type:** HTTP
   - **URL:** `https://data-api-staging-xxxxx.run.app/sync/scheduled`
   - **HTTP method:** POST
   - **Auth header:** Add OIDC token
   - **Service account:** `cloud-scheduler-invoker@daily-task-assistant-church.iam.gserviceaccount.com`
5. Configure Retry:
   - **Max retry attempts:** 3
   - **Attempt deadline:** 180s

#### Via gcloud CLI

```bash
API_URL="https://data-api-staging-xxxxx.run.app"
SA_EMAIL="cloud-scheduler-invoker@$PROJECT_ID.iam.gserviceaccount.com"

gcloud scheduler jobs create http data-bidirectional-sync-staging \
  --location=us-central1 \
  --schedule="*/5 * * * *" \
  --time-zone="America/New_York" \
  --uri="$API_URL/sync/scheduled" \
  --http-method=POST \
  --oidc-service-account-email=$SA_EMAIL \
  --attempt-deadline=180s \
  --max-retry-attempts=3
```

### Step 3: Test the Scheduler

```bash
# Manually trigger the job
gcloud scheduler jobs run data-bidirectional-sync-staging --location=us-central1

# Check logs
gcloud logging read "resource.type=cloud_scheduler_job AND resource.labels.job_id=data-bidirectional-sync-staging" --limit=5
```

### How the Scheduler Works

The scheduler runs every 5 minutes, but the `/sync/scheduled` endpoint is intelligent:

1. **Reads `settings/preferences`** from Firestore
2. **Checks if sync is enabled** (`sync.enabled = true`)
3. **Checks if enough time has passed** based on `sync.interval_minutes` and `sync.last_sync_at`
4. **Only runs sync** if both conditions are met
5. **Records result** back to Firestore

This allows users to configure their preferred sync interval (5, 15, 30, or 60 minutes) without modifying the Cloud Scheduler job.

---

## Verification Steps

### 1. Backend Health Check

```bash
curl https://your-staging-url.run.app/health
# Expected: {"status": "healthy"}
```

### 2. Settings Endpoint Test

```bash
curl -H "X-User-Email: david.a.royes@gmail.com" \
  https://your-staging-url.run.app/settings
# Expected: JSON with inactivityTimeoutMinutes and sync object
```

### 3. Manual Sync Test

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-User-Email: david.a.royes@gmail.com" \
  -d '{"direction": "bidirectional"}' \
  https://your-staging-url.run.app/sync/now
# Expected: JSON with sync results
```

### 4. Scheduled Sync Test

```bash
curl -X POST \
  -H "X-User-Email: david.a.royes@gmail.com" \
  https://your-staging-url.run.app/sync/scheduled
# Expected: {"ran": true/false, ...}
```

### 5. Firestore Verification

Check Firebase Console:
- `settings/preferences` document should exist
- Should contain `inactivity_timeout_minutes` and `sync` fields
- After sync runs, `sync.last_sync_at` should update

---

## Troubleshooting

### Cloud Scheduler Not Triggering Sync

1. **Check job status:**
   ```bash
   gcloud scheduler jobs describe data-bidirectional-sync-staging --location=us-central1
   ```

2. **Check Cloud Run logs:**
   ```bash
   gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=data-api-staging" --limit=20
   ```

3. **Verify service account permissions:**
   ```bash
   gcloud run services get-iam-policy data-api-staging --region=us-central1
   ```

### Sync Runs But No Changes

1. **Check Firestore settings:**
   - Verify `settings/preferences` exists
   - Verify `sync.enabled = true`
   - Check `sync.last_sync_at` is updating

2. **Check if interval has passed:**
   - Compare `last_sync_at` with current time
   - Ensure `interval_minutes` has elapsed

### Frontend Not Connecting to Staging Backend

1. **Verify VITE_API_BASE_URL** is set correctly in `.env.production`
2. **Check CORS** settings in backend if seeing cross-origin errors
3. **Verify OAuth client ID** matches for both frontend and backend

---

## Quick Reference Commands

```bash
# View Cloud Run logs
gcloud logging read "resource.type=cloud_run_revision" --limit=50

# List Cloud Scheduler jobs
gcloud scheduler jobs list --location=us-central1

# Pause scheduler job
gcloud scheduler jobs pause data-bidirectional-sync-staging --location=us-central1

# Resume scheduler job
gcloud scheduler jobs resume data-bidirectional-sync-staging --location=us-central1

# Update scheduler frequency
gcloud scheduler jobs update http data-bidirectional-sync-staging \
  --location=us-central1 \
  --schedule="*/15 * * * *"
```

---

## Related Documents

- [Automated Sync Settings Plan](.cursor/plans/automated_sync_settings_3dd92d30.plan.md)
- [Internal Task System Migration Plan](MIGRATION_PLAN.md)

---

*Last Updated: January 16, 2026*
