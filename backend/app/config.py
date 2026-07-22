"""Konfiguracja aplikacji — wartości nadpisywane zmiennymi środowiskowymi."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Baza danych. Na Render podstawiana automatycznie z render.yaml.
    # Lokalnie, bez PostgreSQL, używany jest plik SQLite.
    database_url: str = "sqlite:///./ppoz_local.db"

    # Token chroniący endpoint POST /api/scrape (pusty = brak ochrony, tylko dev).
    scrape_token: str = ""

    # Harmonogram automatycznego pobierania (2x dziennie, czas PL).
    enable_scheduler: bool = True

    # Przy pustej bazie: pobierz dane z ostatnich N dni zaraz po starcie.
    auto_bootstrap: bool = True
    bootstrap_days_back: int = 14

    # Ile dni wstecz sprawdzać przy cyklicznym pobieraniu.
    scrape_days_back: int = 3

    # Eksperymentalne źródło TED (przetargi UE powyżej progów).
    enable_ted: bool = False

    # CORS — lista originów rozdzielona przecinkami albo "*".
    cors_origins: str = "*"

    # Uczciwy User-Agent — dobra praktyka wobec API publicznych.
    # Podmień adres e-mail na własny kontakt.
    user_agent: str = "PPOZ-Monitor/1.0 (monitoring przetargow ppoz; kontakt: twoj@email.pl)"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
