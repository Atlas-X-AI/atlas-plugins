"""
Pipeline state machine for the plugin. ATOMIC compare-and-swap transitions.
Phases: SETUP -> DISCOVER -> GENERATE -> HANDOFF -> EXECUTE.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from lib import atomic_write, locked_update, read_json, emit_json_error, now_iso

ATLAS_AI_DIR = Path(".atlas-ai")
STATE_DIR = ATLAS_AI_DIR / "state"
PIPELINE_FILE = STATE_DIR / "pipeline.json"
TASKS_FILE = ATLAS_AI_DIR / "taskmaster" / "tasks" / "tasks.json"
PRD_FILE = ATLAS_AI_DIR / "taskmaster" / "docs" / "prd.md"

PHASES = ["SETUP", "DISCOVER", "GENERATE", "HANDOFF", "EXECUTE"]

LEGAL_TRANSITIONS = {
    None: ["SETUP"],
    "SETUP": ["DISCOVER"],
    "DISCOVER": ["GENERATE"],
    "GENERATE": ["HANDOFF"],
    "HANDOFF": ["EXECUTE"],
    "EXECUTE": [],
}


def _load_state() -> dict:
    if not PIPELINE_FILE.exists():
        return {"current_phase": None, "phases_completed": [], "phase_evidence": {}, "version": "5.0.0"}
    return read_json(PIPELINE_FILE)


def current_phase() -> dict:
    state = _load_state()
    return {
        "ok": True,
        "current_phase": state.get("current_phase"),
        "phases_completed": state.get("phases_completed", []),
        "phase_evidence": state.get("phase_evidence", {}),
    }


def advance_phase(expected_current: Optional[str], target: str, evidence: dict) -> dict:
    if target not in PHASES:
        return emit_json_error(f"unknown target phase: {target}", phases=PHASES)

    def transform(content: str) -> str:
        state = json.loads(content) if content.strip() else {"current_phase": None, "phases_completed": [], "phase_evidence": {}, "version": "5.0.0"}
        actual = state.get("current_phase")
        if actual != expected_current:
            raise _CASMiss(actual)
        if target not in LEGAL_TRANSITIONS.get(actual, []):
            raise _IllegalTransition(actual, target)
        state["current_phase"] = target
        completed = state.get("phases_completed", [])
        if expected_current and expected_current not in completed:
            completed.append(expected_current)
        state["phases_completed"] = completed
        state.setdefault("phase_evidence", {})[target] = {
            "entered_at": now_iso(),
            "from": expected_current,
            "evidence": evidence,
        }
        return json.dumps(state, indent=2, default=str)

    try:
        locked_update(PIPELINE_FILE, transform)
    except _CASMiss as e:
        return emit_json_error(
            f"stale expected_current: caller expected {expected_current}, actual is {e.actual}",
            expected=expected_current, actual=e.actual
        )
    except _IllegalTransition as e:
        return emit_json_error(
            f"illegal transition: {e.source} -> {e.target}",
            legal=LEGAL_TRANSITIONS.get(e.source, []),
        )

    return {"ok": True, "new_phase": target, "previous": expected_current}


def check_gate(phase: str, evidence: dict) -> dict:
    violations = []
    if phase == "SETUP":
        vs = evidence.get("validate_setup", {})
        if not vs.get("ready") or vs.get("critical_failures", 1) > 0:
            violations.append("validate_setup must report ready=true with 0 critical failures")
    elif phase == "DISCOVER":
        if not (evidence.get("user_approved") or (evidence.get("auto_classification") == "CLEAR" and evidence.get("assumptions_documented"))):
            violations.append("DISCOVER gate requires user_approved=true OR auto_classification=CLEAR with assumptions_documented=true")
    elif phase == "GENERATE":
        if evidence.get("validation_grade") not in ("EXCELLENT", "GOOD"):
            violations.append("validation_grade must be EXCELLENT or GOOD")
        if evidence.get("task_count", 0) == 0:
            violations.append("tasks must be parsed (task_count > 0)")
        if evidence.get("subtask_coverage", 0) < 1.0:
            violations.append("all tasks must have subtasks (coverage must be 1.0)")
    elif phase == "HANDOFF":
        if not evidence.get("user_mode_choice"):
            violations.append("user_mode_choice must be recorded (from AskUserQuestion)")
        if not evidence.get("plan_file_exists"):
            violations.append("writing-plans must have written the plan file")

    return {
        "ok": True,
        "gate_passed": len(violations) == 0,
        "violations": violations,
        "phase": phase,
    }


def preflight(cwd: Optional[str] = None) -> dict:
    if cwd:
        import os
        os.chdir(cwd)

    state = _load_state()
    cp = state.get("current_phase")

    prd_exists = PRD_FILE.exists()
    tasks_count = 0
    if TASKS_FILE.exists():
        tasks = read_json(TASKS_FILE)
        master = tasks.get("master", {})
        tasks_count = len(master.get("tasks", [])) if isinstance(master, dict) else len(tasks.get("tasks", []))

    has_taskmaster = ATLAS_AI_DIR.joinpath("taskmaster").exists()

    if cp == "EXECUTE" and tasks_count > 0:
        rec = "resume"
    elif prd_exists and tasks_count == 0:
        rec = "parse_prd"
    elif has_taskmaster and not prd_exists:
        rec = "generate_prd"
    elif not has_taskmaster:
        rec = "run_setup"
    elif cp == "EXECUTE" and tasks_count > 0:
        if TASKS_FILE.exists():
            all_tasks = read_json(TASKS_FILE).get("master", {}).get("tasks", [])
            if all(t.get("status") == "done" for t in all_tasks):
                rec = "complete"
            else:
                rec = "resume"
    else:
        rec = "run_setup"

    return {
        "ok": True,
        "current_phase": cp,
        "prd_path": str(PRD_FILE) if prd_exists else None,
        "task_count": tasks_count,
        "has_taskmaster": has_taskmaster,
        "recommended_action": rec,
    }


class _CASMiss(Exception):
    def __init__(self, actual): self.actual = actual

class _IllegalTransition(Exception):
    def __init__(self, source, target):
        self.source = source
        self.target = target
