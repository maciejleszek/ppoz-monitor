# PPOŻ Monitor

Monitoring zamówień publicznych dla firm z branży **ochrony przeciwpożarowej** — aplikacja w duchu serwisów typu oferty-biznesowe.pl czy eurobudowa.pl, ale zbudowana na własnych, oficjalnych źródłach danych.

Codziennie pobiera ogłoszenia o zamówieniach z **Biuletynu Zamówień Publicznych** (oficjalne, publiczne API platformy e-Zamówienia prowadzonej przez UZP), filtruje je słownikiem branżowym PPOŻ (SSP, oddymianie, hydranty, gaśnice, DSO, kody CPV itd.) i prezentuje w przejrzystym panelu z wyszukiwarką, filtrami województw i terminami składania ofert.

**Stack:** React (Vite) · Python (FastAPI + SQLAlchemy + APScheduler) · PostgreSQL

## Struktura projektu

```
.
├── render.yaml              # blueprint wdrożenia na render.com
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py          # API: /api/tenders, /api/stats, /api/scrape…
│       ├── config.py        # konfiguracja (zmienne środowiskowe)
│       ├── database.py      # PostgreSQL (Render) / SQLite (lokalnie)
│       ├── models.py        # tabele: tenders, scrape_runs
│       ├── schemas.py
│       ├── scheduler.py     # automatyczne pobieranie 2× dziennie
│       └── scraper/
│           ├── keywords.py     # ★ słownik branżowy PPOŻ — tu dodajesz hasła
│           ├── ezamowienia.py  # źródło główne: API BZP (e-Zamówienia)
│           ├── ted.py          # źródło eksperymentalne: TED (przetargi UE)
│           └── runner.py
└── frontend/                # React + Vite
    └── src/…
```

## Uruchomienie lokalne

Backend (bez PostgreSQL — automatycznie użyje pliku SQLite):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Przy pustej bazie backend sam pobierze ogłoszenia z ostatnich 14 dni (potrwa to 1–3 min; postęp widać w logach oraz pod `GET /api/stats`). Dokumentacja API: http://localhost:8000/docs

Frontend (w drugim terminalu):

```bash
cd frontend
npm install
npm run dev
```

Aplikacja: http://localhost:5173 (zapytania `/api` idą przez proxy Vite do backendu — nic więcej nie konfigurujesz).

## Wdrożenie na render.com

1. Wgraj projekt do repozytorium na GitHub/GitLab.
2. W panelu Render: **New + → Blueprint**, wskaż repozytorium. Render odczyta `render.yaml` i utworzy trzy zasoby: bazę PostgreSQL `ppoz-monitor-db`, backend `ppoz-monitor-api` i frontend `ppoz-monitor`.
3. Zatwierdź — po kilku minutach frontend będzie dostępny pod adresem `https://ppoz-monitor.onrender.com` (lub podobnym), a przy pierwszym starcie backend sam zasili bazę danymi z ostatnich 14 dni.

Ważne informacje o **planie darmowym** Render: darmowa baza PostgreSQL **wygasa po 30 dniach** (do stałego użytku potrzebny jest płatny plan bazy, od ok. 7 USD/mies.), a darmowy web service **usypia po ~15 min bezczynności** — wtedy nie działa też wbudowany harmonogram pobierania. Prosty obejście: zewnętrzny darmowy cron (np. cron-job.org albo UptimeRobot), który (a) co 10 minut odpytuje `GET https://ppoz-monitor-api.onrender.com/api/health` (utrzymuje usługę przy życiu), (b) 1–2× dziennie wywołuje pobieranie:

```bash
curl -X POST "https://ppoz-monitor-api.onrender.com/api/scrape?days_back=3" \
     -H "X-Scrape-Token: TWÓJ_TOKEN"
```

Token znajdziesz w panelu Render: usługa `ppoz-monitor-api` → Environment → `SCRAPE_TOKEN` (Render generuje go automatycznie).

## Konfiguracja (zmienne środowiskowe backendu)

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `DATABASE_URL` | SQLite lokalnie | Na Render podstawiana z bazy przez `render.yaml`. |
| `SCRAPE_TOKEN` | puste | Token chroniący `POST /api/scrape`. |
| `ENABLE_SCHEDULER` | `true` | Automatyczne pobieranie o 06:20 i 13:20 czasu PL. |
| `AUTO_BOOTSTRAP` | `true` | Przy pustej bazie pobierz od razu ostatnie 14 dni. |
| `SCRAPE_DAYS_BACK` | `3` | Zakres dni przy pobieraniu cyklicznym. |
| `ENABLE_TED` | `false` | Eksperymentalne źródło TED (przetargi unijne). |
| `CORS_ORIGINS` | `*` | Po wdrożeniu warto wpisać adres frontendu. |
| `USER_AGENT` | patrz config.py | Podmień e-mail kontaktowy na własny. |

## Dopasowanie do własnej oferty

Serce aplikacji to plik **`backend/app/scraper/keywords.py`** — listy haseł (dopasowywanych bez względu na wielkość liter i polskie znaki) oraz prefiksów kodów CPV. Dodanie własnej specjalizacji to dopisanie jednej linii, np. `("przepust instalacyjn", "przepusty ppoż")`. Po zmianie słownika wywołaj `POST /api/scrape?days_back=30`, żeby przefiltrować szerszy okres na nowo.

## Główne endpointy API

- `GET /api/tenders?q=&region=&source=&active_only=&sort=&page=` — lista z filtrami i paginacją,
- `GET /api/tenders/{id}` — szczegóły ogłoszenia,
- `GET /api/stats` — liczniki + status ostatniego pobierania,
- `GET /api/regions` — województwa występujące w bazie,
- `POST /api/scrape?days_back=N` — ręczne pobieranie (nagłówek `X-Scrape-Token`),
- `GET /docs` — interaktywna dokumentacja (Swagger).

## Źródła danych, prawo i dobre praktyki

- Źródłem głównym jest **oficjalne API odczytu ogłoszeń BZP** (`https://ezamowienia.gov.pl/mo-board/api/v1/notice`). Zgodnie z informacją UZP odczyt ogłoszeń krajowych **nie wymaga rejestracji ani klucza**, a jawność ogłoszeń wynika wprost z Prawa zamówień publicznych — to w pełni legalne źródło do budowy takiego serwisu.
- Scraper działa kulturalnie: identyfikuje się uczciwym `User-Agent` (ustaw swój e-mail w `config.py`), robi przerwy między zapytaniami i pobiera tylko potrzebny zakres dat. Zachowaj te zasady przy rozbudowie.
- **Nie kopiuj danych z komercyjnych agregatorów** (np. eurobudowa.pl, oferty-biznesowe.pl) — ich bazy są chronione (m.in. ochrona baz danych sui generis, regulaminy serwisów). Wzoruj się na funkcjach, ale dane pobieraj ze źródeł publicznych.
- Moduł TED korzysta z publicznego Search API v3 (`api.ted.europa.eu`); jest oznaczony jako eksperymentalny — przed włączeniem (`ENABLE_TED=true`) zweryfikuj nazwy pól z aktualną dokumentacją TED.

## Pomysły na rozbudowę

Plany postępowań publikowane na e-Zamówieniach (zapowiedzi przyszłych przetargów), rejestry pozwoleń na budowę GUNB jako leady inwestycyjne (dane otwarte), powiadomienia e-mail o nowych ogłoszeniach pasujących do zapisanych filtrów, konta użytkowników i zapisane wyszukiwania, eksport CSV/XLSX.
