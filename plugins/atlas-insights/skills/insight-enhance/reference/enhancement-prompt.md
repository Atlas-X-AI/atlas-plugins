# Bounded Rewrite Prompt Template

> This template is the load-bearing anti-drift control for `/insight-enhance`. Load it into the model verbatim when asking for an enriched rewrite. Do NOT paraphrase — the exact wording is tuned to prevent hallucination, voice loss, and scope creep.

---

## Template (substitute `{{VARS}}`, pass the rest verbatim)

```
You are rewriting an existing captured insight to incorporate verified research
findings. Your output will REPLACE the original via an atomic database write,
and a structural scope-check will compare your output to the original. Violating
the constraints below causes the enrichment to be rejected and discarded.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ORIGINAL INSIGHT (preserve voice and core claim):

{{ORIGINAL_CONTENT}}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESEARCH OUTPUT (use ONLY these sources — do not add facts from memory):

{{RESEARCH_SUMMARY_WITH_CITATIONS}}

Sources:
{{CITATION_LIST}}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONSTRAINTS (violations → rejection):

1. OPENER PRESERVATION — your rewrite MUST begin with the first sentence of
   the original insight, VERBATIM, as its first sentence. Do not rephrase,
   trim, or expand the opener. The scope-check validates first 50 chars by
   substring match.

2. LENGTH CAP — your rewrite MUST be no longer than {{MAX_LENGTH}} characters
   (2x original). Going over means the rewrite is rejected.

3. FACT SOURCE — every factual addition beyond the original MUST be traceable
   to the research output above. Do not add context, examples, or background
   facts from your training data. If a claim is not in the research above,
   do not include it.

4. CITATION INJECTION — weave inline [N] markers into the enriched claims
   where N corresponds to the numbered sources above. A "References" section
   at the end is required.

5. VOICE — preserve the original insight's tone, tag prefix ([PENTEST] /
   [AI] / [SPARK]), and operator-observation style. Do not convert it to
   encyclopedic prose.

6. SCOPE — do not introduce topics not present in either the original insight
   or the research output. The rewrite is about the same thing as the
   original — just better-sourced.

7. NO META-COMMENTARY — do not include phrases like "Enriched with sources
   from" or "Based on the research above". The rewrite is content, not
   narration about the rewrite.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT:

<rewritten insight body with inline [N] markers>

References:
[1] <source 1>
[2] <source 2>
[...]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Emit the rewrite and nothing else. No preamble, no explanation of changes.
```

---

## Variable substitution

| Variable | Source |
|---|---|
| `{{ORIGINAL_CONTENT}}` | `insights.content` of the row being enriched |
| `{{RESEARCH_SUMMARY_WITH_CITATIONS}}` | Merged output from `/question` or `/research-before-coding` |
| `{{CITATION_LIST}}` | Structured list: `[1] Title — URL — accessed DATE` |
| `{{MAX_LENGTH}}` | `original_length * 2` (from schema) |

## Why this exact wording

| Clause | Addresses audit finding |
|---|---|
| Opener preservation | [1.10] voice loss / scope creep — first-50-char substring check downstream |
| Length cap | [1.10] over-expansion filler |
| Fact source restriction | [1.5] citation fabrication, [1.6] silent source-failure drift |
| Citation injection requirement | Citation discipline from research q2 findings |
| No meta-commentary | Prevents recursive self-description drift on future enrichment passes |

## Post-output validation (runs before writeback)

After the model emits the rewrite, `scripts/enhance_one.py` verifies:

1. First 50 chars of enriched content match first 50 chars of original (substring match, whitespace-normalised)
2. Enriched length ≤ `2 * original_length`
3. Count of `[N]` markers in body ≥ `min_citations_required` (default 2)
4. Each `[N]` reference has a corresponding URL in the References section
5. Each URL in References passes `validate_urls.py` (at least 1 returns HTTP 200)

If ANY check fails: the enrichment is discarded, the row stays unenriched, and the failure reason is logged to the final report.
