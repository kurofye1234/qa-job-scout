# 🚀 QA Job Scout — Setup Guide

Daily job alert system for Juan Estrada.
Scrapes Remotive, WeWorkRemotely, and Jobicy every day and sends an email with new QA contractor roles for LATAM.

---

## What it does

- Runs every day at 08:00 UTC (2:00 AM Mexico City time)
- Fetches QA jobs from 3 sources with public APIs
- Filters by: Manual QA · Jr/Middle · LATAM/Worldwide · $20+/hr
- Sends you a formatted HTML email with matching jobs
- Remembers jobs already sent so you never get duplicates

---

## Step 1 — Get a Gmail App Password

> You need this because Gmail blocks regular passwords for scripts.

1. Go to your Google Account → **Security**
2. Enable **2-Step Verification** if not already on
3. Go to **Security → App passwords**
4. Create a new app password → name it "QA Scout"
5. Copy the 16-character password (e.g. `abcd efgh ijkl mnop`)

---

## Step 2 — Push to GitHub

```bash
# In your terminal (on your Mac)
cd qa-job-scout
git init
git add .
git commit -m "Initial QA Job Scout"
git remote add origin https://github.com/YOUR_USERNAME/qa-job-scout.git
git push -u origin main
```

---

## Step 3 — Deploy on Railway

1. Go to [railway.app](https://railway.app) → Sign up with GitHub (free)
2. Click **New Project → Deploy from GitHub repo**
3. Select your `qa-job-scout` repo
4. Railway will auto-detect the Dockerfile and build it

### Add environment variables in Railway dashboard:

| Variable | Value |
|---|---|
| `GMAIL_USER` | your Gmail (e.g. `juan@gmail.com`) |
| `GMAIL_PASSWORD` | the 16-char App Password from Step 1 |
| `NOTIFY_EMAIL` | where to receive alerts (same Gmail or another) |
| `SEEN_FILE` | `/data/seen_jobs.json` |

5. Click **Deploy** — it will run immediately and send your first email

---

## Step 4 — Add a Volume (to persist seen jobs)

Without this, Railway resets memory on restart and you'll get duplicates.

1. In Railway project → click your service → **Volumes**
2. Add volume → Mount path: `/data`
3. Redeploy

---

## Checking logs

In Railway dashboard → your service → **Logs tab**

You'll see something like:
```
2026-06-16 08:00:01 INFO === QA Job Scout starting — June 16, 2026 ===
2026-06-16 08:00:02 INFO Fetching Remotive...
2026-06-16 08:00:03 INFO Remotive: 47 raw jobs
2026-06-16 08:00:04 INFO New matching jobs after filters: 6
2026-06-16 08:00:05 INFO Email sent to juan@gmail.com with 6 jobs.
```

---

## Customizing filters

Edit `scraper.py` to adjust:

- `MIN_SALARY_USD_HOUR = 20` → raise to 24 if you want stricter filter
- `TITLE_EXCLUDE` → add "senior" is already there; add others if needed
- `LOCATION_INCLUDE` → add more countries if needed

---

## Cost

**Railway free tier**: $5/month in credits included. This scraper uses ~$0.50-1/month. Effectively free.

---

## Sources

| Source | API Type | QA Jobs |
|---|---|---|
| [Remotive](https://remotive.com) | Public JSON API | ~50-100/query |
| [WeWorkRemotely](https://weworkremotely.com) | RSS Feed | ~20-40/day |
| [Jobicy](https://jobicy.com) | Public JSON API | ~20-50/query |

---

Built for Juan Estrada · QA Engineer · June 2026
