import argparse
import json
import logging
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SEEN_JOBS_FILE = Path("seen_jobs.json")
SCORED_JOBS_FILE = Path("scored_jobs.json")

DEFAULT_CONFIG = {
    "search_urls": [],
    "max_applicants": 60,
    "max_days_posted": 7,
    "min_relevance_score": 6,
    "recipient_email": "",
    "exclude_contract": True,
    "prefer_remote_hybrid": True,
    "require_salary": False,
    "send_no_match_email": False,
}

SETUP_INSTRUCTIONS = """
Setup required — edit config.json before running:

  search_urls     : Add LinkedIn job search URLs (copy from your browser).
                    Tip: filter by date posted and experience level in LinkedIn, then copy the URL.
  recipient_email : Your email address for the digest.
                    Leave blank to use the RECIPIENT_EMAIL environment variable instead.

Example search URL:
  https://www.linkedin.com/jobs/search/?keywords=VP+Product+Fintech&location=New+York&f_TPR=r604800&f_E=5%2C6

Also ensure these environment variables are set (see .env.example):
  LINKEDIN_EMAIL, LINKEDIN_PASSWORD, ANTHROPIC_API_KEY, RECIPIENT_EMAIL (if not set in config.json)
"""


def setup_logging():
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


def load_config(path: str) -> dict:
    cfg_path = Path(path)
    if not cfg_path.exists():
        cfg_path.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
        print(f"Created default config at {cfg_path}.")
        print(SETUP_INSTRUCTIONS)
        sys.exit(1)

    with cfg_path.open(encoding="utf-8") as f:
        cfg = json.load(f)

    # Resolve recipient_email: config value → RECIPIENT_EMAIL env var → error
    email = cfg.get("recipient_email", "")
    if not email or email == "your@email.com":
        email = os.environ.get("RECIPIENT_EMAIL", "").strip()
    if not email:
        print("ERROR: recipient_email is not set.")
        print("Set it in config.json or as the RECIPIENT_EMAIL environment variable.")
        print(SETUP_INSTRUCTIONS)
        sys.exit(1)
    cfg["recipient_email"] = email

    return cfg


def load_seen_ids() -> set[str]:
    if not SEEN_JOBS_FILE.exists():
        return set()
    try:
        data = json.loads(SEEN_JOBS_FILE.read_text(encoding="utf-8"))
        return {entry["job_id"] for entry in data if "job_id" in entry}
    except Exception:
        return set()


def save_seen_jobs(new_jobs: list[dict]):
    existing: list[dict] = []
    if SEEN_JOBS_FILE.exists():
        try:
            existing = json.loads(SEEN_JOBS_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    now = datetime.now().isoformat()
    for job in new_jobs:
        existing.append(
            {
                "job_id": job["job_id"],
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "date_notified": now,
            }
        )
    SEEN_JOBS_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def save_scored_jobs(jobs: list[dict]):
    SCORED_JOBS_FILE.write_text(
        json.dumps(jobs, indent=2, default=str), encoding="utf-8"
    )


def load_scored_jobs() -> list[dict]:
    if not SCORED_JOBS_FILE.exists():
        return []
    try:
        return json.loads(SCORED_JOBS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def deduplicate(jobs: list[dict], seen_ids: set[str]) -> list[dict]:
    fresh = [j for j in jobs if j["job_id"] not in seen_ids]
    skipped = len(jobs) - len(fresh)
    if skipped:
        logging.getLogger(__name__).info(
            f"Deduplication: skipped {skipped} already-notified job(s)"
        )
    return fresh


def print_dry_run(digest: dict, total_jobs: int):
    bar = "=" * 62
    must_apply = digest.get("must_apply", [])
    strong_fit = digest.get("strong_fit", [])
    ai_opp = digest.get("ai_opportunity", [])
    monitoring = digest.get("worth_monitoring", [])
    market_intel = digest.get("market_intelligence", [])

    print(f"\n{bar}")
    print(f"DRY RUN -- {total_jobs} match(es)")
    print(f"  Must Apply: {len(must_apply)}  |  Strong Fit: {len(strong_fit)}  "
          f"|  AI Roles: {len(ai_opp)}  |  Monitoring: {len(monitoring)}")
    print(bar)

    sections = [
        ("MUST APPLY THIS WEEK", must_apply),
        ("STRONG FIT -- APPLY SOON", strong_fit),
    ]
    for heading, jobs in sections:
        if not jobs:
            continue
        print(f"\n-- {heading} ({len(jobs)}) --")
        for j in jobs:
            ai = " [AI]" if j.get("ai_opportunity") else ""
            print(f"\n  [{j.get('score', '?')}/10]{ai}  {j.get('title')}  @  {j.get('company')}")
            print(f"  Location   : {j.get('location')}")
            print(f"  Rationale  : {j.get('rationale')}")
            tags = ', '.join(j.get('match_tags', []))
            if tags:
                print(f"  Tags       : {tags}")
            if j.get("red_flags"):
                print(f"  Red flags  : {', '.join(j['red_flags'])}")
            print(f"  URL        : {j.get('job_url')}")

    if ai_opp:
        print(f"\n-- AI OPPORTUNITY ROLES ({len(ai_opp)}) --")
        primary = digest.get("_primary_section", {})
        for j in ai_opp:
            ps = primary.get(j["job_id"], "")
            also = f" [also in {ps.replace('_', ' ')}]" if ps in ("must_apply", "strong_fit") else ""
            print(f"  [{j.get('score', '?')}/10]{also}  {j.get('title')}  @  {j.get('company')}")

    if monitoring:
        print(f"\n-- WORTH MONITORING ({len(monitoring)}) --")
        ai_ids = {j["job_id"] for j in ai_opp}
        priority_ids = {j["job_id"] for j in must_apply + strong_fit}
        for j in monitoring:
            if j["job_id"] not in ai_ids and j["job_id"] not in priority_ids:
                print(f"  [{j.get('score', '?')}/10]  {j.get('title')}  @  {j.get('company')}")

    if market_intel:
        print(f"\n-- MARKET INTELLIGENCE --")
        for bullet in market_intel:
            print(f"  * {bullet}")

    print(f"\n{bar}\n")


def main():
    parser = argparse.ArgumentParser(description="LinkedIn Job Scout")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print digest to console; skip email and seen_jobs update",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore deduplication — re-send all scored matches",
    )
    parser.add_argument(
        "--email-only",
        action="store_true",
        help="Skip scraping/scoring; load scored_jobs.json and send digest",
    )
    parser.add_argument(
        "--tailor",
        action="store_true",
        help="Run resume tailoring for must-apply roles (after email, or standalone with --email-only)",
    )
    parser.add_argument(
        "--config",
        default="config.json",
        metavar="PATH",
        help="Path to config file (default: config.json)",
    )
    args = parser.parse_args()

    setup_logging()
    log = logging.getLogger(__name__)
    log.info("=== LinkedIn Job Scout starting ===")

    # Exit code 1: config error (handled inside load_config via sys.exit)
    config = load_config(args.config)

    has_captcha_warning = False

    if args.email_only and args.tailor:
        # ── Tailor-only mode: skip scrape, score, and email ────────────────
        log.info("Tailor-only mode — loading scored_jobs.json for resume tailoring...")
        from bio_agent import run as tailor_run
        tailor_run(dry_run=args.dry_run)
        sys.exit(0)

    if args.email_only:
        # ── Email-only mode: skip scraping and scoring ─────────────────────
        log.info("Email-only mode — loading scored_jobs.json...")
        scored = load_scored_jobs()
        if not scored:
            log.error(f"{SCORED_JOBS_FILE} not found or empty — run a full pass first to populate it")
            sys.exit(1)
        log.info(f"Loaded {len(scored)} scored job(s) from {SCORED_JOBS_FILE}")
    else:
        # ── Stage 1: Scrape ────────────────────────────────────────────────
        log.info("Stage 1/4 — Scraping jobs (Adzuna / The Muse / Greenhouse)...")
        try:
            from scraper import scrape
            scraped = scrape(config)
        except SystemExit:
            raise
        except Exception:
            log.error(f"Scrape stage failed:\n{traceback.format_exc()}")
            sys.exit(2)

        if not scraped:
            log.info("No jobs passed hard filters — nothing to do.")
            sys.exit(0)

        # ── Stage 2: Score ─────────────────────────────────────────────────
        log.info(f"Stage 2/4 — Scoring {len(scraped)} job(s) with Claude...")
        try:
            from scorer import score_jobs
            scored = score_jobs(scraped, config.get("min_relevance_score", 6))
        except Exception:
            log.error(f"Scoring stage failed:\n{traceback.format_exc()}")
            sys.exit(2)

        if not scored:
            log.info("No jobs met the relevance threshold.")
            if not config.get("send_no_match_email", False):
                sys.exit(0)

        # Always persist scored results so --email-only can use them later
        save_scored_jobs(scored)
        log.info(f"Saved {len(scored)} scored job(s) to {SCORED_JOBS_FILE}")

    # ── Stage 3: Deduplicate ───────────────────────────────────────────────
    log.info("Stage 3/4 — Deduplicating...")
    seen_ids = set() if args.force else load_seen_ids()
    new_jobs = deduplicate(scored, seen_ids)
    log.info(f"{len(new_jobs)} new job(s) after deduplication")

    if not new_jobs and not config.get("send_no_match_email", False):
        log.info("No new matches and send_no_match_email=false — done")
        sys.exit(0)

    # ── Stage 3.5: Organize ────────────────────────────────────────────────
    log.info("Stage 3.5/4 — Organizing digest...")
    try:
        from organizer import organize
        digest = organize(new_jobs)
    except Exception:
        log.error(f"Organize stage failed:\n{traceback.format_exc()}")
        # Fallback: build a minimal digest and continue
        digest = {
            "must_apply": [],
            "strong_fit": new_jobs,
            "ai_opportunity": [j for j in new_jobs if j.get("ai_opportunity")],
            "worth_monitoring": [],
            "market_intelligence": [],
            "_primary_section": {},
        }
        log.warning("Falling back to flat digest — organizer failed")

    # ── Dry run exit ───────────────────────────────────────────────────────
    if args.dry_run:
        print_dry_run(digest, len(new_jobs))
        log.info("Dry run complete — email skipped, seen_jobs not updated")
        sys.exit(0)

    # ── Stage 4: Email ─────────────────────────────────────────────────────
    log.info(f"Stage 4/4 — Sending email to {config['recipient_email']}...")
    try:
        from emailer import send_digest
        result = send_digest(
            digest=digest,
            total_jobs=len(new_jobs),
            recipient_email=config["recipient_email"],
            send_no_match_email=config.get("send_no_match_email", False),
            has_captcha_warning=has_captcha_warning,
        )
    except Exception:
        log.error(f"Email stage failed:\n{traceback.format_exc()}")
        sys.exit(3)

    if not result.get("sent"):
        reason = result.get("reason")
        if reason == "no_matches":
            log.info("Email skipped — no matches")
            sys.exit(0)
        log.error(f"Email failed: {result.get('error')}")
        sys.exit(3)

    save_seen_jobs(new_jobs)
    log.info(
        f"=== Done. {len(new_jobs)} job(s) sent to {config['recipient_email']} "
        f"and recorded in seen_jobs.json ==="
    )

    # ── Stage 5 (optional): Tailor resumes ────────────────────────────────
    if args.tailor:
        log.info("Stage 5 — Tailoring resumes for must-apply roles...")
        try:
            from bio_agent import run as tailor_run
            tailor_run(dry_run=False)
        except Exception:
            log.error(f"Resume tailoring failed:\n{traceback.format_exc()}")

    sys.exit(0)


if __name__ == "__main__":
    main()
