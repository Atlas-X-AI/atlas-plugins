#!/usr/bin/env bash
# atlas-insights:insight-harvester — PostToolUse hook
# Forwards insight blocks written to /tmp/insights/<session>.md to the corpus host.
# Recognises ★ Insight ─...─ blocks AND [SPARK]/[AI]/[PENTEST]/[MECHANISM]/...
# tagged blocks. Hash-dedupes per session. Idempotent. Exit 0 always.

set -euo pipefail

ENDPOINT="${ATLAS_INSIGHTS_ENDPOINT:-http://100.113.114.116:3100/insight/store}"
HOST_TAG="${ATLAS_INSIGHTS_HOST_TAG:-$(hostname)}"

INPUT=$(cat)

FILE_PATH=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    fp = (d.get('tool_input') or {}).get('file_path', '')
    tool = d.get('tool_name','')
    if tool in ('Write','Edit','MultiEdit') and fp.startswith('/tmp/insights/') and fp.endswith('.md'):
        print(fp)
except Exception:
    pass
" 2>/dev/null || true)

[[ -z "$FILE_PATH" ]] && exit 0
[[ ! -f "$FILE_PATH" ]] && exit 0

SESSION_BASE=$(basename "$FILE_PATH" .md)
HASHDIR="/tmp/insights/.sent"
mkdir -p "$HASHDIR" 2>/dev/null || true
HASHFILE="$HASHDIR/${SESSION_BASE}.hashes"
touch "$HASHFILE" 2>/dev/null || true

ATLAS_INSIGHTS_ENDPOINT="$ENDPOINT" ATLAS_INSIGHTS_HOST_TAG="$HOST_TAG" \
SESSION="$SESSION_BASE" HASHFILE="$HASHFILE" INSIGHT_FILE="$FILE_PATH" \
python3 <<'PY' >/dev/null 2>&1 || true
import hashlib, json, os, re, sys, urllib.request

session  = os.environ.get('SESSION','unknown')
hashfile = os.environ['HASHFILE']
insight_file = os.environ['INSIGHT_FILE']
endpoint = os.environ['ATLAS_INSIGHTS_ENDPOINT']
host_tag = os.environ['ATLAS_INSIGHTS_HOST_TAG']

try:
    body = open(insight_file, encoding='utf-8', errors='replace').read()
except Exception:
    sys.exit(0)

try:
    sent = set(l.strip() for l in open(hashfile) if l.strip())
except Exception:
    sent = set()

blocks = []
star_re = re.compile(r'^[^\n]*★\s*Insight\s*─+[^\n]*\n(.*?)\n[^\n]*─{5,}[^\n]*$', re.DOTALL | re.MULTILINE)
for m in star_re.findall(body):
    blocks.append(m.strip())

tag_re = re.compile(r'\[(SPARK|AI|PENTEST|MECHANISM|BLINDSPOT|CONTRADICTION|ALTERNATIVE)\]')
for p in re.split(r'\n-{3,}\n', body):
    p = p.strip()
    if p and tag_re.search(p) and p not in blocks:
        blocks.append(p)

NOISE = [re.compile(r'\d+\s+tasks\s+\('),
         re.compile(r'^\s*[✔◻◼✅❌]', re.MULTILINE),
         re.compile(r'^(Last Updated:|##\s+Session State)', re.MULTILINE)]

def is_noise(c):
    if len(c) < 20: return True
    if any(r.search(c) for r in NOISE): return True
    if len(c) > 1500 and len(re.findall(r'\[(SPARK|AI|PENTEST|MECHANISM)\]', c)) < 3: return True
    return False

new_hashes = []
for content in blocks:
    if is_noise(content): continue
    h = hashlib.md5(content.encode('utf-8')).hexdigest()
    if h in sent: continue
    payload = json.dumps({
        'session': session, 'content': content, 'type': 'insight',
        'source': 'harvester-write', 'host': host_tag, 'hash': h,
    }).encode('utf-8')
    req = urllib.request.Request(endpoint, data=payload, method='POST',
                                  headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req, timeout=5).read()
        new_hashes.append(h)
    except Exception:
        pass

if new_hashes:
    try:
        with open(hashfile, 'a') as f:
            for h in new_hashes: f.write(h + '\n')
    except Exception:
        pass
PY

exit 0
