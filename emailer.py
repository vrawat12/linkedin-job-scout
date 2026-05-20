import base64
import logging
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

_SECTION_LABELS = {
    "must_apply": "Must Apply",
    "strong_fit": "Strong Fit",
    "ai_opportunity": "AI Role",
    "worth_monitoring": "Monitoring",
}


def _get_service():
    creds = None
    if Path(TOKEN_FILE).exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        Path(TOKEN_FILE).write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


# ── Badge helpers ─────────────────────────────────────────────────────────────

def _score_badge(score: int) -> str:
    color = "#16a34a" if score >= 8 else ("#d97706" if score >= 6 else "#dc2626")
    return (
        f'<span style="background:{color};color:#fff;padding:3px 11px;'
        f'border-radius:12px;font-size:13px;font-weight:700;">{score}/10</span>'
    )


def _urgency_badge(applicants) -> str:
    """Red badge for <5 applicants, orange for 5-20, else None."""
    if applicants is None:
        return ""
    n = int(applicants)
    if n < 5:
        return (
            '<span style="background:#dc2626;color:#fff;padding:3px 9px;'
            'border-radius:12px;font-size:11px;font-weight:700;margin-left:6px;">'
            '&#9889; &lt;5 applicants</span>'
        )
    if n < 20:
        return (
            '<span style="background:#d97706;color:#fff;padding:3px 9px;'
            'border-radius:12px;font-size:11px;font-weight:700;margin-left:6px;">'
            f'&#9888; {n} applicants</span>'
        )
    return ""


def _ai_badge() -> str:
    return (
        '<span style="background:#7c3aed;color:#fff;padding:3px 9px;'
        'border-radius:12px;font-size:11px;font-weight:700;margin-left:6px;">'
        '&#9889; AI Opportunity</span>'
    )


def _also_in_badge(section: str) -> str:
    label = _SECTION_LABELS.get(section, "")
    if not label:
        return ""
    return (
        f'<span style="background:#f3f4f6;color:#374151;padding:3px 9px;'
        f'border-radius:12px;font-size:11px;font-weight:600;margin-left:6px;">'
        f'Also in {label}</span>'
    )


def _pills(tags: list[str], bg: str, fg: str) -> str:
    if not tags:
        return ""
    pills = "".join(
        f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:10px;'
        f'font-size:12px;margin:2px 2px 0 0;display:inline-block;">{t}</span>'
        for t in tags
    )
    return f'<div style="margin-top:8px;line-height:1.8;">{pills}</div>'


def _bullet_list(items: list[str], color: str = "#374151") -> str:
    if not items:
        return ""
    lis = "".join(
        f'<li style="margin-bottom:4px;color:{color};">{item}</li>'
        for item in items
    )
    return f'<ul style="margin:4px 0 0 0;padding-left:18px;font-size:13px;line-height:1.55;">{lis}</ul>'


def _fit_summary(job: dict, max_alignment: int = 2, max_gaps: int = 1) -> str:
    alignment = job.get("alignment", [])[:max_alignment]
    gaps = job.get("gaps", [])[:max_gaps]
    if not alignment and not gaps:
        return ""

    alignment_html = _bullet_list(alignment, "#166534") if alignment else (
        "<p style='font-size:13px;color:#6b7280;margin:4px 0;'>—</p>"
    )
    gaps_html = _bullet_list(gaps, "#991b1b") if gaps else (
        "<p style='font-size:13px;color:#6b7280;margin:4px 0;'>No significant gaps identified.</p>"
    )

    return f"""
<div style="margin-top:14px;border-top:1px solid #f3f4f6;padding-top:12px;">
  <div style="font-size:12px;font-weight:700;color:#374151;letter-spacing:.05em;
              text-transform:uppercase;margin-bottom:8px;">Fit Summary</div>
  <table width="100%" cellpadding="0" cellspacing="0"><tr valign="top">
    <td width="50%" style="padding-right:12px;">
      <div style="font-size:12px;font-weight:600;color:#166534;margin-bottom:2px;">&#10003; Alignment</div>
      {alignment_html}
    </td>
    <td width="50%" style="padding-left:12px;border-left:1px solid #f3f4f6;">
      <div style="font-size:12px;font-weight:600;color:#991b1b;margin-bottom:2px;">&#9651; Gaps</div>
      {gaps_html}
    </td>
  </tr></table>
</div>"""


# ── Job cards ─────────────────────────────────────────────────────────────────

def _full_card(job: dict, show_ai_badge: bool = True, also_in: str = "") -> str:
    title = job.get("title", "Unknown Title")
    company = job.get("company", "")
    location = job.get("location", "")
    score = job.get("score", 0)
    rationale = job.get("rationale", "")
    match_tags = job.get("match_tags", [])
    red_flags = job.get("red_flags", [])
    ai_opportunity = job.get("ai_opportunity", False)
    applicants = job.get("applicant_count")
    posted_date = str(job.get("posted_date", ""))
    if "T" in posted_date:
        posted_date = posted_date.split("T")[0]
    job_url = job.get("job_url", "#")

    meta_parts = []
    if applicants:
        meta_parts.append(f"{applicants} applicants")
    if posted_date:
        meta_parts.append(f"Posted {posted_date}")
    meta = " &middot; ".join(meta_parts)

    ai_badge_html = _ai_badge() if (ai_opportunity and show_ai_badge) else ""
    urgency_html = _urgency_badge(applicants)
    also_in_html = _also_in_badge(also_in) if also_in else ""
    red_flag_html = _pills(red_flags, "#fee2e2", "#991b1b") if red_flags else ""

    return f"""
<div style="background:#fff;border:1px solid #e5e7eb;border-radius:8px;
            padding:20px 24px;margin-bottom:16px;
            font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0"><tr>
    <td>
      <div style="font-size:17px;font-weight:700;color:#111827;">
        {title}{ai_badge_html}{urgency_html}{also_in_html}
      </div>
      <div style="font-size:13px;color:#6b7280;margin-top:3px;">{company} &middot; {location}</div>
    </td>
    <td align="right" valign="top" style="white-space:nowrap;padding-left:12px;">
      {_score_badge(score)}
    </td>
  </tr></table>
  <div style="font-size:14px;color:#374151;margin-top:10px;line-height:1.55;">{rationale}</div>
  {_pills(match_tags, "#dbeafe", "#1e40af")}
  {red_flag_html}
  {_fit_summary(job)}
  <div style="font-size:12px;color:#9ca3af;margin-top:10px;">{meta}</div>
  <div style="margin-top:14px;">
    <a href="{job_url}"
       style="background:#0a66c2;color:#fff;text-decoration:none;
              padding:8px 16px;border-radius:6px;font-size:13px;font-weight:600;">
      View Job &rarr;
    </a>
  </div>
</div>"""


def _minimal_card(job: dict) -> str:
    title = job.get("title", "Unknown Title")
    company = job.get("company", "")
    score = job.get("score", 0)
    ai_opportunity = job.get("ai_opportunity", False)
    job_url = job.get("job_url", "#")
    ai_badge_html = _ai_badge() if ai_opportunity else ""

    return f"""
<div style="background:#fff;border:1px solid #e5e7eb;border-radius:6px;
            padding:12px 16px;margin-bottom:8px;
            font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0"><tr>
    <td>
      <span style="font-size:14px;font-weight:600;color:#111827;">{title}</span>
      {ai_badge_html}
      <span style="font-size:13px;color:#6b7280;margin-left:8px;">{company}</span>
    </td>
    <td align="right" style="white-space:nowrap;padding-left:12px;">
      {_score_badge(score)}
      &nbsp;
      <a href="{job_url}"
         style="color:#0a66c2;font-size:12px;font-weight:600;text-decoration:none;">
        View &rarr;
      </a>
    </td>
  </tr></table>
</div>"""


# ── Section renderers ─────────────────────────────────────────────────────────

def _section_header(title: str, count: int, accent: str) -> str:
    if count == 0:
        return ""
    return f"""
<div style="margin:28px 0 12px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="display:inline-block;background:{accent};color:#fff;
              padding:4px 14px;border-radius:4px 4px 0 0;
              font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;">
    {title}
  </div>
  <div style="font-size:12px;color:#6b7280;display:inline-block;margin-left:10px;">
    {count} role{"s" if count != 1 else ""}
  </div>
</div>"""


def _market_intel_box(bullets: list[str]) -> str:
    if not bullets:
        return ""
    items = "".join(
        f'<li style="margin-bottom:8px;color:#374151;font-size:13px;line-height:1.55;">{b}</li>'
        for b in bullets
    )
    return f"""
<div style="background:#f8fafc;border:1px solid #e2e8f0;border-left:4px solid #0a66c2;
            border-radius:6px;padding:18px 20px;margin-top:28px;
            font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="font-size:11px;font-weight:700;color:#0a66c2;letter-spacing:.08em;
              text-transform:uppercase;margin-bottom:10px;">Market Intelligence</div>
  <ul style="margin:0;padding-left:18px;line-height:1.6;">
    {items}
  </ul>
</div>"""


def _summary_bar(digest: dict) -> str:
    counts = [
        ("Must Apply", len(digest.get("must_apply", [])), "#dc2626"),
        ("Strong Fit", len(digest.get("strong_fit", [])), "#16a34a"),
        ("AI Roles", len(digest.get("ai_opportunity", [])), "#7c3aed"),
        ("Monitoring", len(digest.get("worth_monitoring", [])), "#6b7280"),
    ]
    cells = "".join(
        f'<td style="text-align:center;padding:0 20px;border-right:1px solid #e5e7eb;">'
        f'<div style="font-size:22px;font-weight:700;color:{color};">{count}</div>'
        f'<div style="font-size:11px;color:#6b7280;text-transform:uppercase;'
        f'letter-spacing:.06em;margin-top:2px;">{label}</div></td>'
        for label, count, color in counts
    )
    # Remove right border from last cell via inline style override
    cells = cells.rsplit('border-right:1px solid #e5e7eb;', 1)
    cells = ''.join(cells)

    return f"""
<div style="background:#fff;border:1px solid #e5e7eb;border-radius:6px;
            padding:16px 0;margin:16px 0;
            font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0"><tr>
    {cells}
  </tr></table>
</div>"""


# ── HTML builder ──────────────────────────────────────────────────────────────

def _build_html(digest: dict, total_jobs: int, captcha_warning: bool) -> str:
    date_str = datetime.now().strftime("%B %d, %Y")
    primary_section = digest.get("_primary_section", {})

    must_apply = digest.get("must_apply", [])
    strong_fit = digest.get("strong_fit", [])
    ai_opportunity = digest.get("ai_opportunity", [])
    worth_monitoring = digest.get("worth_monitoring", [])
    market_intel = digest.get("market_intelligence", [])

    # Section 1: Must Apply
    s1 = _section_header("Must Apply This Week", len(must_apply), "#dc2626")
    s1 += "".join(_full_card(j, show_ai_badge=True) for j in must_apply)

    # Section 2: Strong Fit
    s2 = _section_header("Strong Fit — Apply Soon", len(strong_fit), "#16a34a")
    s2 += "".join(_full_card(j, show_ai_badge=True) for j in strong_fit)

    # Section 3: AI Opportunity — all AI jobs, note if also in s1/s2
    s3 = _section_header("AI Opportunity Roles", len(ai_opportunity), "#7c3aed")
    for j in ai_opportunity:
        ps = primary_section.get(j["job_id"], "")
        also_in = ps if ps in ("must_apply", "strong_fit") else ""
        s3 += _full_card(j, show_ai_badge=False, also_in=also_in)

    # Section 4: Worth Monitoring — jobs NOT already in s1/s2/s3
    ai_ids = {j["job_id"] for j in ai_opportunity}
    priority_ids = {j["job_id"] for j in must_apply + strong_fit}
    monitoring_only = [
        j for j in worth_monitoring
        if j["job_id"] not in ai_ids and j["job_id"] not in priority_ids
    ]
    s4 = _section_header("Worth Monitoring", len(monitoring_only), "#6b7280")
    s4 += "".join(_minimal_card(j) for j in monitoring_only)

    # Section 5: Market Intelligence
    s5 = _market_intel_box(market_intel)

    warning_html = ""
    if captcha_warning:
        warning_html = (
            '<p style="font-size:12px;color:#d97706;margin-top:8px;">'
            "&#9888; Scraper hit rate limits during this run — results may be partial.</p>"
        )

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="background:#f3f4f6;margin:0;padding:24px;">
<div style="max-width:680px;margin:0 auto;">

  <div style="background:#0a66c2;color:#fff;padding:20px 24px;border-radius:8px 8px 0 0;">
    <div style="font-size:20px;font-weight:700;">&#127919; Job Scout</div>
    <div style="font-size:13px;opacity:.85;margin-top:4px;">
      {date_str} &middot; {total_jobs} new match{"es" if total_jobs != 1 else ""}
    </div>
  </div>

  {_summary_bar(digest)}

  <div style="padding:4px 0;">
    {s1}{s2}{s3}{s4}{s5}
  </div>

  {warning_html}
  <p style="font-size:11px;color:#9ca3af;text-align:center;margin-top:20px;">
    Sent by Job Scout &middot; Powered by Claude AI
  </p>

</div>
</body></html>"""


# ── Public API ────────────────────────────────────────────────────────────────

def send_digest(
    digest: dict,
    total_jobs: int,
    recipient_email: str,
    send_no_match_email: bool = False,
    has_captcha_warning: bool = False,
) -> dict:
    if total_jobs == 0 and not send_no_match_email:
        logger.info("No new matches and send_no_match_email=false — skipping email")
        return {"sent": False, "reason": "no_matches"}

    try:
        service = _get_service()
    except Exception as exc:
        logger.error(f"Gmail auth failed: {exc}")
        return {"sent": False, "error": str(exc)}

    date_str = datetime.now().strftime("%b %d")
    n = total_jobs
    subject = f"\U0001f3af Job Scout — {date_str} — {n} new match{'es' if n != 1 else ''}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["To"] = recipient_email
    msg["From"] = "me"
    msg.attach(MIMEText(_build_html(digest, n, has_captcha_warning), "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    try:
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        logger.info(f"Email sent to {recipient_email}: {subject}")
        return {"sent": True}
    except HttpError as exc:
        logger.error(f"Gmail send failed: {exc}")
        return {"sent": False, "error": str(exc)}


def send_resumes(
    docs: list[dict],
    recipient_email: str,
) -> dict:
    """
    Send tailored resume .docx files as email attachments.

    Each entry in docs:
        path       Path   — absolute path to the .docx file
        company    str
        title      str
        role_type  str
        score      int
    """
    if not docs:
        logger.info("No resume docs to send")
        return {"sent": False, "reason": "no_docs"}

    try:
        service = _get_service()
    except Exception as exc:
        logger.error(f"Gmail auth failed: {exc}")
        return {"sent": False, "error": str(exc)}

    date_str = datetime.now().strftime("%b %d, %Y")
    n = len(docs)
    subject = f"Tailored Resumes — {n} doc{'s' if n != 1 else ''} ({date_str})"

    # ── HTML body — summary table ─────────────────────────────────────────────
    rows = "".join(
        f'<tr>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">'
        f'<strong>{d["company"]}</strong></td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;color:#374151;">'
        f'{d["title"]}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;white-space:nowrap;">'
        f'<span style="background:#dbeafe;color:#1e40af;padding:2px 8px;border-radius:10px;'
        f'font-size:12px;">{d["role_type"]}</span></td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;white-space:nowrap;">'
        f'<span style="background:#16a34a;color:#fff;padding:2px 8px;border-radius:10px;'
        f'font-size:12px;">{d["score"]}/10</span></td>'
        f'</tr>'
        for d in docs
    )
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="background:#f3f4f6;margin:0;padding:24px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:680px;margin:0 auto;">
  <div style="background:#1B3A6B;color:#fff;padding:20px 24px;border-radius:8px 8px 0 0;">
    <div style="font-size:18px;font-weight:700;">Resume Tailoring Complete</div>
    <div style="font-size:13px;opacity:.85;margin-top:4px;">
      {date_str} &middot; {n} tailored doc{'s' if n != 1 else ''} attached
    </div>
  </div>
  <div style="background:#fff;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 8px 8px;padding:8px 0;">
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
      <thead>
        <tr style="background:#f9fafb;">
          <th style="padding:10px 12px;text-align:left;font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid #e5e7eb;">Company</th>
          <th style="padding:10px 12px;text-align:left;font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid #e5e7eb;">Role</th>
          <th style="padding:10px 12px;text-align:left;font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid #e5e7eb;">Type</th>
          <th style="padding:10px 12px;text-align:left;font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid #e5e7eb;">Score</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
  <p style="font-size:11px;color:#9ca3af;text-align:center;margin-top:16px;">
    Sent by Job Scout &middot; Review each doc before submitting
  </p>
</div>
</body></html>"""

    # ── Assemble multipart message with attachments ────────────────────────────
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["To"] = recipient_email
    msg["From"] = "me"
    msg.attach(MIMEText(html, "html"))

    missing = []
    for d in docs:
        p = Path(d["path"])
        if not p.exists():
            logger.warning(f"Attachment not found, skipping: {p}")
            missing.append(str(p))
            continue
        with open(p, "rb") as f:
            part = MIMEApplication(f.read(), Name=p.name)
        part["Content-Disposition"] = f'attachment; filename="{p.name}"'
        msg.attach(part)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    try:
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        logger.info(f"Resumes emailed to {recipient_email}: {subject}")
        if missing:
            logger.warning(f"Skipped {len(missing)} missing attachment(s): {missing}")
        return {"sent": True, "attachments": n - len(missing)}
    except HttpError as exc:
        logger.error(f"Gmail send failed: {exc}")
        return {"sent": False, "error": str(exc)}
