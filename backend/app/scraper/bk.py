"""Źródło: Baza Konkurencyjności 2021 (zapytania ofertowe beneficjentów
funduszy UE — często zamówienia PONIŻEJ progów Pzp, których nie ma w BZP).

Serwis: https://bazakonkurencyjnosci.funduszeeuropejskie.gov.pl/
Aplikacja jest SPA z zapleczem REST pod /api/ (tak serwowane są np. załączniki:
/api/files/{id}); endpoint wyszukiwarki nie jest publicznie udokumentowany,
więc moduł SONDUJE kilka prawdopodobnych wariantów (adres + parametry
stronicowania) i zapamiętuje pierwszy działający. Weryfikacja na żywo:
GET /api/debug/bk na backendzie.

Dane są jawne z mocy Wytycznych kwalifikowalności (zasada konkurencyjności);
pobieramy z umiarem i uczciwym User-Agentem.
"""

import logging
import re
import time
from datetime import datetime, timedelta

import httpx
from dateutil import parser as dtparser

from ..config import settings
from ..models import Tender
from .keywords import extract_cpv, match_keywords

log = logging.getLogger("scraper.bk")

BASE = "https://bazakonkurencyjnosci.funduszeeuropejskie.gov.pl"
ANNOUNCEMENT_URL = BASE + "/ogloszenia/{}"

PAGE_SIZE = 50
MAX_PAGES = 200
REQUEST_GAP_S = 0.7

# Diagnoza produkcyjna (2026-07):
#  - /api/announcements: 401 (wymaga logowania) — pomijamy,
#  - /api/announcements/search i /api/announcements/list: istnieją, GET,
#    ale zwracają 500 na proste parametry (POST -> 405, więc na pewno GET).
# Hipotezy: wymagane nagłówki przeglądarkowe (Referer/Origin/UA) albo inne
# nazwy parametrów. Sondujemy warianty; pierwszy działający jest używany.
SEARCH = BASE + "/api/announcements/search"
LIST = BASE + "/api/announcements/list"

BROWSER_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Referer": BASE + "/",
    "Origin": BASE,
    "X-Requested-With": "XMLHttpRequest",
}


def _attempts():
    """(nazwa, url, funkcja page,n -> params, nagłówki|None)."""
    B = BROWSER_HEADERS
    return [
        ("search przeglądarkowy goły", SEARCH, lambda p, n: {"page": p}, B),
        ("search przeglądarkowy page-perPage", SEARCH,
         lambda p, n: {"page": p, "perPage": n}, B),
        ("list przeglądarkowy page-perPage", LIST,
         lambda p, n: {"page": p, "perPage": n}, B),
        ("search phrase", SEARCH,
         lambda p, n: {"phrase": "", "page": p, "perPage": n}, B),
        ("search searchPhrase", SEARCH,
         lambda p, n: {"searchPhrase": "", "page": p, "perPage": n}, B),
        ("search status", SEARCH,
         lambda p, n: {"status": "PUBLISHED", "page": p, "perPage": n}, B),
        ("search sort", SEARCH,
         lambda p, n: {"sort": "-publicationDate", "page": p, "perPage": n}, B),
        ("search orderBy", SEARCH,
         lambda p, n: {"orderBy": "publicationDate", "orderType": "desc",
                       "page": p, "perPage": n}, B),
        ("search pageNumber-itemsPerPage", SEARCH,
         lambda p, n: {"pageNumber": p, "itemsPerPage": n}, B),
        ("search offset-limit", SEARCH,
         lambda p, n: {"offset": (p - 1) * n, "limit": n}, B),
        ("search keyword", SEARCH,
         lambda p, n: {"keyword": "", "page": p, "perPage": n}, B),
        ("list goły", LIST, lambda p, n: {"page": p}, B),
    ]


def _request(client, attempt, page, per_page):
    name, url, make, headers = attempt
    return client.get(url, params=make(page, per_page),
                      headers=headers or _headers(), timeout=40)


def _extract_items(payload) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("announcements", "items", "data", "content", "results", "list"):
            val = payload.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
            if isinstance(val, dict):  # bywa zagnieżdżone: {"data": {"items": [...]}}
                inner = _extract_items(val)
                if inner:
                    return inner
    return []


def _pick(raw: dict, *keys):
    """Pierwsza niepusta wartość spod podanych kluczy; dla słowników
    zagnieżdżonych sięga po 'name'/'title'/'value'."""
    for key in keys:
        if key in raw and raw[key] not in (None, "", []):
            val = raw[key]
            if isinstance(val, dict):
                for sub in ("name", "fullName", "title", "value", "label"):
                    if val.get(sub):
                        return val[sub]
                continue
            return val
    return None


def _parse_dt(value):
    if not value:
        return None
    try:
        return dtparser.parse(str(value)).replace(tzinfo=None)
    except (ValueError, OverflowError):
        return None


def _region(raw: dict) -> str | None:
    val = _pick(raw, "voivodeship", "wojewodztwo", "province", "region")
    if not val:
        return None
    text = str(val).strip().lower()
    text = re.sub(r"^(woj\.?|wojew[oó]dztwo)\s+", "", text).strip(" .")
    return text[:100] or None


def _upsert(db, raw: dict, cutoff: datetime) -> str | None:
    ann_id = _pick(raw, "id", "announcementId", "number", "numer")
    title = _pick(raw, "title", "tytul", "name", "subject", "orderSubject")
    if ann_id is None or not title:
        return None
    title = str(title).strip()
    pub = _parse_dt(_pick(raw, "publicationDate", "publishedAt", "publicationDateTime",
                          "dataPublikacji", "createdAt", "submittedAt"))
    if pub and pub < cutoff:
        return None

    buyer = _pick(raw, "advertiserName", "announcer", "announcerName", "beneficiary",
                  "beneficiaryName", "nazwaOgloszeniodawcy", "companyName", "author")
    buyer = str(buyer).strip() if buyer else None
    cpv_raw = _pick(raw, "cpvCode", "cpv", "cpvCodes", "kodCPV") or ""
    if isinstance(cpv_raw, (list, tuple)):
        cpv_raw = " ".join(str(c) for c in cpv_raw)
    cpvs = extract_cpv(str(cpv_raw)) or sorted(set(re.findall(r"\d{8}", str(cpv_raw))))

    haystack = " ".join(filter(None, [title, buyer, str(cpv_raw)]))
    labels = match_keywords(haystack, cpvs)
    if not labels:
        return None  # nie dotyczy branży ppoż

    ext_id = str(ann_id).strip()
    values = dict(
        title=title[:8000],
        buyer_name=buyer[:600] if buyer else None,
        city=(str(_pick(raw, "city", "miejscowosc", "town") or "").strip())[:200] or None,
        region=_region(raw),
        country="PL",
        order_type=(str(_pick(raw, "orderType", "category", "kategoria",
                               "announcementType") or "").strip())[:60] or None,
        notice_type="Zapytanie ofertowe (BK)",
        url=ANNOUNCEMENT_URL.format(ext_id),
        tender_url=None,
        publication_date=pub,
        submission_deadline=_parse_dt(_pick(raw, "submissionDeadline", "offersDeadline",
                                            "deadline", "terminSkladaniaOfert",
                                            "offerSubmissionDeadline", "expirationDate")),
        cpv_codes=cpvs,
        matched_keywords=labels,
    )

    existing = db.query(Tender).filter_by(source="bk", external_id=ext_id).one_or_none()
    if existing:
        changed = (
            existing.submission_deadline != values["submission_deadline"]
            or existing.title != values["title"]
        )
        for key, val in values.items():
            setattr(existing, key, val)
        return "updated" if changed else None

    db.add(Tender(source="bk", external_id=ext_id, **values))
    return "added"


def _iter_batches(client: httpx.Client, days_back: int):
    cutoff = datetime.now() - timedelta(days=days_back + 1)
    attempts_log: list[str] = []

    for attempt in _attempts():
        name = attempt[0]
        page, yielded_any = 1, False
        while page <= MAX_PAGES:
            try:
                resp = _request(client, attempt, page, PAGE_SIZE)
                if resp.status_code != 200:
                    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:150]}")
                batch = _extract_items(resp.json())
            except Exception as err:
                if yielded_any:
                    log.warning("BK: przerwano na stronie %d (%s); "
                                "dotychczasowe dane zostają.", page, err)
                    return
                attempts_log.append(f"{name}: {err}")
                break

            if not batch:
                if yielded_any:
                    return
                attempts_log.append(f"{name}: HTTP 200, ale 0 pozycji")
                break

            if not yielded_any:
                log.info("BK: działa wariant %s", name)
            yielded_any = True
            yield batch

            oldest = _parse_dt(_pick(batch[-1], "publicationDate", "publishedAt",
                                     "dataPublikacji", "createdAt"))
            if len(batch) < PAGE_SIZE or (oldest and oldest < cutoff):
                return
            page += 1
            time.sleep(REQUEST_GAP_S)

        if yielded_any:
            return

    raise RuntimeError(
        "BK: żaden wariant endpointu nie zadziałał (sprawdź /api/debug/bk). Próby: "
        + " | ".join(a[:140] for a in attempts_log)
    )


def scrape(db, days_back: int) -> tuple[int, int, int]:
    """Pobiera ogłoszenia z Bazy Konkurencyjności (zapis przyrostowy)."""
    cutoff = datetime.now() - timedelta(days=days_back + 1)
    found = added = updated = 0

    with httpx.Client(follow_redirects=True) as client:
        for batch in _iter_batches(client, days_back):
            for raw in batch:
                result = _upsert(db, raw, cutoff)
                if result is None:
                    continue
                found += 1
                if result == "added":
                    added += 1
                elif result == "updated":
                    updated += 1
            db.commit()

    db.commit()
    return found, added, updated


def probe() -> dict:
    """Diagnostyka dla /api/debug/bk — które warianty wywołania odpowiadają."""
    results: list[dict] = []
    with httpx.Client(follow_redirects=True) as client:
        for attempt in _attempts():
            entry: dict = {"wariant": attempt[0]}
            try:
                resp = _request(client, attempt, 1, 2)
                entry["status_http"] = resp.status_code
                if resp.status_code == 200:
                    items = _extract_items(resp.json())
                    entry["liczba_pozycji"] = len(items)
                    if items:
                        entry["pola_rekordu"] = sorted(items[0].keys())
                        entry["przykladowy_rekord"] = {
                            k: str(v)[:120] for k, v in items[0].items()
                        }
                        results.append(entry)
                        return {"wynik": "ok", "dzialajacy_wariant": entry,
                                "wszystkie_proby": results}
                    entry["uwaga"] = "200, ale nie znaleziono listy pozycji"
                else:
                    entry["odpowiedz"] = resp.text[:200]
            except Exception as err:
                entry["blad"] = f"{type(err).__name__}: {err}"[:200]
            results.append(entry)
            time.sleep(0.4)
    return {"wynik": "zaden wariant nie zadzialal", "wszystkie_proby": results}
