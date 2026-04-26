# atlas-insights

> Your AI is already generating wisdom. You're throwing it away.

Every session your AI emits `★ Insight ─...─` blocks — lateral connections, attacker mental models, non-obvious reframes, MITRE-relevant observations, mechanism-discovery callouts. They appear in chat. You read them. You move on. **They're gone the moment the session ends.**

If you've been using Claude Code with the explanatory output style for any length of time, you've already lost hundreds of these. (We measured: one operator, four weeks, **478 hermes + 4,964 archie = 5,442** insights pulled from JSONL transcripts that nobody had been mining.)

---

## What this plugin does

One install, two automatic capture paths, one shared corpus:

1. **PostToolUse hook** — anything you write to `/tmp/insights/<session>.md` ships to the corpus instantly.
2. **SessionEnd hook** — every session, automatically scraped on close. Whatever the AI said in chat that bore `★ Insight ─` or `[SPARK] / [AI] / [PENTEST] / [MECHANISM]` tags — captured. No operator effort. No "remember to save it." It just lives.

Then a federated MCP (`shade-insights-rag`) lets the same AI, or *any* AI on *any* host you've installed this on, **search across every insight you've ever produced**. SQLite + vector store today. Pinecone tomorrow. Clients don't care which.

## The unlock

- **"Have we figured this out before?"** is now a question your AI can actually answer.
- `/insight-review` at the end of a long debugging day → *"You circled these three patterns. Build the script that catches them."*
- A `[SPARK]` from three months ago surfaces in today's recon because it's still semantically nearby.
- Multi-host: archie's AI knows what hermes's AI learned. They're contributing to the same ledger.

## How much will this hurt to install

When published: **one line in `~/.claude/settings.json`**. That's the entire install. The plugin brings its own hooks, its own skills (`/insight-review`, `/insight-enhance`), its own MCP registration. You point it at a corpus host (one Tailnet hop or local) and you're done.

You also get:

- `/insight-enhance` — upgrade raw insights into researched, cited entries with HEAD-200 URL validation. Original rows are immutable; enrichment is INSERT-only with `parent_id` lineage. No fabrication can land in your corpus.
- `/insight-review --hours 24` — mine recent insights and propose 3–5 ship-today builds, classified by *fingerprint / tool / trust trap / architectural lesson*.
- Web dashboard at `http://<corpus-host>:3100/insights` — Atlas-branded, type filter, full-text search.

## Who should NOT install this

- You don't use the explanatory output style or any insight-tagging convention. (Nothing to capture.)
- You're a single-shot user — one session a month. (Compounding benefit needs volume.)
- You can't or won't run a corpus host on your network. (Hosted version coming; not yet.)

## The actual reason you want it

Every operator has the same line in their head: *"I had this exact realisation two weeks ago and I can't remember the details."* This plugin makes that line obsolete. Every realisation your AI surfaces is durable, queryable, and can come back to inform the next session — without you doing anything.

The longer you run it, the smarter it makes every future session.

---

# How it works

## Components

| Component | Purpose |
|---|---|
| `hooks/insight-harvester.sh` | PostToolUse: catches `★ Insight ─` blocks written to `/tmp/insights/<session>.md` and POSTs them to the corpus host's moll-e API. |
| `hooks/insight-session-scrape.sh` | SessionEnd: scrapes the just-finished session's transcript JSONL for insight blocks the assistant emitted in chat — closes the gap where in-chat insights weren't auto-captured. |
| `skills/insight-review/` | `/insight-review` — mine recent insights and propose 3–5 ship-today builds. Pure SQL via SSH-shim against the corpus host. |
| `skills/insight-enhance/` | `/insight-enhance` — enrich raw insights via `/question` or `/research-before-coding`, with HEAD-200 cite gate and INSERT-only lineage. SSH-shim to corpus host. |
| `mcp-servers/shade-insights-rag.json` | Federated RAG MCP via SSH-stdio bridge to the corpus host. Exposes `insight_search`, `insight_recent`, `claude_insights_search`, etc. |
| `lib/insights-backfill.py` | One-shot or per-session transcript scraper. Used by SessionEnd hook and for manual backfills. |

## Architecture

```
┌──────────────── CORPUS HOST (archie today, swappable) ────────────────┐
│  moll-e (HTTP :3100)  ←── /insight/store ──┐                          │
│       │                                    │                          │
│  insights.db (sqlite + sqlite-vec)  ──→ insight-vectorizer ──→ qdrant │
│       │                                                              │
│  shade-insights-mcp (FastMCP, stdio)  ←── any client over SSH ────────┘
└──────────────────────────────▲─────────────▲─────────────────────────┘
                               │             │
                       HTTP POST       SSH-stdio MCP
                               │             │
┌─── ANY CLIENT (this plugin installed) ─────┴──────────────────────────┐
│  PostToolUse hook  →  POST /insight/store                             │
│  SessionEnd hook   →  scrape transcript → POST /insight/store         │
│  shade-insights-rag MCP → ssh-stdio to corpus → semantic search      │
│  /insight-review, /insight-enhance skills → SSH-shim to corpus       │
└───────────────────────────────────────────────────────────────────────┘
```

## Configuration

Override via env vars (place in `~/.claude/atlas-insights.local.md` or shell rc):

| Variable | Default | Purpose |
|---|---|---|
| `ATLAS_INSIGHTS_CORPUS_HOST` | `archie` | SSH alias / Tailnet hostname of corpus host |
| `ATLAS_INSIGHTS_ENDPOINT` | `http://100.113.114.116:3100/insight/store` | moll-e write API. Override to `http://127.0.0.1:3100/insight/store` when running ON the corpus host. |
| `ATLAS_INSIGHTS_HOST_TAG` | `$(hostname)` | Tag for cross-host distinguishability in the corpus |
| `ATLAS_INSIGHTS_LOG` | `/tmp/insight-session-scrape.log` | Where SessionEnd hook logs its activity |

## Install (once published to a marketplace)

```jsonc
// ~/.claude/settings.json
"enabledPlugins": {
  "atlas-insights@atlas-plugins": true
}
```

Until then, install from this repo directly:

```bash
git clone --depth 1 git@github.com:anombyte93/atlas-insights.git ~/.claude/plugins/atlas-insights
```

then add to `enabledPlugins`:

```jsonc
"enabledPlugins": {
  "atlas-insights": true
}
```

## Why this exists

Built in two days (2026-04-25/26) after observing that:

1. archie had multiple capture pipelines (`pipe-extractor`, `watchdog-research`, `api`) but **none of them caught in-chat `★ Insight ─` blocks** the assistant emits during sessions.
2. hermes had no capture at all — its insights lived only in transcript JSONL with no DB.
3. Both hosts converging on a single SoT corpus (with Pinecone-ready abstraction) is the only way to avoid drift, and the MCP-over-SSH-stdio bridge means clients never need to mirror the backend.

The 2026-04-26 session backfilled **5,442 historical insights** (478 from hermes + 4,964 from archie) and proved the architecture by observing 0 dup-collisions across hosts — host-distinguishable insight streams are real and worth preserving.

## Roadmap

1. **moll-e Discord embed format**: footer doesn't include local-tz date; bump dashboard `LIMIT 200` → paginated. See `lib/routes/insights.js`.
2. **Locate `[batch] N insights captured HH:MM` decorator** in `~/.claude/scripts/insight-batch-flusher.py` — strip the polluting prefix.
3. Publish to a marketplace (`atlas-plugins`) so a single `enabledPlugins` toggle suffices.
4. Add an HTTP-MCP variant for clients that can't SSH (browser-based AIs, Codex CLI, etc.).
5. Pinecone migration on the corpus host — abstracted away from clients by the MCP boundary.
6. SessionEnd-hook backwards-compat shim for hosts running older Claude Code releases without `transcript_path` payload.

## License

Private — all rights reserved. Contact the maintainer for licensing terms.
