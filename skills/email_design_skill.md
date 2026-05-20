# Email Design — Skill File

## Purpose
Defines the structure, sections, and visual design of 
the HTML digest email sent by emailer.py.

## Subject line format
"🎯 Job Scout — {date} — {n} new matches"

## Header summary bar
Must apply: X | Strong fit: X | AI roles: X | Monitoring: X

## Section order and design
1. MUST APPLY THIS WEEK
   - Red badge if applicants < 5 (exceptional urgency)
   - Orange badge if applicants 5-20
   - Full job card: title, company, location, score, 
     rationale, top 2 alignment bullets, top 1 gap, 
     applicant count, posted date, View on LinkedIn button

2. STRONG FIT — APPLY SOON
   - Green score badge
   - Full job card as above

3. AI OPPORTUNITY ROLES
   - Purple AI badge
   - Note if also in section 1 or 2
   - Include what AI exposure the role offers

4. WORTH MONITORING
   - Minimal card: title, company, score, link only
   - No full detail — keeps email scannable

5. MARKET INTELLIGENCE
   - Insight box at bottom, not a job card
   - Bulleted list of 3-5 observations

## Design principles
- Clean, scannable — most important info at the top
- Color encodes urgency not just score
- Sections have clear visual separation
- Mobile readable — single column layout
- No image attachments — HTML only
