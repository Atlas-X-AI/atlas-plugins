---
name: setup
description: >-
  Phase 0 of the prd-taskmaster pipeline. Verifies task-master is installed,
  the project is initialized, the provider stack is configured (DETECT-FIRST —
  never overwrite a working user config), and the AI pipeline actually runs.
  Autonomous: zero user questions unless a hard block is hit. Declares the
  Setup phase complete so DISCOVER can follow.
user-invocable: false
allowed-tools:
  - Read
  - Bash
  - Skill
---

# Phase 0: Setup

Declarative phase skill. Invoked by the prd-taskmaster orchestrator when
`current_phase` is null or `SETUP`. Never called directly by a user.

## Entry gate

1. Call `mcp__plugin_prd_taskmaster_prd_taskmaster__check_gate(target_phase="SETUP")`.
   If the call returns `{allowed: false, reason: ...}`, report the reason and stop.
   The gate protects against re-entering a completed phase or skipping ahead.

## Procedure (5 steps, abort on hard failure)

### Step 1: Installation check

Run `which task-master-ai`.

If the binary is not found, report:

```
task-master not installed. Install with:
  npm install -g task-master-ai
Then re-run this skill.
```

Abort the phase. Do NOT auto-install.

### Step 2: Project init

Check whether the current project has a `.taskmaster/` directory.

If missing, run `task-master init --yes`. If present, continue.

### Step 3: Provider configuration — DETECT-FIRST

**Read `task-master models` output BEFORE setting anything.** This is the
load-bearing rule. A working user config must NOT be overwritten silently.

| `task-master models` output | Action |
|---|---|
| Main / Research / Fallback all populated with a supported provider | SKIP — go to Step 4. |
| Main set, Research/Fallback empty | Partial mutate — fill the empty roles only. |
| All three empty (fresh install) | Full configure — use the default stack below. |
| Provider flagged unsupported / deprecated | Ask the user before mutating. |

**Why DETECT-FIRST:** v4 dogfood (2026-04-13, LEARNING #9) caught the skill
overwriting a working `gemini-cli / gemini-3-pro-preview` config because the
procedure wasn't branch-aware. Detect first, mutate only the empty slots.

**Default stack (fresh install only):**

```bash
task-master models --set-main gemini-3-pro-preview --gemini-cli
task-master models --set-research gemini-3-pro-preview --gemini-cli
task-master models --set-fallback gemini-3-flash-preview --gemini-cli
```

Why Gemini CLI: ~113× more token-efficient than sonnet on parse-prd, free via
any Google account, no API key. One provider, three roles, zero cost.

**Alternatives:** Claude Max (`--claude-code sonnet/opus/haiku`), any of the
12 task-master provider families, or a registered MCP research tool for the
Research role.

### Step 4: Probe test

If tasks already exist, call the MCP tool
`mcp__plugin_prd_taskmaster_prd_taskmaster__validate_setup` or run
`task-master analyze-complexity --id 1`.

If no tasks exist yet (fresh project), skip the probe — Step 3's provider
configuration is sufficient evidence the pipeline is wired.

### Step 5: Status line

Emit a compact one-block status:

```
Setup:
  task-master: installed (<version>)
  project: initialized (.taskmaster/)
  provider: <main-provider> (main) / <research-provider> (research)
  pipeline: verified
```

## Exit gate

After Steps 1–5 report green:

1. Call `mcp__plugin_prd_taskmaster_prd_taskmaster__advance_phase(next_phase="DISCOVER")`.
   The call atomically transitions `pipeline.json` from SETUP to DISCOVER.
2. Return control to the orchestrator (`prd-taskmaster` skill). Do NOT invoke
   DISCOVER directly — the orchestrator re-reads `current_phase` and routes.

## Red flags (stop and report, do not paper over)

- "The config is set but looks wrong — I'll fix it" → NO. Report and ask.
- "No tasks exist so I'll skip the whole provider step" → NO. Provider must be
  configured before DISCOVER runs (otherwise `parse-prd` fails later).
- "I'll auto-install task-master via npm" → NO. Installation is a user action;
  this skill only detects and reports.
- "I can call advance_phase without check_gate" → NO. Gate first, always.

## Non-exits

This skill does not use explicit process termination. A hard block reports
the reason and returns control to the orchestrator; the orchestrator decides
whether to surface to the user.
