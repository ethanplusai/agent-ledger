# Validation

Validated locally on macOS, September 12, 2026. Automated fixtures and screenshots are synthetic. A bounded compatibility check against a real Claude session used a temporary private cache that was removed afterward; no transcript material is included in the repository.

| Check | Result |
| --- | --- |
| Python 3.14 regression suite | 88 tests passed |
| Python 3.12 regression suite | 88 tests passed |
| Usage browser suite | Passed context defaults, per-response changes/table selection, largest-response navigation, contributor explanation, selection, keyboard tabs/chart, filters, refresh, evidence, inert text, empty states, themes, and 360/736/1024/1440 widths |
| Project briefing browser suite | Passed source navigation, copied handoff contents, editing/saving without duplicates, per-project draft isolation, and mobile layouts |
| Combined workspace browser suite | Passed finding-to-evidence navigation, search/read/save/edit/delete, day selection, MCP configuration, empty/error recovery, narrow layouts, and no external requests |
| Official TypeScript MCP SDK interoperability | Passed initialization, tool discovery, search/read citations, invalid arguments, and subprocess shutdown |
| Claude import | Synthetic stream merging, copied-source deduplication, conflict exclusion, inclusive cache counts, appends, incomplete tails, replacement, and malformed/oversized records checked |
| Context accounting | Page boundaries, filtered baselines, source isolation, decreases, missing cache counts, conflict exclusion, recorded limits, and credit-component sums including unsplit output checked |
| Context persistence | Project/global notes, validation, search beyond the first notes page, stale-citation rejection, and surrounding-message pagination checked |
| HTTP boundaries | Capability, Host/Origin/Fetch Metadata, static allowlist, headers, bounded note mutations, private connection configuration, and invalid input checks passed |
| Generated large-file smoke | 96 MiB including a 32 MiB oversized line; 905 unique responses; 16.2 MiB peak traced Python allocations; unchanged rerun read 0 records |
| Publication scan | No findings in the prospective public file set |
| Visual inspection | Synthetic Start light/dark/mobile and Usage screenshots reviewed |

The earlier Codex engine was also exercised with a generated 3,104.1 MiB file. That historical stress run is not a fresh benchmark of every new workspace query. Peak traced allocations are not total RSS. Performance depends on history shape, storage, and scope.

## Reproduce

```sh
python3 -m unittest discover -s tests -v
python3 scripts/large_file_smoke.py --mib 64
python3 scripts/check_public_tree.py
```

Browser scripts require a development-only Playwright installation and Chromium. Use `NODE_PATH` to expose that installation if it is outside this checkout. They start their own synthetic server on an ephemeral origin, block external requests, and shut down afterward. `--screenshots` updates only generated demonstration images.

```sh
node scripts/browser_smoke.cjs --screenshots
node scripts/workspace_smoke.cjs --screenshots
node scripts/briefing_smoke.cjs --screenshots
```

For MCP integration, set `MCP_SDK_ROOT` to an installed `@modelcontextprotocol/sdk` package directory and run `node scripts/mcp_smoke.mjs`. The official SDK is only a test dependency; the app runs with Python's standard library.

## Limits

- Python 3.10, Linux, and Windows have a CI matrix; local results above are macOS only. Check the repository's Actions results for remote platform execution.
- Chromium was exercised locally; other browser engines and assistive-technology combinations are not exhaustively tested.
- Internal transcript formats can change. These tests do not guarantee compatibility with every agent release or record variant.
- MCP tools are read-only and expose committed indexed data. Refresh remains explicit, or can run periodically while the foreground app runs with `--watch`.
- The public scanner is a guardrail, not a proof of total secret detection. The source package includes only reviewed code, documentation, and synthetic assets, with no imported private repository history.
