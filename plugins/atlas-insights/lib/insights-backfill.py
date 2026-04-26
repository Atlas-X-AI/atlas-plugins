#!/usr/bin/env python3
"""Backfill historical insight blocks from hermes Claude Code transcripts → archie corpus.

Idempotent. Reuses the live harvester's exact regex + noise filters so backfilled and
live rows are stylistically uniform. Hash-dedupes per run; cross-run dedup is enforced
by moll-e's UNIQUE(hash) constraint on insights.db.

Filtering (informed by transcript-recon agents 2026-04-26):
  - Only `type=assistant` records
  - Skip `isSidechain=true` (subagent transcripts; treat separately if ever needed)
  - Only `message.content[*].type == 'text'` blocks (skip thinking/tool_use/tool_result)
  - Apply harvester's noise filters (short, task-list-like, glyph-led, etc.)

Usage:
  insights-backfill.py                          # all transcripts
  insights-backfill.py --limit 1                # smoke-test on first file only
  insights-backfill.py --file <basename.jsonl>  # one specific file
  insights-backfill.py --dry-run                # parse + filter, do not POST
"""

import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import os as _os
ARCHIE_MOLLE = _os.environ.get(
    "ATLAS_INSIGHTS_ENDPOINT",
    "http://100.113.114.116:3100/insight/store",
)
# Default scope = ALL projects (every cwd's transcript dir). Plugin runs across hosts.
PROJECTS_DIR = Path.home() / ".claude" / "projects"

# Same regexes as ~/.claude/hooks/insight-harvester.sh
STAR_RE = re.compile(
    r'^[^\n]*★\s*Insight\s*─+[^\n]*\n(.*?)\n[^\n]*─{5,}[^\n]*$',
    re.DOTALL | re.MULTILINE,
)
TAG_RE = re.compile(
    r'\[(SPARK|AI|PENTEST|MECHANISM|BLINDSPOT|CONTRADICTION|ALTERNATIVE)\]'
)
TAG_RE_DENSE = re.compile(r'\[(SPARK|AI|PENTEST|MECHANISM)\]')

NOISE_TASKS_RE = re.compile(r'\d+\s+tasks\s+\(')
NOISE_GLYPH_RE = re.compile(r'^\s*[✔◻◼✅❌]', re.MULTILINE)
NOISE_HEADER_RE = re.compile(r'^(Last Updated:|##\s+Session State)', re.MULTILINE)


def is_noise(c: str) -> bool:
    if len(c) < 20:
        return True
    if NOISE_TASKS_RE.search(c):
        return True
    if NOISE_GLYPH_RE.search(c):
        return True
    if NOISE_HEADER_RE.search(c):
        return True
    if len(c) > 1500 and len(TAG_RE_DENSE.findall(c)) < 3:
        return True
    return False


def extract_blocks(text: str):
    blocks = []
    for m in STAR_RE.findall(text):
        b = m.strip()
        if b:
            blocks.append(b)
    for p in re.split(r'\n-{3,}\n', text):
        p = p.strip()
        if not p or p in blocks:
            continue
        if TAG_RE.search(p):
            blocks.append(p)
    return blocks


def assistant_texts(jsonl_path: Path):
    """Yield (text, msg_uuid, ts) for assistant text-content blocks that look insight-bearing."""
    with open(jsonl_path, encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if e.get('type') != 'assistant':
                continue
            if e.get('isSidechain'):
                continue
            content = (e.get('message') or {}).get('content') or []
            if not isinstance(content, list):
                continue
            for blk in content:
                if not isinstance(blk, dict) or blk.get('type') != 'text':
                    continue
                t = blk.get('text', '')
                if not t:
                    continue
                if '★ Insight' in t or TAG_RE.search(t):
                    yield t, e.get('uuid', ''), e.get('timestamp', '')


def post_insight(payload: dict) -> str:
    req = urllib.request.Request(
        ARCHIE_MOLLE,
        data=json.dumps(payload).encode('utf-8'),
        method='POST',
        headers={'Content-Type': 'application/json'},
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()
        return 'ok'
    except urllib.error.HTTPError as e:
        if e.code in (409, 422, 200):
            return 'dup'
        return f'http{e.code}'
    except Exception as e:
        return f'err:{type(e).__name__}'


def main():
    args = sys.argv[1:]
    dry_run = '--dry-run' in args
    # Walk every project subdirectory (e.g. -home-anombyte, -home-anombyte--claude, …)
    files = sorted(PROJECTS_DIR.glob('*/*.jsonl'))

    if '--file' in args:
        target = args[args.index('--file') + 1]
        p = Path(target)
        files = [p if p.is_absolute() else (PROJECTS_DIR / p)]
    if '--limit' in args:
        files = files[: int(args[args.index('--limit') + 1])]

    seen = set()
    stats = dict(files=0, msgs=0, blocks=0, posted=0, dup=0, err=0, noise=0, hash_collide=0)
    started = time.time()

    for f in files:
        stats['files'] += 1
        session = f'hermes-backfill:{f.stem[:8]}'
        f_blocks = 0
        for text, uuid, ts in assistant_texts(f):
            stats['msgs'] += 1
            for blk in extract_blocks(text):
                if is_noise(blk):
                    stats['noise'] += 1
                    continue
                h = hashlib.md5(blk.encode('utf-8')).hexdigest()
                if h in seen:
                    stats['hash_collide'] += 1
                    continue
                seen.add(h)
                stats['blocks'] += 1
                f_blocks += 1
                if dry_run:
                    continue
                payload = {
                    'session': session,
                    'content': blk,
                    'type': 'insight',
                    'source': 'harvester-backfill',
                    'host': 'hermes',
                    'hash': h,
                }
                r = post_insight(payload)
                if r == 'ok':
                    stats['posted'] += 1
                elif r == 'dup':
                    stats['dup'] += 1
                else:
                    stats['err'] += 1
        print(f'  {f.name[:40]:40s} blocks={f_blocks:4d} (cum posted={stats["posted"]} dup={stats["dup"]} err={stats["err"]})',
              file=sys.stderr)

    elapsed = time.time() - started
    mode = 'DRY-RUN' if dry_run else 'LIVE'
    print(f'\n[{mode}] {stats["files"]} files, {stats["msgs"]} assistant msgs scanned, {elapsed:.1f}s')
    print(f'  unique blocks extracted : {stats["blocks"]}')
    print(f'  noise filtered          : {stats["noise"]}')
    print(f'  intra-run hash dupes    : {stats["hash_collide"]}')
    if not dry_run:
        print(f'  POSTed (new in corpus)  : {stats["posted"]}')
        print(f'  rejected (already in db): {stats["dup"]}')
        print(f'  errors                  : {stats["err"]}')


if __name__ == '__main__':
    main()
