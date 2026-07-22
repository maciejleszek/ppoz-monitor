"""Uruchamianie pobierania ze wszystkich włączonych źródeł + log w bazie."""

import logging
import threading
from datetime import datetime

from ..config import settings
from ..database import SessionLocal
from ..models import ScrapeRun
from . import ezamowienia, ted

log = logging.getLogger("scraper.runner")

# Jedno pobieranie naraz — chroni przed nakładaniem się przebiegów.
scrape_lock = threading.Lock()


def _sources() -> list[tuple[str, callable]]:
    sources = [("bzp", ezamowienia.scrape)]
    if settings.enable_ted:
        sources.append(("ted", ted.scrape))
    return sources


def run_scrape(days_back: int | None = None) -> dict:
    """Pobiera dane ze wszystkich źródeł. Zwraca podsumowanie per źródło."""
    days = days_back or settings.scrape_days_back
    summary: dict = {}

    db = SessionLocal()
    try:
        for name, scrape_fn in _sources():
            run = ScrapeRun(source=name, status="running")
            db.add(run)
            db.commit()
            try:
                found, added, updated = scrape_fn(db, days)
                run.status = "ok"
                run.found, run.added, run.updated = found, added, updated
                summary[name] = {"found": found, "added": added, "updated": updated}
                log.info("Źródło %s: %d pasujących, %d nowych, %d zaktualizowanych",
                         name, found, added, updated)
            except Exception as err:  # jedno źródło nie blokuje pozostałych
                db.rollback()
                run.status = "error"
                run.message = str(err)[:2000]
                summary[name] = {"error": str(err)[:300]}
                log.exception("Źródło %s: błąd pobierania", name)
            finally:
                run.finished_at = datetime.now()
                db.commit()
    finally:
        db.close()

    return summary


def run_scrape_locked(days_back: int | None = None) -> dict | None:
    """Wersja z blokadą — używana przez harmonogram i endpoint /api/scrape."""
    if not scrape_lock.acquire(blocking=False):
        log.info("Pobieranie już trwa — pomijam.")
        return None
    try:
        return run_scrape(days_back)
    finally:
        scrape_lock.release()
