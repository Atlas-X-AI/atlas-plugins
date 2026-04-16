#!/usr/bin/env python3
"""Deterministic ship-check. Emits SHIP_CHECK_OK to stdout ONLY when all gates pass.

Referenced by /atlas-ralph-loop:ralph-loop --completion-promise SHIP_CHECK_OK per spec §11.8.
(atlas-ralph-loop is Hayden's patched+improved fork of /ralph-loop; legacy /ralph-loop:ralph-loop
remains fallback only.)

DIVERGENCE FROM PLAN §D7.3 (gen5 Jobs-Lens diagnosis):
  Plan comment says "Gate 1: pipeline.json says EXECUTE + complete" but plan code only checks
  current_phase == "EXECUTE". Spec §D (lines 876-877) proves pipeline.json has BOTH fields:
      assert pipeline_json["current_phase"] == "EXECUTE"
      assert pipeline_json["state"] == "complete"
  Without the state check, a pipeline stuck IN EXECUTE phase with unfinished work passes Gate 1.
  This draft fixes that — Gate 1 requires both conditions.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def check() -> tuple[bool, list[str]]:
    failures: list[str] = []
    atlas = Path(".atlas-ai")

    # Gate 1: pipeline.json EXECUTE + complete
    pf = atlas / "state" / "pipeline.json"
    if not pf.exists():
        failures.append("pipeline.json missing")
    else:
        try:
            state = json.loads(pf.read_text())
        except json.JSONDecodeError as exc:
            failures.append(f"pipeline.json invalid JSON: {exc}")
        else:
            if state.get("current_phase") != "EXECUTE":
                failures.append(f"current_phase != EXECUTE (got {state.get('current_phase')!r})")
            if state.get("state") != "complete":
                failures.append(f"pipeline state != complete (got {state.get('state')!r})")

    # Gate 2: tasks.json all done with evidence
    tf = atlas / "taskmaster" / "tasks" / "tasks.json"
    if not tf.exists():
        failures.append("tasks.json missing")
    else:
        try:
            tdata = json.loads(tf.read_text())
        except json.JSONDecodeError as exc:
            failures.append(f"tasks.json invalid JSON: {exc}")
        else:
            all_tasks = tdata.get("master", {}).get("tasks", [])
            if not all_tasks:
                failures.append("tasks.json has no tasks under master.tasks")
            for t in all_tasks:
                if t.get("status") != "done":
                    failures.append(f"task {t.get('id')} not done (status={t.get('status')!r})")
                elif not t.get("evidence_files"):
                    failures.append(f"task {t.get('id')} has no evidence_files")

    # Gate 3: plan file exists
    plans = Path("docs/superpowers/plans")
    if not plans.exists() or not list(plans.glob("*.md")):
        failures.append("no plan file in docs/superpowers/plans/")

    # Gate 4: ralph-loop prompt exists (per spec §11.9)
    if not (atlas / "ralph-loop-prompt.md").exists():
        failures.append(".atlas-ai/ralph-loop-prompt.md missing (ralph-loop will fail with empty prompt)")

    return len(failures) == 0, failures


def main() -> None:
    ok, failures = check()
    if ok:
        print("SHIP_CHECK_OK")
        sys.exit(0)
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
