"""
QA Job Scout v3 - Juan Estrada Edition
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

This file is intended as a production starter.
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

GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD", "")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL", "")
SEEN_FILE = Path(os.getenv("SEEN_FILE", "/data/seen_jobs.json"))

MIN_HOURLY = 20
MIN_MONTHLY = 3500
MIN_YEARLY = 40000

# ------------------------------------------------------------------
# HTTP
# ------------------------------------------------------------------

try:
    import requests

    def http_get(url):
        r = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": "QAJobScout/3.0"}
        )
        r.raise_for_status()
        return r.text

except Exception:

    def http_get(url):
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "QAJobScout/3.0"}
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
    "quality",
    "tester",
    "quality assurance",
    "quality engineer",
    "qa engineer",
    "qa analyst",
    "quality analyst",
    "test engineer",
    "test analyst",
    "testing engineer",
    "testing analyst",
    "software tester",
    "software testing",
    "manual tester",
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
    "fullstack"
    "rater",

    "evaluator",
    "annotator",
    "reviewer",
    "translator",
    "german",
    "french",
    "spanish",
    "language"
]

LOCATION_EXCLUDE = [
    "us only",
    "usa only",
    "canada only",
    "uk only",
    "security clearance"
    "germany",
    "german",
    "france",
    "french",
    "italy",
    "italian",
    "spain",
    "spain only",
    "europe only",
    "emea"
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
    "uk",
]

ALLOWED_LOCATIONS = [
    "remote",
    "worldwide",
    "latin america",
    "latam",
    "mexico",
    "mexican",
    "global"
]

PROFILE_KEYWORDS = {
    "api testing": 12,
    "postman": 12,
    "manual testing": 12,
    "jira": 10,
    "azure devops": 10,
    "testrail": 10,
    "rest": 8,
    "soap": 8,
    "regression": 8,
    "exploratory": 8,
    "functional testing": 8,
    "sql": 6,
    "agile": 4,
    "scrum": 4,
}

NEGATIVE_KEYWORDS = {
    "sdet": -20,
    "automation only": -20,
    "100% automation": -20,
    "cypress": -10,
    "selenium": -5,
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
    	log.error(f"RSS error in {source}: {e}")
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

    text = f"{location} {desc}".lower()
    if any(x in text for x in LOCATION_BLOCKLIST):

        return False
    return True

def extract_salary(text):

    text = (text or "").lower()

    # -------------------------
    # Hourly
    # -------------------------

    m = re.search(
        r'\$?(\d{2,3}(?:\.\d+)?)\s*(?:usd\s*)?(?:/hr|/hour|per hour)',
        text
    )

    if m:
        return {
            "type": "hourly",
            "amount": float(m.group(1))
        }

    # -------------------------
    # Monthly
    # -------------------------

    m = re.search(
        r'\$?([\d,]{3,6})\s*(?:usd\s*)?(?:/month|per month|monthly|/mo)',
        text
    )

    if m:
        return {
            "type": "monthly",
            "amount": float(
                m.group(1).replace(",", "")
            )
        }

    # -------------------------
    # Annual (40k, 50k, etc)
    # -------------------------

    m = re.search(
        r'(\d{2,3})k',
        text
    )

    if m:
        return {
            "type": "yearly",
            "amount": float(m.group(1)) * 1000
        }

    # -------------------------
    # Annual ($40,000)
    # -------------------------

    m = re.search(
        r'\$?([\d,]{4,7})\s*(?:usd\s*)?(?:year|yearly|annual|annually)',
        text
    )

    if m:
        return {
            "type": "yearly",
            "amount": float(
                m.group(1).replace(",", "")
            )
        }

    return None

def salary_ok(salary):

    if salary is None:
        return True

    if salary["type"] == "hourly":
        return salary["amount"] >= MIN_HOURLY

    if salary["type"] == "monthly":
        return salary["amount"] >= MIN_MONTHLY

    if salary["type"] == "yearly":
        return salary["amount"] >= MIN_YEARLY

    return True


def calculate_match(title, desc):
    text = f"{title} {desc}".lower()

    score = 0

    for k, v in PROFILE_KEYWORDS.items():
        if k in text:
            score += v

    for k, v in NEGATIVE_KEYWORDS.items():
        if k in text:
            score += v

    if any(x in text for x in CONTRACT_WORDS):
        score += 10

    if "senior" in text:
        score -= 5

    return max(0, min(score, 100))

def compatibility_bar(score):
    blocks = round(score / 10)
    return "#" * blocks + "#" * (10 - blocks)

# ------------------------------------------------------------------
# RSS
# ------------------------------------------------------------------

def parse_rss(xml_text, source):

    jobs = []

    try:
        root = ET.fromstring(xml_text)

        for item in root.findall(".//item"):

            jobs.append({
                "title": item.findtext("title", ""),
                "url": item.findtext("link", ""),
                "desc": item.findtext("description", ""),
                "company": "",
                "location": "Remote",
                "salary": "",
                "source": source
            })

    except Exception as e:
        log.error(

            f"RSS PARSE ERROR [{source}]: {repr(e)}"

        )

        return []

# ------------------------------------------------------------------
# SOURCES
# ------------------------------------------------------------------


def fetch_remoteok():
    try:
        data = json.loads(
            http_get("https://remoteok.com/api")
        )

        jobs = []

        for j in data:

            if not isinstance(j, dict):
                continue

            jobs.append({
                "title": j.get("position", ""),
                "company": j.get("company", ""),
                "location": j.get("location", "Remote"),
                "url": j.get("url", ""),
                "desc": " ".join(j.get("tags", [])),
                "salary": "",
                "source": "RemoteOK"
            })

        return jobs

    except Exception as e:
        log.error(f"RemoteOK error: {e}")
        return []

def fetch_remotive():
    try:
        data = json.loads(
            http_get(
                "https://remotive.com/api/remote-jobs?category=qa&limit=100"
            )
        )

        return [
            {
                "title": j.get("title", ""),
                "company": j.get("company_name", ""),
                "location": j.get("candidate_required_location", ""),
                "url": j.get("url", ""),
                "desc": j.get("description", ""),
                "salary": str(j.get("salary", "")),
                "source": "Remotive"
            }
            for j in data.get("jobs", [])
        ]

    except Exception:
        return []

def fetch_jobicy():
    try:
        data = json.loads(
            http_get(
                "https://jobicy.com/api/v2/remote-jobs?tag=qa&count=50"
            )
        )

        return [
            {
                "title": j.get("jobTitle", ""),
                "company": j.get("companyName", ""),
                "location": j.get("jobGeo", ""),
                "url": j.get("url", ""),
                "desc": j.get("jobDescription", ""),
                "salary": "",
                "source": "Jobicy"
            }
            for j in data.get("jobs", [])
        ]

    except Exception:
        return []

def fetch_rss():
    feeds = [
        ("https://remotive.com/remote-jobs/qa/feed", "Remotive RSS"),
        ("https://weworkremotely.com/categories/remote-programming-jobs.rss", "WeWorkRemotely"),
        ("https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss", "WeWorkRemotely"),
        ("https://jobicy.com/feed/remote-jobs", "Jobicy RSS"),
    ]

    jobs = []

    for url, source in feeds:
        try:
            log.info(f"Loading RSS: {source}")
            rss_jobs = parse_rss(
                http_get(url),
                source
            )
            log.info(
                f"{source} returned {len(rss_jobs)} jobs"
            )
            jobs.extend(rss_jobs)
        except Exception as e:
            log.error(
                f"RSS ERROR [{source}]: {repr(e)}")
        return jobs

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
            log.info(f"REJECT TITLE: {j.get('title','')}")
            continue
        log.info(f"PASSED TITLE FILTER: {j.get('title','')}")

        if not ok_location(
            j.get("location", ""),
            j.get("desc", "")
        ):
            continue

        salary = extract_salary(
            str(j.get("salary", ""))
            + " "
            + j.get("desc", "")
        )

        if not salary_ok(salary):
            continue

        match = calculate_match(
            j.get("title", ""),
            j.get("desc", "")
        )

        results.append({
            "id": job_id,
            "title": j["title"],
            "company": j.get("company", ""),
            "location": j.get("location", "Remote"),
            "url": url,
            "source": j.get("source", ""),
            "match": match,
            "salary": salary
        })

    results.sort(
        key=lambda x: x["match"],
        reverse=True
    )

    return results[:10]

# ------------------------------------------------------------------
# EMAIL
# ------------------------------------------------------------------

def build_html(jobs):

    cards = ""

    for job in jobs:

        cards += f"""
        <div style='border:1px solid #ddd;padding:12px;margin-bottom:10px'>
            <h3>{job['title']}</h3>
            <p>{job['company']}</p>
            <p>Match: {job['match']}%</p>
            <p>{compatibility_bar(job['match'])}</p>
            <a href="{job['url']}">Apply</a>
        </div>
        """

    return f"<html><body><h2>QA Job Scout</h2>{cards}</body></html>"

def send_email(jobs):

    log.info("send_email() entered")

    if not (GMAIL_USER and GMAIL_PASSWORD and NOTIFY_EMAIL):
        log.info("Email disabled - missing env vars")
        return

    log.info("Creating message")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"QA Scout - {len(jobs)} jobs"
    msg["From"] = GMAIL_USER
    msg["To"] = NOTIFY_EMAIL

    msg.attach(MIMEText(build_html(jobs), "html"))

    try:
        log.info("Connecting to Gmail SMTP")

        with smtplib.SMTP_SSL(
            "smtp.gmail.com",
            465,
            timeout=15
        ) as s:

            log.info("Connected")
            s.login(GMAIL_USER, GMAIL_PASSWORD)

            log.info("Logged in")
            s.sendmail(
                GMAIL_USER,
                NOTIFY_EMAIL,
                msg.as_string()
            )

            log.info("Email sent")

    except Exception as e:
        log.error(f"EMAIL ERROR: {repr(e)}")

# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------

def main():

    seen = load_seen()

    log.info("Starting Remotive...")
    r1 = fetch_remotive()
    log.info(f"Remotive returned {len(r1)} jobs")
    log.info("Starting Jobicy...")
    r2 = fetch_jobicy()
    log.info(f"Jobicy returned {len(r2)} jobs")
    log.info("Starting RSS...")
    r3 = fetch_rss()
    log.info(f"RSS returned {len(r3)} jobs")

    log.info("Starting RemoteOK...")
    r4 = fetch_remoteok()
    log.info(f"RemoteOK returned {len(r4)} jobs")

    raw = r1 + r2 + r3 + r4

    log.info("Filtering jobs...")

    for j in raw:
    	log.info(f"RAW: {j.get('title','')} | {j.get('location','')}")

    jobs = filter_jobs(raw, seen)

    log.info(f"Found {len(jobs)} matching jobs")

    log.info("=== JOBS FOUND ===")

    for job in jobs:
    	log.info(
        	f"{job['title']} | "
        	f"{job['company']} | "
        	f"{job['url']}"
         )

# send_email(jobs)

    log.info("About to send email...")
    #send_email(jobs)
    log.info("Email completed")

    for j in jobs:
        seen.add(j["id"])

    save_seen(seen)

    print(f"Found {len(jobs)} jobs")

if __name__ == "__main__":
    main()
