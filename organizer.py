"""
Stage 3.5: Rule-based bucketing + Claude market intelligence.
Organizes scored jobs into a structured digest dict for emailer.py.
"""
import json
import logging
import os
import time

import anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a career advisor helping a senior fintech/AI product leader review this week's job matches.
You will receive a list of scored job listings as JSON.

Your task: write 3-5 concise market intelligence bullets based on what you observe across the full set.

Each bullet should address one of:
- Which companies are hiring most actively this week
- Which domains (payments, risk, fraud, credit, AI infra, solutions) have the most openings
- Whether competition (applicant counts) is high or low for top roles — or if data is missing
- Any notable or surprising companies appearing for the first time
- Seniority or title trends visible across the listings

Return ONLY a JSON array of 3-5 strings. No markdown, no backticks, no preamble, no explanation.
Example: ["Stripe dominates this week with 20+ roles across risk, BD, and solutions.",
          "All 4 Anthropic openings are AI-native engineering or strategy — no traditional PM roles."]
"""


def _get_market_intelligence(jobs: list[dict], retries: int = 3) -> list[str]:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return []

    client = anthropic.Anthropic(api_key=api_key)

    summaries = [
        {
            "title": j.get("title"),
            "company": j.get("company"),
            "location": j.get("location"),
            "score": j.get("score"),
            "applicant_count": j.get("applicant_count"),
            "ai_opportunity": j.get("ai_opportunity"),
            "match_tags": j.get("match_tags", []),
        }
        for j in jobs
    ]
    user_content = (
        f"Here are {len(jobs)} scored job listings from this week's run:\n\n"
        + json.dumps(summaries, indent=2)
    )

    for attempt in range(retries):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=400,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            bullets = json.loads(raw.strip())
            if isinstance(bullets, list) and bullets:
                return [str(b) for b in bullets[:5]]
        except json.JSONDecodeError as exc:
            logger.warning(f"Market intelligence JSON parse error (attempt {attempt + 1}): {exc}")
        except anthropic.APIError as exc:
            logger.warning(f"Market intelligence API error (attempt {attempt + 1}): {exc}")

        if attempt < retries - 1:
            time.sleep(2 ** attempt)

    logger.warning("Market intelligence generation failed after retries — section omitted")
    return []


def _bucket(job: dict) -> str:
    """Returns the primary bucket name for a job based on score and applicant count."""
    score = job.get("score", 0)
    applicants = job.get("applicant_count")

    if applicants is not None:
        n = int(applicants)
        if score >= 8 and n < 20:
            return "must_apply"
        if score >= 7 and n <= 60:
            return "strong_fit"
        return "worth_monitoring"

    # No applicant data — use score alone as proxy
    if score >= 9:
        return "must_apply"
    if score >= 7:
        return "strong_fit"
    return "worth_monitoring"


def organize(jobs: list[dict]) -> dict:
    """
    Buckets jobs by urgency/score rules; generates market intelligence via Claude.
    A job can appear in both ai_opportunity AND must_apply/strong_fit/worth_monitoring.
    Returns a digest dict matching the organizer_skill.md schema.
    """
    must_apply: list[dict] = []
    strong_fit: list[dict] = []
    ai_opportunity: list[dict] = []
    worth_monitoring: list[dict] = []
    primary_section: dict[str, str] = {}

    for job in jobs:
        jid = job["job_id"]
        bucket = _bucket(job)

        if bucket == "must_apply":
            must_apply.append(job)
        elif bucket == "strong_fit":
            strong_fit.append(job)
        else:
            worth_monitoring.append(job)

        primary_section[jid] = bucket

        if job.get("ai_opportunity"):
            ai_opportunity.append(job)

    for section in (must_apply, strong_fit, ai_opportunity, worth_monitoring):
        section.sort(key=lambda j: j.get("score", 0), reverse=True)

    market_intelligence = _get_market_intelligence(jobs)

    digest = {
        "must_apply": must_apply,
        "strong_fit": strong_fit,
        "ai_opportunity": ai_opportunity,
        "worth_monitoring": worth_monitoring,
        "market_intelligence": market_intelligence,
        "_primary_section": primary_section,
    }

    logger.info(
        f"Organize complete — must_apply: {len(must_apply)}, "
        f"strong_fit: {len(strong_fit)}, ai_opportunity: {len(ai_opportunity)}, "
        f"worth_monitoring: {len(worth_monitoring)}"
    )
    return digest
