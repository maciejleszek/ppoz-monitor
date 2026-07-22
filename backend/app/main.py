"""PPOŻ Monitor — API.

Agregator ogłoszeń o zamówieniach publicznych z branży ochrony
przeciwpożarowej. Źródło główne: oficjalne API Biuletynu Zamówień
Publicznych (ezamowienia.gov.pl).
"""

import logging
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, func, nullslast, or_
from sqlalchemy.orm import Session

from . import scheduler
from .config import settings
from .database import Base, engine, get_db, SessionLocal
from .models import ScrapeRun, Tender
from .schemas import LastRun, StatsOut, TenderList, TenderOut
from .scraper.runner import run_scrape_locked, scrape_lock

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
log = logging.getLogger("app")


def _bootstrap_if_empty() -> None:
    """Przy pierwszym uruchomieniu (pusta baza) pobierz dane w tle."""
    if not settings.auto_bootstrap:
        return
    try:
        db = SessionLocal()
        empty = db.query(Tender.id).first() is None
        db.close()
    except Exception:
        log.exception("Nie udało się sprawdzić stanu bazy przy starcie.")
        return
    if empty:
        log.info("Baza pusta — startuję pobieranie z ostatnich %d dni.",
                 settings.bootstrap_days_back)
        threading.Thread(
            target=run_scrape_locked,
            kwargs={"days_back": settings.bootstrap_days_back},
            daemon=True,
        ).start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _bootstrap_if_empty()
    if settings.enable_scheduler:
        scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(
    title="PPOŻ Monitor API",
    description="Przetargi publiczne dla branży ochrony przeciwpożarowej.",
    version="1.0.0",
    lifespan=lifespan,
)

origins = (
    ["*"]
    if settings.cors_origins.strip() == "*"
    else [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Endpointy podstawowe ────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "PPOŻ Monitor API", "docs": "/docs", "health": "/api/health"}


@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


# ── Ogłoszenia ──────────────────────────────────────────────────────────────

@app.get("/api/tenders", response_model=TenderList)
def list_tenders(
    db: Session = Depends(get_db),
    q: str = Query("", description="Szukany tekst (tytuł, zamawiający, miasto)"),
    region: str = Query("", description="Województwo, np. mazowieckie"),
    source: str = Query("", description="bzp | ted"),
    active_only: bool = Query(False, description="Tylko z terminem ofert w przyszłości"),
    sort: str = Query("newest", description="newest | deadline | oldest"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = db.query(Tender)

    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Tender.title.ilike(like),
                Tender.buyer_name.ilike(like),
                Tender.city.ilike(like),
                Tender.description.ilike(like),
            )
        )
    if region.strip():
        query = query.filter(Tender.region == region.strip().lower())
    if source.strip():
        query = query.filter(Tender.source == source.strip().lower())
    if active_only:
        now = datetime.now()
        query = query.filter(
            or_(Tender.submission_deadline.is_(None), Tender.submission_deadline >= now)
        )

    total = query.count()

    if sort == "deadline":
        query = query.order_by(nullslast(Tender.submission_deadline.asc()))
    elif sort == "oldest":
        query = query.order_by(nullslast(Tender.publication_date.asc()))
    else:  # newest
        query = query.order_by(nullslast(Tender.publication_date.desc()))

    items = query.offset((page - 1) * page_size).limit(page_size).all()
    pages = max(1, -(-total // page_size))  # sufit z dzielenia

    return TenderList(items=items, total=total, page=page, pages=pages, page_size=page_size)


@app.get("/api/tenders/{tender_id}", response_model=TenderOut)
def get_tender(tender_id: int, db: Session = Depends(get_db)):
    tender = db.get(Tender, tender_id)
    if tender is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono ogłoszenia.")
    return tender


@app.get("/api/regions", response_model=list[str])
def list_regions(db: Session = Depends(get_db)):
    rows = (
        db.query(Tender.region)
        .filter(Tender.region.isnot(None), Tender.region != "")
        .distinct()
        .order_by(Tender.region.asc())
        .all()
    )
    return [r[0] for r in rows]


@app.get("/api/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db)):
    now = datetime.now()
    total = db.query(func.count(Tender.id)).scalar() or 0
    new_24h = (
        db.query(func.count(Tender.id))
        .filter(Tender.publication_date >= now - timedelta(days=1))
        .scalar() or 0
    )
    new_7d = (
        db.query(func.count(Tender.id))
        .filter(Tender.publication_date >= now - timedelta(days=7))
        .scalar() or 0
    )
    closing_7d = (
        db.query(func.count(Tender.id))
        .filter(
            Tender.submission_deadline.isnot(None),
            Tender.submission_deadline >= now,
            Tender.submission_deadline <= now + timedelta(days=7),
        )
        .scalar() or 0
    )
    sources = dict(
        db.query(Tender.source, func.count(Tender.id)).group_by(Tender.source).all()
    )
    last = db.query(ScrapeRun).order_by(desc(ScrapeRun.started_at)).first()
    last_run = LastRun.model_validate(last) if last else None

    return StatsOut(
        total=total,
        new_24h=new_24h,
        new_7d=new_7d,
        closing_7d=closing_7d,
        sources=sources,
        last_run=last_run,
    )


# ── Ręczne wyzwolenie pobierania ────────────────────────────────────────────

def _check_token(header_token: str | None, query_token: str | None) -> None:
    expected = settings.scrape_token.strip()
    if expected and (header_token or query_token) != expected:
        raise HTTPException(status_code=401, detail="Nieprawidłowy token.")


@app.post("/api/scrape")
def trigger_scrape(
    background: BackgroundTasks,
    days_back: int | None = Query(None, ge=1, le=60, description="Ile dni wstecz pobrać"),
    token: str | None = Query(None, description="Alternatywa dla nagłówka"),
    x_scrape_token: str | None = Header(None, alias="X-Scrape-Token"),
):
    """Uruchamia pobieranie w tle. Wymaga tokenu (env SCRAPE_TOKEN).
    Postęp i wynik: GET /api/stats (pole last_run)."""
    _check_token(x_scrape_token, token)
    if scrape_lock.locked():
        raise HTTPException(status_code=409, detail="Pobieranie już trwa.")
    background.add_task(run_scrape_locked, days_back)
    return {
        "status": "started",
        "days_back": days_back or settings.scrape_days_back,
        "check": "/api/stats",
    }
