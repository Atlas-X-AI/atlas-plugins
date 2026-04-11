#!/bin/bash
# Test suite for stop-hook.sh
# Tests promise detection, session isolation, max iterations, and edge cases.

set -euo pipefail

HOOK_SCRIPT="$(cd "$(dirname "$0")/.." && pwd)/hooks/stop-hook.sh"
PASS=0
FAIL=0
ERRORS=""

# --- Helpers ---

setup_tmpdir() {
  TMPDIR_TEST=$(mktemp -d)
  mkdir -p "$TMPDIR_TEST/.claude"
}

teardown_tmpdir() {
  rm -rf "$TMPDIR_TEST"
}

# Write a ralph state file with given params
# Usage: write_state <iteration> <max_iterations> <promise> <session_id> <prompt>
write_state() {
  local iter="$1" max="$2" promise="$3" session="$4" prompt="$5"
  cat > "$TMPDIR_TEST/.claude/ralph-loop.local.md" <<STATEEOF
---
iteration: $iter
max_iterations: $max
completion_promise: "$promise"
session_id: $session
---
$prompt
STATEEOF
}

# Build a JSONL transcript line for an assistant text block
jsonl_text() {
  local text="$1"
  jq -nc --arg t "$text" '{"role":"assistant","message":{"content":[{"type":"text","text":$t}]}}'
}

# Build a JSONL transcript line for a tool_use block
jsonl_tool_use() {
  local name="${1:-bash}"
  jq -nc --arg n "$name" '{"role":"assistant","message":{"content":[{"type":"tool_use","name":$n}]}}'
}

# Run the hook in the temp dir context and capture output + exit code
# Usage: run_hook <session_id> <transcript_path>
run_hook() {
  local session_id="$1"
  local transcript="$2"
  local hook_input
  hook_input=$(jq -nc --arg sid "$session_id" --arg tp "$transcript" \
    '{"session_id":$sid,"transcript_path":$tp}')

  local output exit_code
  # Run from the temp dir so the hook finds .claude/ralph-loop.local.md
  output=$(cd "$TMPDIR_TEST" && echo "$hook_input" | bash "$HOOK_SCRIPT" 2>&1) && exit_code=$? || exit_code=$?
  echo "$output"
  return $exit_code
}

# Assert that the hook output contains "decision":"block" (loop continues)
assert_blocks() {
  local test_name="$1"
  local output="$2"
  if echo "$output" | grep -q '"decision"'; then
    if echo "$output" | jq -e '.decision == "block"' >/dev/null 2>&1; then
      PASS=$((PASS + 1))
      echo "  PASS: $test_name"
      return 0
    fi
  fi
  FAIL=$((FAIL + 1))
  ERRORS="${ERRORS}\n  FAIL: $test_name — expected block, got: $(echo "$output" | head -3)"
  echo "  FAIL: $test_name"
  return 1
}

# Assert that the hook exits 0 without blocking (promise detected or max iterations)
assert_allows_exit() {
  local test_name="$1"
  local output="$2"
  local exit_code="$3"
  # Should NOT contain "decision":"block"
  if echo "$output" | jq -e '.decision == "block"' >/dev/null 2>&1; then
    FAIL=$((FAIL + 1))
    ERRORS="${ERRORS}\n  FAIL: $test_name — expected allow exit, got block"
    echo "  FAIL: $test_name"
    return 1
  fi
  if [[ "$exit_code" -eq 0 ]]; then
    PASS=$((PASS + 1))
    echo "  PASS: $test_name"
    return 0
  fi
  FAIL=$((FAIL + 1))
  ERRORS="${ERRORS}\n  FAIL: $test_name — expected exit 0, got exit $exit_code"
  echo "  FAIL: $test_name"
  return 1
}

# =============================================================================
# TESTS
# =============================================================================

echo "Running stop-hook.sh tests..."
echo ""

# --- T1: Promise in LAST text block (should always pass) ---
echo "T1: Promise in last text block"
setup_tmpdir
write_state 1 10 "GREEN - all tests pass" "sess-001" "Do the work"
TRANSCRIPT="$TMPDIR_TEST/transcript.jsonl"
{
  jsonl_text "Working on it..."
  jsonl_text "Done! <promise>GREEN - all tests pass</promise>"
} > "$TRANSCRIPT"

OUTPUT=$(run_hook "sess-001" "$TRANSCRIPT") && EC=$? || EC=$?
assert_allows_exit "T1: promise in last block detected" "$OUTPUT" "$EC" || true
teardown_tmpdir

# --- T2: Promise in NON-LAST text block (THE BUG) ---
echo "T2: Promise in non-last text block"
setup_tmpdir
write_state 1 10 "GREEN - all tests pass" "sess-001" "Do the work"
TRANSCRIPT="$TMPDIR_TEST/transcript.jsonl"
{
  jsonl_text "Starting work..."
  jsonl_text "Done! <promise>GREEN - all tests pass</promise>"
  jsonl_text "Let me also clean up some files."
} > "$TRANSCRIPT"

OUTPUT=$(run_hook "sess-001" "$TRANSCRIPT") && EC=$? || EC=$?
assert_allows_exit "T2: promise in non-last block detected" "$OUTPUT" "$EC" || true
teardown_tmpdir

# --- T3: Promise followed by tool_use then more text ---
echo "T3: Promise followed by tool_use then text"
setup_tmpdir
write_state 1 10 "GREEN - all tests pass" "sess-001" "Do the work"
TRANSCRIPT="$TMPDIR_TEST/transcript.jsonl"
{
  jsonl_text "<promise>GREEN - all tests pass</promise>"
  jsonl_tool_use "bash"
  jsonl_text "Tool output processed."
} > "$TRANSCRIPT"

OUTPUT=$(run_hook "sess-001" "$TRANSCRIPT") && EC=$? || EC=$?
assert_allows_exit "T3: promise before tool_use detected" "$OUTPUT" "$EC" || true
teardown_tmpdir

# --- T4: No promise tag at all (should continue loop / block) ---
echo "T4: No promise tag"
setup_tmpdir
write_state 1 10 "GREEN - all tests pass" "sess-001" "Do the work"
TRANSCRIPT="$TMPDIR_TEST/transcript.jsonl"
{
  jsonl_text "Working on it..."
  jsonl_text "Still going."
} > "$TRANSCRIPT"

OUTPUT=$(run_hook "sess-001" "$TRANSCRIPT") && EC=$? || EC=$?
assert_blocks "T4: no promise continues loop" "$OUTPUT" || true
teardown_tmpdir

# --- T5: File-based termination .claude/ralph-done (not implemented yet) ---
echo "T5: File-based termination (not implemented — expected FAIL)"
setup_tmpdir
write_state 1 10 "GREEN - all tests pass" "sess-001" "Do the work"
TRANSCRIPT="$TMPDIR_TEST/transcript.jsonl"
{
  jsonl_text "Working..."
} > "$TRANSCRIPT"
# Create the done file that Task 2 will implement
touch "$TMPDIR_TEST/.claude/ralph-done"

OUTPUT=$(run_hook "sess-001" "$TRANSCRIPT") && EC=$? || EC=$?
# This SHOULD allow exit once Task 2 is implemented, but currently it will block
if echo "$OUTPUT" | jq -e '.decision == "block"' >/dev/null 2>&1; then
  echo "  XFAIL: T5: file-based termination not implemented yet (expected)"
  # Don't count as pass or fail — it's expected to fail
else
  PASS=$((PASS + 1))
  echo "  PASS: T5: file-based termination works"
fi
teardown_tmpdir

# --- T6: Max iterations reached ---
echo "T6: Max iterations reached"
setup_tmpdir
write_state 5 5 "GREEN - all tests pass" "sess-001" "Do the work"
TRANSCRIPT="$TMPDIR_TEST/transcript.jsonl"
{
  jsonl_text "Still going..."
} > "$TRANSCRIPT"

OUTPUT=$(run_hook "sess-001" "$TRANSCRIPT") && EC=$? || EC=$?
assert_allows_exit "T6: max iterations stops loop" "$OUTPUT" "$EC" || true
teardown_tmpdir

# --- T7: Session isolation ---
echo "T7: Session isolation"
setup_tmpdir
write_state 1 10 "GREEN - all tests pass" "sess-001" "Do the work"
TRANSCRIPT="$TMPDIR_TEST/transcript.jsonl"
{
  jsonl_text "Working..."
} > "$TRANSCRIPT"

# Different session should be ignored (exit 0, no block)
OUTPUT=$(run_hook "sess-OTHER" "$TRANSCRIPT") && EC=$? || EC=$?
assert_allows_exit "T7: different session ignores state" "$OUTPUT" "$EC" || true
teardown_tmpdir

# --- T8: Common word promise "the" (Perl regex fix test) ---
echo "T8: Common word promise (Perl regex edge case)"
setup_tmpdir
write_state 1 10 "the" "sess-001" "Do the work"
TRANSCRIPT="$TMPDIR_TEST/transcript.jsonl"
{
  jsonl_text "Here is the output with the word the in it but no promise tags."
} > "$TRANSCRIPT"

OUTPUT=$(run_hook "sess-001" "$TRANSCRIPT") && EC=$? || EC=$?
# Should NOT match — the word "the" appears in text but not in <promise> tags
# With the broken Perl regex, the entire text gets returned and may match
assert_blocks "T8: common word without tags does NOT match" "$OUTPUT" || true
teardown_tmpdir

# --- T8b: Perl regression — promise equals full output, no tags ---
echo "T8b: Perl regression (promise equals full output text, no tags)"
setup_tmpdir
write_state 1 10 "Working on it" "sess-001" "Do the work"
TRANSCRIPT="$TMPDIR_TEST/transcript.jsonl"
{
  jsonl_text "Working on it"
} > "$TRANSCRIPT"

OUTPUT=$(run_hook "sess-001" "$TRANSCRIPT") && EC=$? || EC=$?
# Old Perl regex returned full input on no-match. If that full input happened
# to equal the completion promise, the loop would spuriously terminate.
# New regex returns empty on no-match, so this correctly continues.
assert_blocks "T8b: no tags + promise equals full text continues loop" "$OUTPUT" || true
teardown_tmpdir

# =============================================================================
# SUMMARY
# =============================================================================

echo ""
echo "================================"
echo "Results: $PASS passed, $FAIL failed"
if [[ -n "$ERRORS" ]]; then
  echo ""
  echo "Failures:"
  echo -e "$ERRORS"
fi
echo "================================"

exit $FAIL
