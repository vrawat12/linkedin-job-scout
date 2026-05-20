# Job Scout — Agentic Job Search Pipeline
An end-to-end agentic system that enables a proactive job search to support your career goals instead of it being reactively driven. This system autonomously discovers, scores, prioritizes, and prepares job applications for senior product leadership roles in fintech and AI. Built with Python, Claude AI (Anthropic), and GitHub Actions.

---

## What this system does

Agentification of a manual workflow forjob search: Instead of manually searching job boards, filtering results, and tailoring application materials, this pipeline does it autonomously:

1. **Discovers** identifies relevant job listings based on career goals and experience across multiple sources using job board APIs
2. **Scores** each listing for personal relevance using Claude AI — with nuanced judgment about role type, domain fit, and career alignment
3. **Organizes** results into a personalized, prioritized, organized digest with urgency tiers and market intelligence
4. **Delivers** a structured email digest with alignment analysis, gap identification, and applicant count per role
5. **Tailors** the base resume for each must-apply role using Claude — adapting emphasis based on whether the role is fintech platform, data analytics, or AI-adjacent
6. **Evaluates** scorer accuracy using a structured eval suite with labeled test cases and five independent checks per case

---

## Architecture overview

```
Trigger (manual or GitHub Actions workflow_dispatch)
        │
        ▼
   agent.py — Orchestrator
        │
        ├── Stage 1:   scraper.py      — Multi-source job discovery (API-based)
        ├── Stage 2:   scorer.py       — Claude AI relevance scoring     ★ Agent
        ├── Stage 3:   Deduplication   — seen_jobs.json persistent memory
        ├── Stage 3.5: organizer.py    — Claude AI digest organization   ★ Agent
        ├── Stage 4:   emailer.py      — Gmail HTML digest delivery
        └── Stage 5:   bio_agent.py    — Claude AI resume tailoring      ★ Agent

Quality assurance (run explicitly on scoring logic changes):
        └── evals/run_evals.py         — Scorer eval suite, 13 test cases
```

Three of the five pipeline stages are genuine AI agents — components where Claude makes autonomous reasoning decisions that cannot be replaced by deterministic rules.

---

## Why this is an agentic system

This project was built to demonstrate a understanding of agentic architecture — not just API calls, but the properties that make a system genuinely agentic:

| Property | Implementation |
|---|---|
| **Perception** | scraper.py retrieves live job data from multiple APIs autonomously |
| **Reasoning** | Claude LLM reasons, scores, organizes, and tailors with nuanced judgment per run |
| **Memory** | seen_jobs.json persists across all runs — the system never re-alerts on seen jobs |
| **Tool use** | Three external tools coordinated: job APIs + Claude API + Gmail API |
| **Autonomy** | Runs on-demand with no human in the loop between trigger and email delivery |

---

## Data sources — why APIs over web scraping

The system uses three job board APIs as its data sources. An earlier version used Playwright to scrape LinkedIn directly. That approach was deliberately replaced for the following reasons:

### LinkedIn web scraping — why we moved away from it

**Account risk.** LinkedIn's Terms of Service prohibit automated scraping. During development the LinkedIn scraping approach triggered an account flag after a single session. For someone actively job searching, a LinkedIn account restriction is a direct harm — it blocks the very activity the system is meant to support.

**Detection brittleness.** Even with human-like delays, randomized timing, and real browser fingerprints, LinkedIn's bot detection operates at a behavioral level that is difficult to fully evade. Any change to LinkedIn's detection logic can break the scraper without warning.

**Maintenance overhead.** Browser-based scrapers break when the target site changes its DOM structure, CSS classes, or page rendering behavior. API-based sources have versioned contracts — they are designed for programmatic access and do not change without notice.

### Current API sources — why each was chosen

**Adzuna API** (`developer.adzuna.com`)
- Primary source — broadest market coverage across US job listings
- Free tier: 250 requests per day — sufficient for daily runs
- Structured data including salary ranges, posting dates, and company info
- Designed for programmatic access — zero account risk
- Covers the full seniority spectrum including VP and Director level roles

**The Muse API** (`themuse.com/api/public/jobs`)
- No credentials required — fully public API
- Skews toward tech and fintech companies — higher signal-to-noise for target roles
- Good coverage of AI-native and growth-stage companies
- Complements Adzuna by covering companies that prefer The Muse's candidate audience

**Greenhouse company boards** (`boards.greenhouse.io/{company}`)
- Direct ATS feeds from target companies — no intermediary noise
- Many AI-native companies use Greenhouse: Ramp, Brex, Anthropic, Sardine, Socure, Alloy, Unit21
- Public job boards designed for programmatic access — zero account risk
- Catches roles that may not appear on aggregators due to posting strategy

### LinkedIn as an optional source

LinkedIn scraping is documented as an optional configuration for users who want to enable it and accept the associated risk. It is not the default. If enabled:
- Requires Playwright and Chromium installed locally
- Uses LinkedIn credentials stored as environment variables
- Runs with conservative delays (8–15 seconds between requests)
- Limited to 6 searches and 30 listings per run maximum
- Runs only on manual trigger — never on a schedule
- **Recommended only for local testing, not for GitHub Actions deployment**

To enable, set `"use_linkedin": true` in `config.json` and add `LINKEDIN_EMAIL` and `LINKEDIN_PASSWORD` to your `.env` file.

---

## Tech stack

| Component | Technology |
|---|---|
| Orchestration | Python 3.11 |
| AI reasoning | Anthropic Claude API (claude-sonnet-4-20250514) |
| Job data — primary | Adzuna API |
| Job data — secondary | The Muse API |
| Job data — direct | Greenhouse company boards |
| Job data — optional | LinkedIn (Playwright, local only, not recommended) |
| Email delivery | Gmail API (OAuth2) |
| Document generation | docx (Node.js) |
| Scheduling | GitHub Actions (workflow_dispatch — manual trigger only) |
| Secrets management | GitHub Actions Secrets |

---

## Project structure

```
linkedin-job-scout/
├── agent.py                  Orchestrator — pipeline, CLI flags, logging
├── scraper.py                Multi-source job scraper — perception layer
├── scorer.py                 Claude AI scorer — reasoning layer            ★
├── organizer.py              Claude AI organizer — prioritization          ★
├── emailer.py                Gmail digest sender — action layer
├── bio_agent.py              Claude AI resume tailor — application layer   ★
├── generate_doc.js           Word document generator (Node.js)
├── seen_jobs.json            Deduplication memory store (gitignored)
├── scored_jobs.json          Cached scored results (gitignored)
├── config.json               Search configuration
├── scout.log                 Append-only run log (gitignored)
├── requirements.txt          Python dependencies
├── .github/
│   └── workflows/
│       └── job_scout.yml     GitHub Actions workflow (manual trigger only)
├── context/
│   ├── profile.md            Professional background for Claude scoring
│   ├── target_roles.md       Target titles, domains, hard scoring rules
│   ├── sample_job.md         High/low relevance calibration examples
│   └── resume_preferences.md Resume voice, tone, and formatting rules
├── skills/
│   ├── pipeline_skill.md     Pipeline architecture reference
│   ├── scorer_skill.md       Scorer agent design and prompt schema
│   ├── organizer_skill.md    Organizer agent design and urgency rules
│   ├── email_design_skill.md Email structure and visual design rules
│   ├── bio_agent_skill.md    Resume tailoring agent design
│   └── evals_skill.md        Eval suite design and test case guide
├── evals/
│   ├── run_evals.py          Eval runner — 13 test cases, 5 checks each
│   ├── scorer_evals.json     Labeled test cases with expected values
│   ├── eval_history.csv      Pass rate tracking across runs
│   └── results/              Per-run detailed results (gitignored)
└── tailored_resumes/         Output folder for tailored Word docs (gitignored)
```

---

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- Anthropic API key — [console.anthropic.com](https://console.anthropic.com)
- Adzuna API credentials — free at [developer.adzuna.com](https://developer.adzuna.com)
- Gmail API OAuth credentials — Google Cloud Console

### Installation

```bash
# Clone the repo
git clone https://github.com/vrawat12/linkedin-job-scout
cd linkedin-job-scout

# Install Python dependencies
pip install -r requirements.txt

# Install Node.js dependency for document generation
npm install -g docx
```

### Environment variables

Create a `.env` file in the project root (never commit this file):

```
ANTHROPIC_API_KEY=sk-ant-...
ADZUNA_APP_ID=your_app_id
ADZUNA_API_KEY=your_api_key
RECIPIENT_EMAIL=your@email.com

# Optional — only if enabling LinkedIn source
# LINKEDIN_EMAIL=your@linkedin.com
# LINKEDIN_PASSWORD=yourpassword
```

### Gmail OAuth (one-time local setup)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project, enable Gmail API
3. Configure OAuth consent screen (External, add yourself as test user)
4. Create OAuth 2.0 Desktop credentials
5. Download as `credentials.json` and place in project root
6. Run `python agent.py --dry-run` — browser opens for consent, saves `token.json`

### Configure your search

Edit `config.json`:

```json
{
  "search_keywords": [
    "Senior Director Product Management Fintech",
    "VP Product Payments",
    "Head of Product AI Financial Services",
    "Director Product Risk Decisioning",
    "VP Product AI Platform"
  ],
  "search_locations": ["New York", "New Jersey", "Remote"],
  "greenhouse_companies": [
    "ramp", "brex", "stripe", "plaid", "anthropic",
    "sardine", "socure", "alloy", "unit21", "marqeta"
  ],
  "max_applicants": 60,
  "max_days_posted": 7,
  "min_relevance_score": 6,
  "recipient_email": "your@email.com",
  "use_linkedin": false
}
```

---

## Usage

```bash
# Full pipeline — scrape, score, organize, email
python agent.py

# Dry run — no email sent, no seen_jobs updated
python agent.py --dry-run

# Email only — use cached scored results, skip scraping
python agent.py --email-only

# Full pipeline + resume tailoring for must-apply roles
python agent.py --tailor

# Resume tailoring only — from last scored results
python bio_agent.py

# Resume tailoring dry run — show role type detection only
python bio_agent.py --dry-run

# Run scorer eval suite
python evals/run_evals.py
```

---

## How the AI scoring works

Each job description is sent to Claude alongside the candidate's professional profile, target criteria, hard scoring rules, and calibration examples. Claude returns structured JSON with:

- **Score** (1–10) — relevance to background and target roles
- **Rationale** — 2-sentence reasoning
- **Match tags** — which domains align
- **Red flags** — mismatches worth noting
- **AI opportunity** — whether the role builds toward AI expertise
- **Alignment bullets** — where experience directly matches the JD
- **Gap bullets** — where JD requirements outpace current experience

The scoring is genuinely agentic because the same job title scores differently depending on company, domain, scope, and how the description frames the role — judgment no keyword rule can replicate.

### Hard scoring rules

The scorer applies explicit caps and floors before domain scoring:

| Rule | Details |
|---|---|
| Solutions Architect, Post-Sales Delivery | Maximum 5/10 regardless of company or domain |
| Consulting / Professional Services | Maximum 4/10, consulting flagged in red_flags |
| Research Engineer without PM responsibilities | Maximum 3/10, flagged in red_flags |
| Data analytics at financial institutions (no AI) | Minimum 4/10 if domain matches |
| Right domain but too junior | Score 2–4, never 1 |
| Score of 1 | Reserved for zero domain relevance |

These rules were established through eval runs and calibration — not set arbitrarily upfront.

---

## How resume tailoring works

`bio_agent.py` reads all must-apply jobs from the last scoring run, then for each role:

1. Detects role type: `fintech_platform`, `data_analytics`, `ai_adjacent`, or `hybrid`
2. Adapts emphasis accordingly — same experience, different framing per role type
3. Rewrites experience bullets to be outcome-led and metric-first
4. Generates a tailored professional summary and cover letter opener
5. Outputs a formatted Word document matching the candidate's resume visual style

**Critical constraint:** Claude reframes and reorders real experience only. It never invents metrics, skills, or roles not present in the original resume. This constraint is enforced in the system prompt and documented in `context/resume_preferences.md`.

---

## Evals

The scorer agent includes a structured eval suite that measures whether Claude is scoring correctly, consistently, and in alignment with stated preferences.

### What is measured

| Check | What it tests | Target |
|---|---|---|
| Schema conformance | All required fields present on every response | 100% always |
| Score accuracy | Score within expected range for labeled test cases | ≥ 85% |
| AI opportunity flag | Correct identification of AI-adjacent roles | ≥ 85% |
| Match tags | Right domains tagged | ≥ 85% |
| Red flags | Problems flagged when expected | ≥ 85% |
| Consistency | Same job scores within 1 point across 3 runs | Variance ≤ 1 |

### Test case design

13 test cases covering:
- Known correct high scores from real production runs (ground truth positive)
- Known false positives with identified failure modes (ground truth negative)
- Synthetic strong fit, weak fit, and grey zone roles
- Edge cases: AI-adjacent roles, right domain wrong level

### First run results

```
10/13 passing (77%) on first run

Fixed:   Research Engineer scored 2/10 ✓ (was scoring too high)
Fixed:   Consulting FDE scored 4/10 ✓ (consulting correctly flagged)
Remaining: Solutions Architect, Data Analytics floor, Junior PM floor
           → Fixed by adding hard scoring rules to target_roles.md
```

### When to run evals

Run evals when changing `context/target_roles.md`, `context/profile.md`, `scorer.py`, or `skills/scorer_skill.md` — any change that could affect what score Claude assigns. Not needed when changing email formatting, search keywords, or downstream pipeline components.

```bash
python evals/run_evals.py
```

---

## GitHub Actions

The workflow runs only on manual trigger (`workflow_dispatch`) — never on an automatic schedule. This is a deliberate design decision: automation that runs without explicit human intent carries risk when interacting with external services.

To trigger from GitHub:
1. Go to your repo → Actions tab
2. Select `job_scout` workflow
3. Click **Run workflow**

Required GitHub secrets:
- `ANTHROPIC_API_KEY`
- `ADZUNA_APP_ID`
- `ADZUNA_API_KEY`
- `GMAIL_CREDENTIALS_JSON` (base64-encoded credentials.json)
- `GMAIL_TOKEN_JSON` (base64-encoded token.json)
- `RECIPIENT_EMAIL`

To encode credentials for GitHub secrets:
```bash
# Mac
base64 -i credentials.json | pbcopy
base64 -i token.json | pbcopy
```

---

## Design decisions

**Why manual trigger only, not scheduled**
An earlier version ran on a daily cron schedule. LinkedIn scraping during scheduled runs triggered an account flag. Beyond that specific risk, scheduled automation that touches external services should require explicit human intent before running. The workflow_dispatch trigger enforces that.

**Why score ranges in evals, not exact scores**
Requiring an exact score of 8 is too brittle — Claude might reasonably score the same job 7 or 9 depending on which aspects of the JD it weights. A range tests correct behavior without being fragile to small variations in reasoning. This is called eval robustness.

**Why fix context files when evals fail, not test cases**
Test cases represent the candidate's scoring rubric — what correct looks like. When Claude disagrees, the right response is to improve Claude's instructions, not adjust the rubric to match Claude's output. Adjusting test cases to pass would hide failures rather than fix them.

**Why separate checks per eval case, not one pass/fail**
A single pass/fail verdict tells you something went wrong. Five independent checks tell you exactly what went wrong and why. Schema failing means a prompt change broke the output contract. Accuracy failing means the scoring criteria need tuning. Red flags failing means Claude recognized a problem but underweighted it. Each check diagnoses a different type of failure.

---

## Roadmap

- [ ] Feedback agent — record applications, learn from rejections to improve future scoring
- [ ] Search strategy agent — self-improving keyword selection based on result quality
- [ ] Cover letter agent — full cover letter generation per role beyond the opener
- [ ] Application tracker — status dashboard per role applied to
- [ ] Organizer evals — extend eval suite to cover organizer agent
- [ ] Bio agent evals — check resume tailoring against preference rules

---

## Skills and context files

The `skills/` directory contains markdown files that document design decisions, prompt schemas, and constraints for each AI component. These serve as institutional memory — any future modification to an agent component starts by reading the relevant skill file to ensure consistency and prevent regression.

The `context/` directory contains the candidate's professional profile, target role criteria, calibration examples, and resume preferences — the grounding data provided to Claude at every reasoning step. The quality of these files directly determines the quality of AI output.

---

*Built with Claude Code and the Anthropic API.*