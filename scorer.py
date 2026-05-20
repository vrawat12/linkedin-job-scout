import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

PROFILE_PATH = Path("context/profile.md")
TARGET_ROLES_PATH = Path("context/target_roles.md")
SAMPLE_JOB_PATH = Path("context/sample_job.md")

SYSTEM_PROMPT = """\
You are a job relevance scorer. You will receive a candidate profile and a job posting.
Respond ONLY with valid JSON — no markdown fences, no preamble, no trailing text.

Required JSON schema (exactly this shape):
{
  "score": <integer 1-10>,
  "rationale": "<2 sentences max>",
  "match_tags": ["<short tag>", ...],
  "red_flags": ["<short flag>", ...],
  "ai_opportunity": <true if role offers meaningful hands-on AI/ML exposure, else false>,
  "alignment": ["<bullet: where candidate experience directly matches>", ...],
  "gaps": ["<bullet: meaningful gap between candidate and role>", ...]
}

Rules for alignment and gaps:
- alignment: 2-3 concise bullets describing where the candidate's background directly fits
  the role requirements. Be specific — reference actual experience from their profile.
- gaps: 1-2 concise bullets for meaningful mismatches. If there are no significant gaps,
  return ["No significant gaps identified."]

Scoring calibration:
9-10  Near-perfect — right title level, fintech/AI/payments domain, platform scope,
      risk/decisioning or AI-native company, hybrid or remote, under 60 applicants.
7-8   Strong — right seniority level, good domain fit, minor gaps.
5-6   Moderate — some relevant signals but missing title level, domain, or scope.
3-4   Weak — wrong domain or seniority, no AI/ML/fintech angle.
1-2   Poor — consumer mobile, contract/freelance, irrelevant field.

AI-native company scoring rules:
- Score AI-native companies selling into financial services equally to or higher than
  traditional financial institutions, even if the role type is non-traditional
  (forward deployed engineer, BD, solutions architect, consulting).
- For AI-adjacent roles (forward deployed, BD, solutions, consulting, advisory):
  score 7+ if the role offers meaningful hands-on AI product exposure in a
  fintech or financial services context.
- Set ai_opportunity: true for any role that builds deep hands-on AI/ML expertise,
  regardless of whether the title is traditional PM or not.

Boost score for: decisioning, underwriting, risk orchestration, AI/ML product ownership,
platform/infrastructure scope, compliance-adjacent work, LLMs, agents, decisioning AI,
fraud AI, credit AI, Discover/Capital One/Mastercard/Stripe context,
Oscilar/Sardine/Socure/Alloy/Unit21/Anthropic/OpenAI or similar AI-native fintech.

Boost for AI-adjacent roles if: role involves deploying/implementing AI with customers,
bridges technical AI capability and financial services domain, or is at a company in
AI infrastructure, AI safety, ML ops, AI decisioning, agentic platforms, or applied AI for fintech.

Lower score for: pure consumer mobile with no platform component, contract/freelance,
relocation outside NY/NJ/remote, legacy financial institution with no meaningful AI component.

Flag in red_flags when: role is at a legacy financial institution with no meaningful
AI component and no platform/decisioning scope.\
"""


def _read_file(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    txt = path.with_suffix(path.suffix + ".txt")
    if txt.exists():
        return txt.read_text(encoding="utf-8")
    logger.warning(f"Context file not found: {path}")
    return ""


def load_context() -> str:
    parts = []
    for p in (PROFILE_PATH, TARGET_ROLES_PATH, SAMPLE_JOB_PATH):
        content = _read_file(p)
        if content:
            parts.append(f"=== {p.stem} ===\n{content}")
    return "\n\n".join(parts)


def _score_one(
    client: anthropic.Anthropic,
    cached_system: list[dict],
    job: dict,
    retries: int = 3,
) -> Optional[dict]:
    user_content = (
        f"Score this job posting for the candidate.\n\n"
        f"Title: {job.get('title', '')}\n"
        f"Company: {job.get('company', '')}\n"
        f"Location: {job.get('location', '')}\n"
        f"Applicants: {job.get('applicant_count', 'unknown')}\n\n"
        f"Full Description:\n{job.get('description', '')[:6000]}"
    )

    for attempt in range(retries):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=700,
                system=cached_system,
                messages=[{"role": "user", "content": user_content}],
            )
            raw = response.content[0].text.strip()
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning(f"JSON parse error (attempt {attempt + 1}) for {job['job_id']}: {exc}")
        except anthropic.APIError as exc:
            logger.warning(f"API error (attempt {attempt + 1}) for {job['job_id']}: {exc}")

        if attempt < retries - 1:
            time.sleep(2 ** attempt)

    return None


def score_jobs(jobs: list[dict], min_score: int) -> list[dict]:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    context = load_context()

    # Static context is sent once as a cached system block — all subsequent
    # calls for different jobs reuse the cache hit.
    cached_system = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT + "\n\n" + context,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    scored: list[dict] = []
    for job in jobs:
        result = _score_one(client, cached_system, job)
        if result is None:
            logger.warning(f"Skipping {job['job_id']} — scoring failed after retries")
            continue

        score = result.get("score", 0)
        if score < min_score:
            logger.info(
                f"Score {score}/10 below threshold ({min_score}): "
                f"[{job['company']}] {job['title']}"
            )
            continue

        job.update(result)
        scored.append(job)
        ai_flag = " [AI]" if result.get("ai_opportunity") else ""
        logger.info(f"Score {score}/10{ai_flag}: [{job['company']}] {job['title']}")

    logger.info(f"Scoring complete — {len(scored)}/{len(jobs)} job(s) met threshold")
    return scored
