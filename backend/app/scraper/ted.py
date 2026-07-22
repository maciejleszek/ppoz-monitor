"""Źródło: TED — Tenders Electronic Daily (przetargi UE powyżej progów).

Oficjalne Search API v3 (bez klucza dla odczytu opublikowanych ogłoszeń):
    POST https://api.ted.europa.eu/v3/notices/search
Dokumentacja: https://docs.ted.europa.eu/api/latest/search.html

Zapytanie typu "expert query" filtruje: miejsce realizacji = Polska,
branżowe kody CPV (ppoż), data publikacji. Pola odpowiedzi bywają
wielojęzyczne (słowniki {"pol": ..., "eng": ...}) — preferujemy polski.
"""

import logging
import re
import time
from datetime import datetime, timedelta

import httpx
from dateutil import parser as dtparser

from ..config import settings
from ..models import Tender
from .keywords import match_keywords

log = logging.getLogger("scraper.ted")

API_URL = "https://api.ted.europa.eu/v3/notices/search"
NOTICE_URL = "https://ted.europa.eu/pl/notice/-/detail/{}"

PAGE_SIZE = 50
MAX_PAGES = 20          # TED dla PL + CPV ppoż to pojedyncze ogłoszenia dziennie
REQUEST_GAP_S = 0.7

# Pełne kody CPV branży ppoż (TED oczekuje kodów, wildcardy bywają kapryśne).
CPV_CODES = [
    "35111000", "35111100", "35111200", "35111300", "35111400", "35111500",
    "35110000", "31625000", "31625100", "31625200", "31625300",
    "45312100", "45343000", "45343100", "45343200", "45343210", "45343220",
    "44480000", "44481000", "44482000", "44482100", "44482200",
    "50413200", "75251000", "75251100", "75251110", "75251120",
    "71317100", "45216121",
]

# Zestawy pól odpowiedzi — od bogatego do minimalnego (gwarantowanego).
FIELDSETS = [
    ("pelny", [
        "publication-number", "publication-date", "notice-title",
        "buyer-name", "buyer-city", "buyer-country",
        "classification-cpv", "deadline-receipt-tenders", "notice-type",
    ]),
    ("podstawowy", [
        "publication-number", "publication-date", "notice-title",
        "buyer-name", "buyer-country", "classification-cpv",
    ]),
    ("minimalny", ["publication-number"]),
]


def _queries(days_back: int) -> list[tuple[str, str]]:
    since = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")
    cpv_list = " ".join(CPV_CODES)
    base = f"(place-of-performance IN (POL)) AND (publication-date >= {since})"
    return [
        ("cpv-lista", f"(classification-cpv IN ({cpv_list})) AND {base}"),
        ("cpv-wildcard",
         "(classification-cpv IN (35111* 45343* 31625* 44482*)) AND " + base),
    ]


def _first_text(value) -> str | None:
    """TED zwraca teksty jako str, listę lub słownik języków — bierzemy polski,
    potem angielski, potem cokolwiek."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        for v in value:
            t = _first_text(v)
            if t:
                return t
        return None
    if isinstance(value, dict):
        for key in ("pol", "POL", "pl", "eng", "ENG", "en"):
            if value.get(key):
                return _first_text(value[key])
        for v in value.values():
            t = _first_text(v)
            if t:
                return t
    return None


def _parse_dt(value):
    text = _first_text(value)
    if not text:
        return None
    try:
        return dtparser.parse(text).replace(tzinfo=None)
    except (ValueError, OverflowError):
        return None


def _cpvs(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        raw = " ".join(str(v) for v in value)
    else:
        raw = str(value)
    return sorted(set(re.findall(r"\d{8}", raw)))


def _post(client: httpx.Client, body: dict) -> httpx.Response:
    return client.post(
        API_URL,
        json=body,
        headers={"Accept": "application/json", "User-Agent": settings.user_agent},
        timeout=40,
    )


def _search_pages(client: httpx.Client, query: str, fields: list[str]):
    """Generator stron wyników dla danego zapytania i zestawu pól."""
    page = 1
    while page <= MAX_PAGES:
        body = {
            "query": query,
            "fields": fields,
            "page": page,
            "limit": PAGE_SIZE,
            "scope": "ACTIVE",
            "checkQuerySyntax": False,
            "paginationMode": "PAGE_NUMBER",
        }
        resp = _post(client, body)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        notices = data.get("notices") or []
        if not notices:
            return
        yield notices
        total = data.get("totalNoticeCount") or 0
        if page * PAGE_SIZE >= total:
            return
        page += 1
        time.sleep(REQUEST_GAP_S)


def _upsert(db, raw: dict) -> str | None:
    pub_number = _first_text(raw.get("publication-number"))
    if not pub_number:
        return None
    title = _first_text(raw.get("notice-title")) or f"Ogłoszenie TED {pub_number}"
    buyer = _first_text(raw.get("buyer-name"))
    cpvs = _cpvs(raw.get("classification-cpv"))

    labels = match_keywords(" ".join(filter(None, [title, buyer])), cpvs)
    if not labels:
        labels = ["CPV ppoż (TED)"]  # zapytanie już filtruje po branżowych CPV

    values = dict(
        title=title[:8000],
        buyer_name=(buyer or "")[:600] or None,
        city=(_first_text(raw.get("buyer-city")) or "")[:200] or None,
        region=None,
        country=(_first_text(raw.get("buyer-country")) or "PL")[:10],
        order_type=None,
        notice_type=(_first_text(raw.get("notice-type")) or "TED")[:80],
        url=NOTICE_URL.format(pub_number),
        tender_url=None,
        publication_date=_parse_dt(raw.get("publication-date")),
        submission_deadline=_parse_dt(raw.get("deadline-receipt-tenders")),
        cpv_codes=cpvs,
        matched_keywords=labels,
    )

    existing = db.query(Tender).filter_by(source="ted", external_id=pub_number).one_or_none()
    if existing:
        changed = (
            existing.submission_deadline != values["submission_deadline"]
            or existing.title != values["title"]
        )
        for key, val in values.items():
            setattr(existing, key, val)
        return "updated" if changed else None

    db.add(Tender(source="ted", external_id=pub_number, **values))
    return "added"


def scrape(db, days_back: int) -> tuple[int, int, int]:
    """Pobiera ogłoszenia TED (PL, CPV ppoż) z zapisem przyrostowym."""
    found = added = updated = 0
    last_err = None

    with httpx.Client(follow_redirects=True) as client:
        for q_name, query in _queries(days_back):
            for f_name, fields in FIELDSETS[:2]:  # minimalny nie ma sensu do zapisu
                try:
                    got_any = False
                    for notices in _search_pages(client, query, fields):
                        got_any = True
                        for raw in notices:
                            result = _upsert(db, raw)
                            if result is None:
                                continue
                            found += 1
                            if result == "added":
                                added += 1
                            elif result == "updated":
                                updated += 1
                        db.commit()
                    log.info("TED: wariant %s/%s — %d pasujących.", q_name, f_name, found)
                    db.commit()
                    return found, added, updated
                except (RuntimeError, httpx.HTTPError) as err:
                    last_err = f"{q_name}/{f_name}: {err}"
                    log.warning("TED — wariant nieudany: %s", str(last_err)[:300])
                    continue

    raise RuntimeError(f"TED: żaden wariant zapytania nie zadziałał. Ostatni błąd: {last_err}")


def probe() -> dict:
    """Diagnostyka dla /api/debug/ted — pojedyncze zapytania testowe."""
    results: list[dict] = []
    with httpx.Client(follow_redirects=True) as client:
        for q_name, query in _queries(7):
            for f_name, fields in FIELDSETS:
                entry: dict = {"zapytanie": q_name, "pola": f_name}
                body = {
                    "query": query, "fields": fields, "page": 1, "limit": 2,
                    "scope": "ACTIVE", "checkQuerySyntax": False,
                    "paginationMode": "PAGE_NUMBER",
                }
                try:
                    resp = _post(client, body)
                    entry["status_http"] = resp.status_code
                    if resp.status_code == 200:
                        data = resp.json()
                        notices = data.get("notices") or []
                        entry["liczba_pozycji"] = len(notices)
                        entry["total"] = data.get("totalNoticeCount")
                        if notices:
                            entry["pola_rekordu"] = sorted(notices[0].keys())
                            entry["przykladowy_rekord"] = {
                                k: str(v)[:120] for k, v in notices[0].items()
                            }
                            results.append(entry)
                            return {"wynik": "ok", "dzialajacy_wariant": entry,
                                    "wszystkie_proby": results}
                    else:
                        entry["odpowiedz"] = resp.text[:250]
                except Exception as err:
                    entry["blad"] = f"{type(err).__name__}: {err}"[:200]
                results.append(entry)
                time.sleep(0.4)
    return {"wynik": "zaden wariant nie zadzialal", "wszystkie_proby": results}
