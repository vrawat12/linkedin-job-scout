# Scorer Eval Suite

Validates that `scorer.py` scores job listings correctly, consistently,
and in alignment with candidate preferences.

## Quick start

```bash
python evals/run_evals.py
```

Run from the project root. The runner calls the same Claude model and
system prompt that `scorer.py` uses in production — any drift between
the two is a bug.

## What it tests

### 13 test cases across 3 groups

**Group 1 — Known correct high scores (real jobs)**
Jobs from actual pipeline runs that should score 7-10. These are ground truth.
If any of these fail, the scorer has regressed on cases it previously handled.

| ID     | Job                                        | Expected |
|--------|--------------------------------------------|----------|
| tc_001 | Head of Product Trust & Safety @ Square    | 7-10     |
| tc_002 | Agentic Treasury Director @ JPMorgan       | 8-10     |
| tc_003 | Product Lead AI @ Stripe                   | 8-10     |
| tc_004 | Director Product Mgmt Next Gen @ Marqeta   | 7-10     |

**Group 2 — Known false positives (real jobs)**
Jobs Claude may score too high due to surface-level domain match, but which
have disqualifying role-type mismatches. Expected score: 1-6.

| ID     | Job                                        | Failure Mode                        |
|--------|--------------------------------------------|-------------------------------------|
| tc_005 | Research Engineer Safeguards @ AI lab      | Wrong role type not penalized       |
| tc_006 | Senior Solutions Architect @ Alloy         | Non-PM role type not checked        |
| tc_007 | Forward Deployed Engineer @ consulting firm | Consulting exclusion not applied    |

**Group 3 — Synthetic edge cases**
Synthetic JDs that probe scoring nuance — strong fit, weak fit, grey zone, edge cases.

| ID     | Job                                        | Expected |
|--------|--------------------------------------------|----------|
| tc_008 | VP Product AI Decisioning @ Series B fintech | 8-10   |
| tc_009 | Senior PM Social Features @ consumer app  | 1-3      |
| tc_010 | Director Data Analytics @ regional bank   | 4-7      |
| tc_011 | CSM Enterprise @ Anthropic (fintech focus) | 6-9     |
| tc_012 | Associate PM @ payments company           | 2-5      |
| tc_013 | Same job scored 3x (consistency test)     | variance ≤ 1 pt |

## The three failure modes

These are specific known gaps in the scorer that this suite was designed to catch.

**1. Wrong role type not penalized** (tc_005)
Research Engineer or ML Researcher roles in AI/fintech domains can fool the
scorer because the domain keywords match. But research roles require PhD-level
ML research backgrounds and have no PM responsibilities. Expected: score 1-4,
red_flags non-empty mentioning "research" or "not a product role".

**2. Non-PM role type not checked** (tc_006)
Solutions Architect and Implementation Engineer roles at fintech companies
sound relevant (KYC, fraud, identity decisioning) but require a technical SA
background the candidate does not have. Expected: score 3-6, red_flags non-empty.

**3. Consulting exclusion not applied** (tc_007)
"Forward Deployed Engineer" sounds like the Anthropic FDE roles (which score 9),
but FDE at a consulting firm (Deloitte, McKinsey, boutique consultancies) is a
professional services delivery role with billable hours and no internal product
ownership. The candidate has no consulting background and is not seeking these
roles. Expected: score 1-4, red_flags non-empty. Note: "Consulting / Advisory,
AI Product (financial services)" in target_roles.md refers to advisory at an
AI-native company, not external consulting delivery.

## How to interpret output

```
─────────────────────────────────────────────────────────────────
tc_001 | Head of Product, Trust and Safety at Block (Square) | PASS
  Score: 8/10 (expected 7-10) ✓
  Schema: all fields present ✓
  AI opportunity: True ✓
  Match tags: ['fintech', 'fraud prevention', 'payments platform', 'risk'] ✓

tc_005 | Research Engineer, Safeguards at Apex AI Research | FAIL
  Score: 7/10 (expected 1-4) ✗
  Schema: all fields present ✓
  AI opportunity: True ✗
  Red flags: [] ✗
  ✗ Score 7/10 outside expected range [1-4]  ← wrong_role_type_not_penalized
```

### Pass rate targets
- Schema conformance: **100%** — any failure is a code bug
- Score accuracy: **≥ 85%** (at least 11/12 accuracy cases)
- AI opportunity: **≥ 90%**
- Consistency variance: **≤ 1 point** always

## Results files

Each run saves a timestamped JSON file to `evals/results/`:

```
evals/results/eval_results_20260519_143022.json
```

Schema:
```json
{
  "run_date": "2026-05-19T14:30:22",
  "model": "claude-sonnet-4-6",
  "total_cases": 13,
  "overall_pass_rate": 0.846,
  "results": [
    {
      "test_id": "tc_001",
      "title": "Head of Product, Trust and Safety at Block (Square)",
      "source": "real",
      "failure_mode_tested": "none",
      "eval_type": "accuracy",
      "claude_score": 8,
      "expected_range": [7, 10],
      "checks": {
        "schema": "pass",
        "accuracy": "pass",
        "ai_opportunity": "pass",
        "match_tags": "pass",
        "red_flags": "n/a",
        "forbidden_tags": "n/a"
      },
      "overall": "pass",
      "failures": [],
      "claude_full_response": { ... }
    }
  ]
}
```

## Adding new test cases

1. Open `evals/scorer_evals.json`
2. Add a new entry to the `test_cases` array following the schema:

```json
{
  "id": "tc_014",
  "description": "One line: what this tests",
  "source": "real",
  "job": {
    "job_id": "eval_tc_014",
    "title": "...",
    "company": "...",
    "location": "...",
    "applicant_count": null,
    "description": "Full JD text here."
  },
  "expected": {
    "score_min": 7,
    "score_max": 10,
    "ai_opportunity": true,
    "required_match_tags": ["fintech", "AI"],
    "forbidden_match_tags": [],
    "red_flags_expected": false
  },
  "eval_type": "accuracy",
  "failure_mode_tested": "none"
}
```

3. Run `python evals/run_evals.py` to verify it behaves as expected.

## When to run evals

- Before any change to `scorer.py`
- After any change to `context/target_roles.md`
- After any change to `context/profile.md`
- After any model version change in `scorer.py`
- Monthly baseline check
