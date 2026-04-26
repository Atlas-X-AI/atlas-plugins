---
name: insight-enhance
description: Harvest the current session's captured insights from ~/.claude/state/insights.db, enrich them via /question or /research-before-coding (adding verified citations), write enriched versions back with full lineage tracking, and optionally compose with ash-protocol to wind down the session. Use when user says /insight-enhance, "enhance my insights", "before I ash this session", or at the end of a working session to durably capture what was learned. Default is current session, dry-run preview. --apply writes back; --ash composes the teardown.
---

# Insight Enhance

> Insights captured during a session are cheap but fragile: short, often uncited, prone to being forgotten or overwritten. This skill upgrades them in place — researched, cited, URL-validated, atomically written back with full lineage to the original row.

## The One Rule

**Original rows are never overwritten. Every enrichment is a new INSERT with parent_id pointing to the original. Rollback is always one SQL statement.**

## When to run

- End of a session, before `/stop` or `--ash`, to capture learnings durably
- After a productive run of debugging/pentesting that generated ≥3 session insights
- Before archiving a session's context (`/atlas-handoff`, ashing)
- NOT for: sessions with <3 insights (nothing to enhance), public sessions where you want zero DB side effects

## Arguments

| Flag | Default | Effect |
|---|---|---|
| `--session NAME` | current session (from `CLAUDE_SESSION_NAME`/tmux) | filter to that session's insights only |
| `--hours N` | no limit | time window (e.g. `--hours 2` for current-pane work) |
| `--type TAG` | all | filter by insight type (`insight`, `finding`, `debrief`) |
| `--limit N` | 5 | max rows to enrich per run (prevents runaway cost) |
| `--apply` | off (dry-run) | actually write back to insights.db |
| `--republish` | off | POST enriched rows to Moll-E for Discord relay |
| `--notify` | off | push ntfy on completion |
| `--ash` | off | after enrichment, invoke ash-protocol agent to decide session disposition |
| `--force` | off | re-enrich rows that already have citations (default skips them) |

## Procedure

Run phases in order:

1. **FETCH** (see `phases/FETCH.md`) — migrate schema, resolve session, claim rows atomically
2. **ENHANCE** (see `phases/ENHANCE.md`) — triage → research via `/question`/`/research-before-coding` → URL-validate → bounded rewrite → atomic writeback
3. **REPORT** (see `phases/REPORT.md`) — summary table; optional ash composition

Dry-run mode (default, no `--apply`): execute through the end of step 5 in ENHANCE (post-rewrite verification) but do NOT invoke `writeback.py`. Present what WOULD be written in the REPORT. Release all locks.

## Hard rules

1. **Every enrichment is an INSERT** (audit [1.1]). Original rows are untouched except for `superseded_by` being set.
2. **Minimum 2 citations required** for writeback (audit [1.6]). Insufficient research → abort that row, release lock.
3. **At least 1 cited URL must HEAD-respond 200** (audit [1.5]). Fabricated citations fail this gate.
4. **`is_enriched=1` excludes from future enhancement runs** (audit [1.3]). No v2→v3 drift.
5. **All locks cleared on exit**, success or failure. A stranded lock is a bug.
6. **Heuristics live in `config/triage-rules.json`** (audit [1.4]). Edit that file to retune judgement; the Python scripts never hardcode thresholds.

## Composition

- Calls `/question` for single-claim factoid insights (word_count < 80 AND claim_count ≤ 1)
- Calls `/research-before-coding` for multi-claim or architectural insights
- Optionally dispatches `ash-protocol` agent when `--ash` is passed
- See `reference/composition-contract.md` for the full invocation contract

## Files

```
~/.claude/skills/insight-enhance/
├── SKILL.md                                      # this file
├── config/triage-rules.json                      # deterministic heuristics
├── reference/
│   ├── enhancement-prompt.md                     # bounded rewrite template
│   └── composition-contract.md                   # how /question + /research-before-coding are called
├── scripts/
│   ├── schema_upgrade.py                         # idempotent ALTER TABLE
│   ├── fetch_and_lock.py                         # atomic SELECT + SET processing_lock
│   ├── triage.py                                 # safe-parser classification (no eval)
│   ├── validate_urls.py                          # HEAD-check citations
│   ├── writeback.py                              # atomic INSERT + UPDATE
│   └── release_lock.py                           # abort-path unlock
└── phases/
    ├── FETCH.md
    ├── ENHANCE.md
    └── REPORT.md
```

## Example run

```
/insight-enhance
  → dry-run: fetches last 24h of current session's insights, shows what would be enriched

/insight-enhance --apply
  → actually enriches; writes new rows with is_enriched=1

/insight-enhance --apply --republish --ash
  → enriches + re-pushes to Moll-E for Discord relay + hands off to ash-protocol

/insight-enhance --session harvester-deep --hours 48 --limit 10 --apply
  → enhances up to 10 of harvester-deep's last-48h insights
```

## Rollback

If an enrichment is bad after the fact:

```sql
-- restore original; discard enriched version
UPDATE insights SET superseded_by = NULL WHERE id = <original_id>;
DELETE FROM insights WHERE id = <new_id> AND parent_id = <original_id>;
```

Original content is always recoverable because it's never overwritten.

## Critical rules

1. Never UPDATE the `content` column of an existing row. Only INSERT new.
2. Never skip URL validation. Citations without HEAD-checks are fabrication surface.
3. Never run without schema_upgrade.py first — the other scripts depend on the added columns.
4. Never call `/research-before-coding` as a fallback when `/question` returns empty. Skip the row instead.
