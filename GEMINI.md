# Gemini CLI adapter

@AGENTS.md

Use `docs/WORKFLOW.md` and the common Python CLI for state and validation. Choose
an available subscription model from the Gemini CLI model picker and record it in
the inventory before routing. No Gemini model version is hardcoded.

This adapter provides context and CLI integration; it does not install Gemini
event hooks. Run `check --all` before declaring DONE and enforce `harness-ci` at
merge time. If native subagents are unavailable, record sequential review mode.
