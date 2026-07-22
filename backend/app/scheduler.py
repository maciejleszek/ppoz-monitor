"""Harmonogram: automatyczne pobieranie 2x dziennie (czas polski).

Uwaga dla darmowego planu Render: usługa "zasypia" po ~15 min bezczynności
i harmonogram wtedy nie działa. Rozwiązanie opisane w README (zewnętrzny
cron pingujący /api/health i wywołujący /api/scrape).
"""

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from .config import settings
from .scraper.runner import run_scrape_locked

log = logging.getLogger("scheduler")
_scheduler: BackgroundScheduler | None = None


def start() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone=ZoneInfo("Europe/Warsaw"))
    _scheduler.add_job(
        run_scrape_locked,
        trigger="cron",
        hour="6,13",
        minute=20,
        kwargs={"days_back": settings.scrape_days_back},
        id="daily_scrape",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    _scheduler.start()
    log.info("Harmonogram uruchomiony: codziennie 06:20 i 13:20 (Europe/Warsaw).")


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
