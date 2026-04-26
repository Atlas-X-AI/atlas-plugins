---
name: insight-review
description: Mine recent [PENTEST]/[AI]/[SPARK] insights from insights.db and propose 3-5 concrete, ship-today improvements. Use when user says /insight-review, "what should we build from recent insights", "mine my insights", or after a long working day to convert lessons into action. Default window 24h; args override.
---

# Insight Review

> Insights are cheap to generate and easy to forget. This skill harvests the last N insights, groups them, and forces conversion from "observation" to "thing we build tomorrow."

## When to run

- End of a working day / session → distil what was learned into actionable tickets
- After a run of debugging or pentesting → turn fingerprints into tooling
- When Hayden asks "what should I build?" → answer grounded in his own recent thinking
- NOT for: one-off questions, shallow chats, sessions with < ~10 insights in the window

## Arguments

Accept inline args after `/insight-review`:
- `--hours N` — window to pull (default 24)
- `--limit M` — max insights to load (default 40)
- `--type <all|pentest|ai|spark>` — filter by tag (default all)

If the user gave a domain cue ("frigate insights", "pentest insights from this week"),
translate to the nearest flag combo and tell them what you chose.

## Procedure

1. **Fetch** — run the helper script. It handles DB path, noise filtering, grouping, and markdown rendering. No need to open the DB directly.
   ```bash
   python3 ~/.claude/skills/insight-review/fetch_insights.py --hours 24 --limit 40 --type all
   ```
   Capture stdout. This is the raw distilled corpus.

2. **Read the corpus yourself.** Do not skim. For each insight, ask:
   - Is this a *fingerprint* of a recurring failure mode? (→ build a monitor)
   - Is this a *tool* we kept using manually? (→ wrap in a skill or script)
   - Is this a *trust trap* or *silent failure*? (→ add a guardrail)
   - Is this an *architectural lesson*? (→ document in CLAUDE.md, do not keep re-deriving)

3. **Propose 3–5 actionable improvements.** Format each as:
   ```
   ### Improvement N: <name>
   **Source insights:** <ids>
   **Build:** <one-sentence artifact — script, skill, hook, systemd unit, doc>
   **Why now:** <which pain does this remove>
   **Effort:** <trivial | small | medium>  |  **Payoff:** <low | medium | high>
   ```
   Prefer improvements backed by ≥2 insights — those are signal, not noise.
   Skip improvements that are already live (check via `ls ~/bin`, `ls ~/.claude/skills`, `systemctl --user list-units`).

4. **Rank by payoff/effort.** Surface the top 1 as "build this first" with a concrete file path and first command.

5. **Do NOT auto-build.** Per Jobs Lens Fix-Don't-Demolish rule: AI classifies and proposes; human decides. Ask Hayden which to build. If he replies with a number, execute that one.

## Output shape

- ≤ 600 words total
- Indexed `[N.M]` per the reply indexing convention
- End with: one direct question — "which of these do you want built first?"

## Guardrails

- If fewer than 5 insights qualify, say so plainly and suggest widening `--hours`. Do not fabricate improvements.
- If the corpus is dominated by one project, name it — otherwise Hayden cannot tell if the review is representative.
- Never dump raw insight content longer than 400 chars — trust the source IDs for drill-down.
- Cite insight IDs `[1234]` next to every claim. If you cannot cite, the claim does not belong.

## Example invocations

- `/insight-review` → last 24h, all tags
- `/insight-review --hours 72 --type pentest` → pentest fingerprints over the long weekend
- `/insight-review --type spark` → reframe candidates only
