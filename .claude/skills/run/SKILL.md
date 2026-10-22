---
name: run
description: Implement or resume a project task using the shared, provider-neutral harness workflow.
---
Read AGENTS.md, docs/WORKFLOW.md and docs/MODEL_POLICY.md. Follow the common workflow
instead of maintaining separate Claude-only instructions. Initialize/resume a task
before editing, verify subscription model selection, select light/full mode, and
handle DONE/PARTIAL/BLOCKED worker reports explicitly. Use common CLI receipts for
tests and reviews. Do not declare DONE until check --all and the DONE transition
succeed. Respect bounded retries and report STUCK honestly when necessary.
