# Daily Task Assistant

A companion service that regularly pulls prioritized tasks from the Task Management Smartsheet and proactively assists with execution/delivery. The assistant combines data ingestion, context enrichment, and automation workflows so that high-priority items are unblocked as quickly as possible.

## Objectives
- Mirror the user's Smartsheet task list locally with rich metadata (owners, due dates, blockers, assets).
- Classify tasks by effort, risk, dependency, and automation potential to recommend next actions.
- Offer hands-on assistance (drafting emails, preparing documents, scheduling follow-ups) where automation is feasible.
- Surface concise summaries and action plans through chat or dashboard interfaces.

## Data Source & Sync Plan
1. **Connector**: Poll the Smartsheet REST API using a dedicated access token scoped to the Task Management sheet. Support incremental sync via `modifiedSince` timestamps.
2. **Normalization**: Map Smartsheet columns (Task, Status, Owner, Due Date, Notes, Attachments) to an internal schema stored in a local SQLite/Parquet cache for quick querying.
3. **Change Detection**: Emit events when new tasks arrive, deadlines change, or blockers are added. These events kick off downstream automation.
4. **Security**: Store Smartsheet credentials in `.env` / secret manager; never commit.

### Secrets & Environment
- Cursor web secret `Smartsheet` should be injected as the runtime token (e.g., export `SMARTSHEET_API_TOKEN=$(cursor secrets get Smartsheet)` before running jobs).
- Local `.env` entries should reference `SMARTSHEET_API_TOKEN` only; never persist raw tokens in repo files.
- When running in CI or other environments, configure the same `Smartsheet` secret or equivalent secure store entry with least-privilege scope.

## Core Capability Roadmap
- **Intake Pipeline**: Background worker that syncs every 5 minutes and tags tasks needing attention.
- **Prioritization Engine**: Heuristics (deadline proximity, status stalled > 48h, blocker notes) combined with optional LLM scoring for ambiguity.
- **Assistance Library**: Reusable actions (draft communication, create Jira tickets, prep meeting agendas, summarize attachments) orchestrated via prompt templates and external APIs.
- **Progress Tracking**: Update Smartsheet rows (comments or status) when automations complete to keep humans in the loop.
- **Interface**: CLI/chat endpoint plus optional lightweight web UI for reviewing queued assists.

## Proposed Architecture
- `sync/collector` — handles Smartsheet API calls, pagination, and caching.
- `analysis/prioritizer` — ranks tasks, identifies blocking dependencies, and chooses assist strategies.
- `actions/` — modular executors for outbound emails, document drafting, scheduling, etc.
- `interfaces/` — adapters for CLI, chat, or future Notion/Slack integrations.
- `storage/` — persistence layer (SQLite now; can upgrade to Postgres + Redis for scale).

## Next Steps
1. Define the Smartsheet schema + column IDs in `config/smartsheet.yml`.
2. Scaffold the sync worker (likely Python FastAPI + Celery/APS) with local cache.
3. Draft a minimal CLI that lists tasks needing assistance and suggests one automated action each.
4. Add integration tests that mock Smartsheet responses to validate the sync + prioritization pipeline.

This README will evolve as components land; the first milestone is establishing reliable Smartsheet ingestion plus a CLI prototype that proves out automated assistance on real tasks.

## Running the CLI Stub
The repository now includes a starter CLI (`projects/daily-task-assistant/cli.py`) that exercises configuration loading and prints placeholder tasks. It is intentionally simple so new capabilities can be layered in without refactoring.

1. Make sure Python 3.10+ is available.
2. Export the Smartsheet token (Cursor will inject the `Smartsheet` secret automatically):
   ```bash
   export SMARTSHEET_API_TOKEN=$(cursor secrets get Smartsheet)
   ```
3. Run the CLI:
   ```bash
   python projects/daily-task-assistant/cli.py list --limit 2
   ```
   The command prints a small table of stubbed tasks plus confirmation that the token/environment resolved. As we wire up the real Smartsheet sync, this command will show live data. Use `python projects/daily-task-assistant/cli.py check-token` to verify configuration without listing tasks.
