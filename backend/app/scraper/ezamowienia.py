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
import re
import time
from datetime import datetime, timedelta

import httpx
from dateutil import parser as dtparser

from ..config import settings
from ..models import Tender
from .keywords import extract_cpv, match_keywords, normalize

log = logging.getLogger("scraper.bzp")

API_URL = "https://ezamowienia.gov.pl/mo-board/api/v1/notice"
NOTICE_DETAILS = "https://ezamowienia.gov.pl/mo-client-board/bzp/notice-details/id/{}"
TENDER_PAGE = "https://ezamowienia.gov.pl/mp-client/search/list/{}"
FALLBACK_URL = "https://ezamowienia.gov.pl/mo-client-board/bzp/list"

# Interesują nas ogłoszenia o wszczęciu postępowania.
NOTICE_TYPES = ["ContractNotice"]

PAGE_SIZE = 50
MAX_PAGES = 400         # bezpiecznik; realnie przerywamy po dacie granicznej
REQUEST_GAP_S = 0.7     # przerwa między stronami — nie obciążamy API


class _BadParams(Exception):
    pass


# ── Województwa: normalizacja do kanonicznych nazw ──────────────────────────
# API bywa niekonsekwentne (wielkie litery, brak polskich znaków, prefiks
# "woj.", czasem kod TERYT), więc sprowadzamy wszystko do 16 nazw wzorcowych.

VOIVODESHIPS = [
    "dolnośląskie", "kujawsko-pomorskie", "lubelskie", "lubuskie",
    "łódzkie", "małopolskie", "mazowieckie", "opolskie",
    "podkarpackie", "podlaskie", "pomorskie", "śląskie",
    "świętokrzyskie", "warmińsko-mazurskie", "wielkopolskie",
    "zachodniopomorskie",
]
_REGION_LOOKUP = {normalize(name): name for name in VOIVODESHIPS}
_TERYT = {
    "02": "dolnośląskie", "04": "kujawsko-pomorskie", "06": "lubelskie",
    "08": "lubuskie", "10": "łódzkie", "12": "małopolskie",
    "14": "mazowieckie", "16": "opolskie", "18": "podkarpackie",
    "20": "podlaskie", "22": "pomorskie", "24": "śląskie",
    "26": "świętokrzyskie", "28": "warmińsko-mazurskie",
    "30": "wielkopolskie", "32": "zachodniopomorskie",
}
_REGION_KEYS = (
    "organizationProvince", "organizationVoivodeship", "organizationRegion",
    "province", "voivodeship", "region",
)


def _region(raw: dict) -> str | None:
    value = next((raw.get(k) for k in _REGION_KEYS if raw.get(k)), None)
    if value is None:
        return None
    text = str(value).strip()
    if text.isdigit():
        return _TERYT.get(text.zfill(2))
    text = re.sub(r"^(woj\.?|wojew[oó]dztwo)\s+", "", text, flags=re.I).strip(" .")
    if not text:
        return None
    return _REGION_LOOKUP.get(normalize(text)) or text.lower()[:100]


BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _header_profiles() -> list[tuple[str, dict]]:
    """Najpierw uczciwy User-Agent; jeśli WAF go odrzuca — profil przeglądarkowy."""
    return [
        ("wlasny-ua", {"Accept": "application/json", "User-Agent": settings.user_agent}),
        (
            "przegladarkowy",
            {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
                "User-Agent": BROWSER_UA,
                "Referer": FALLBACK_URL,
            },
        ),
    ]


def _param_recipes(days_back: int) -> list[tuple[str, dict]]:
    """API bywa wybredne — próbujemy kolejnych wariantów parametrów."""
    d_from = datetime.now() - timedelta(days=days_back)
    d_to = datetime.now() + timedelta(days=1)
    iso = {
        "PublicationDateFrom": d_from.strftime("%Y-%m-%dT00:00:00.000Z"),
        "PublicationDateTo": d_to.strftime("%Y-%m-%dT23:59:59.999Z"),
    }
    plain = {
        "PublicationDateFrom": d_from.strftime("%Y-%m-%d"),
        "PublicationDateTo": d_to.strftime("%Y-%m-%d"),
    }
    sort = {"SortingColumnName": "PublicationDate", "SortingDirection": "DESC"}
    return [
        ("daty-iso+sort", {**iso, **sort}),
        ("daty-proste+sort", {**plain, **sort}),
        ("daty-proste", dict(plain)),
        ("bez-dat+sort", dict(sort)),
        ("bez-parametrow", {}),
    ]


def _parse_dt(value):
    if not value:
        return None
    try:
        return dtparser.parse(str(value)).replace(tzinfo=None)
    except (ValueError, OverflowError):
        return None


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
    attempts: list[str] = []

    for profile_name, headers in _header_profiles():
        for recipe_name, extra in _param_recipes(days_back):
            has_sort = "SortingColumnName" in extra
            has_dates = "PublicationDateFrom" in extra
            # bez sortowania i bez dat nie da się bezpiecznie paginować w głąb
            max_pages = MAX_PAGES if (has_sort or has_dates) else 40
            items: list[dict] = []
            try:
                page = 1
                while page <= max_pages:
                    params = {
                        "NoticeType": notice_type,
                        "PageNumber": page,
                        "PageSize": PAGE_SIZE,
                        **extra,
                    }
                    resp = client.get(API_URL, params=params, headers=headers, timeout=40)
                    if resp.status_code in (400, 403, 422):
                        raise _BadParams(f"HTTP {resp.status_code}: {resp.text[:200]}")
                    resp.raise_for_status()

                    batch = _extract_items(resp.json())
                    if not batch:
                        break
                    items.extend(batch)

                    oldest = _parse_dt(batch[-1].get("publicationDate"))
                    if len(batch) < PAGE_SIZE or (has_sort and oldest and oldest < cutoff):
                        break
                    page += 1
                    time.sleep(REQUEST_GAP_S)

                if not items:
                    # 200 OK, ale zero wyników = najpewniej zignorowane parametry
                    raise _BadParams("HTTP 200, ale 0 wyników")

                log.info(
                    "BZP %s: pobrano %d ogłoszeń (nagłówki=%s, parametry=%s)",
                    notice_type, len(items), profile_name, recipe_name,
                )
                return items
            except (_BadParams, httpx.HTTPError) as err:
                note = f"{profile_name}/{recipe_name}: {err}"
                attempts.append(note)
                log.warning("BZP %s — próba nieudana: %s", notice_type, note[:300])
                continue

    raise RuntimeError(
        "API BZP odrzuciło wszystkie warianty zapytania. Próby: "
        + " | ".join(a[:160] for a in attempts)
    )


def probe() -> dict:
    """Diagnostyka dla /api/debug/bzp — pojedyncze zapytania testowe
    z tego serwera do API BZP, bez zapisu do bazy. Pokazuje kod HTTP,
    fragment odpowiedzi i (przy sukcesie) rzeczywiste pola rekordu."""
    results: list[dict] = []
    with httpx.Client(follow_redirects=True) as client:
        for profile_name, headers in _header_profiles():
            for recipe_name, extra in _param_recipes(3):
                params = {
                    "NoticeType": "ContractNotice",
                    "PageNumber": 1,
                    "PageSize": 1,
                    **extra,
                }
                entry: dict = {"naglowki": profile_name, "parametry": recipe_name}
                try:
                    resp = client.get(API_URL, params=params, headers=headers, timeout=25)
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
                    else:
                        entry["odpowiedz"] = resp.text[:200]
                except Exception as err:  # diagnostyka ma pokazać każdy rodzaj błędu
                    entry["blad"] = f"{type(err).__name__}: {err}"[:200]
                results.append(entry)
                time.sleep(0.4)
    return {"wynik": "zaden wariant nie zadzialal", "wszystkie_proby": results}


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
        region=_region(raw),
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
