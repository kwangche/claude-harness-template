---
name: verify
description: Verify current changes using execution evidence and actual review results.
---
Read docs/WORKFLOW.md. Run configured checks through .harness/cli.py using the
shared session ID. A matching current PASS receipt can be reused; rerun after code
or configuration changes, or after merging parallel work. Review the actual diff,
record the real reviewer and independent/sequential mode, and run check --all.
Transition to DONE only after it succeeds. On failure, refine within budget or
record STUCK/BLOCKED with an actionable explanation. Never count NO_TESTS, skipped
checks, a failed process, or an unverified model switch as success.
