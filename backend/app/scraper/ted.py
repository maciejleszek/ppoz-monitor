"""Źródło (EKSPERYMENTALNE): TED — Tenders Electronic Daily.

Przetargi unijne (powyżej progów UE) z terenu Polski, filtrowane po kodach
CPV branży ppoż. Używa publicznego Search API v3:
    POST https://api.ted.europa.eu/v3/notices/search

UWAGA: API TED bywa zmieniane. Moduł jest domyślnie WYŁĄCZONY
(ENABLE_TED=false). Przed włączeniem zweryfikuj nazwy pól z aktualną
dokumentacją: https://docs.ted.europa.eu/api/latest/index.html
Kod napisany jest defensywnie — błędne pole nie wywraca całego pobierania.
"""

import logging
from datetime import datetime, timedelta

import httpx
from dateutil import parser as dtparser

from ..config import settings
from ..models import Tender
from .keywords import CPV_PREFIXES, match_keywords

log = logging.getLogger("scraper.ted")

SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"
NOTICE_URL = "https://ted.europa.eu/pl/notice/-/detail/{}"

# Pełne kody CPV wyprowadzone z prefiksów słownika branżowego.
_CPV_FULL = [
    "35111000", "35110000", "31625100", "31625200", "45312100",
    "45343000", "44480000", "44482000", "50413200", "75251000",
    "75251110", "71317100", "45216121", "24951220",
]


def _first_text(value):
    """TED zwraca teksty jako dict {'pol': ..., 'eng': ...} albo listy."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for lang in ("pol", "eng"):
            if value.get(lang):
                return _first_text(value[lang])
        for v in value.values():
            if v:
                return _first_text(v)
        return None
    if isinstance(value, list):
        return _first_text(value[0]) if value else None
    return str(value)


def _parse_dt(value):
    text = _first_text(value)
    if not text:
        return None
    try:
        return dtparser.parse(text).replace(tzinfo=None)
    except (ValueError, OverflowError):
        return None


def scrape(db, days_back: int) -> tuple[int, int, int]:
    date_from = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")
    query = (
        f"(classification-cpv IN ({' '.join(_CPV_FULL)})) "
        f"AND (place-of-performance IN (POL)) "
        f"AND (publication-date >= {date_from})"
    )
    payload = {
        "query": query,
        "fields": [
            "publication-number", "notice-title", "buyer-name", "buyer-city",
            "publication-date", "deadline-receipt-tenders", "classification-cpv",
        ],
        "page": 1,
        "limit": 100,
    }

    found = added = updated = 0
    with httpx.Client(follow_redirects=True) as client:
        resp = client.post(
            SEARCH_URL, json=payload, timeout=40,
            headers={"Accept": "application/json", "User-Agent": settings.user_agent},
        )
        resp.raise_for_status()
        notices = resp.json().get("notices", []) or []

    for raw in notices:
        pub_number = _first_text(raw.get("publication-number"))
        title = _first_text(raw.get("notice-title"))
        if not pub_number or not title:
            continue

        cpvs = [
            str(c) for c in (raw.get("classification-cpv") or [])
            if str(c)[:5].isdigit()
        ]
        labels = match_keywords(title, [f"{c[:8]}-0" for c in cpvs if len(c) >= 8])
        if not labels:
            # dopasuj po samych prefiksach CPV
            for code in cpvs:
                for prefix, label in CPV_PREFIXES:
                    if code.startswith(prefix) and label not in labels:
                        labels.append(label)
        if not labels:
            continue

        found += 1
        values = dict(
            title=title[:8000],
            buyer_name=(_first_text(raw.get("buyer-name")) or "")[:600] or None,
            city=(_first_text(raw.get("buyer-city")) or "")[:200] or None,
            country="PL",
            notice_type="ContractNotice",
            url=NOTICE_URL.format(pub_number),
            publication_date=_parse_dt(raw.get("publication-date")),
            submission_deadline=_parse_dt(raw.get("deadline-receipt-tenders")),
            cpv_codes=cpvs[:20],
            matched_keywords=labels,
        )

        existing = (
            db.query(Tender)
            .filter_by(source="ted", external_id=pub_number)
            .one_or_none()
        )
        if existing:
            for key, val in values.items():
                setattr(existing, key, val)
            updated += 1
        else:
            db.add(Tender(source="ted", external_id=pub_number, **values))
            added += 1

    db.commit()
    return found, added, updated
