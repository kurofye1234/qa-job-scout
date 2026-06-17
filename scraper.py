"""
QA Job Scout v4 - Juan Estrada Edition
Railway Ready

Target Profile:
- QA Manual
- API Testing
- Postman
- SOAP / REST
- Jira
- Azure DevOps
- TestRail
- Remote LATAM
- Contractor Friendly
"""

import os
import re
import json
import hashlib
import logging
import smtplib
import urllib.request
import xml.etree.ElementTree as ET

from pathlib import Path
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------

GMAIL_USER     = os.getenv("GMAIL_USER", "")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD", "")
NOTIFY_EMAIL   = os.getenv("NOTIFY_EMAIL", "")
SEEN_FILE      = Path(os.getenv("SEEN_FILE", "/tmp/seen_jobs.json"))

MIN_HOURLY  = 20
MIN_MONTHLY = 3500
MIN_YEARLY  = 40000

# ------------------------------------------------------------------
# HTTP
# ------------------------------------------------------------------

try:
    import requests

    def http_get(url):
        r = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": "QAJobScout/4.0"}
        )
        r.raise_for_status()
        return r.text

except Exception:

    def http_get(url):
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "QAJobScout/4.0"}
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8")

# ------------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

log = logging.getLogger("qa_scout")

# ------------------------------------------------------------------
# FILTERS
# ------------------------------------------------------------------

TITLE_INCLUDE = [
    "qa",
    "quality assurance",
    "quality analyst",
    "quality engineer",
    "qa engineer",
    "qa analyst",
    "test engineer",
    "test analyst",
    "testing engineer",
    "software tester",
    "manual tester",
    "manual qa",
    "application tester",
    "qe"
]

TITLE_EXCLUDE = [
    "director",
    "head of",
    "vp",
    "manager",
    "frontend engineer",
    "backend engineer",
    "data engineer",
    "fullstack",
    "rater",
    "evaluator",
    "annotator",
    "reviewer",
    "translator",
    "german",
    "french",
    "language"
]

LOCATION_BLOCKLIST = [
    "germany",
    "australia",
    "india",
    "brazil",
    "philippines",
    "poland",
    "italy",
    "united kingdom",
    " uk ",
]

LOCATION_EXCLUDE = [
    "us only",
    "usa only",
    "canada only",
    "uk only",
    "security clearance",
    "remote in ca only",
    "remote in us only",
    "europe only",
    "emea only"
]

PROFILE_KEYWORDS = {
    "api testing": 12,
    "postman": 12,
    "manual testing": 12,
    "jira": 10,
    "azure devops": 10,
    "testrail": 10,
    "test case": 10,
    "test plan": 10,
    "bug report": 10,
    "rest": 8,
    "soap": 8,
    "regression": 8,
    "exploratory": 8,
    "functional testing": 8,
    "sql": 6,
    "playwright": 6,
    "selenium": 4,
    "agile": 4,
    "scrum": 4,
}

NEGATIVE_KEYWORDS = {
    "sdet": -20,
    "automation only": -20,
    "100% automation": -20,
}

CONTRACT_WORDS = [
    "contract",
    "contractor",
    "freelance",
    "1099",
    "independent contractor"
]

# ------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------

def jid(url):
    return hashlib.md5(url.encode()).hexdigest()

def load_seen():
    try:
        if SEEN_FILE.exists():
            return set(json.loads(SEEN_FILE.read_text()))
    except Exception as e:
        log.error(f"Error loading seen: {e}")
    return set()

def save_seen(seen):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(list(seen)))

def ok_title(title):
    t = title.lower()
    return (
        any(x in t for x in TITLE_INCLUDE)
        and not any(x in t for x in TITLE_EXCLUDE)
    )

def ok_location(location, desc):
    loc = (location or "").lower()
    desc_lower = (desc or "").lower()
    # Blocklist only against location field — not description
    if any(x in loc for x in LOCATION_BLOCKLIST):
        return False
    # Hard exclusions check both
    combined = f"{loc} {desc_lower}"
    if any(x in combined for x in LOCATION_EXCLUDE):
        return False
    return True

def extract_salary(text):
    text = (text or "").lower()

    # Hourly: $25/hr, $30/hour
    m = re.search(r'\$?(\d{2,3}(?:\.\d+)?)\s*(?:usd\s*)?(?:/hr|/hour|per hour)', text)
    if m:
        return {"type": "hourly", "amount": float(m.group(1))}

    # Monthly: $3,500/month, $4000/mo
    m = re.search(r'\$?([\d,]{3,6})\s*(?:usd\s*)?(?:/month|per month|monthly|/mo)', text)
    if m:
        return {"type": "monthly", "amount": float(m.group(1).replace(",", ""))}

    # Annual shorthand: 50k, 60k
    m = re.search(r'(\d{2,3})k', text)
    if m:
        return {"type": "yearly", "amount": float(m.group(1)) * 1000}

    # Annual explicit: $50,000/year
    m = re.search(r'\$?([\d,]{4,7})\s*(?:usd\s*)?(?:year|yearly|annual|annually)', text)
    if m:
        return {"type": "yearly", "amount": float(m.group(1).replace(",", ""))}

    return None

def salary_ok(salary):
    if salary is None:
        return True  # no salary info = include it
    if salary["type"] == "hourly":
        return salary["amount"] >= MIN_HOURLY
    if salary["type"] == "monthly":
        return salary["amount"] >= MIN_MONTHLY
    if salary["type"] == "yearly":
        return salary["amount"] >= MIN_YEARLY
    return True

def salary_label(salary):
    if salary is None:
        return "Salary not specified"
    if salary["type"] == "hourly":
        return f"~${salary['amount']:.0f}/hr"
    if salary["type"] == "monthly":
        return f"~${salary['amount']:,.0f}/mo"
    if salary["type"] == "yearly":
        return f"~${salary['amount']:,.0f}/yr (~${salary['amount']/2080:.0f}/hr)"
    return ""

def calculate_match(title, desc):
    text = f"{title} {desc}".lower()
    score = sum(v for k, v in PROFILE_KEYWORDS.items() if k in text)
    score += sum(v for k, v in NEGATIVE_KEYWORDS.items() if k in text)
    if any(x in text for x in CONTRACT_WORDS):
        score += 10
    if "senior" in text:
        score -= 3
    return max(0, min(score, 100))

def compatibility_bar(score):
    filled = round(score / 10)
    return "█" * filled + "░" * (10 - filled)

# ------------------------------------------------------------------
# RSS — FIXED: now returns jobs correctly
# ------------------------------------------------------------------

def parse_rss(xml_text, source):
    jobs = []
    try:
        root = ET.fromstring(xml_text)
        for item in root.findall(".//item"):
            title   = item.findtext("title", "")
            url     = item.findtext("link", "")
            desc    = item.findtext("description", "")
            company = item.findtext("author", "") or ""
            region  = item.findtext("region", "") or "Remote"
            # WeWorkRemotely format: "Company: Title"
            if ":" in title and source == "WeWorkRemotely":
                parts = title.split(":", 1)
                company, title = parts[0].strip(), parts[1].strip()
            jobs.append({
                "title": title, "company": company, "location": region,
                "url": url, "desc": desc, "salary": "", "source": source
            })
    except Exception as e:
        log.error(f"RSS PARSE ERROR [{source}]: {repr(e)}")
    return jobs  # ← BUG FIX: was missing return

# ------------------------------------------------------------------
# SOURCES
# ------------------------------------------------------------------

def fetch_remotive():
    log.info("Fetching Remotive...")
    try:
        data = json.loads(
            http_get("https://remotive.com/api/remote-jobs?category=qa&limit=100")
        )
        jobs = [
            {
                "title":    j.get("title", ""),
                "company":  j.get("company_name", ""),
                "location": j.get("candidate_required_location", ""),
                "url":      j.get("url", ""),
                "desc":     j.get("description", ""),
                "salary":   str(j.get("salary", "")),
                "source":   "Remotive"
            }
            for j in data.get("jobs", [])
        ]
        log.info(f"Remotive: {len(jobs)} jobs")
        return jobs
    except Exception as e:
        log.error(f"Remotive error: {e}")
        return []

def fetch_himalayas():
    log.info("Fetching Himalayas...")
    try:
        data = json.loads(
            http_get("https://himalayas.app/jobs/api?categories=quality-assurance&limit=100")
        )
        jobs = []
        for j in data.get("jobs", []):
            location = j.get("locationRestrictions", [])
            loc_str = ", ".join(location) if location else "Worldwide"
            jobs.append({
                "title":    j.get("title", ""),
                "company":  j.get("companyName", "") or j.get("company", {}).get("name", ""),
                "location": loc_str,
                "url":      j.get("applicationLink", "") or j.get("url", ""),
                "desc":     j.get("description", ""),
                "salary":   "",
                "source":   "Himalayas"
            })
        log.info(f"Himalayas: {len(jobs)} jobs")
        return jobs
    except Exception as e:
        log.error(f"Himalayas error: {e}")
        return []

def fetch_arbeitnow():
    log.info("Fetching Arbeitnow...")
    try:
        data = json.loads(
            http_get("https://www.arbeitnow.com/api/job-board-api")
        )
        jobs = []
        for j in data.get("data", []):
            title = j.get("title", "")
            if not any(x in title.lower() for x in ["qa", "quality", "tester", "test"]):
                continue
            jobs.append({
                "title":    title,
                "company":  j.get("company_name", ""),
                "location": j.get("location", "Remote"),
                "url":      j.get("url", ""),
                "desc":     j.get("description", ""),
                "salary":   "",
                "source":   "Arbeitnow"
            })
        log.info(f"Arbeitnow: {len(jobs)} jobs")
        return jobs
    except Exception as e:
        log.error(f"Arbeitnow error: {e}")
        return []

def fetch_remoteok():
    log.info("Fetching RemoteOK...")
    try:
        data = json.loads(http_get("https://remoteok.com/api"))
        jobs = []
        for j in data:
            if not isinstance(j, dict):
                continue
            jobs.append({
                "title":    j.get("position", ""),
                "company":  j.get("company", ""),
                "location": j.get("location", "Remote"),
                "url":      j.get("url", ""),
                "desc":     " ".join(j.get("tags", [])),
                "salary":   "",
                "source":   "RemoteOK"
            })
        log.info(f"RemoteOK: {len(jobs)} jobs")
        return jobs
    except Exception as e:
        log.error(f"RemoteOK error: {e}")
        return []

def fetch_jobicy():
    log.info("Fetching Jobicy...")
    try:
        data = json.loads(
            http_get("https://jobicy.com/api/v2/remote-jobs?tag=qa&count=50")
        )
        jobs = [
            {
                "title":    j.get("jobTitle", ""),
                "company":  j.get("companyName", ""),
                "location": j.get("jobGeo", ""),
                "url":      j.get("url", ""),
                "desc":     j.get("jobDescription", ""),
                "salary":   "",
                "source":   "Jobicy"
            }
            for j in data.get("jobs", [])
        ]
        log.info(f"Jobicy: {len(jobs)} jobs")
        return jobs
    except Exception as e:
        log.error(f"Jobicy error: {e}")
        return []

def fetch_rss():
    log.info("Fetching RSS feeds...")
    feeds = [
        ("https://remotive.com/remote-jobs/qa/feed", "Remotive RSS"),
        ("https://weworkremotely.com/categories/remote-programming-jobs.rss", "WeWorkRemotely"),
    ]
    jobs = []
    for url, source in feeds:
        try:
            rss_jobs = parse_rss(http_get(url), source)
            log.info(f"{source}: {len(rss_jobs)} jobs")
            jobs.extend(rss_jobs)
        except Exception as e:
            log.error(f"RSS error [{source}]: {repr(e)}")
    return jobs  # ← BUG FIX: was inside the loop before

# ------------------------------------------------------------------
# PIPELINE
# ------------------------------------------------------------------

def filter_jobs(raw, seen):
    results = []
    for j in raw:
        url = j.get("url", "")
        if not url:
            continue
        job_id = jid(url)
        if job_id in seen:
            continue
        if not ok_title(j.get("title", "")):
            continue
        if not ok_location(j.get("location", ""), j.get("desc", "")):
            continue
        salary = extract_salary(str(j.get("salary", "")) + " " + j.get("desc", ""))
        if not salary_ok(salary):
            continue
        match = calculate_match(j.get("title", ""), j.get("desc", ""))
        results.append({
            "id":       job_id,
            "title":    j["title"],
            "company":  j.get("company", ""),
            "location": j.get("location", "Remote"),
            "url":      url,
            "source":   j.get("source", ""),
            "match":    match,
            "salary":   salary
        })
    results.sort(key=lambda x: x["match"], reverse=True)
    return results[:15]

# ------------------------------------------------------------------
# EMAIL
# ------------------------------------------------------------------

def build_html(jobs, run_date):
    if not jobs:
        body = "<p style='color:#666;font-size:14px;'>No new matching jobs today. Script is running fine!</p>"
    else:
        cards = ""
        for j in jobs:
            bar = compatibility_bar(j["match"])
            cards += f"""
            <div style="border:1px solid #dde3ea;border-radius:8px;padding:16px 20px;margin-bottom:12px;background:#fff;">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;margin-bottom:8px;">
                <div>
                  <div style="font-size:15px;font-weight:600;color:#111;">{j['title']}</div>
                  <div style="font-size:13px;color:#1F5C99;margin-top:2px;">{j['company']}</div>
                </div>
                <a href="{j['url']}" style="background:#1F5C99;color:#fff;padding:6px 14px;border-radius:6px;text-decoration:none;font-size:12px;font-weight:500;white-space:nowrap;">Apply ↗</a>
              </div>
              <div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px;">
                <span style="background:#EAF3DE;color:#27500A;font-size:11px;padding:2px 8px;border-radius:99px;">{j['location']}</span>
                <span style="background:#E6F1FB;color:#0C447C;font-size:11px;padding:2px 8px;border-radius:99px;">{j['source']}</span>
                <span style="background:#FAEEDA;color:#633806;font-size:11px;padding:2px 8px;border-radius:99px;">{salary_label(j['salary'])}</span>
              </div>
              <div style="font-size:11px;color:#aaa;font-family:monospace;">Match: {bar} {j['match']}pts</div>
            </div>"""
        body = f"<p style='color:#555;font-size:14px;margin-bottom:16px;'><strong>{len(jobs)} new jobs</strong> matching your QA profile today.</p>" + cards

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#F4F6F9;font-family:Arial,sans-serif;">
<div style="max-width:620px;margin:28px auto;padding:0 12px 28px;">
  <div style="background:#1F5C99;border-radius:10px 10px 0 0;padding:20px 24px;">
    <div style="color:#fff;font-size:20px;font-weight:700;">🚀 QA Job Scout</div>
    <div style="color:#bdd6f0;font-size:12px;margin-top:3px;">{run_date} · Daily digest for Juan Estrada</div>
  </div>
  <div style="background:#fff;border-radius:0 0 10px 10px;padding:20px 24px;">
    <div style="font-size:11px;color:#aaa;margin-bottom:16px;">
      Filters: QA Manual · Jr/Middle · LATAM or Worldwide · $20+/hr<br>
      Sources: Remotive · Himalayas · Arbeitnow · RemoteOK · WeWorkRemotely
    </div>
    {body}
    <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
    <p style="font-size:11px;color:#ccc;text-align:center;">QA Job Scout v4 · Railway · Built for Juan Estrada</p>
  </div>
</div></body></html>"""

def send_email(jobs, run_date):
    log.info(f"GMAIL_USER set: {'YES' if GMAIL_USER else 'NO'}")
    log.info(f"GMAIL_PASSWORD set: {'YES' if GMAIL_PASSWORD else 'NO'}")
    log.info(f"NOTIFY_EMAIL set: {'YES' if NOTIFY_EMAIL else 'NO'}")
    if not (GMAIL_USER and GMAIL_PASSWORD and NOTIFY_EMAIL):
        log.warning("Missing credentials — skipping email.")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🚀 QA Scout: {len(jobs)} job(s) — {run_date}"
    msg["From"]    = GMAIL_USER
    msg["To"]      = NOTIFY_EMAIL
    msg.attach(MIMEText(build_html(jobs, run_date), "html"))
    try:
        log.info("Connecting to Gmail SMTP...")
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as s:
            s.ehlo()
            s.starttls()
            s.ehlo()
            s.login(GMAIL_USER, GMAIL_PASSWORD)
            s.sendmail(GMAIL_USER, NOTIFY_EMAIL, msg.as_string())
        log.info(f"✓ Email sent to {NOTIFY_EMAIL}")
    except Exception as e:
        log.error(f"Email failed: {repr(e)}")

# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------

def main():
    run_date = datetime.now(timezone.utc).strftime("%B %d, %Y")
    log.info(f"=== QA Job Scout v4 — {run_date} ===")

    seen = load_seen()

    log.info("Fetching all sources...")
    raw = (
        fetch_remotive()
        + fetch_himalayas()
        + fetch_arbeitnow()
        + fetch_remoteok()
        + fetch_jobicy()
        + fetch_rss()
    )
    log.info(f"Total raw jobs: {len(raw)}")

    jobs = filter_jobs(raw, seen)
    log.info(f"Matched jobs: {len(jobs)}")

    for j in jobs:
        log.info(f"  ✓ [{j['match']}pts] {j['title']} | {j['company']} | {j['location']}")

    send_email(jobs, run_date)

    for j in jobs:
        seen.add(j["id"])
    save_seen(seen)

    log.info("Done ✓")
    log.info("Hola soy nueva version  ✓")

if __name__ == "__main__":
    main()