# Changelog

All notable changes to the Daily Task Assistant project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added

#### F1: Label Validation & Smarter Rules (2025-12-20)
- **Account-specific allowed labels**: Church (9 labels) and Personal (6 labels) have curated label sets
- **New endpoint**: `GET /email/rules/{account}/allowed-labels` returns valid labels per account
- **Improved Haiku prompt**: Added RULE SUGGESTION GUIDELINES, WHEN TO SUGGEST RULES, and PATTERN RECOGNITION sections
- **No default fallback**: DATA only suggests rules when there's a clear pattern match (removed "1 Week Hold" default)
- **F7 Parallel Prompts**: Added to backlog for future consideration (split unified prompt into 3 focused parallel prompts)

#### Staging Deployment (2025-12-20)
- **PR #18 merged**: F1 Persistence Layer deployed to staging
- **CI/CD docs updated**: Custom domain URLs (`staging.dailytaskassistant.ai`, `dailytaskassistant.ai`)
- **Test fixes**: 6 tests updated for new label validation behavior

#### F1: Complete Persistence Layer (2025-12-19)
- **Suggestions persist across refresh**: Action suggestions saved to Firestore via `suggestion_store.py`
- **Rules persist across refresh**: Rule suggestions saved to Firestore via `rule_store.py`
- **Last Analysis Audit**: Settings page shows breakdown per account (emails fetched, tracked, dismissed, Haiku analyzed, suggestions/rules/attention generated)
- **Cross-machine sync**: Analysis results persist to Firestore, visible from any machine
- **Storage Key Architecture**: Documented GLOBAL vs ACCOUNT keying strategy in `docs/STORAGE_ARCHITECTURE.md`

#### Email Dashboard UI Improvements (2025-12-19)
- **Clickable dashboard tiles**: Click Unread, Rules, Suggestions, or Attention tiles to navigate to that tab
- **Suggestions tile highlighted**: Yellow styling to emphasize importance for Trust Gradient
- **Suggestions count badge**: Tab shows count like Rules and Attention tabs
- **Email cache persistence**: Cache survives Task/Email mode switches (state lifted to App.tsx)

### Fixed

#### Persistence Bug Fixes (2025-12-19)
- **Duplicate endpoint removed**: Two `/email/suggestions/{account}/pending` endpoints caused all suggestions to have same `number`, making approve clear all suggestions
- **Stale cache on account switch**: Cache now always updates, even when response is empty (prevents showing stale data from other account)
- **Zombie uvicorn processes**: Documented fix for orphaned child processes holding old code on Windows

#### Workspace Context Selection (2025-12-14)
- **Multi-select workspace items for Plan generation**: Check workspace cards to include as context when generating plans
- **Multi-select workspace items for Email drafts**: Selected workspace content included in email draft generation
- **"N items selected for context" indicator**: Shows how many workspace items are selected
- DATA references selected workspace content in plans and emails when relevant

#### Email Rich Text Rendering (2025-12-14)
- **Email drafts render as HTML**: Bold, italic, bullet lists, numbered lists, and paragraphs display properly
- Added `_convert_markdown_formatting()` for markdown-to-HTML conversion
- Enhanced `_convert_to_simple_html()` to handle all common formatting patterns
- API returns `bodyHtml` field alongside plain text `body`

#### Workspace Context in Chat
- **Selected workspace items now visible to DATA**: Check workspace cards to include their content in chat messages
- DATA can reference and analyze workspace content directly in responses
- Fixed Pydantic model config for proper alias mapping (`workspaceContext` → `workspace_context`)

#### Assistant Panel Features
- **Workspace "+" button**: Manually add empty cards to workspace for custom context
- **Clear plan button**: Remove current plan before regenerating (visual confirmation)
- **Improved button styling**: Consistent styling between plan and workspace controls

#### Developer Scripts
- **`reset-backend.ps1`**: Kill hung Python processes + restart backend with env vars
- **`reset-frontend.ps1`**: Kill hung Node processes + restart frontend
- Both scripts clean up zombie processes that can hold ports

#### E2E Tests
- **Assistant Panel test suite**: 16 new Playwright tests covering:
  - Workspace management (add, clear, checkbox selection)
  - Plan management (generate, clear, push to workspace)
  - Workspace context in chat integration
  - Conversation button styling verification

### Fixed
- **Clear plan no longer disengages from task** (2025-12-14): Added `isEngaged` state separate from plan state. Clearing the plan keeps you engaged with the task.
- **Reset scripts no longer kill Claude Code** (2025-12-14): Removed aggressive process killing that terminated all background Node/Python processes. Scripts now only kill the specific process on the target port.
- **Conversation button spacing**: Changed from `space-between` to `gap: 6px` for proper button proximity
- **Workspace controls positioning**: Moved controls away from scrollbar (`right: 20px`)

### Security
- **Removed PII from test_conversations/**: Real conversation data with names, emails, and phone numbers removed from git tracking and added to .gitignore

---

## [0.3.1] - 2025-12-12

### 🔍 Smarter Email Attention Detection

This release significantly improves the email attention detection system with broader scanning and more accurate pattern matching.

### Added

#### Broader Email Scanning
- **Account-specific label scanning**: Attention scan now looks beyond inbox
  - **Church**: Scans Admin, Ministry Comms, Personal, Unknown labels
  - **Personal**: Scans 1 Week Hold, Admin, Transactional, Personal labels
  - Excludes Junk, Promotional, Trash from scanning
  - Uses 7-day lookback window

#### New Attention Patterns
Based on analysis of real inbox data:
- `pending purchase request` - Procurement reminders
- `awaiting delivery/approval/response/review` - Items waiting on action
- `approval status` - Purchase orders needing review
- `fwd:` prefix - Forwarded emails (potential delegations)
- `invoice` - Proactive payment tracking (catch before past due)

#### Enhanced UI
- **Labels on Attention cards**: Email labels now displayed as badges on attention items
- **Task status in Dashboard**: Email cards show `📋 PENDING` / `IN_PROGRESS` / `COMPLETED` badge when task exists
  - Consistent styling between Dashboard and Attention tabs
  - Prevents duplicate task creation

### Changed
- **Refined "please" pattern**: Now only triggers on action verbs (review, approve, confirm, check, update, submit)
  - Avoids false positives from "please add" in prayer requests
- **Soft exclusions**: Prayer requests, newsletters, elder assignments, weekly notifications don't trigger attention on their own

### Fixed
- **Email detail panel**: Selecting an email from Attention tab now correctly displays in DATA panel
  - Added `fetchedEmail` state to store full email details for non-inbox emails

### Backlog
- Added "Dismissed Attention Cache" feature (Medium Priority)
  - Track dismissed email IDs with 7-day TTL
  - Prevents nagging about already-reviewed emails

---

## [0.3.0] - 2025-12-12

### 🚀 Email Reply Feature & Enhanced Email-Task Integration

This release delivers a complete email reply workflow with AI assistance and significant improvements to email-task integration.

### Added

#### Email Reply Feature
- **Full email body loading**: Click on any email to load the complete message content
- **Expand/collapse toggle**: Arrow button to show/hide full email body in DATA panel
- **Thread context with AI summarization**: Gemini Flash summarizes thread history for context
- **Reply & Reply All buttons**: Quick action buttons in the DATA panel
- **AI-generated reply drafts**: DATA generates human-like responses based on email context
- **Conversational reply trigger**: Say "draft a reply" in chat and DATA opens the reply panel
- **Tiptap rich text editor**: Full formatting support (bold, italic, lists, links) for email body
- **Smart recipient handling**: From account defaults based on active account, CC recipients pre-filled

#### Email-Task Integration
- **Task creation icon on Dashboard emails**: Small 📋 icon in top-right corner of every email
  - Works in Recent Messages and Search Results
  - Click to instantly open task creation form
- **Task exists indicator**: Emails with linked tasks show "📋 Task exists" badge
- **Project field**: Task creation form now includes Project dropdown
- **Email Tasks filter**: New filter in Task panel to view Firestore-created tasks

#### Email Suggestions Enhancement
- **Skip already-labeled emails**: Suggestions no longer appear for emails with custom labels

### Changed
- **Dark theme email readability**: HTML email content now has proper color contrast
  - White text on dark background
  - Blue links
  - Subtle blockquote styling
  - Table border styling
- **Removed bullet point restriction**: EMAIL_REPLY_SYSTEM_PROMPT no longer discourages bullets

### Technical
- **API Endpoints Added**:
  - `GET /email/{account}/message/{message_id}` - Fetch full email with body
  - `GET /email/{account}/thread/{thread_id}` - Get summarized thread context
  - `POST /email/{account}/reply-draft` - Generate AI reply draft
  - `POST /email/{account}/reply-send` - Send reply with proper threading headers
- **EmailMessage dataclass extended**: body, bodyHtml, attachmentCount, attachments fields
- **Gmail threading support**: In-Reply-To, References headers for proper thread continuation

---

## [0.2.1] - 2025-12-03

### 🚀 First Production Deployment!

This release marks the **first production deployment** of the Daily Task Assistant.

### Added
- **Production environment**: Fully operational at `daily-task-assistant-prod.web.app`
- **Firebase multi-site hosting**: Separate staging and production hosting targets
- **IAM configuration**: Production Cloud Run service account with Secret Manager access

### Infrastructure
- **Production URLs**:
  - Frontend: https://daily-task-assistant-prod.web.app
  - Backend: https://daily-task-assistant-prod-368257400464.us-central1.run.app
- **OAuth configuration**: Production origin added to Google OAuth client
- **Deployment time**: ~8 minutes via CI/CD pipeline

---

## [0.2.0] - 2025-12-02

### 🚀 First Staging Deployment via CI/CD Pipeline

This release marks the first successful automated deployment to staging using our new CI/CD pipeline.

### Added

#### Security & Authentication
- **Email allowlist**: Only `davidroyes@southpointsda.org` and `david.a.royes@gmail.com` can access the app
  - Backend returns 403 Forbidden for unauthorized emails
  - Frontend shows error message before attempting API calls
  - Configurable via `DTA_ALLOWED_EMAILS` environment variable
- **Auth persistence**: Login state now survives page refresh
  - Google OAuth tokens persisted to localStorage
  - Automatic token expiry validation (tokens valid ~1 hour per Google's policy)
  - Periodic expiry check every 5 minutes while app is running

#### Contact Feature
- **AI-powered entity extraction**: Contact search now uses Anthropic for Named Entity Recognition (NER)
  - Finds names and organizations embedded in prose text
  - Falls back to regex patterns if AI extraction unavailable
  - Increased confirmation threshold from 3 to 10 entities

#### CI/CD Pipeline
- **GitHub Actions workflows**: Automated testing and deployment
  - `test.yml`: Runs pytest + TypeScript type check on PRs
  - `deploy-staging.yml`: Auto-deploys to Cloud Run + Firebase on merge to `staging`
  - `deploy-prod.yml`: Deploys to production on merge to `main` (requires approval)
- **Post-deployment verification**: Health checks validate Anthropic, Smartsheet, and Gmail configuration
- **Branch protection rules**: PRs required, status checks must pass

### Changed

#### Research Feature
- **Improved prompt**: Research now focuses on deeper understanding, not generic tool comparisons
  - Surfaces pros/cons, best practices, and alternative approaches
  - New sections: Key Insights, Approach Options, Getting Started
  - Explicitly avoids product/tool comparisons with pricing
- **Better formatting**: Fixed bullet point line breaks in Research/Summarize output
  - Removed Anthropic's internal reasoning from output
  - Collapsed multiple newlines for cleaner display

#### Email Draft
- **Fixed JSON parsing**: Handles markdown code fences (` ```json `) in Anthropic responses

#### Frontend
- **Updated branding**: Tab title now "DATA - Task Assistant" with custom favicon
- **Removed unused state**: Cleaned up `researchResults` and `summarizeResults` (now added directly to workspace)

### Fixed
- Backend tests now include test email in allowlist
- Auth cache cleared before app import in tests
- Contact status banner displays correctly regardless of workspace content

### Infrastructure
- **Staging URLs**:
  - Frontend: https://daily-task-assistant-church.web.app
  - Backend: https://daily-task-assistant-staging-368257400464.us-central1.run.app
- **Secret Manager**: 10 secrets configured (Smartsheet, Anthropic, Church Gmail x4, Personal Gmail x4)

---

## [0.1.0] - 2025-11-XX

### Added
- Initial release with core functionality
- Smartsheet integration for task management
- Anthropic Claude integration for AI assistance
- Gmail integration for email drafting and sending
- React web dashboard with Google OAuth
- FastAPI backend with conversation history
- Activity logging to Firestore
- CLI tools for task management

### Features
- Task list with priority sorting
- AI-generated plans with next steps and efficiency tips
- Research capability with web search
- Task summarization
- Contact search
- Email draft generation and sending
- Conversation history per task
- Feedback collection system

---

## Version History

| Version | Date | Milestone |
|---------|------|-----------|
| 0.3.1 | 2025-12-12 | **Smarter Email Attention Detection** |
| 0.3.0 | 2025-12-12 | Email Reply Feature & Email-Task Integration |
| 0.2.1 | 2025-12-03 | First production deployment |
| 0.2.0 | 2025-12-02 | First CI/CD staging deployment |
| 0.1.0 | 2025-11-XX | Initial development release |

