# Scorer Eval Suite — Skill File

## Purpose
Eval suite for scorer.py — validates that Claude scores job listings
correctly, consistently, and in alignment with candidate preferences.
Run before any change to scorer.py, target_roles.md, or profile.md.

## How to run
```
python evals/run_evals.py
```
Run from project root. Results printed to console and saved to
evals/results/eval_results_YYYYMMDD_HHMMSS.json.

## Test case categories

### Group 1 — Known correct high scores (real jobs, ground truth)
Real jobs from prior pipeline runs that scored 8-10. These validate
that the scorer catches genuinely strong matches.
- tc_001: Head of Product Trust & Safety at Square
- tc_002: Agentic Treasury Product Strategy Director at JPMorgan
- tc_003: Product Lead AI at Stripe
- tc_004: Director Product Management Next Gen Platform at Marqeta

### Group 2 — Known false positives (real jobs, failure modes)
Real jobs that Claude may score too high due to identified gaps
in the scoring logic.
- tc_005: Research Engineer Safeguards at AI lab
- tc_006: Senior Solutions Architect at Alloy
- tc_007: Forward Deployed Engineer at consulting firm

### Group 3 — Synthetic edge cases
Synthetic JDs designed to probe specific scoring nuances.
- tc_008: Strong fit — VP Product AI credit decisioning at Series B fintech
- tc_009: Weak fit — Senior PM at consumer social app
- tc_010: Grey zone — Director of Data Analytics at regional bank
- tc_011: Edge case — CSM Enterprise at Anthropic (AI-native, not PM)
- tc_012: Edge case — Associate PM at payments company (right domain, wrong level)
- tc_013: Consistency — same job (tc_001) scored 3x, variance must be <= 1 pt

## The three failure modes this suite detects

### 1. wrong_role_type_not_penalized
Research Engineer, ML Researcher, and similar IC research roles get scored
as if they were PM roles because the AI/fintech domain matches. Claude should
flag these in red_flags (e.g. "research engineer, not a PM role") and score
them 1-4. tc_005 tests this.

### 2. non_pm_role_type_not_checked
Solutions Architect, Implementation Engineer, and similar technical delivery
roles require specialized SA/implementation background the candidate does not
have. Claude should penalize the role type mismatch and note it in red_flags.
tc_006 tests this.

### 3. consulting_exclusion_not_applied
Forward Deployed Engineer (and similar titles) at a consulting firm
(billable-hours professional services model) is different from FDE at an
AI-native company. The candidate has no consulting delivery background and
is not seeking external consulting roles. Claude should score these 1-4 and
flag in red_flags. tc_007 tests this. Note: "Consulting / Advisory, AI Product"
is in target_roles.md as open-to — this refers to advisory at an AI company,
not billable consulting at a consulting firm.

## Check types and pass criteria

| Check           | Pass condition                                           |
|-----------------|----------------------------------------------------------|
| schema          | All 7 required fields present with correct types         |
| accuracy        | score within [expected.score_min, expected.score_max]    |
| ai_opportunity  | ai_opportunity matches expected value                    |
| match_tags      | At least one required_match_tag present (case-insensitive substring) |
| red_flags       | red_flags is non-empty when red_flags_expected=true      |
| forbidden_tags  | None of forbidden_match_tags appear in match_tags        |
| consistency     | max(scores) - min(scores) <= 1 across 3 runs             |

## Target pass rates
- Schema conformance: 100% always (any failure = bug in scorer)
- Score accuracy: >= 85% (>= 11/12 accuracy test cases)
- AI opportunity: >= 90%
- Consistency variance: <= 1 point always

## How to add new test cases
1. Add entry to evals/scorer_evals.json following the schema
2. Assign next tc_XXX id (continue from tc_013)
3. Set source: "real" for jobs from actual pipeline runs, "synthetic" otherwise
4. Set failure_mode_tested to the failure mode name or "none"
5. Write realistic JD in job.description (plain text, no special formatting needed)
6. Run: python evals/run_evals.py
7. Verify new case behaves as expected

## How to interpret failures

### Accuracy fail on Group 1 (high-score known goods)
Scorer is under-scoring genuinely strong matches. Check if a recent
context file change (target_roles.md, profile.md) lowered the baseline.

### Accuracy fail on Group 2 (known false positives)
Scorer is still over-scoring failure modes. Add explicit negative scoring
rules to scorer.py SYSTEM_PROMPT or target_roles.md for the specific pattern.

### Consistency variance > 1
Scoring criteria are too ambiguous for stable outputs. Add more specific
calibration examples to context/sample_job.md or tighten the scoring rubric
in the SYSTEM_PROMPT.

### Schema fail
Always a bug — scorer.py returned malformed JSON. Check retry logic and
JSON parse stripping in scorer._score_one().

## When to run evals
- Before any change to scorer.py
- After any change to context/target_roles.md
- After any change to context/profile.md
- After any change to context/sample_job.md
- Monthly baseline check
- After any model version change in scorer.py

## Files
- evals/scorer_evals.json — all test cases with JDs and expected values
- evals/run_evals.py      — eval runner (imports SYSTEM_PROMPT from scorer.py)
- evals/results/          — timestamped JSON result files
- evals/README_EVALS.md   — user-facing documentation
