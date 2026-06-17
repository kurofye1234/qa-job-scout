"""
cron_runner.py — runs scraper daily at 08:00 UTC using stdlib only (no schedule pkg needed).
"""
import time, logging
from datetime import datetime, timezone
from scraper import main as run_scraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TARGET_HOUR = 8   # UTC

log.info("QA Job Scout scheduler started. Daily run at 08:00 UTC.")
log.info("Running initial scan now...")
run_scraper()

last_run_day = datetime.now(timezone.utc).day

while True:
    now = datetime.now(timezone.utc)
    if now.hour == TARGET_HOUR and now.day != last_run_day:
        log.info(f"Scheduled run triggered at {now.isoformat()}")
        run_scraper()
        last_run_day = now.day
    time.sleep(55)  # check every ~1 minute
