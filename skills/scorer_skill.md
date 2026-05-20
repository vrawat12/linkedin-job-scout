# Scorer Agent — Skill File

## Purpose
Scores each job listing for relevance against the candidate 
profile. Runs as Stage 2 in the pipeline.

## Model
claude-sonnet-4-6

## Context files to include in every prompt
- context/profile.md — professional background
- context/target_roles.md — target titles and domains
- context/sample_job.md — calibration examples

## Output JSON schema per job
{
  "score": int 1-10,
  "rationale": "2 sentences max",
  "match_tags": [],
  "red_flags": [],
  "ai_opportunity": true/false,
  "alignment": ["bullet 1", "bullet 2", "bullet 3"],
  "gaps": ["bullet 1", "bullet 2"]
}

## Scoring rules
- AI-native companies selling into fintech: score equally 
  to or higher than traditional financial institutions
- Forward deployed, BD, solutions roles at AI companies: 
  score 7+ if meaningful hands-on AI exposure in fintech
- Legacy financial institution with no AI component: 
  flag in red_flags
- Descriptions under 50 characters: skip, log as skipped

## Error handling
- Retry 3x with exponential backoff
- Validate score is int between 1-10
- Validate all required fields present
- Strip markdown fences before JSON parse
- On persistent failure: skip job, log with reason
