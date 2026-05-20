"""
Multi-source job scraper: Adzuna API + Greenhouse public boards.
No browser automation, no account required, zero LinkedIn risk.
"""

import logging
import os
import re
import time
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)

CONTRACT_KEYWORDS = [
    "contract", "freelance", "contractor", "temp ", "temporary",
    "c2c", "1099", "corp-to-corp",
]

# Greenhouse: only score jobs whose title matches at least one of these terms.
# Prevents spending Claude calls on Account Executives, SWEs, HR roles, etc.
GREENHOUSE_TITLE_TERMS = {
    # Product roles
    "product manager", "product lead", "product director", "product management",
    "head of product", "vp ", "vice president", "general manager", "gm ",
    "staff product", "principal product",
    # AI-adjacent / forward-deployed
    "forward deployed", "solutions architect", "solutions engineer",
    "applied ai", "technical program manager", "research engineer",
    "ml engineer", "field engineer",
    # Business / strategy
    "business development", "partner development", "partner enablement",
    "client enablement", "strategic partner", "strategist", "strategy",
    # Domain signals
    "risk", "fraud", "credit", "compliance", "underwriting",
    "machine learning", "llm",
    # Customer success (enterprise scope)
    "customer success",
}

# Accepted location terms for Greenhouse jobs (empty = include)
LOCATION_TERMS = {
    "new york", " ny", "new jersey", " nj", "remote", "united states",
    "hybrid", "anywhere", "us-", "usa",
}

DEFAULT_GREENHOUSE_COMPANIES = [
    "brex", "stripe", "marqeta", "anthropic", "scaleai", "alloy",
]

# Shorter, broader Adzuna queries — long multi-word phrases return 0 results
DEFAULT_ADZUNA_QUERIES = [
    "Director Product Management Fintech",
    "VP Product",
    "Head of Product",
    "Forward Deployed Engineer",
    "AI Solutions Engineer",
    "Product Lead AI",
    "Director Product Payments",
    "VP Product Risk",
    "Head of Product Credit",
    "Solutions Architect Fintech",
    "General Manager AI Products",
    "Director Product Fraud",
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html or "").strip()


def _is_contract(title: str, description: str) -> bool:
    combined = (title + " " + description).lower()
    return any(kw in combined for kw in CONTRACT_KEYWORDS)


def _is_too_old(posted_date: Optional[datetime], max_days: int) -> bool:
    if posted_date is None:
        return False
    return (datetime.now() - posted_date).days > max_days


def _parse_iso(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        normalized = re.sub(r"[+-]\d{2}:\d{2}$", "", date_str.replace("Z", ""))
        return datetime.fromisoformat(normalized).replace(tzinfo=None)
    except Exception:
        return None


def _get(url: str, params: dict = None, timeout: int = 15) -> Optional[dict]:
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as exc:
        logger.warning(f"HTTP {exc.response.status_code} fetching {url}")
        return None
    except Exception as exc:
        logger.warning(f"Request error fetching {url}: {exc}")
        return None


def _job_id(source: str, raw_id) -> str:
    return f"{source}_{raw_id}"


def _gh_title_relevant(title: str) -> bool:
    t = title.lower()
    # Whole-word "ai" check (e.g. "Product Lead, AI", "Applied AI Engineer")
    if re.search(r"\bai\b", t):
        return True
    return any(term in t for term in GREENHOUSE_TITLE_TERMS)


def _location_ok(location: str) -> bool:
    if not location:
        return True
    loc = location.lower()
    return any(term in loc for term in LOCATION_TERMS)


# ── Adzuna ───────────────────────────────────────────────────────────────────

def _scrape_adzuna(
    queries: list[str],
    max_days: int,
    exclude_contract: bool,
) -> list[dict]:
    app_id = os.environ.get("ADZUNA_APP_ID", "")
    api_key = os.environ.get("ADZUNA_API_KEY", "")
    if not app_id or not api_key:
        logger.warning("ADZUNA_APP_ID / ADZUNA_API_KEY not set — skipping Adzuna")
        return []

    jobs: list[dict] = []
    seen: set[str] = set()

    for query in queries:
        for page in range(1, 3):  # 2 pages × 50 = up to 100 per query
            data = _get(
                f"https://api.adzuna.com/v1/api/jobs/us/search/{page}",
                params={
                    "app_id": app_id,
                    "app_key": api_key,
                    "what": query,
                    "max_days_old": max_days,
                    "results_per_page": 50,
                    "content-type": "application/json",
                },
            )
            if not data:
                break

            results = data.get("results", [])
            if not results:
                break

            for r in results:
                raw_id = str(r.get("id", ""))
                if not raw_id or raw_id in seen:
                    continue

                title = r.get("title", "")
                # Skip obviously irrelevant titles before scoring
                if not _gh_title_relevant(title):
                    continue

                company = r.get("company", {}).get("display_name", "")
                location = r.get("location", {}).get("display_name", "")
                description = r.get("description", "")
                job_url = r.get("redirect_url", "")
                posted_date = _parse_iso(r.get("created", ""))

                if _is_too_old(posted_date, max_days):
                    continue
                if exclude_contract and _is_contract(title, description):
                    continue

                seen.add(raw_id)
                jobs.append({
                    "job_id": _job_id("az", raw_id),
                    "title": title,
                    "company": company,
                    "location": location,
                    "description": description,
                    "applicant_count": None,
                    "posted_date": posted_date.isoformat() if posted_date else "",
                    "job_url": job_url,
                })

            time.sleep(0.4)

    logger.info(f"Adzuna: {len(jobs)} job(s) from {len(queries)} queries")
    return jobs


# ── Greenhouse ────────────────────────────────────────────────────────────────

def _scrape_greenhouse(
    companies: list[str],
    max_days: int,
    exclude_contract: bool,
) -> list[dict]:
    jobs: list[dict] = []
    seen: set[str] = set()

    for slug in companies:
        data = _get(
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
            params={"content": "true"},
        )
        if not data:
            logger.warning(f"Greenhouse: no board found for '{slug}'")
            continue

        company_name = data.get("name", slug.replace("-", " ").title())
        board_jobs = data.get("jobs", [])
        added = skipped_title = skipped_loc = skipped_age = 0

        for r in board_jobs:
            raw_id = str(r.get("id", ""))
            if not raw_id or raw_id in seen:
                continue

            title = r.get("title", "")
            if not _gh_title_relevant(title):
                skipped_title += 1
                continue

            location = r.get("location", {}).get("name", "")
            if not _location_ok(location):
                skipped_loc += 1
                continue

            posted_date = _parse_iso(r.get("updated_at", ""))
            if _is_too_old(posted_date, max_days):
                skipped_age += 1
                continue

            description = _strip_html(r.get("content", ""))
            job_url = r.get("absolute_url", "")

            if exclude_contract and _is_contract(title, description):
                continue

            seen.add(raw_id)
            jobs.append({
                "job_id": _job_id("gh", raw_id),
                "title": title,
                "company": company_name,
                "location": location,
                "description": description,
                "applicant_count": None,
                "posted_date": posted_date.isoformat() if posted_date else "",
                "job_url": job_url,
            })
            added += 1

        logger.info(
            f"Greenhouse [{slug}]: {added} passed "
            f"({skipped_title} wrong title, {skipped_loc} wrong location, "
            f"{skipped_age} too old) of {len(board_jobs)} total"
        )
        time.sleep(0.3)

    return jobs


# ── Entry point ───────────────────────────────────────────────────────────────

def scrape(config: dict) -> list[dict]:
    # Adzuna uses shorter dedicated queries; fall back to DEFAULT if not in config
    adzuna_queries = config.get("adzuna_queries", DEFAULT_ADZUNA_QUERIES)
    gh_companies = config.get("greenhouse_companies", DEFAULT_GREENHOUSE_COMPANIES)
    max_days = config.get("max_days_posted", 7)
    exclude_contract = config.get("exclude_contract", True)

    all_jobs: list[dict] = []
    seen_ids: set[str] = set()

    def _merge(new_jobs: list[dict]):
        for job in new_jobs:
            if job["job_id"] not in seen_ids:
                seen_ids.add(job["job_id"])
                all_jobs.append(job)

    _merge(_scrape_adzuna(adzuna_queries, max_days, exclude_contract))
    _merge(_scrape_greenhouse(gh_companies, max_days, exclude_contract))

    logger.info(f"Scrape complete — {len(all_jobs)} unique job(s) from all sources")
    return all_jobs
