# Changelog

## Unreleased — project questions and usage investigation

- Ask why a project decision was made: review locally retrieved evidence, then request a cited answer through the installed Claude Code CLI. Follow-up questions stay scoped to the project.
- Review proposed memory cleanup and edit an answer as a saved decision. Models cannot change notes; saves and deletes remain explicit.
- Rank a session’s largest recorded tasks and connect repeated failures, repeated output, large results, and context growth to evidence-backed optimization experiments.
- Bound optional answers with one active subprocess, cancellation, a two-minute deadline, and an output limit. Demo answers never invoke a model.
- Replay a session as it happened: each recorded message shows the tokens attributed to it, a running session total, the tool calls that followed, and any failures or context resets.
- Break a scope down by tool: observed results, failures, text returned, and the largest single result, for one session or all filtered history.
- Compare Claude Code and Codex side by side, and narrow every usage view to one agent.
- Mark recorded compactions on the context chart, so a drop in the next bar has a visible cause.
- Show a failure badge on tool results that recorded a non-zero exit or an error flag.
- Record a Claude compaction as an activity, matching the Codex adapter; it was previously counted but never stored.
- Extend the daily grid from 90 days to the full 366 days already returned, and scroll it on narrow screens.
- Give the synthetic demo an interleaved conversation and Claude tool activity so these views have something to show.
- Read the exit status Codex records inside each exec result chunk. A script runs several commands and each one
  reports its own status, so results that failed were previously counted as successful. On a real history this
  moved Codex from 0 recorded failures to 855 of 11,459 observed results, with no other tool affected.
- Lead the README with a recorded walkthrough of the demo instead of a static screenshot, and regenerate every
  screenshot against the current interface.

## 0.2.0 — project recovery and handoffs

- Start with a project briefing: recent recorded updates, saved decisions, and direct source links.
- Prepare an editable handoff with your next objective; copy it into any agent or save it as project context.
- Keep unsaved drafts separate while switching projects; repeat saves update the handoff within the editing session.
- Add a read-only `project_briefing` MCP tool.
- Defer usage analysis until a project review is requested.

- Avoid revisiting already-linked tool results when associating new responses; preserve existing caches and accounting.
- Replace per-file terminal spam with named agent stages, elapsed time, current-file percentages, and an explicit ready message.

## 0.1.0 — combined local release

- Local Claude Code and Codex history in one workspace; no website or hosted service.
- Start with measured usage patterns, explanations, next steps, and evidence links.
- Search conversation excerpts, browse surrounding messages, and save explicit project context.
- Create, edit, delete, and import text/Markdown notes; preserve source citations.
- Optional read-only stdio MCP tools, with no hidden model calls or agent-setting changes.
- Preserve response accounting, conservative coverage, reference credits, and detailed tool evidence from Usage Lens.
- Synthetic demo, privacy checks, and cross-platform CI definition. See validation for executed checks and limits.
