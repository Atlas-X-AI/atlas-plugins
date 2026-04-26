# Phase: FETCH

> Load rules, run schema migration, claim insight rows atomically.

## Steps

1. **Schema upgrade** (idempotent — no-op if columns exist):

   ```
   python3 ~/.claude/skills/insight-enhance/scripts/schema_upgrade.py
   ```

   Expected stdout: `schema_upgrade: added N column(s)` on first run, `schema_upgrade: no-op (7 columns already present)` thereafter. Non-zero exit → abort phase.

2. **Resolve session name**:
   - From `--session` arg if provided
   - Else derive from `CLAUDE_SESSION_NAME` env var
   - Else derive from `tmux display-message -p '#{session_name}'`
   - If still empty → abort with `ERROR: cannot determine session`

3. **Fetch + lock** (one atomic transaction):

   ```
   python3 ~/.claude/skills/insight-enhance/scripts/fetch_and_lock.py \
       --session "$SESSION" [--hours N] [--type TAG] [--limit N] \
       > /tmp/insight-enhance-fetched.json
   ```

   Output is a JSON array of eligible, now-locked rows. Empty array is OK — means "no eligible rows", skill proceeds to REPORT and exits clean.

4. **Record locked IDs** for unlock-on-abort path. Write them to `/tmp/insight-enhance-locked-ids.txt` (one per line). On any subsequent failure, call `release_lock.py --ids ...` against these IDs before exiting.

## Exit criteria

- [ ] schema_upgrade.py exited 0
- [ ] Session name resolved
- [ ] fetch_and_lock.py produced a JSON array (possibly empty)
- [ ] Locked IDs recorded for abort path
