# Claude Code adapter

@AGENTS.md

Common workflow: `docs/WORKFLOW.md`. Model policy: `docs/MODEL_POLICY.md`.

Use `/run`, `/plan`, and `/verify` as convenience entry points. Skill auto-selection
is model-dependent; use `/run` explicitly when needed. Project agents inherit the
selected commander model by default, so no paid/unavailable model ID is hardcoded.
Native per-call worker model overrides are optional and must be in the verified
subscription inventory.

SessionStart initializes a baseline; compaction/resume never resets an existing
session. Hooks do not discover subscription entitlements or change the main model.
Use the same `HARNESS_SESSION_ID` in workers and the CLI (the hook payload's
`session_id` is the fallback). The Stop hook checks common receipts, including those
created by tester subagents. It never searches the parent's transcript for Bash.

Hook paths are rooted at `${CLAUDE_PROJECT_DIR}` and quoted for spaces. The runtime
currently requires Python 3.11+ on PATH. If entering a worktree mid-session, start
a separate harness task from that worktree; do not reuse main-checkout receipts.
