"""
Stage 5 (optional): Resume tailoring agent.
Reads must_apply jobs from scored_jobs.json, tailors resume via Claude,
generates Word docs via generate_doc.js.
"""
import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import anthropic
from docx import Document
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SCORED_JOBS_FILE = Path("scored_jobs.json")
RESUME_TEMPLATE = Path("resume_template.docx")
PREFERENCES_CANDIDATES = [
    Path("context/resume_preferences.md"),
    Path("context/resume_preferences.md.txt"),
]
PROFILE_FILE = Path("context/profile.md")
OUTPUT_DIR = Path("tailored_resumes")

REQUIRED_FIELDS = {
    "role_type_detected", "emphasis_rationale", "summary",
    "why_this_role", "experience", "skills",
    "keywords_incorporated", "gaps_addressed",
}

# Known section header text (normalized: uppercase, trailing period stripped)
_SECTION_HEADERS = {
    "EXECUTIVE SUMMARY", "EXPERIENCE", "EDUCATION", "COMMUNITY", "SKILLS"
}

SYSTEM_PROMPT = """\
You are an expert resume writer for senior product leaders in fintech, AI, and payments. \
You tailor resumes by reordering and reframing real experience to maximize relevance \
for a specific role.

You must follow the candidate's resume preferences exactly. \
These preferences override any generic resume writing conventions.

Resume preferences:
{preferences}

ABSOLUTE RULES — never break these:
1. Never invent experience, metrics, companies, titles, or dates not in the original resume
2. Never estimate or fabricate metrics — only use numbers already present in the resume
3. Never start a bullet with a buzzword from the avoid list in preferences
4. Every bullet must lead with outcome or metric first
5. If a JD requirement has no honest match, note it in gaps_addressed — do not paper over it
6. Metrics must come from the original resume only
7. Do not rewrite or modify Education or Community sections. These are carried through \
unchanged from the original resume. Focus only on: Executive Summary, Experience bullets, \
and Skills.

One-page target: Aim to keep the tailored resume to one page where possible. Prefer 4-5 \
strong bullets per role over 6-8 weaker ones. Quality over quantity. The most recent two \
roles (Capital One, Mastercard) should have the most bullets (4-5 each). Earlier roles \
(EY) should have 3-4 bullets. Keep summary to 3-4 lines maximum.

Return only valid JSON. No markdown. No preamble. No backticks. Raw JSON only."""

USER_PROMPT = """\
Candidate profile:
{profile}

Job being applied to:
Title: {title}
Company: {company}
Applicant count: {applicant_count}
Relevance score: {score}/10
Match tags: {match_tags}
Gaps identified by scorer: {gaps}

Full job description:
{description}

Candidate base resume (full text for context — do NOT rewrite Education or Community):
{resume_text}

Detect the role type and tailor accordingly:
- fintech_platform: payments, risk, decisioning, credit, fraud, AI/ML platform, infrastructure
- data_analytics: data products, analytics, reporting, BI, data strategy, governance
- ai_adjacent: forward deployed, solutions, BD or consulting at AI-native company
- hybrid: spans two or more domains equally

Return this exact JSON:
{{
  "role_type_detected": "fintech_platform / data_analytics / ai_adjacent / hybrid",
  "emphasis_rationale": "one sentence on what was emphasized and why",
  "summary": "3-4 lines. Opens with positioning statement naming domain and level. Never opens with I. No buzzwords. Bridges candidate background to this specific role and company.",
  "why_this_role": "2-3 sentences for cover letter opener. Names the company. Specific to this role not generic.",
  "experience": [
    {{
      "company": "exact from original resume",
      "title": "exact from original resume",
      "dates": "exact from original resume",
      "bullets": [
        "Outcome or metric first, then action that caused it. Strong past-tense verb. 1-2 lines. Metric from original resume only. Capital One and Mastercard: 4-5 bullets each. EY: 3-4 bullets."
      ]
    }}
  ],
  "skills": {{
    "domain": ["Fintech", "Payments", "Risk Decisioning"],
    "product": ["Platform PM", "AI/ML Products"],
    "tools": []
  }},
  "keywords_incorporated": [
    "JD keyword truthfully added to a bullet"
  ],
  "gaps_addressed": "Honest note on any JD requirement with no resume match. Or: No significant gaps identified."
}}"""


def _setup_logging():
    if logging.getLogger().handlers:
        return
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)
    fh = logging.FileHandler("scout.log", encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)


def _load_must_apply_jobs() -> list[dict]:
    if not SCORED_JOBS_FILE.exists():
        print("No scored jobs found. Run python agent.py first then re-run bio_agent.py")
        sys.exit(0)
    try:
        jobs = json.loads(SCORED_JOBS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error(f"Failed to read {SCORED_JOBS_FILE}: {exc}")
        sys.exit(1)

    from organizer import _bucket
    return [j for j in jobs if _bucket(j) == "must_apply"]


def _extract_resume(doc_path: Path) -> dict:
    """
    Extracts structured content from resume_template.docx.
    Returns: name, contact, full_text (for Claude), education lines, community lines.
    Education and Community are extracted separately so they can be carried through
    unchanged without being rewritten by Claude.
    """
    if not doc_path.exists():
        print("Place your base resume as resume_template.docx in the project root folder then re-run.")
        sys.exit(0)

    doc = Document(doc_path)
    paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

    name = paras[0] if paras else "Vartika Rawat"
    contact = paras[1] if len(paras) > 1 else ""

    education_lines: list[str] = []
    community_lines: list[str] = []
    current_section: str | None = None
    all_lines: list[str] = [name, contact]

    for para in paras[2:]:
        normalized = para.upper().strip().rstrip(".")
        if normalized in _SECTION_HEADERS:
            current_section = normalized
            all_lines.append(para)
            continue

        all_lines.append(para)
        if current_section == "EDUCATION":
            education_lines.append(para)
        elif current_section == "COMMUNITY":
            community_lines.append(para)

    logger.info(f"  Resume: name='{name}', education={len(education_lines)} line(s), "
                f"community={len(community_lines)} line(s)")

    return {
        "name": name,
        "contact": contact,
        "full_text": "\n".join(all_lines),
        "education": education_lines,
        "community": community_lines,
    }


def _read_preferences() -> str:
    for p in PREFERENCES_CANDIDATES:
        if p.exists():
            return p.read_text(encoding="utf-8")
    logger.warning("resume_preferences.md not found — tailoring will use default conventions")
    return ""


def _slug(text: str, max_words: int = 4) -> str:
    words = re.sub(r"[^a-zA-Z0-9\s]", "", text).split()
    return "_".join(w.capitalize() for w in words[:max_words])


def _make_filename(company: str, title: str) -> str:
    date_str = datetime.now().strftime("%Y%m%d")
    return f"{_slug(company, 1)}_{_slug(title, 4)}_{date_str}.docx"


def _tailor_one(
    client: anthropic.Anthropic,
    job: dict,
    resume_text: str,
    preferences: str,
    profile: str,
    retries: int = 3,
) -> dict | None:
    system = SYSTEM_PROMPT.format(preferences=preferences)
    user = USER_PROMPT.format(
        profile=profile,
        title=job.get("title", ""),
        company=job.get("company", ""),
        applicant_count=job.get("applicant_count") or "unknown",
        score=job.get("score", "?"),
        match_tags=", ".join(job.get("match_tags", [])),
        gaps=", ".join(job.get("gaps", [])) if job.get("gaps") else "None identified",
        description=job.get("description", "")[:5000],
        resume_text=resume_text,
    )

    for attempt in range(retries):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4000,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            raw = response.content[0].text.strip()
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw.strip())
            result = json.loads(raw)
            missing = REQUIRED_FIELDS - set(result.keys())
            if missing:
                logger.warning(f"Missing fields {missing} for {job['job_id']} — retrying")
                continue
            return result
        except json.JSONDecodeError as exc:
            logger.warning(f"JSON parse error (attempt {attempt + 1}) for {job['job_id']}: {exc}")
        except anthropic.APIError as exc:
            logger.warning(f"API error (attempt {attempt + 1}) for {job['job_id']}: {exc}")

        if attempt < retries - 1:
            time.sleep(2 ** attempt)

    return None


def _generate_doc(tailored: dict, job: dict, extracted: dict, output_path: Path):
    doc_data = {
        "candidate_name": extracted["name"],
        "contact": extracted["contact"],
        "education": extracted["education"],
        "community": extracted["community"],
        "target_title": job.get("title", ""),
        "target_company": job.get("company", ""),
        "target_score": job.get("score", ""),
        "target_date": datetime.now().strftime("%B %d, %Y"),
        "role_type_detected": tailored.get("role_type_detected", ""),
        "emphasis_rationale": tailored.get("emphasis_rationale", ""),
        "summary": tailored.get("summary", ""),
        "why_this_role": tailored.get("why_this_role", ""),
        "experience": tailored.get("experience", []),
        "skills": tailored.get("skills", {}),
        "keywords_incorporated": tailored.get("keywords_incorporated", []),
        "gaps_addressed": tailored.get("gaps_addressed", ""),
        "output_path": str(output_path),
    }
    proc = subprocess.run(
        ["node", "generate_doc.js"],
        input=json.dumps(doc_data, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "generate_doc.js exited non-zero")
    if proc.stdout.strip():
        logger.debug(proc.stdout.strip())


def run(dry_run: bool = False, email_resumes: bool = False, recipient_email: str = ""):
    _setup_logging()
    OUTPUT_DIR.mkdir(exist_ok=True)

    must_apply = _load_must_apply_jobs()
    if not must_apply:
        logger.info("No must-apply jobs in scored_jobs.json — nothing to tailor")
        return
    logger.info(f"Found {len(must_apply)} must-apply role(s) to tailor resumes for")

    extracted = _extract_resume(RESUME_TEMPLATE)
    preferences = _read_preferences()
    profile = PROFILE_FILE.read_text(encoding="utf-8") if PROFILE_FILE.exists() else ""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    generated = 0
    doc_metadata: list[dict] = []

    for job in must_apply:
        title = job.get("title", "Unknown")
        company = job.get("company", "Unknown")
        logger.info(f"Tailoring: [{job.get('score')}/10] {title} @ {company}")

        tailored = _tailor_one(client, job, extracted["full_text"], preferences, profile)
        if tailored is None:
            logger.warning(f"  Skipping {job['job_id']} — tailoring failed after retries")
            continue

        role_type = tailored.get("role_type_detected", "unknown")
        logger.info(f"  Role type : {role_type}")
        logger.info(f"  Emphasis  : {tailored.get('emphasis_rationale', '')}")

        if dry_run:
            continue

        filename = _make_filename(company, title)
        output_path = OUTPUT_DIR / filename
        try:
            _generate_doc(tailored, job, extracted, output_path)
            logger.info(f"  Generated: tailored_resumes/{filename}")
            generated += 1
            doc_metadata.append({
                "path": str(output_path),
                "company": company,
                "title": title,
                "role_type": role_type,
                "score": job.get("score", "?"),
            })
        except Exception as exc:
            logger.warning(f"  Doc generation failed for {job['job_id']}: {exc}")

    if not dry_run:
        logger.info(
            f"Resume tailoring complete: {generated} doc(s) generated. "
            f"Saved to tailored_resumes/"
        )

        if email_resumes and doc_metadata and recipient_email:
            logger.info(f"Emailing {len(doc_metadata)} resume(s) to {recipient_email}...")
            from emailer import send_resumes
            result = send_resumes(doc_metadata, recipient_email)
            if result.get("sent"):
                logger.info(
                    f"Resumes emailed — {result.get('attachments', 0)} attachment(s) sent"
                )
            else:
                logger.error(f"Resume email failed: {result.get('error', result.get('reason'))}")


def main():
    parser = argparse.ArgumentParser(description="Resume Tailoring Agent")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Detect role type and emphasis only — skip Word doc generation",
    )
    parser.add_argument(
        "--email-resumes", action="store_true",
        help="Email all generated .docx files to recipient_email from config.json",
    )
    args = parser.parse_args()

    recipient_email = ""
    if args.email_resumes:
        cfg_path = Path("config.json")
        if cfg_path.exists():
            try:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                recipient_email = cfg.get("recipient_email", "")
            except Exception:
                pass
        if not recipient_email:
            print("ERROR: recipient_email not set in config.json — cannot email resumes")
            sys.exit(1)

    run(dry_run=args.dry_run, email_resumes=args.email_resumes, recipient_email=recipient_email)


if __name__ == "__main__":
    main()
