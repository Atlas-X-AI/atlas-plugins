# atlas-ralph-loop

Hardened fork of [claude-plugins-official/ralph-loop](https://github.com/anthropics/claude-code-plugins) with reliable termination detection.

## What's Different

The upstream ralph-loop has a critical bug: it only checks the **last text block** in Claude's output for the `<promise>` completion tag. If Claude does any work after outputting the promise (tool calls, more text), the tag is missed and the loop runs forever.

### Fixes in this fork

| Fix | What | Why |
|-----|------|-----|
| **Scan all text blocks** | jq `last` → `join("\n")` | Promise tag detected regardless of position in output |
| **File-based termination** | `.claude/ralph-done` signal | Position-independent, works even with stale transcripts |
| **Perl regex no-match** | `-pe` → `-ne` with explicit match | Old regex returned full input on no-match, causing spurious exits |
| **Scan window bump** | 100 → 300 lines | Prevents missed tags in long multi-tool iterations |
| **Regression test suite** | 9 tests covering all failure modes | TDD-verified, catches regressions |

### Dual Termination Protocol

Claude can signal completion via **either** method (both checked):

1. **File signal (most reliable):** Write the promise word to `.claude/ralph-done`
2. **Promise tag (original):** Output `<promise>WORD</promise>` in text

The file method is position-independent — it works regardless of what Claude does after writing it.

## Quick Start

```bash
/ralph-loop "Build a REST API for todos. Output <promise>DONE</promise> when complete." --completion-promise "DONE" --max-iterations 20
```

## Commands

### /ralph-loop

Start a Ralph loop in your current session.

```bash
/ralph-loop "<prompt>" --max-iterations <n> --completion-promise "<text>"
```

**Options:**
- `--max-iterations <n>` — Stop after N iterations (default: unlimited)
- `--completion-promise <text>` — Phrase that signals completion

### /cancel-ralph

Cancel the active Ralph loop.

```bash
/cancel-ralph
```

## Prompt Best Practices

### Use unique completion words

```bash
# Good — unique, can't accidentally match
--completion-promise "DONE"
--completion-promise "TASK COMPLETE"

# Bad — common word, fragile
--completion-promise "the"
```

### Always set max-iterations as a safety net

```bash
/ralph-loop "Fix the auth bug" --completion-promise "FIXED" --max-iterations 20
```

### Include termination instructions in your prompt

```markdown
When genuinely complete:
1. Write 'DONE' to .claude/ralph-done
2. Output <promise>DONE</promise> as your final line
```

## Running Tests

```bash
bash tests/test-stop-hook.sh
```

Expected: 9/9 pass.

## How It Works

1. `/ralph-loop` creates `.claude/ralph-loop.local.md` state file
2. Claude works on the task
3. When Claude tries to exit, the Stop hook fires
4. Hook checks for `.claude/ralph-done` file (instant, reliable)
5. Hook scans ALL recent text blocks for `<promise>` tags
6. If neither found: blocks exit, re-injects same prompt
7. If found: cleans up state, allows exit

## Credits

Based on the [Ralph Wiggum technique](https://ghuntley.com/ralph/) by Geoffrey Huntley. Original plugin by Anthropic. Hardened by [anombyte93](https://github.com/anombyte93).

## License

MIT
