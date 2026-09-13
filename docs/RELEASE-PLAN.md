# Combined local release

Working name: Agent Ledger. A public MIT source repository that runs locally; no marketing site, hosted service, account, telemetry, or bundled model.

## User outcomes

1. Recover a prior decision: search Claude Code and Codex conversations, open a bounded source excerpt, and save an explicit project note.
2. Understand usage: start with an explanation of observed repetition, large tool results, or growing context; inspect evidence and get a concrete prompt to use in the next session. No invented waste score, savings claim, or inferred bill.
3. Reuse context: optionally register a read-only stdio MCP server with an existing agent. The client starts/stops it. Retrieved context can be sent by that client to its model provider; local storage does not make a connected cloud model local.

## Implementation decisions

Keep the tested Python accounting/import engine and one SQLite cache. Reimplement the useful memory workflows in this runtime rather than require users to operate Python and Node servers. Preserve the source projects separately. Import only explicitly supported local transcript directories; never agent credentials/configuration. Claude usage includes cache creation/read in input and has no Codex credit conversion. Stream fragments merge by message/request identity; copied appearances deduplicate, conflicting source totals remain excluded.

Implemented: the home view leads to findings, recent sessions, and a clickable daily activity view. Search covers bounded user/assistant text plus explicitly saved notes. Notes are authored by the user, not automatically promoted from old transcripts. Knowledge text/Markdown can be imported explicitly. Evidence remains untrusted text.

MCP exposes bounded read-only search, read, notes, and usage findings. No agent write tools, configuration edits, hooks, hidden model calls, or OS daemon installation in this release. The local app has explicit refresh; an optional foreground watch loop keeps the index current. The agent connection is useful without the browser process running.

## Release gates

- Synthetic Claude and Codex data only in source, tests, demo, and screenshots.
- Tests for stream deduplication, append/replacement, malformed records, redaction, search isolation, note lifecycle, actionable findings, and MCP lifecycle/error handling.
- Browser flows: first run, search to evidence to note, insight to response, daily/project filters, empty/error states, keyboard navigation, narrow widths, light/dark.
- Preserve accounting and HTTP security regressions; test bounded request bodies and independent MCP process shutdown.
- Public artifact allowlist, privacy scan, license review, reproducible local instructions, clean publication history. Publish only after the concrete release is verified.
