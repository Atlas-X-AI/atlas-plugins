---
name: execute-task
description: >-
  Execute the next TaskMaster task using the implementation plan with CDD
  verification. Picks the next ready task, matches it to the plan step,
  implements via a dispatched subagent, verifies subtasks with evidence,
  marks the task done, and loops until every task is complete.

  Wraps the TaskMaster next -> in-progress -> done lifecycle with CDD
  GREEN / RED / BLUE verification and the plugin's triple-verification
  rule. Autonomous by design — no user prompts inside the loop.
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Skill
  - Agent
---

# execute-task

The execution loop. Three sources converge:

- **Plan** (HOW) — `docs/superpowers/plans/*.md` produced by GENERATE
- **TaskMaster** (WHAT) — `.atlas-ai/taskmaster/tasks/tasks.json` with
  dependencies and complexity scores
- **CDD** (PROOF) — acceptance cards per task, evidence-gated

execute-task is the single skill that runs the full build from "tasks are
ready" to SHIP_CHECK_OK. It is autonomous — no AskUserQuestion inside the
loop. Any gap that would require user input is surfaced through the recon
escalation ladder (step 11) or the inbox (steps 4 and 8), never via a modal
prompt.

## Entry

This skill is invoked either:

1. Directly by the user once HANDOFF has completed and a task-execution
   mode (A/B/C) has been dispatched, **or**
2. By the `prd-taskmaster` orchestrator when `current_phase` is `EXECUTE`.

On entry, confirm that:

- `.atlas-ai/state/pipeline.json` exists and records `phase: EXECUTE`
- `.atlas-ai/taskmaster/tasks/tasks.json` exists with at least one ready task
- `.atlas-ai/customizations/system-prompt-template.md` is present (may be
  empty — absence is a setup bug, empty is fine)

If any of the above are missing, report the gap and halt. Do NOT attempt to
bootstrap the missing artifact from inside this loop — that is the
orchestrator's job.

## Cycle (per iteration)

Each pass through this cycle moves exactly one TaskMaster task from `pending`
to `done`. Do the 13 steps in order. Do not skip.

1. **Heartbeat check**: verify the execute-task heartbeat timer is running.
   If missing, register one via `CronCreate("execute-task-heartbeat", "* * * * *", "echo heartbeat")`.
   Abort the iteration if the timer cannot be created — a missing heartbeat
   means a missing stuck-session detector, and that is load-bearing.

2. **Inbox reconciliation**: read `.atlas-ai/state/pipeline.json`,
   `.atlas-ai/taskmaster/tasks/tasks.json`, and the current TodoWrite list.
   Diff them. If the three are stale by more than 5 tasks (i.e. TodoWrite
   says 10 done but tasks.json says 3 done), report the diff and halt — do
   not paper over bookkeeping drift by silently reconciling.

3. **Pick next task**: run the TaskMaster next command with the plugin's
   project-root pointer. Use exactly this invocation:

   ```bash
   TASK_MASTER_PROJECT_ROOT=.atlas-ai/taskmaster task-master next --format json
   ```

   Parse the JSON result.
   - If no ready tasks and all tasks are `done`, run `.atlas-ai/ship-check.py`,
     emit SHIP_CHECK_OK on success, exit the loop.
   - If no ready tasks but pending tasks exist, the dependency graph is
     deadlocked — report and halt.

4. **Load plan step**: read `docs/superpowers/plans/*.md` for the matching
   task ID. If no matching step is found, the task was invented downstream
   of the plan — mark the task `blocked`, inbox the parent orchestrator with
   `message_type="blocker"`, and continue to the next iteration.

5. **Generate CDD card**: convert the task's `subtasks` field into a
   `testing_plan`. Each subtask becomes a verifiable check with a concrete
   evidence path (file, command output, or test name). Write the card to
   `.atlas-ai/cdd/task-<id>.json`. A task without subtasks is treated as a
   single RED card.

6. **Set in-progress**: run `task-master set-status --id <N> --status in-progress`
   with `TASK_MASTER_PROJECT_ROOT=.atlas-ai/taskmaster`. This flip is
   observable by watchers and anchors the iteration in TaskMaster itself.

7. **Dispatch implementer subagent** — NEVER in-session. The controller
   must:

   - Provide the FULL task text to the subagent. Never tell the subagent to
     "read tasks.json" — per spec §12, the controller serialises the task
     into the dispatch prompt.
   - Inject the plugin customisation block at `.atlas-ai/customizations/system-prompt-template.md`
     into the subagent's system prompt. If the file is empty, inject nothing
     and continue.
   - Tier the model by TaskMaster complexity score:
     - `1-4 fast` — use the fast tier (Haiku-class)
     - `5-7 standard` — use the standard tier (Sonnet-class)
     - `8-10 capable` — use the capable tier (Opus-class)
   - Wait for the subagent to return a terminal status: `DONE`,
     `DONE_WITH_CONCERNS`, `NEEDS_CONTEXT`, or `BLOCKED`.

   Rationale: complexity-tiered dispatch keeps the dollars-per-task curve
   sensible. A complexity-2 boilerplate task does not need Opus; a
   complexity-9 architectural task should not be given to Haiku.

8. **Route by status**: the subagent's return status drives the next move.

   - **DONE** — proceed to the spec gate, then the quality gate. If both
     pass, advance to step 9.
   - **DONE_WITH_CONCERNS** — the subagent completed but flagged concerns.
     Address each concern before advancing; re-dispatch if needed.
   - **NEEDS_CONTEXT** — the subagent requested more context. Provide the
     requested context and re-dispatch. Retry cap at 2 — if the subagent
     still returns NEEDS_CONTEXT after two re-dispatches, escalate via the
     recon ladder (step 11).
   - **BLOCKED** — the subagent cannot proceed. Try one model-tier upgrade
     first (e.g. standard -> capable). If still blocked, break the task
     into smaller subtasks via `task-master expand --id <N>`. If still
     blocked, set status=blocked, inbox parent, halt this iteration.

   Do NOT invent new status values. The four above are the only terminal
   returns. Any other string from the subagent is a protocol violation and
   should be logged + treated as BLOCKED.

9. **Triple verification** — the plugin's core quality gate, per spec §11.4.
   Three independent checks must agree:

   - Plugin-native check: evidence file count vs declared subtask count
     (from the CDD card in step 5). Missing evidence = fail.
   - `/doubt` skill — adversarial doubt sweep on the claimed completion.
   - `/validate` skill — deterministic validation pass (lint / tests / exit
     codes).
   - External `Opus subagent` sanity pass — asks a fresh subagent "would
     you merge this?" with the task spec + diff + evidence.

   3+ agree pass -> task passes. Disagreement -> halt this iteration,
   surface to inbox.

10. **Mark done**: run `task-master set-status --id <N> --status done`.
    Update `.atlas-ai/state/pipeline.json` atomically in the same step —
    read, modify, write to a temp file, rename. Never leave pipeline.json
    and tasks.json mutually inconsistent.

11. **Check stepback triggers**: if 15 minutes have passed with no task
    moving to done, OR 5 consecutive iterations have failed on the same
    task class, the recon escalation ladder is MANDATORY. Climb the ladder
    in this exact order, not out of order:

    `/stepback` -> `/research-before-coding` -> `/question` -> `pivot`

    - `/stepback` — reassess the architectural assumption. Was the plan
      wrong?
    - `/research-before-coding` — feed the blocker into the Perplexity +
      Context7 + GitHub pipeline for fresh external context.
    - `/question` — batch-research the unresolved unknowns in parallel.
    - `pivot` — the plan step itself is unsound; kick the task back to the
      plan author (inbox parent with `message_type="plan_pivot_requested"`).

    The ladder is append-only — if `/stepback` surfaces a fix, apply it and
    return to step 3. Only climb if the prior rung did not yield progress.

12. **Render gamify score** — emit the atlas-gamify one-line score for this
    iteration (tasks done / tasks total, complexity-weighted). This is the
    human-visible progress signal and also feeds the dogfood debrief.

13. **Loop**: back to step 1 until SHIP_CHECK_OK or a halt condition fires.

## Termination

Only emit a completion signal when `.atlas-ai/ship-check.py` returns
SHIP_CHECK_OK. Do not emit on a mere "DONE" keyword match in a subagent
reply, and do not emit on "all tasks marked done" without the explicit
ship-check.

The ship-check script is deterministic — it verifies:

- Every task in tasks.json is `status=done`
- Every CDD card has its evidence file
- The plan's exit criteria are satisfied
- The pipeline.json `phase` is `EXECUTE` with no outstanding blockers

Only when all four pass does it print `SHIP_CHECK_OK`. That token is the
one thing the orchestrator watches for — emit it nowhere else in your
output to avoid false positives on log-watchers.

## Red flags

These are the most common pressure points where the loop silently degrades
from "verified" to "performative". If you catch yourself thinking any of
them, stop and repair the gap.

- "Close enough, mark it done" -> NO. Evidence OR nothing.
- "Let me skip the doubt step this time" -> NO. Triple verification is non-negotiable.
- "I'll retry with same model+prompt" (BLOCKED) -> NO. Escalate.
- "The task says done, don't check evidence files" -> NO. Task status must reflect evidence.

## Observability

Every iteration appends a structured row to
`.atlas-ai/state/execute-log.jsonl` with:

- iteration number, timestamp, task id, complexity, tier used
- subagent terminal status, retry count
- triple-verification result (pass / fail + which checker dissented)
- stepback triggered (yes / no) and ladder rung reached
- gamify score

This log is the dogfood artifact — debrief tools consume it, the
orchestrator greps it, and future runs read it for retrospective analysis.

## Composition

- **Orchestrator handoff**: this skill is invoked post-HANDOFF. It does
  not call `/handoff` — that direction is one-way.
- **Plan editing**: if the plan is unsound, the ladder escalates to
  `pivot`, which inboxes the plan author. This skill does not mutate the
  plan in place.
- **Ship-check**: `.atlas-ai/ship-check.py` is the terminal gate. This
  skill calls it; it does not reimplement the checks.

## Non-exits

This skill uses no explicit process termination. A halt condition reports
the reason in the structured log and returns control to the caller (the
user or the orchestrator). Never kill the shell — the caller owns the
session lifecycle.
