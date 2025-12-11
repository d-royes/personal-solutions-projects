# Smartsheet Valid Status Values

This document is the authoritative reference for valid Smartsheet task status values.

## Active Statuses

These statuses indicate tasks that are in progress or pending action:

| Status | Description | Use When |
|--------|-------------|----------|
| **Scheduled** | Task is planned but not yet started | Default for new tasks |
| **Recurring** | Regular recurring task | Tasks that repeat on a schedule |
| **On Hold** | Task is paused/blocked | Waiting on a decision, resource, or dependency |
| **In Progress** | Actively being worked on | Task work has begun |
| **Follow-up** | Needs follow-up action | After initial work, needs additional attention |
| **Awaiting Reply** | Waiting for external response | Sent email/message, waiting for response |
| **Delivered** | Work delivered, may need confirmation | Submitted deliverable, awaiting feedback |
| **Create ZD Ticket** | Needs Zendesk ticket creation | Work tasks requiring ticket tracking |
| **Validation** | In review/validation phase | Task output needs verification |
| **Needs Approval** | Waiting for approval | Submitted for manager/stakeholder approval |

## Terminal Statuses

These statuses indicate tasks that are done. They automatically mark the **Done** checkbox:

| Status | Description | Use When |
|--------|-------------|----------|
| **Ticket Created** | Zendesk ticket has been created | After creating associated ticket |
| **Cancelled** | Task is no longer needed | Requirements changed, no longer applicable |
| **Delegated** | Task handed off to someone else | Reassigned responsibility |
| **Completed** | Task is fully done | All work finished successfully |

## Invalid Statuses (DO NOT USE)

The following are **not valid** Smartsheet status values and should never be used:

- ~~Blocked~~ → Use **On Hold** or **Awaiting Reply**
- ~~Waiting~~ → Use **Awaiting Reply** or **On Hold**
- ~~Complete~~ → Use **Completed**
- ~~Not Started~~ → Use **Scheduled**
- ~~Done~~ → Use **Completed**

## Code References

When implementing status logic, use these constants:

```python
# projects/daily-task-assistant/api/main.py
VALID_STATUSES = [
    "Scheduled", "Recurring", "On Hold", "In Progress", "Follow-up", "Awaiting Reply",
    "Delivered", "Create ZD Ticket", "Ticket Created", "Validation", "Needs Approval",
    "Cancelled", "Delegated", "Completed"
]

TERMINAL_STATUSES = ["Ticket Created", "Cancelled", "Delegated", "Completed"]
```

## Last Updated

December 11, 2025

