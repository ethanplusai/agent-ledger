# Architecture

Agent Ledger is one Python standard-library application with a private SQLite cache and static browser interface. There is no hosted backend, asset CDN, bundled model, Node runtime requirement, or build step.

## Boundaries

`ledger.py` calls the compatible `report.py` entry point. It resolves history roots and a separate cache, runs an incremental import, and serves the UI on capability-protected loopback. `--mcp` instead opens an existing database and communicates with an agent through newline-delimited JSON-RPC over stdio. The browser server and MCP process may operate independently. `--watch` is an optional foreground refresh thread, not an installed daemon.

`lens/importer.py` streams Codex records with byte-bounded lines, resume fingerprints, and transactional checkpoints. `lens/claude.py` reuses those mechanics for Claude Code. Native response identities are separate from source appearances. Copied responses union; conflicting usage signatures are excluded. Claude stream fragments update one source appearance rather than adding totals. Claude input is normalized to include cache reads and creation. No cross-provider credit mapping is inferred.

`lens/storage.py` contains the source, session, context, usage-appearance, activity, diagnostic, conversation-excerpt, FTS5, and curated-note tables. Source replacement cascades to imported material; curated notes survive. AUTOINCREMENT excerpt/note IDs prevent deleted citations from silently resolving to newly allocated rows within the same database. Citations are database-local, not portable across rebuilds in a different cache.

`lens/memory.py` captures bounded user/assistant text, searches excerpts and saved notes, retrieves a selected excerpt with neighbors and pagination, and creates evidence-backed review suggestions. Search is lexical, matches all entered words, and uses parameterized FTS expressions rather than accepting raw FTS syntax. Notes are explicitly authored or imported by the user, never automatically promoted from transcripts. Project scope uses the recorded full working-directory path, not inferred Git-root grouping.

`lens/privacy.py` redacts common credential patterns before storing conversation text and notes, and before storing activity previews. Redaction is best effort; private business context, personal paths, and uncommon secrets may remain. Byte counts and hashes describe original observed outputs, not the redacted preview. No private source material is part of the release.

`lens/query.py` implements unioned accounting scopes, pagination, findings, and provenance. Decimal rate math remains in `lens/accounting.py`. Unavailable subsets, legacy counters, ambiguous mirrors, missing sources, and conflicts retain their conservative behavior. The UI does not convert observations into savings claims or an efficiency score.

`lens/server.py` allows four static assets and explicit API routes. All APIs require a per-launch capability header and validate Host, Origin, and Fetch Metadata. Note mutations additionally require bounded JSON bodies. No API accepts arbitrary filesystem reads or shell commands. SQL is parameterized and transcript text enters the DOM via text nodes.

`lens/mcp.py` exposes five read-only tools; SQLite query-only mode reinforces that boundary. It implements initialization/capability negotiation, tool discovery/calls, ping, protocol errors, bounded frames, and EOF shutdown for revisions through 2025-11-25. No sampling, agent configuration editing, hook installation, model invocation, or remote transport. Retrieved history remains untrusted evidence. The consuming agent controls whether context goes to a cloud provider.

## Limits

Conversation text is capped per message, not retained as a full transcript archive. SQLite FTS indexes these excerpts only. Long records skipped by the importer do not become searchable. Missing files are retained with diagnostics so transient discovery failures do not erase history. UI queries are serialized against refresh in the browser process; MCP reads committed snapshots through SQLite. Large cross-history queries can take time, and the UI uses visible status/error messages rather than pretending results are instantaneous.

The original engine's bounded-allocation and incremental-import guarantees apply to import, not an unlimited zero-memory promise for every aggregate query. Optional tests cover synthetic large files, browser flows, and official MCP SDK interoperability.
