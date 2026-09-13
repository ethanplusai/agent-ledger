# Security and privacy

Agent Ledger handles sensitive local logs. The source repository and synthetic demo are intended for public distribution; a report generated from real history is private.

## Boundaries

- No credentials or account connection. No outgoing network client in the analyzer.
- Reads discovered Codex and Claude Code transcript JSONL files; writes only a separate private cache. Explicit text/Markdown imports are opt-in.
- Common secret patterns are redacted before conversation text and notes are stored. This is not comprehensive secret detection or anonymization.
- Optional MCP exposes read-only queries over stdio. Connected agents may send retrieved context to their model providers; there are no model calls in Ledger itself.
- Notes can be edited/deleted through authenticated, bounded JSON requests. Notes and imported history share a private database; removing it deletes both.
- Binds only to `127.0.0.1` on an ephemeral port. No remote serving option.
- Per-launch random capability token, passed in a request header for API access. The initial URL fragment is removed from the address bar and retained in tab session storage.
- Exact Host and Origin checks, Fetch Metadata checks, no CORS support, no arbitrary path endpoint.
- An explicit four-file asset allowlist, restrictive CSP, no-store responses, frame denial, and no-referrer policy.
- Log content is rendered with text nodes, never HTML or executable commands. Encrypted reasoning, image payloads, and unknown non-text blocks are not decoded.
- Bounded input lines and previews; parameterized SQL; raw exceptions and HTTP access URLs are not logged.
- A process-level writer lock protects normal CLI imports into the same cache; source records and checkpoints commit together.

This is a local investigation utility, not a hardened multiuser service. Other software running as your operating-system user can read your logs, cache, browser state, and local process data. Tokens do not protect against that access. Do not expose or forward the port, share the capability URL, or put the cache in a publicly accessible directory. No share-safe export is provided.

## Reporting

For a suspected vulnerability, use the repository’s private vulnerability reporting feature when enabled. If unavailable, open an issue asking for a private contact channel, without exploit details or private data. Use synthetic examples. Never attach real logs, credentials, prompts, databases, or private screenshots.

## Publication review

Run `python3 scripts/check_public_tree.py` and inspect the actual staged diff. The scanner checks the prospective Git file set for private artifact types, common personal paths, token-shaped values, private keys, and unexpected binaries. Only the manually inspected synthetic `docs/screenshots/demo-*.png` assets are exempted from text scanning. It is a guardrail, not comprehensive secret detection. Do not force-add ignored history/cache files.
