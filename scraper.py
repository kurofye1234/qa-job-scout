"""
QA Job Scout — Daily scraper for Juan Estrada
Sources: Remotive API, WeWorkRemotely RSS, Jobicy API
Filters: QA + LATAM/Mexico/Worldwide + Contractor + $20+/hr + Manual/Jr/Middle
"""

import os, json, re, hashlib, smtplib, logging, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

try:
    import requests as _req
    def http_get(url):
        r = _req.get(url, timeout=15, headers={"User-Agent": "QAJobScout/1.0"})
        r.raise_for_status()
        return r.text
except ImportError:
    def http_get(url):
        req = urllib.request.Request(url, headers={"User-Agent": "QAJobScout/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
GMAIL_USER     = os.environ.get("GMAIL_USER", "")
GMAIL_PASSWORD = os.environ.get("GMAIL_PASSWORD", "")
NOTIFY_EMAIL   = os.environ.get("NOTIFY_EMAIL", "")
SEEN_FILE      = Path(os.environ.get("SEEN_FILE", "/data/seen_jobs.json"))

# ─── FILTERS ──────────────────────────────────────────────────────────────────
TITLE_INCLUDE = [
    "qa", "quality assurance", "quality engineer", "qe ",
    "tester", "test engineer", "test analyst", "qa analyst",
    "manual tester", "manual qa"
]
TITLE_EXCLUDE = [
    "senior", "sr.", "sr ", "lead", "manager", "director", "head of",
    "principal", "staff ", "devops engineer", "data engineer",
    "frontend engineer", "backend engineer", "fullstack", "full stack",
    "mobile engineer", "ios engineer", "android engineer"
]
LOCATION_INCLUDE = [
    "worldwide", "anywhere", "global", "latam", "latin america",
    "mexico", "méxico", "remote", "north america", "us timezone",
    "argentina", "colombia", "brazil", "chile", "peru", "central america"
]
DESC_POSITIVE = [
    "manual testing", "manual qa", "test cases", "test plan",
    "regression", "exploratory", "jira", "bug report", "agile",
    "scrum", "api testing", "postman", "playwright", "selenium",
    "functional testing", "uat", "azure devops", "test management"
]
DESC_EXCLUDE = [
    "must be located in us", "us citizen", "us only",
    "united states only", "security clearance"
]
MIN_HOURLY = 20

# ─── SALARY ───────────────────────────────────────────────────────────────────
def extract_salary(text: str) -> dict:
    t = (text or "").lower()
    r = {"found": False, "hourly": None, "raw": ""}

    m = re.search(r'\$?(\d{2,3}(?:\.\d+)?)\s*(?:usd\s*)?(?:/hr|/hour|per hour|per h\b)', t)
    if m:
        v = float(m.group(1))
        return {"found": True, "hourly": v, "raw": f"~${v:.0f}/hr"}

    m = re.search(r'\$?([\d,]{4,7})\s*(?:-\s*\$?[\d,]+)?\s*(?:usd\s*)?(?:/mo|per month|/month)', t)
    if m:
        v = float(m.group(1).replace(",", ""))
        h = round(v / 160, 1)
        return {"found": True, "hourly": h, "raw": f"${v:.0f}/mo (~${h}/hr)"}

    m = re.search(r'\$?(\d{2,3})k|\$?([\d]{2,3},\d{3})', t)
    if m:
        raw = m.group(1) or m.group(2)
        v = float(raw.replace(",", ""))
        if v < 500: v *= 1000
        h = round(v / 2080, 1)
        return {"found": True, "hourly": h, "raw": f"${v:,.0f}/yr (~${h}/hr)"}

    return r

def ok_salary(s): return not s["found"] or (s["hourly"] is not None and s["hourly"] >= MIN_HOURLY)
def ok_title(t):
    tl = t.lower()
    return any(k in tl for k in TITLE_INCLUDE) and not any(k in tl for k in TITLE_EXCLUDE)
def ok_location(l):
    if not l: return True
    ll = l.lower()
    return any(k in ll for k in LOCATION_INCLUDE)
def ok_desc(d):
    dl = (d or "").lower()
    return not any(k in dl for k in DESC_EXCLUDE)
def score(d):
    dl = (d or "").lower()
    return sum(1 for k in DESC_POSITIVE if k in dl)
def jid(url): return hashlib.md5(url.encode()).hexdigest()

# ─── SEEN STORE ───────────────────────────────────────────────────────────────
def load_seen():
    try:
        if SEEN_FILE.exists():
            return set(json.loads(SEEN_FILE.read_text()))
    except Exception: pass
    return set()

def save_seen(seen):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(list(seen)))

# ─── RSS PARSER (stdlib only) ─────────────────────────────────────────────────
def parse_rss(xml_text: str, source: str) -> list:
    jobs = []
    try:
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        # Handle both RSS and Atom
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)
        for item in items:
            def g(tag):
                el = item.find(tag) or item.find(f"atom:{tag}", ns)
                return (el.text or "").strip() if el is not None else ""
            title    = g("title")
            link     = g("link") or g("id")
            desc     = g("description") or g("summary") or g("content")
            company  = g("author") or ""
            location = g("region") or "Worldwide"
            # WeWorkRemotely format: "Company: Title"
            if ":" in title and source == "WeWorkRemotely":
                parts = title.split(":", 1)
                company, title = parts[0].strip(), parts[1].strip()
            jobs.append({"title": title, "company": company, "location": location,
                         "url": link, "desc": desc, "salary": "", "source": source})
    except Exception as e:
        log.error(f"RSS parse error ({source}): {e}")
    return jobs

# ─── SOURCES ──────────────────────────────────────────────────────────────────
def fetch_remotive() -> list:
    log.info("Fetching Remotive API...")
    try:
        data = json.loads(http_get("https://remotive.com/api/remote-jobs?category=qa&limit=100"))
        jobs = []
        for j in data.get("jobs", []):
            jobs.append({"title": j.get("title",""), "company": j.get("company_name",""),
                         "location": j.get("candidate_required_location",""),
                         "url": j.get("url",""), "desc": j.get("description",""),
                         "salary": str(j.get("salary","")), "source": "Remotive"})
        log.info(f"Remotive: {len(jobs)} raw")
        return jobs
    except Exception as e:
        log.error(f"Remotive: {e}"); return []

def fetch_weworkremotely() -> list:
    log.info("Fetching WeWorkRemotely RSS...")
    jobs = []
    for url in [
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    ]:
        try:
            jobs += parse_rss(http_get(url), "WeWorkRemotely")
        except Exception as e:
            log.error(f"WWR: {e}")
    log.info(f"WeWorkRemotely: {len(jobs)} raw")
    return jobs

def fetch_jobicy() -> list:
    log.info("Fetching Jobicy API...")
    try:
        data = json.loads(http_get("https://jobicy.com/api/v2/remote-jobs?tag=qa&count=50"))
        jobs = []
        for j in data.get("jobs", []):
            jobs.append({"title": j.get("jobTitle",""), "company": j.get("companyName",""),
                         "location": j.get("jobGeo","Worldwide"),
                         "url": j.get("url",""), "desc": j.get("jobDescription",""),
                         "salary": str(j.get("annualSalaryMin","")), "source": "Jobicy"})
        log.info(f"Jobicy: {len(jobs)} raw")
        return jobs
    except Exception as e:
        log.error(f"Jobicy: {e}"); return []

def fetch_remotive_rss() -> list:
    log.info("Fetching Remotive RSS...")
    try:
        jobs = parse_rss(http_get("https://remotive.com/remote-jobs/qa/feed"), "Remotive RSS")
        log.info(f"Remotive RSS: {len(jobs)} raw")
        return jobs
    except Exception as e:
        log.error(f"Remotive RSS: {e}"); return []

# ─── PIPELINE ─────────────────────────────────────────────────────────────────
def filter_jobs(raw, seen):
    results = []
    for j in raw:
        url = j.get("url","")
        if not url: continue
        jid_ = jid(url)
        if jid_ in seen: continue
        if not ok_title(j.get("title","")): continue
        if not ok_location(j.get("location","")): continue
        if not ok_desc(j.get("desc","")): continue
        sal = extract_salary(str(j.get("salary","")) + " " + j.get("desc",""))
        if not ok_salary(sal): continue
        results.append({
            "id": jid_, "title": j["title"], "company": j.get("company",""),
            "location": j.get("location","Remote / Worldwide"),
            "url": url, "salary": sal["raw"] if sal["found"] else "Not specified",
            "score": score(j.get("desc","")), "source": j.get("source",""),
        })
    results.sort(key=lambda x: x["score"], reverse=True)
    return results

# ─── EMAIL ────────────────────────────────────────────────────────────────────
def build_html(jobs, run_date):
    if not jobs:
        body = "<p style='color:#666;font-size:14px;'>No new matching jobs found today. Script is running — check back tomorrow!</p>"
    else:
        cards = ""
        for j in jobs:
            dots = "●" * min(j["score"], 10) + "○" * (10 - min(j["score"], 10))
            cards += f"""
            <div style="border:1px solid #dde3ea;border-radius:8px;padding:16px 20px;margin-bottom:14px;background:#fff;">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;margin-bottom:8px;">
                <div>
                  <div style="font-size:16px;font-weight:600;color:#111;margin-bottom:2px;">{j['title']}</div>
                  <div style="font-size:13px;color:#1F5C99;">{j['company']}</div>
                </div>
                <a href="{j['url']}" style="background:#1F5C99;color:#fff;padding:7px 16px;border-radius:6px;text-decoration:none;font-size:13px;font-weight:500;white-space:nowrap;">Apply ↗</a>
              </div>
              <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px;">
                <span style="background:#EAF3DE;color:#27500A;font-size:11px;font-weight:500;padding:3px 9px;border-radius:99px;">{j['location']}</span>
                <span style="background:#E6F1FB;color:#0C447C;font-size:11px;font-weight:500;padding:3px 9px;border-radius:99px;">{j['source']}</span>
                <span style="background:#FAEEDA;color:#633806;font-size:11px;font-weight:500;padding:3px 9px;border-radius:99px;">{j['salary']}</span>
              </div>
              <div style="font-size:12px;color:#aaa;">Match: <span style="color:#1F5C99;letter-spacing:1px;">{dots}</span></div>
            </div>"""
        body = f"<p style='color:#555;font-size:14px;margin-bottom:16px;'>Found <strong>{len(jobs)} new job(s)</strong> today matching your profile.</p>" + cards

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#F4F6F9;font-family:Arial,sans-serif;">
<div style="max-width:640px;margin:32px auto;padding:0 16px 32px;">
  <div style="background:#1F5C99;border-radius:10px 10px 0 0;padding:24px 28px;">
    <div style="color:#fff;font-size:22px;font-weight:700;">🚀 QA Job Scout</div>
    <div style="color:#bdd6f0;font-size:13px;margin-top:4px;">{run_date} · Daily digest for Juan Estrada</div>
  </div>
  <div style="background:#fff;border-radius:0 0 10px 10px;padding:24px 28px;">
    <div style="font-size:12px;color:#aaa;margin-bottom:18px;">
      Filters active: QA · Manual / Jr / Middle · LATAM or Worldwide · Contractor · $20+/hr<br>
      Sources: Remotive · WeWorkRemotely · Jobicy
    </div>
    {body}
    <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
    <p style="font-size:11px;color:#bbb;text-align:center;">QA Job Scout · Running on Railway · Built for Juan Estrada</p>
  </div>
</div></body></html>"""

def send_email(jobs, run_date):
    if not GMAIL_USER or not GMAIL_PASSWORD or not NOTIFY_EMAIL:
        log.warning("No email credentials — printing to console.")
        for j in jobs:
            print(f"[{j['source']}] {j['title']} @ {j['company']} | {j['salary']} | {j['url']}")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🚀 QA Scout: {len(jobs)} new job(s) — {run_date}"
    msg["From"]    = GMAIL_USER
    msg["To"]      = NOTIFY_EMAIL
    msg.attach(MIMEText(build_html(jobs, run_date), "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_USER, GMAIL_PASSWORD)
            s.sendmail(GMAIL_USER, NOTIFY_EMAIL, msg.as_string())
        log.info(f"Email sent → {NOTIFY_EMAIL} ({len(jobs)} jobs)")
    except Exception as e:
        log.error(f"Email failed: {e}"); raise

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    run_date = datetime.now(timezone.utc).strftime("%B %d, %Y")
    log.info(f"=== QA Job Scout — {run_date} ===")
    seen = load_seen()
    raw  = fetch_remotive() + fetch_weworkremotely() + fetch_remotive_rss() + fetch_jobicy()
    log.info(f"Total raw: {len(raw)}")
    jobs = filter_jobs(raw, seen)
    log.info(f"New matches: {len(jobs)}")
    send_email(jobs, run_date)
    for j in jobs: seen.add(j["id"])
    save_seen(seen)
    log.info("Done ✓")

if __name__ == "__main__":
    main()
