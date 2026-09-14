# Agent Ledger release specification · 0.1.0

## Product promise

A developer can clone the source, run one Python command, and recover local Claude Code/Codex context and investigate recorded usage offline. The report explains what is recorded, what can only be estimated, and what activity correlates with a response. It does not adjudicate waste or reconcile account billing.

## Release decisions

1. **Correct totals take priority over complete-looking charts.** Native provider/response identities are unioned. Conflicting counts are excluded. Missing subsets stay missing. Legacy cumulative amounts appear as session-level evidence, never fabricated model responses.
2. **Partial coverage is a first-class result.** Skipped records, counter resets, ambiguous mirrors, missing models, cache writes without rates, and retained missing sources have explicit unavailable values or diagnostics. An empty history is a usable state.
3. **The public repository must be independent of private history.** Synthetic generators, tests, and screenshots are committed; no real rollouts or transcript extracts. Cache defaults are outside the checkout. The local report remains private.
4. **Bound memory by record size, not rollout size.** Stream complete JSONL lines, enforce a configurable byte cap, drain oversized lines, store bounded observed previews, and page response/activity data. No giant transcript embedded in HTML.
5. **The server is a private loopback application.** No arbitrary filesystem serving, remote binding, external assets, telemetry, or log evaluation. API access needs a capability and same-origin request checks.
6. **Show evidence without inventing causation.** Findings require recognized exact actions and output evidence. Observed bytes are not billed tokens; nested orchestration gets no fractional cost allocation.

## Usage-inspector scope

- Session overview with explicit UTC date range (30 calendar dates by default), full-path project grouping, model/Astra filters, credit/token sorting, totals and coverage.
- Session/turn/descendant selection with a union of native responses.
- Stacked recorded-token and reference-credit views, paged at 100 responses; native selector and keyboard-operable bars.
- Per-response model, speed assumption, provenance, token subsets, credit allocation, recorded context size and optional recorded limit.
- Paged preceding tool results, plain-text previews, observed byte/character size, explicit or chronological association.
- Findings: largest results, exact unchanged observed output, repeated recorded failures, largest input increases, most reasoning output.
- Session activity browser, including unassociated calls/results and compaction markers; legacy amount evidence; import diagnostics.
- Per-agent totals for Claude Code and Codex in the active filter, and an agent filter that narrows every view. Token volume is comparable between agents; credits are not.
- Conversation replay pairing each recorded message with the usage of the responses attributed to it, a running session total, following tool calls, failures and context resets. Attribution is positional: a response is attributed to the message it preceded in the same source file, which is an ordering fact and not a causal claim.
- Tool breakdown by observed results, recorded failures, returned bytes and largest single result, scoped to the selected session or to all filtered history.
- Minimal neutral workspace: unboxed overview values, compact session navigation, one primary chart, and separate Response/Conversation/Tools/Findings/Activity/Coverage tabs.
- System-derived initial light/dark theme and 360/736/1024+ px layouts. Mobile session browsing is an explicit disclosure.

## Deliberate conservative limits

- Legacy first snapshots/deltas are observation-time session amounts and can represent multiple responses or earlier work. Legacy child history is excluded because copied ancestry lacks unique IDs. Ambiguous native/legacy overlap is excluded and diagnosed rather than apportioned.
- Native ownership uses explicit recorded thread IDs. Parent relationships alone do not establish that all child activity is new. Provenance exposes each owner/session appearance.
- A tool result counts as failed only where its source recorded an exit status or an error flag: an explicit field, a recognized process-exit line, a complete per-command JSON chunk in an exec result, or a Claude error flag. No status is scraped from surrounding prose. A tool that records none reports no failures rather than none having occurred, so failure counts are not comparable between agents that record differently.
- Model and speed resolve from the preceding same-turn context, or the first later context if no earlier context exists. No inference from response latency or reasoning effort. Unknown formats/settings remain unavailable.
- Exact command recognition preserves all arguments and working-directory context. This favors missed matches over falsely merging different operations. Wrapper differences and ambiguous tools can prevent findings.
- Missing source files are retained with warnings, so a temporary permissions/discovery issue cannot silently erase coverage. A new cache rebuild intentionally resets that policy.
- Replaced/truncated files rebuild using inode/device, file size, modification time, and bounded prefix/checkpoint fingerprints. Arbitrary interior edits with unchanged fingerprints during append cannot be detected without a full rehash; rollouts are assumed append-only between replacements.
- No on-demand raw source-file reads or export route in v0. Bounded cached previews and source byte offsets supply evidence while keeping filesystem access narrow.

## Acceptance evidence

The regression suite covers arithmetic and rates, deduplication and provenance, source restarts/replacements, legacy baselines/deltas/transitions/gaps, output matching, scope filters, and HTTP security. A generated large-file smoke test checks allocation behavior and idempotence. Optional browser tests check interaction, offline asset use, inert previews, empty states, themes, and responsive widths. See [VALIDATION.md](VALIDATION.md) for executed checks and platform limitations.

## Deferred

Live hooks and alerts; account billing reconciliation; API-dollar estimates; near-duplicate command heuristics; model-generated recommendations; exact tool/file costs; hosted/multiuser access; share-safe export; Cursor and cloud-only agents.

## Combined workspace scope

The release retains the accounting contract above and adds local Claude Code conversation/usage import, bounded conversation search, recent sessions, a 90-day UTC activity grid, explicitly saved project/global context, text/Markdown import, and an optional read-only MCP server. The first screen is Start, with evidence-backed explanations and practical next steps. The original detailed inspector is available under Usage.

No standalone website, hosted service, built-in AI chat, automatic memory extraction, agent write tools, or configuration mutation is included. Both humans and optional connected agents can retrieve saved context. The six MCP tools share the browser's database and bounded read/query code. See README and ARCHITECTURE for current commands and behavior.

Claude native message IDs identify usage independently of transcript fragments. Inclusive input is ordinary input plus cache reads plus cache creation. Monotonic streaming snapshots update one response; inconsistent snapshots are marked incomplete/excluded rather than summed. Recorded historical branches are not excluded merely because they are no longer on a conversation's active path: they may still represent work performed. Native identity deduplication addresses copied work. Claude credit conversion remains unavailable.

The combined cache uses a new default directory and filename, so prior Usage Lens caches are not silently reused without indexing conversation text. Saved notes are private durable data within that cache; deleting or selecting another cache affects their availability. Historical citations never become executable instructions.

## 0.2.0 project recovery

Start offers recent project shortcuts and a project briefing. The briefing collects the latest assistant excerpt from each of three recent sessions and up to six saved notes, with citations, clipping labels, and explicit historical-report status. Users supply the next objective and review an editable handoff before copying or saving. No model is invoked and no inferred task status is presented as fact. Per-project drafts are held only in page memory; explicit saves persist context.

The read-only `project_briefing` MCP tool exposes the same bounded collection. Start defers usage analysis until an explicit project review request. Existing cache data remains compatible.
