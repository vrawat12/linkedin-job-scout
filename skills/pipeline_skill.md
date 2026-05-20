# Pipeline Architecture — Skill File

## Purpose
Documents the full agent pipeline so any future changes 
maintain the correct stage order and data contracts.

## Stage order
1. scrape        scraper.py    → list of raw job dicts
2. score         scorer.py     → list of enriched job dicts
3. deduplicate   agent.py      → list of new jobs only
3.5. organize    organizer.py  → structured digest dict
4. email         emailer.py    → delivered HTML email
5. persist       agent.py      → seen_jobs.json updated
6. tailor        bio_agent.py  → tailored_resumes/*.docx
                   optional — --tailor flag only
                   reads:  scored_jobs.json, resume_template.docx,
                           context/resume_preferences.md,
                           context/profile.md
                   writes: tailored_resumes/{Company}_{TitleSlug}_{Date}.docx

## CLI flags
--dry-run     Skip email send and seen_jobs update
--force       Skip deduplication
--email-only  Skip scrape and score, load scored_jobs.json
--config      Path to alternate config file

## Exit codes
0  success
1  config or credential error
2  scrape failure
3  email failure

## Key files
config.json        User configuration
seen_jobs.json     Deduplication memory (90-day pruning)
scored_jobs.json   Cached scored results for --email-only
search_feedback.json  Search quality history
scout.log          Append-only timestamped run log
context/           Profile and criteria files for Claude
skills/            Skill files for each agent component

## Data contract between stages
Each stage must receive and return the same job dict 
schema — never drop fields, only add new ones. The 
organizer receives enriched dicts and returns a 
structured digest dict — it does not modify individual 
job dicts.
