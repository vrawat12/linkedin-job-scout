# Organizer Agent — Skill File

## Purpose
Takes scored job dicts from scorer.py and organizes them 
into a structured prioritized digest before email composition.
Runs as Stage 3.5 in the pipeline between deduplication 
and emailing.

## Model
claude-sonnet-4-20250514

## Input
List of scored job dicts, each containing:
- job_id, title, company, location, job_url
- score (int 1-10), rationale, match_tags, red_flags
- ai_opportunity (bool), alignment (list), gaps (list)
- applicant_count, posted_date

## Output JSON schema
{
  "must_apply": [],        // score 8-10, applicants < 20
  "strong_fit": [],        // score 7-10, applicants 20-60
  "ai_opportunity": [],    // ai_opportunity = true, any score
  "worth_monitoring": [],  // score 6-7, any applicant count
  "market_intelligence": [] // 3-5 insight bullets
}

## Urgency rules
- Exceptional urgency: applicants < 5, score >= 8
- High urgency: applicants 5-20, score >= 8
- Strong fit: score 7-10, applicants 20-60
- A job can appear in both ai_opportunity AND must_apply/strong_fit

## Market intelligence guidelines
Claude should observe and report on:
- Which companies are hiring most actively this week
- Which domains have the most openings
- Whether competition (applicant counts) is trending high or low
- Any notable new companies appearing for the first time
- Salary trends if visible in listings

## Error handling
- Retry 3x with exponential backoff on API failure
- On persistent failure: pass flat scored list directly 
  to emailer, log warning to scout.log
- Validate output JSON schema before passing to emailer

## Prompt style
- System prompt establishes career advisor persona
- User prompt sends all jobs as JSON
- Instruct model: return only raw JSON, no markdown, 
  no backticks, no preamble
- Strip any markdown fences before parsing response
