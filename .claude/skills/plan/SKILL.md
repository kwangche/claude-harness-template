---
name: plan
description: Create or revise a bounded plan without implicitly implementing the request.
---
Read AGENTS.md and docs/WORKFLOW.md. For a plan-only request, provide the plan and
stop; do not initialize implementation or require fabricated test receipts. For
implementation, write docs/PLAN.md with goal, acceptance criteria, assumptions,
scope exclusions, risks, task IDs, dependencies, file ownership and verification.
Choose light/full mode based on risk and coupling rather than a fixed line limit.
Full mode requires a recorded PASS plan review before PLANNED; exhausted reviews
become STUCK. Do not change requirements just to make a failing implementation pass.
