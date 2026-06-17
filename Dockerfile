FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY scraper.py .
COPY cron_runner.py .

# Create data directory for seen_jobs persistence
RUN mkdir -p /data

# Environment variables (set these in Railway dashboard)
# GMAIL_USER       = your Gmail address
# GMAIL_PASSWORD   = Gmail App Password (not your real password)
# NOTIFY_EMAIL     = where to send job alerts (can be same as GMAIL_USER)
# SEEN_FILE        = /data/seen_jobs.json (default, don't change)

CMD ["python", "cron_runner.py"]
