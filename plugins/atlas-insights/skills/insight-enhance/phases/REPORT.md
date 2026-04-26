# Phase: REPORT

> Summarise the run. Optionally invoke ash-protocol.

## Summary table

Present a table to the user:

```
| ID    | Type     | Outcome           | Reason / new_id             |
|-------|----------|-------------------|------------------------------|
| 4938  | insight  | enriched          | → new id 4943 (2 citations) |
| 4939  | insight  | skip:no_signals   | no enrichable rules fired   |
| 4940  | insight  | skip:self_obs     | "in this session" detected  |
| 4941  | insight  | enriched          | → new id 4944 (3 citations) |
| 4942  | insight  | abort:no_urls     | 0/3 citations reachable     |
```

Totals line: `enriched: N  |  skipped: M  |  aborted: K  |  locked-still: 0`

If any row is `locked-still > 0` — that is a bug. Emit a CRITICAL warning to stderr and suggest running `release_lock.py --session $SESSION` as recovery.

## Optional ash composition

If `--ash` flag was passed:

1. Verify all locks are released (safety check before session teardown).
2. Dispatch the `ash-protocol` agent with:

   - `subagent_type: "ash-protocol"`
   - prompt: include session name, enriched count, skipped count, and the explicit intent: "insight enrichment complete; evaluate session purpose-completion and recommend ash disposition (new_soul / egg / terminal)"

3. Relay the agent's RECOMMENDATION block back to the user unchanged. Do NOT act on it — ash-protocol owns the decision.

## Optional ntfy push

If `--notify` flag was passed OR the run enriched ≥ 3 insights, push a ntfy with:

- title: `[<session>] insight-enhance: N enriched, M skipped`
- body: totals + top 3 enriched IDs + "open insights.db to review" or equivalent

## Exit

- Write final summary to `/tmp/insight-enhance-<session>-report.md` for archival.
- Exit 0 on success; non-zero only if a bug left locks stranded.
