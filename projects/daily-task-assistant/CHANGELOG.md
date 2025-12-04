# Changelog

All notable changes to the Daily Task Assistant project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

*No unreleased changes*

---

## [0.3.0] - 2025-12-04

### 🎯 Context-Aware Planning & Multi-Sheet Smartsheet Integration

This release adds powerful context-awareness to DATA's planning and email capabilities, plus support for multiple Smartsheets.

### Added

#### Context-Aware Planning
- **Workspace selection**: Checkbox UI on workspace items allows multi-select
- **Add content button**: "+" button in workspace header creates empty items for direct input
- **Context-informed plans**: Selected workspace content sent to Anthropic as additional context
- **Context-informed emails**: Selected workspace items become source material for email drafts

#### Multi-Sheet Smartsheet Support
- **Work Smartsheet integration**: Added second Smartsheet for work tasks
- **Source filtering**: Work tasks excluded from "All" view, shown in dedicated "Work" filter
- **Work badge**: Shows count of urgent/overdue work tasks on Work filter button
- **Source-aware updates**: All writes (comments, row updates) go to correct sheet

#### Expanded Field Editing
- DATA can now update **9 Smartsheet fields** via natural conversation:
  - `#` (task number), `Priority`, `Contact` (flag), `Recurring`, `Project`
  - `Task` (title), `Assigned To`, `Notes`, `Estimated Hours`
- **Picklist validation**: Strict validation for select fields on write
- **MULTI_PICKLIST support**: Proper handling for Recurring field column type
- **MULTI_CONTACT support**: Proper handling for Assigned To field column type

#### Recurring Task Handling
- **Smart mark_complete**: When marking a recurring task complete, only checks "Done" box
- **Preserves recurrence**: Status remains "Recurring" to maintain the recurrence pattern
- **Done filter**: Tasks with "Done" checked are filtered out of all views

### Changed
- **Read-time validation removed**: Smartsheet field values only validated on write operations
- **Numbered priorities for Work**: Work tasks use `5-Critical`, `4-Urgent`, etc. format
- **Priority styling**: CSS attribute selectors for numbered priority classes

### Fixed
- **Pydantic v2 alias handling**: Added `populate_by_name=True` for proper camelCase field parsing
- **Contact field alias**: Added proper alias for `contactFlag` field
- **Work task sorting**: Updated priority order mappings for numbered work priorities

### Infrastructure
- **PR #12**: Deployed to staging (2m 45s)
- **8 files changed**: 197 insertions, 48 deletions

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
| 0.3.0 | 2025-12-04 | **Context-Aware Planning** + Multi-Sheet Smartsheet + 9 editable fields |
| 0.2.1 | 2025-12-03 | First production deployment |
| 0.2.0 | 2025-12-02 | First CI/CD staging deployment |
| 0.1.0 | 2025-11-XX | Initial development release |

