"""Źródło: Biuletyn Zamówień Publicznych (platforma e-Zamówienia, UZP).

Korzysta z OFICJALNEGO, publicznego API odczytu ogłoszeń krajowych:
    https://ezamowienia.gov.pl/mo-board/api/v1/notice
Zgodnie z regulaminem platformy odczyt ogłoszeń BZP nie wymaga rejestracji
ani klucza (https://ezamowienia.gov.pl/pl/integracja/).

Pola odpowiedzi (m.in.): objectId, noticeNumber, noticeType, orderType,
publicationDate, orderObject, cpvCode, submittingOffersDate,
organizationName, organizationCity, organizationProvince, tenderId.
"""

import logging
import time
from datetime import datetime, timedelta

import httpx
from dateutil import parser as dtparser

from ..config import settings
from ..models import Tender
from .keywords import extract_cpv, match_keywords

log = logging.getLogger("scraper.bzp")

API_URL = "https://ezamowienia.gov.pl/mo-board/api/v1/notice"
NOTICE_DETAILS = "https://ezamowienia.gov.pl/mo-client-board/bzp/notice-details/id/{}"
TENDER_PAGE = "https://ezamowienia.gov.pl/mp-client/search/list/{}"
FALLBACK_URL = "https://ezamowienia.gov.pl/mo-client-board/bzp/list"

# Interesują nas ogłoszenia o wszczęciu postępowania.
NOTICE_TYPES = ["ContractNotice"]

PAGE_SIZE = 50
MAX_PAGES = 80          # bezpiecznik na wypadek pętli
REQUEST_GAP_S = 0.7     # przerwa między stronami — nie obciążamy API


class _BadParams(Exception):
    pass


def _headers() -> dict:
    return {"Accept": "application/json", "User-Agent": settings.user_agent}


def _parse_dt(value):
    if not value:
        return None
    try:
        return dtparser.parse(str(value)).replace(tzinfo=None)
    except (ValueError, OverflowError):
        return None


def _date_variants(days_back: int) -> list[dict]:
    """API bywa wybredne co do formatu dat — próbujemy kilku wariantów,
    a w ostateczności pobieramy bez filtra dat i tniemy lokalnie."""
    d_from = datetime.now() - timedelta(days=days_back)
    d_to = datetime.now() + timedelta(days=1)
    return [
        {
            "PublicationDateFrom": d_from.strftime("%Y-%m-%dT00:00:00.000Z"),
            "PublicationDateTo": d_to.strftime("%Y-%m-%dT23:59:59.999Z"),
        },
        {
            "PublicationDateFrom": d_from.strftime("%Y-%m-%d"),
            "PublicationDateTo": d_to.strftime("%Y-%m-%d"),
        },
        {},  # bez filtra — sortujemy malejąco i przerywamy po przekroczeniu cutoff
    ]


def _extract_items(payload) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "data", "results", "notices"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


def _fetch_notices(client: httpx.Client, notice_type: str, days_back: int) -> list[dict]:
    cutoff = datetime.now() - timedelta(days=days_back + 1)
    last_err = None

    for extra in _date_variants(days_back):
        items: list[dict] = []
        try:
            page = 1
            while page <= MAX_PAGES:
                params = {
                    "NoticeType": notice_type,
                    "PageNumber": page,
                    "PageSize": PAGE_SIZE,
                    "SortingColumnName": "PublicationDate",
                    "SortingDirection": "DESC",
                    **extra,
                }
                resp = client.get(API_URL, params=params, headers=_headers(), timeout=40)
                if resp.status_code == 400:
                    raise _BadParams(resp.text[:300])
                resp.raise_for_status()

                batch = _extract_items(resp.json())
                if not batch:
                    break
                items.extend(batch)

                oldest = _parse_dt(batch[-1].get("publicationDate"))
                if len(batch) < PAGE_SIZE or (oldest and oldest < cutoff):
                    break
                page += 1
                time.sleep(REQUEST_GAP_S)

            log.info("BZP %s: pobrano %d ogłoszeń (wariant dat: %s)",
                     notice_type, len(items), "brak" if not extra else "ok")
            return items
        except _BadParams as err:
            last_err = err
            continue  # spróbuj kolejnego formatu dat

    raise RuntimeError(f"API BZP odrzuciło wszystkie warianty zapytania: {last_err}")


def _upsert(db, raw: dict, cutoff: datetime) -> str | None:
    """Zwraca 'added' / 'updated' / None (pominięto)."""
    pub = _parse_dt(raw.get("publicationDate"))
    if pub and pub < cutoff:
        return None

    title = (raw.get("orderObject") or "").strip()
    buyer = (raw.get("organizationName") or "").strip() or None
    cpvs = extract_cpv(raw.get("cpvCode"))

    haystack = " ".join(filter(None, [title, buyer, str(raw.get("cpvCode") or "")]))
    labels = match_keywords(haystack, cpvs)
    if not labels:
        return None  # nie dotyczy branży ppoż

    ext_id = str(raw.get("noticeNumber") or raw.get("objectId") or "").strip()
    if not ext_id or not title:
        return None

    object_id = raw.get("objectId")
    tender_id = raw.get("tenderId")
    values = dict(
        title=title[:8000],
        buyer_name=buyer[:600] if buyer else None,
        city=(raw.get("organizationCity") or "").strip()[:200] or None,
        region=(raw.get("organizationProvince") or "").strip().lower()[:100] or None,
        country="PL",
        order_type=(raw.get("orderType") or "").strip()[:60] or None,
        notice_type=(raw.get("noticeType") or "ContractNotice")[:80],
        url=NOTICE_DETAILS.format(object_id) if object_id else FALLBACK_URL,
        tender_url=TENDER_PAGE.format(tender_id) if tender_id else None,
        publication_date=pub,
        submission_deadline=_parse_dt(raw.get("submittingOffersDate")),
        cpv_codes=cpvs,
        matched_keywords=labels,
    )

    existing = (
        db.query(Tender).filter_by(source="bzp", external_id=ext_id).one_or_none()
    )
    if existing:
        changed = (
            existing.submission_deadline != values["submission_deadline"]
            or existing.title != values["title"]
        )
        for key, val in values.items():
            setattr(existing, key, val)
        return "updated" if changed else None

    db.add(Tender(source="bzp", external_id=ext_id, **values))
    return "added"


def scrape(db, days_back: int) -> tuple[int, int, int]:
    """Pobiera ogłoszenia z BZP z ostatnich `days_back` dni.
    Zwraca (dopasowane_do_branży, dodane, zaktualizowane)."""
    cutoff = datetime.now() - timedelta(days=days_back + 1)
    found = added = updated = 0

    with httpx.Client(follow_redirects=True) as client:
        for notice_type in NOTICE_TYPES:
            for raw in _fetch_notices(client, notice_type, days_back):
                result = _upsert(db, raw, cutoff)
                if result is None:
                    continue
                found += 1
                if result == "added":
                    added += 1
                elif result == "updated":
                    updated += 1

    db.commit()
    return found, added, updated
