# Phase: ENHANCE

> Per-insight enrichment loop. Triage → research → validate → rewrite → writeback.

## Per-row flow

For each row in `/tmp/insight-enhance-fetched.json`:

### 1. Triage

Pipe the whole fetched array through `triage.py`, then filter for `outcome == "enrichable"`:

```
jq '.' /tmp/insight-enhance-fetched.json \
  | python3 ~/.claude/skills/insight-enhance/scripts/triage.py \
  > /tmp/insight-enhance-triaged.json
```

Release locks for every row classified as `skip:*` or `broken:*`:

```
SKIP_IDS=$(jq -r '.[] | select(.outcome | startswith("skip:") or startswith("broken:")) | .id' /tmp/insight-enhance-triaged.json)
python3 ~/.claude/skills/insight-enhance/scripts/release_lock.py --ids $SKIP_IDS
```

### 2. Research (per enrichable row)

For each enrichable row, dispatch the skill named in its `route_to` field.

- `route_to: /question` + `mode: quick` → invoke `Skill(name="question", args="<core claim> --quick")`
- `route_to: /research-before-coding` → invoke `Skill(name="research-before-coding", args="<core claim + context>")`

**Extract citations** from the research output into a structured array:

```json
[
  {"url": "https://...", "title": "...", "http_status": null, "validated_at": null}
]
```

If fewer than `hard_gates.min_citations_required` (default 2) citations come back → abort this row, release its lock, log reason `insufficient-research-output`.

### 3. URL validation (audit [1.5] guard)

```
python3 ~/.claude/skills/insight-enhance/scripts/validate_urls.py \
    --urls <each url from research> \
    --require 1
```

If exit code != 0 (no URL returned 200) → abort this row, release its lock, log reason `no-valid-citations`. The JSON output can be captured and merged into the sources payload later.

### 4. Bounded rewrite

Load `~/.claude/skills/insight-enhance/reference/enhancement-prompt.md`. Substitute:

- `{{ORIGINAL_CONTENT}}` → row.content
- `{{RESEARCH_SUMMARY_WITH_CITATIONS}}` → research output body
- `{{CITATION_LIST}}` → formatted `[N] Title — URL — accessed ISO-8601`
- `{{MAX_LENGTH}}` → `2 * len(row.content)`

Send that prompt to the model and capture the enriched body.

### 5. Post-rewrite verification (runs inline, before writeback)

Check ALL of these — any failure aborts the row:

- [ ] First 50 chars of enriched body match first 50 chars of original (whitespace-normalised substring)
- [ ] Length of enriched body ≤ 2 × original length
- [ ] Count of `[N]` markers in enriched body ≥ 2
- [ ] Every `[N]` reference has a matching URL in the enriched body's References section

On any failure: release lock, log reason, move to next row.

### 6. Writeback (audit [1.1] atomic)

Write the enriched body to `/tmp/insight-enhance-<id>-body.txt` and the sources array to `/tmp/insight-enhance-<id>-sources.json`, then:

```
python3 ~/.claude/skills/insight-enhance/scripts/writeback.py \
    --original-id <id> \
    --enriched-content /tmp/insight-enhance-<id>-body.txt \
    --sources /tmp/insight-enhance-<id>-sources.json \
    [--moll-e-republish]
```

Capture the returned JSON `{original_id, new_id, new_hash}` for the report.

### 7. Optional Moll-E republish

If `--republish` flag was passed AND writeback succeeded, POST the enriched content to `http://localhost:3100/insight/store` with session/type/project copied from the original. Use the **new hash** as idempotency key.

## Exit criteria

- [ ] Every row has been triaged
- [ ] Every enrichable row has either been written back OR had its lock released
- [ ] No row is left locked
- [ ] Writeback results captured for REPORT phase
