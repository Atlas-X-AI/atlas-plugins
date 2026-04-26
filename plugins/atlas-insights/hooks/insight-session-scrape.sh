#!/usr/bin/env bash
# atlas-insights:insight-session-scrape — SessionEnd hook
# Scrapes the just-finished session's transcript JSONL for ★ Insight blocks
# and POSTs them to the corpus. Closes the gap where in-chat insights weren't
# auto-captured (the PostToolUse harvester only fires on /tmp/insights/* writes).
#
# Idempotent — moll-e UNIQUE(hash) rejects duplicates.
# Exit 0 always — never block session close.

set -u
LOG="${ATLAS_INSIGHTS_LOG:-/tmp/insight-session-scrape.log}"

INPUT=$(cat)

TRANSCRIPT=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('transcript_path', '') or '')
except Exception:
    pass
" 2>/dev/null)

if [[ -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]]; then
    echo "[$(date -Is)] no transcript_path in SessionEnd payload, skipping" >> "$LOG"
    exit 0
fi

echo "[$(date -Is)] scraping $TRANSCRIPT" >> "$LOG"
python3 "${CLAUDE_PLUGIN_ROOT}/lib/insights-backfill.py" --file "$TRANSCRIPT" >> "$LOG" 2>&1 || true

exit 0
