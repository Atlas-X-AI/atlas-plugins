# Composition Contract

> `/insight-enhance` composes three existing skills/agents. This document is the invocation contract — what we call, what we expect back, how we handle failure.

## 1. `/question` (FACTOID-shape insights)

**When called**: triage classifies the insight as `factoid_single_claim` (word_count < 80, claim_count ≤ 1).

**Invocation**:
```
/question "<core claim extracted from insight>" --quick
```

**Expected return shape**: compiled answer with inline [N] citations + References section. `/question`'s internal Context7 + Perplexity pipeline handles source gathering; we don't invoke Perplexity ourselves.

**Failure modes handled**:
- `/question` self-aborts with `CODEBAQDE_LOOKUP` → we treat this as "not enrichable via research"; skip the insight with reason `codebase-lookup-only`.
- `/question` returns < 2 citations → SKIP enrichment (min-source gate per audit finding [1.6]).
- `/question` returns empty body → SKIP enrichment.
- `/question` returns with citation count ≥ 2 → pass to rewrite step.

## 2. `/research-before-coding` (ARCHITECTURE-shape insights)

**When called**: triage classifies as `architecture_multi_claim` (word_count ≥ 80 OR claim_count ≥ 2).

**Invocation**:
```
/research-before-coding "<core claim + context>"
```

**Expected return shape**: merged Perplexity + agent summary with citations; `/research-before-coding`'s pipeline already includes a coaching pass to 95%+ quality.

**Failure modes handled**: same as `/question` above.

**Rationale for split**: `/question` is quick + cheap (≤ 4 parallel queries). `/research-before-coding` is heavier (parallel Perplexity + agent pipelines + merge + coach). Using the right tool per insight shape keeps the per-run cost bounded — enriching 5 factoid insights costs 5× `/question`, not 5× the heavy pipeline.

## 3. `ash-protocol` agent (optional `--ash` flag)

**When called**: user passed `--ash` flag AND enhancement run completed successfully (at least 1 insight enriched OR all rows triaged as skip/complete).

**Invocation**: dispatched via `Agent` tool with `subagent_type=ash-protocol`. Prompt includes:
- Session identifier
- Summary of enrichment results (counts by outcome)
- Explicit intent: "enhance done; ready for ash transition; evaluate purpose-completion and disposition"

**Expected return**: ash-protocol's structured RECOMMENDATION block. The insight-enhance skill does NOT act on the recommendation — it relays it back to the user. ash-protocol owns the lifecycle decision; insight-enhance is a pre-ash enrichment pass.

**Failure mode**: if ash-protocol returns `action=hold_ash` (ambiguity gate), we surface that to the user unchanged. No retry.

## 4. Non-composed dependencies

| Resource | Purpose |
|---|---|
| `~/.claude/state/insights.db` (SQLite) | Source of truth + write target |
| `http://localhost:3100/insight/store` (Moll-E REST) | Optional `--republish` re-push of enriched rows |
| `shade-insights-rag` MCP | Optional pre-check: skip enrichment if RAG already has higher-quality version |

## Invariants across compositions

1. **One research dispatch per insight per run.** If `/question` fails, we do NOT fall back to `/research-before-coding`; we skip the insight. Prevents runaway cost on already-problematic rows.
2. **Research output treated as input-only.** We never quote or cite the research output without the model passing it through the bounded-rewrite prompt (see `enhancement-prompt.md`). No raw "here's what Perplexity said" write-back.
3. **Lock-release discipline.** If a composition call fails or times out, `processing_lock` MUST be cleared on the affected row(s) before the skill exits. See `writeback.py` for the unlock fallback path.
