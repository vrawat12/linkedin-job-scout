# Bio Agent — Skill File

## Purpose
Tailors the candidate's base resume for each must-apply job.
Runs as Stage 5 (optional) in the pipeline, triggered by --tailor flag.

## Model
claude-sonnet-4-6

## Inputs
- scored_jobs.json           — source of must-apply job list
- resume_template.docx       — base resume (python-docx extraction)
- context/resume_preferences.md (or .md.txt) — governs all tailoring decisions
- context/profile.md         — candidate background summary

## Outputs
- tailored_resumes/{Company}_{TitleSlug}_{Date}.docx

## Filename convention
{Company}_{TitleSlug}_{Date}.docx
  Company   = first word of company name, Title Case
  TitleSlug = first 4 significant words, Title Case, underscored
  Date      = YYYYMMDD
Example: Block_Head_Of_Product_20260519.docx

## Role type detection
Claude detects one of four role types per job:
- fintech_platform  — payments, risk, decisioning, credit, fraud, AI/ML platform, infrastructure
- data_analytics    — data products, analytics, reporting, BI, data strategy, governance
- ai_adjacent       — forward deployed, solutions, BD or consulting at AI-native company
- hybrid            — spans two or more domains equally

## Emphasis rules by role type
fintech_platform:
  Lead with Capital One decisioning + KYC/fraud platform scope
  Highlight Mastercard $130M P&L and ML credit diagnostics
  EY KYC platform as supporting evidence ($40M fraud prevention)

data_analytics:
  Lead with Mastercard data products and GenAI narrative automation
  Highlight Capital One data product strategy (3 data products)
  Show breadth: marketable data, application data, concerns data

ai_adjacent:
  Lead with agentic AI use case identification (Capital One)
  Highlight GenAI initiative at Mastercard (60% time-to-insight reduction)
  Frame all experience as "bridge between AI capability and financial services"

hybrid:
  Balance platform scope with AI/ML product evidence
  Use Mastercard as the bridge: ML products + platform scale + data

## JSON output schema (Claude → bio_agent.py)
{
  "role_type_detected": "fintech_platform | data_analytics | ai_adjacent | hybrid",
  "emphasis_rationale": "one sentence on what was emphasized and why",
  "summary": "3-4 lines. Opens with positioning statement naming domain and level.",
  "why_this_role": "2-3 sentences for cover letter opener. Names the company. Role-specific.",
  "experience": [
    {
      "company": "exact from original resume",
      "title": "exact from original resume",
      "dates": "exact from original resume",
      "bullets": ["Outcome first, then action. Past-tense verb. 1-2 lines. Metric from original only."]
    }
  ],
  "skills": {
    "domain": ["Fintech", "Payments", "Risk Decisioning"],
    "product": ["Platform PM", "AI/ML Products"],
    "tools": []
  },
  "keywords_incorporated": ["JD keyword truthfully added to a bullet"],
  "gaps_addressed": "Honest gap note or: No significant gaps identified."
}

## Absolute rules — never break
1. Never invent experience, metrics, companies, titles, or dates
2. Never estimate or fabricate metrics — only use numbers from the original resume
3. Never start a bullet with a banned word (see resume_preferences.md avoid list)
4. Every bullet must lead with outcome or metric first
5. Metrics in bullets must come from the original resume only
6. If a JD requirement has no honest match, report it in gaps_addressed

## Preferred bullet verbs (from resume_preferences.md)
Built, Led, Delivered, Drove, Reduced, Grew, Launched, Redesigned,
Partnered, Owned, Scaled, Defined, Negotiated, Replaced, Consolidated

## Banned words / buzzwords (from resume_preferences.md)
synergy, passionate, thought leader, leverage (as verb), guru, ninja,
rockstar, dynamic, innovative, proactive, results-driven

## Key metrics available from original resume (use only these)
- 1M+ applicants monthly (Capital One platform scale)
- $130M+ global platform P&L (Mastercard)
- 18% YoY platform growth (Mastercard)
- $50M new revenue opportunity from two net-new product lines (Mastercard)
- $5M+ incremental ARR from ML credit diagnostics (Mastercard)
- 60% reduction in time-to-insight from GenAI initiative (Mastercard)
- 85% performance improvement + 60% reliability improvement (Mastercard re-arch)
- 7 PMs + 80+ engineers managed (Mastercard)
- 4,000+ institutional clients (Mastercard)
- 50% processing time reduction (EY KYC platform)
- $40M+ annual fraud losses prevented (EY KYC platform)
- 30% MoM increase in new customer acquisition (EY wealth platform)
- A decade at EY (2011-2021)

## Error handling
- Retry 3x with exponential backoff on API failure
- Validate all required JSON fields present before doc generation
- Strip markdown fences before JSON parse
- On persistent Claude failure: skip role, log warning, continue
- On generate_doc.js failure: log error with stderr, continue to next role

## CLI flags
python bio_agent.py            — full tailoring, generate all Word docs
python bio_agent.py --dry-run  — role type + emphasis only, no Word docs

In agent.py pipeline:
--tailor                       — run tailoring after email in full pipeline
--email-only --tailor          — load scored_jobs.json, tailor only, skip email

## Resume Visual Format

### Color palette
- #1B3A6B (navy)  — candidate name, all section headers
- #000000 (black) — all body text, contact line, bullets
- #888888 (gray)  — footer metadata only

### Name (header)
- 28pt bold navy, centered
- Spacing after: 40

### Contact line
- 10pt black, centered
- Extracted directly from resume_template.docx (never hardcoded)
- Spacing after: 120

### Section headers
- 11pt bold navy, ALL CAPS (toUpperCase() in JS)
- Paragraph border bottom: navy, SINGLE, size 6, space 4
- Spacing before: 200, after: 80

### Job header (experience entry)
- Left: Company bold 10.5pt + " | " + Title normal 10.5pt
- Right: Dates 10pt, right-aligned via tab stop at 9720 DXA
- Spacing before: 160, after: 60

### Bullets
- 10.5pt black, LevelFormat.BULLET
- Indent: left 360, hanging 360
- Never unicode bullet in paragraph text
- Spacing before: 40, after: 40

### Section order (every resume)
1. Header (name, contact)
2. Executive Summary  ← Claude rewrites
3. Experience         ← Claude rewrites bullets
4. Education          ← carried through unchanged
5. Community          ← carried through unchanged
6. Skills             ← conditional, omit if not relevant
7. Cover Letter Opening ← supplementary, always at end

### Tailored-for notation
- In the page footer only (right-aligned, 8pt gray)
- Format: "Tailored for {title} at {company} | {date} | Score: {score}/10 | {role_type}"
- Never in the resume body

### One-page target
- Capital One + Mastercard: 4-5 bullets each (most recent = most space)
- EY: 3-4 bullets
- Summary: 3-4 lines maximum
- Skills: inline grouped text, not a table

### Education and Community
- Extracted from resume_template.docx and carried through as-is
- Claude never receives these sections for rewriting
- Rendered as plain body paragraphs (10.5pt black)

### Page settings
- US Letter: 12240 × 15840 DXA
- Margins: top/bottom 1080 DXA (0.75"), left/right 1260 DXA (0.875")
- Content width (tab stop position): 9720 DXA
- No page numbers in body — footer carries metadata

## Doc generation (generate_doc.js)
- Input: JSON via stdin (not CLI arg — avoids Windows length limits)
- Output: .docx written to data.output_path
- doc_data fields: candidate_name, contact, education[], community[],
  target_title, target_company, target_score, target_date,
  role_type_detected, emphasis_rationale, summary, why_this_role,
  experience[], skills{}, keywords_incorporated[], gaps_addressed
- Bullets: LevelFormat.BULLET (never unicode bullet character in paragraph text)
- Dividers: paragraph border bottom in navy (never tables)
- Tab stop at CONTENT_W (9720 DXA) for right-aligned dates
