"""
PRD validation module: 14 quality checks (13 content + 1 placeholder attribution).

Ported from prd-taskmaster-v4 script.py (cmd_validate_prd) with refactoring:
  - Returns a dict instead of exiting (spec §13.3)
  - Accepts ai: bool parameter (stubbed for v5.0 baseline)
  - No subprocess calls, no forced process termination

All check logic, thresholds, and grading bands are preserved exactly from v4.
"""
from __future__ import annotations

import re
from pathlib import Path

from lib import emit_json_error

# ─── Constants ────────────────────────────────────────────────────────────────

VAGUE_WORDS = [
    "fast", "quick", "slow", "good", "bad", "poor",
    "user-friendly", "easy", "simple", "secure", "safe",
    "scalable", "flexible", "performant", "efficient",
]

VAGUE_PATTERN = re.compile(
    r'\b(?:should\s+be\s+|must\s+be\s+|needs?\s+to\s+be\s+)?'
    r'(' + '|'.join(VAGUE_WORDS) + r')\b',
    re.IGNORECASE
)

PLACEHOLDER_PATTERNS = re.compile(
    r'(\{\{[^}]+\}\}|\[TBD\]|\[TODO\]|\[FIXME\]|\[PLACEHOLDER\])',
    re.IGNORECASE,
)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def word_count(text: str) -> int:
    return len(text.split())


def count_requirements(text: str) -> int:
    """Count REQ-NNN patterns in PRD text."""
    return len(set(re.findall(r'REQ-\d{3}', text)))


def has_section(text: str, heading: str) -> bool:
    """Check if markdown heading exists (case-insensitive)."""
    pattern = r'^#{1,6}\s+.*' + re.escape(heading) + r'.*$'
    return bool(re.search(pattern, text, re.MULTILINE | re.IGNORECASE))


def get_section_content(text: str, heading: str) -> str:
    """Extract content under a markdown heading until next same-level heading."""
    lines = text.split('\n')
    capturing = False
    level = 0
    content = []
    heading_re = re.compile(r'^(#{1,6})\s+(.*)')
    for line in lines:
        heading_match = heading_re.match(line)
        if heading_match and heading.lower() in heading_match.group(2).lower():
            capturing = True
            level = len(heading_match.group(1))
            continue
        if capturing:
            if heading_match and len(heading_match.group(1)) <= level:
                break
            content.append(line)
    return '\n'.join(content).strip()


# ─── Public API ───────────────────────────────────────────────────────────────

def validate_prd(prd_path: str, ai: bool = False) -> dict:
    """Run 14 quality checks on a PRD file and return a result dict.

    Args:
        prd_path: Path to the PRD markdown file.
        ai:       When True, trigger optional AI-assisted review.
                  In v5.0 baseline this is stubbed — returns
                  {"ai_review": "not_yet_implemented"} without blocking.

    Returns a dict with at minimum:
        ok: bool
        grade: str  — EXCELLENT / GOOD / ACCEPTABLE / NEEDS_WORK
        score: int
        max_score: int
        warnings: list
        placeholders_found: int
        checks: list of per-check result dicts
    """
    path = Path(prd_path)
    if not path.is_file():
        return emit_json_error(f"PRD file not found: {prd_path}")

    text = path.read_text()
    checks = []
    warnings = []

    # ─── Required Elements (9 checks, 5 points each = 45 points) ─────────

    # Check 1: Executive summary exists and is 20-500 words
    exec_summary = get_section_content(text, "Executive Summary")
    wc = word_count(exec_summary)
    checks.append({
        "id": 1,
        "category": "required",
        "name": "Executive summary exists",
        "passed": has_section(text, "Executive Summary") and 20 <= wc <= 500,
        "detail": f"Found {wc} words" if exec_summary else "Section missing",
        "points": 5,
    })

    # Check 2: Problem statement includes user impact
    problem = get_section_content(text, "Problem Statement")
    has_user_impact = bool(
        re.search(r'user\s+impact|who\s+is\s+affected|pain\s+point', problem, re.IGNORECASE)
        or has_section(text, "User Impact")
    )
    checks.append({
        "id": 2,
        "category": "required",
        "name": "Problem statement includes user impact",
        "passed": has_user_impact,
        "detail": "User impact found" if has_user_impact else "No user impact section",
        "points": 5,
    })

    # Check 3: Problem statement includes business impact
    has_biz_impact = bool(
        re.search(r'business\s+impact|revenue|cost|strategic', problem, re.IGNORECASE)
        or has_section(text, "Business Impact")
    )
    checks.append({
        "id": 3,
        "category": "required",
        "name": "Problem statement includes business impact",
        "passed": has_biz_impact,
        "detail": "Business impact found" if has_biz_impact else "No business impact section",
        "points": 5,
    })

    # Check 4: Goals have SMART metrics
    goals_section = get_section_content(text, "Goals")
    has_smart = bool(re.search(
        r'(metric|baseline|target|timeframe|measurement)',
        goals_section, re.IGNORECASE
    ))
    checks.append({
        "id": 4,
        "category": "required",
        "name": "Goals have SMART metrics",
        "passed": has_smart,
        "detail": "SMART elements found" if has_smart else "Goals lack measurable metrics",
        "points": 5,
    })

    # Check 5: User stories have acceptance criteria (min 3 per story)
    stories_section = get_section_content(text, "User Stories")
    story_blocks = re.split(r'###\s+Story\s+\d+', stories_section)
    ac_counts = []
    for block in story_blocks[1:]:  # skip pre-heading text
        ac_matches = re.findall(r'- \[[ x]\]', block)
        ac_counts.append(len(ac_matches))
    stories_ok = all(c >= 3 for c in ac_counts) if ac_counts else False
    checks.append({
        "id": 5,
        "category": "required",
        "name": "User stories have acceptance criteria (min 3)",
        "passed": stories_ok or not ac_counts,  # pass if no stories section (minimal template)
        "detail": f"Stories: {len(ac_counts)}, AC counts: {ac_counts}" if ac_counts else "No user stories found (may be minimal PRD)",
        "points": 5,
    })

    # Check 6: Functional requirements are testable (no vague language)
    reqs_section = get_section_content(text, "Functional Requirements")
    if not reqs_section:
        reqs_section = get_section_content(text, "Requirements")
    vague_in_reqs = VAGUE_PATTERN.findall(reqs_section)
    checks.append({
        "id": 6,
        "category": "required",
        "name": "Functional requirements are testable",
        "passed": len(vague_in_reqs) == 0,
        "detail": f"Vague terms found: {vague_in_reqs}" if vague_in_reqs else "All requirements are specific",
        "points": 5,
    })

    # Check 7: Each requirement has priority (Must/Should/Could or P0/P1/P2)
    has_priority = bool(re.search(
        r'(must\s+have|should\s+have|could\s+have|nice\s+to\s+have|P0|P1|P2)',
        reqs_section, re.IGNORECASE
    ))
    checks.append({
        "id": 7,
        "category": "required",
        "name": "Requirements have priority labels",
        "passed": has_priority,
        "detail": "Priority labels found" if has_priority else "No priority classification found",
        "points": 5,
    })

    # Check 8: Requirements are numbered (REQ-NNN)
    req_count = count_requirements(text)
    checks.append({
        "id": 8,
        "category": "required",
        "name": "Requirements are numbered (REQ-NNN)",
        "passed": req_count > 0,
        "detail": f"Found {req_count} numbered requirements" if req_count else "No REQ-NNN numbering found",
        "points": 5,
    })

    # Check 9: Technical considerations address architecture
    tech_section = get_section_content(text, "Technical")
    has_arch = bool(re.search(
        r'(architecture|system\s+design|component|integration|diagram)',
        tech_section, re.IGNORECASE
    ))
    checks.append({
        "id": 9,
        "category": "required",
        "name": "Technical considerations address architecture",
        "passed": has_arch,
        "detail": "Architecture content found" if has_arch else "No architectural detail found",
        "points": 5,
    })

    # ─── Taskmaster-specific (4 checks, 3 points each = 12 points) ───────

    # Check 10: Non-functional requirements have specific targets
    nfr_section = get_section_content(text, "Non-Functional")
    has_nfr_targets = bool(re.search(
        r'\d+\s*(ms|seconds?|minutes?|%|MB|GB|requests?/s)',
        nfr_section, re.IGNORECASE
    ))
    checks.append({
        "id": 10,
        "category": "taskmaster",
        "name": "Non-functional requirements have specific targets",
        "passed": has_nfr_targets or not nfr_section,
        "detail": "Specific targets found" if has_nfr_targets else "No measurable NFR targets",
        "points": 3,
    })

    # Check 11: Requirements have task breakdown hints
    has_task_hints = bool(re.search(
        r'task\s+breakdown|implementation\s+step|~\d+h',
        text, re.IGNORECASE
    ))
    checks.append({
        "id": 11,
        "category": "taskmaster",
        "name": "Requirements have task breakdown hints",
        "passed": has_task_hints,
        "detail": "Task breakdown hints found" if has_task_hints else "No task breakdown hints",
        "points": 3,
    })

    # Check 12: Dependencies identified
    has_deps = bool(re.search(
        r'(dependenc|depends\s+on|blocked\s+by|prerequisite|REQ-\d{3}.*depends)',
        text, re.IGNORECASE
    ))
    checks.append({
        "id": 12,
        "category": "taskmaster",
        "name": "Dependencies identified for task sequencing",
        "passed": has_deps,
        "detail": "Dependencies documented" if has_deps else "No dependency information found",
        "points": 3,
    })

    # Check 13: Out of scope defined
    has_oos = has_section(text, "Out of Scope")
    oos_content = get_section_content(text, "Out of Scope")
    checks.append({
        "id": 13,
        "category": "taskmaster",
        "name": "Out of scope explicitly defined",
        "passed": has_oos and len(oos_content.strip()) > 10,
        "detail": "Out of scope section found" if has_oos else "No Out of Scope section",
        "points": 3,
    })

    # ─── Placeholder scan with reason attribution (per inbox 1559) ───────
    # Philosophy: placeholders are not technical debt if they're intentional.
    # A placeholder paired with `reason: <explanation>` is a DEFERRED DECISION
    # — explicitly acknowledged and attributed. A bare placeholder is a bug.
    lines = text.splitlines()
    bare_placeholders = []
    deferred_decisions = []
    for i, line in enumerate(lines):
        for match in PLACEHOLDER_PATTERNS.finditer(line):
            same_line = line.lower()
            next_line = lines[i + 1].lower() if i + 1 < len(lines) else ""
            has_reason = (
                "reason:" in same_line
                or "defer:" in same_line
                or "reason:" in next_line[:200]
                or "defer:" in next_line[:200]
            )
            entry = {
                "placeholder": match.group(1),
                "line_number": i + 1,
                "line_text": line.strip()[:200],
            }
            if has_reason:
                deferred_decisions.append(entry)
            else:
                bare_placeholders.append(entry)

    # Check 14: Bare placeholders (no reason attribution)
    checks.append({
        "id": 14,
        "category": "required",
        "name": "Placeholders have `reason:` attribution (no bare placeholders)",
        "passed": len(bare_placeholders) == 0,
        "detail": (
            f"{len(bare_placeholders)} bare placeholder(s) found — must have `reason:` explaining why deferred"
            if bare_placeholders
            else (
                f"All {len(deferred_decisions)} placeholders have reason attribution"
                if deferred_decisions
                else "No placeholders — clean"
            )
        ),
        "points": 5,
        "bare_placeholders": bare_placeholders[:10],
        "deferred_decisions_count": len(deferred_decisions),
    })

    # ─── Vague language warnings ─────────────────────────────────────────
    all_vague = VAGUE_PATTERN.findall(text)
    vague_penalty = min(len(all_vague), 5)
    for match in set(all_vague):
        warnings.append({
            "type": "vague_language",
            "term": match,
            "suggestion": f"Replace '{match}' with a specific, measurable target",
        })

    # ─── Missing detail warnings ─────────────────────────────────────────
    if not has_section(text, "Validation Checkpoint"):
        warnings.append({
            "type": "missing_detail",
            "item": "Validation checkpoints",
            "suggestion": "Add validation checkpoints for each implementation phase",
        })

    # ─── Scoring ─────────────────────────────────────────────────────────
    score = sum(c["points"] for c in checks if c["passed"])
    max_score = sum(c["points"] for c in checks)
    score -= vague_penalty
    score = max(0, score)

    pct = (score / max_score * 100) if max_score > 0 else 0
    if pct >= 91:
        grade = "EXCELLENT"
    elif pct >= 83:
        grade = "GOOD"
    elif pct >= 75:
        grade = "ACCEPTABLE"
    else:
        grade = "NEEDS_WORK"

    passed_count = sum(1 for c in checks if c["passed"])

    result = {
        "ok": True,
        "score": score,
        "max_score": max_score,
        "percentage": round(pct, 1),
        "grade": grade,
        "checks_passed": passed_count,
        "checks_total": len(checks),
        "checks": checks,
        "warnings": warnings,
        "vague_penalty": vague_penalty,
        "deferred_decisions": deferred_decisions,
        "deferred_decisions_count": len(deferred_decisions),
        "bare_placeholders_count": len(bare_placeholders),
        # Convenience field: total placeholders found (bare + deferred)
        "placeholders_found": len(bare_placeholders) + len(deferred_decisions),
    }

    # ─── Optional AI review (v5.0 stub) ──────────────────────────────────
    # Real AI review lands in a later task. For now: declare intent, don't crash.
    if ai:
        result["ai_review"] = "not_yet_implemented"

    return result
