# Changelog

All notable changes to atlas-insights will be documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-04-26

### Added

- **PostToolUse hook** (`insight-harvester.sh`) — captures `★ Insight ─` blocks and `[SPARK]/[AI]/[PENTEST]/[MECHANISM]/[BLINDSPOT]/[CONTRADICTION]/[ALTERNATIVE]`-tagged blocks written to `/tmp/insights/<session>.md`. Hash-dedupes per session. POSTs to corpus moll-e endpoint.
- **SessionEnd hook** (`insight-session-scrape.sh`) — scrapes the just-finished session's transcript JSONL for in-chat insight blocks. Closes the gap where in-chat insights aren't caught by the file-write harvester.
- **`insight-review` skill** — `/insight-review --hours N --type all|pentest|ai|spark` — mines recent corpus rows, classifies into fingerprint/tool/trust-trap/architectural-lesson, proposes 3–5 ship-today builds. SSH-shim implementation against corpus host.
- **`insight-enhance` skill** — `/insight-enhance [--apply] [--ash]` — enrich raw insights via `/question` or `/research-before-coding` with HEAD-200 cite gate, ≥2 cited-URL minimum, INSERT-only lineage (`parent_id`/`superseded_by`), atomic processing-lock claim.
- **Federated MCP** (`shade-insights-rag`) — SSH-stdio bridge to corpus host. Exposes `insight_search`, `insight_recent`, `insight_by_phase`, `insight_stats`, `claude_insights_search`, `claude_insights_stats`, `reference_heatmap`, `reference_search`, `reference_timeline`.
- **`lib/insights-backfill.py`** — historical transcript scraper. Same regex/noise filters as the harvester so live and backfilled rows are stylistically uniform. Hash-dedups via moll-e UNIQUE constraint.
- **Configurable via env vars** — `ATLAS_INSIGHTS_CORPUS_HOST`, `ATLAS_INSIGHTS_ENDPOINT`, `ATLAS_INSIGHTS_HOST_TAG`, `ATLAS_INSIGHTS_LOG`.
- **Plugin manifest** with `${CLAUDE_PLUGIN_ROOT}` paths so the plugin is host-agnostic.

### Verified

- Smoke-tested SessionEnd hook against a live in-progress session — 18 fresh in-chat insights captured, 0 errors.
- Backfilled 478 historical insights from hermes transcripts (24s wall-time, 0 errors, 0 collisions).
- Backfilled 4,964 historical insights from archie transcripts across 254 project subdirs (15s wall-time, 0 errors, 0 collisions with archie's own pipelines — confirms host-distinguishable streams).

### Known issues / next-session work

- moll-e Discord embed footer is UTC-only with no date string; dashboard `LIMIT 200` is hardcoded.
- A `[batch] N insights captured HH:MM` polluter is being prepended somewhere in the moll-e/insight-batch-flusher path. Source located (`~/.claude/scripts/insight-batch-flusher.py` on archie); strip-on-write fix queued.
- Currently SSH-stdio MCP only — clients must have SSH access to the corpus host. HTTP-MCP variant planned for browser/Codex clients.
