# Autonomous Chat & History Integration

## Vision
- Persistent per-task conversations stored in Firestore.
- Assistant persona: problem solver, project manager, motivational partner.
- Future action expansion (email today, Chrome/other automations tomorrow).

## Backend Plan
1. Extend POST /assist/{rowId} to accept user instructions and a conversationId/history payload.
2. Add GET /assist/{rowId}/history to fetch stored conversation turns.
3. Firestore schema: conversations/{taskId}/messages/{timestamp} storing role, text, plan snapshot, metadata.
4. execute_assist consumes prior history, seeds Anthropic prompt accordingly, writes the new assistant turn plus the triggering user instruction.
5. When Smartsheet status enters a completed state, archive/delete the conversation to keep storage lean.
6. Activity log entries reference conversationId + messageId for traceability.

## Frontend Plan
1. Assistant panel gains a chat thread (You vs Assistant bubbles) beneath the plan output.
2. Load history on task selection via the new history endpoint; store in local state.
3. Message composer posts to /assist/{rowId} with accumulated history; append responses immediately.
4. Original Run Assist button seeds the conversation if empty (first assistant turn).
5. Provide persona-tuned quick tips in the composer placeholder (e.g., "Ask for a shorter summary").

## Prompt & Persona
- Emphasize project management cadence: confirm goal, suggest next steps, flag blockers, keep tone encouraging.
- When history exists, reference prior assistant outputs ("As drafted earlier").
- Respect instructions like "scrap the last change" by checkpointing previous plan text.
- Maintain motivational tone ("You've got this", "Nice progress") while staying concise; avoid empty cheerleading.

## Validation Plan
1. Task with long notes: ensure assistant summarizes and conversation toggle works.
2. Blocked task (status "Waiting"): assistant should surface blockers and propose follow-ups.
3. Multi-step follow-up: send at least two user instructions and verify assistant references prior context.
4. Persistence test: reload page, reselect task, confirm conversation restores.
5. Completion test: mark task as completed (simulate) and verify history cleared.

## Open Questions / Next Steps
- Consider versioning for future action types (email vs Chrome automation).
- Evaluate cost of storing full plans vs deltas per message.
- Later: add ability to tag follow-up actions as accepted/applied directly from chat.
- Investigate automatic persona tweaks when new action types (Chrome automations) are available.

## Validation Results — 2025-11-29
- **Long-note task (Safety Office Information, Smartsheet live data)**  
  - UI: note truncation + "Show full note" toggle verified in both task tile and assistant panel.  
  - Assist output summarized multi-paragraph context and generated matching email draft (`web-dashboard-plan.png`, `web-dashboard-chat4.png`).  
  - Conversation bubble persisted across page reload and re-auth (`safety-after-reload.png` + `safety-after-reload-chat.png`).  
  - Risk: LLM template still verbose; consider follow-up prompts for shorter copy.

- **Blocked task (Schedule onboarding with vendor, stub data)**  
  - Data source switched to `stub` to exercise deterministic dataset.  
  - Assist plan called out "status blocked" and explicitly listed unblock steps and Gmail draft (`stub-assist.png`).  
  - Chat history stored per task; API `GET /assist/1002/history` returned assistant + user entries (`ConvertTo-Json` output captured).

- **Multi-turn instructions**  
  - User instruction "Need brief follow-up email" sent via chat composer (see `stub-multiturn.png`).  
  - API history shows user turn + subsequent assistant response appended; UI currently shows assistant bubbles but template fallback does not yet rephrase email.  
  - Action item: once Anthropic integration is live, assert that the follow-up response references the user's request (tracked separately).

- **Persistence across sessions**  
  - Reloaded `http://localhost:5173`, re-authenticated via dev bypass, and reselected tasks.  
  - Existing history reloaded immediately for both live and stub tasks (`loadConversation ... [object Object]` console logs, `safety-after-reload.png`).  
  - Confirms Firestore/file fallback survives process restarts.

- **Completion / reset behavior**  
  - Simulated completion by calling `POST /assist/1002` with `{"resetConversation":true}`; verified history cleared via `GET /assist/1002/history` (Count = 1).  
  - Front-end picks this up automatically on next load since `/history` endpoint now returns a single assistant entry seeded post-reset.

- **Known gaps surfaced**  
  - Template-based assist responses ignore user instructions until Anthropic API is enabled.  
  - Conversation UI shows assistant bubbles; upcoming work should expose user bubbles inline for easier visual trace.
