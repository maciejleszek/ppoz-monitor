"""Modele: Tender (ogłoszenie) i ScrapeRun (log pobierania)."""

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)

from .database import Base


class Tender(Base):
    __tablename__ = "tenders"

    id = Column(Integer, primary_key=True)

    source = Column(String(20), nullable=False, index=True)  # "bzp" | "ted"
    external_id = Column(String(160), nullable=False)  # np. numer ogłoszenia BZP

    title = Column(Text, nullable=False)  # przedmiot zamówienia
    description = Column(Text)  # dłuższy opis (jeśli źródło go daje)

    buyer_name = Column(String(600))  # zamawiający
    city = Column(String(200))
    region = Column(String(100), index=True)  # województwo (małymi literami)
    country = Column(String(10), default="PL")

    order_type = Column(String(60))  # Roboty budowlane / Dostawy / Usługi
    notice_type = Column(String(80))  # rodzaj ogłoszenia w źródle

    url = Column(Text)  # link do treści ogłoszenia
    tender_url = Column(Text)  # link do strony postępowania (jeśli jest)

    publication_date = Column(DateTime, index=True)
    submission_deadline = Column(DateTime, index=True)  # termin składania ofert

    value_amount = Column(Numeric(18, 2))  # szacunkowa wartość (rzadko podawana)
    value_currency = Column(String(10))

    cpv_codes = Column(JSON, default=list)  # np. ["45343000-3"]
    matched_keywords = Column(JSON, default=list)  # dopasowane hasła branżowe

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_tender_source_ext"),
    )


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id = Column(Integer, primary_key=True)
    source = Column(String(20), nullable=False)
    started_at = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime)
    status = Column(String(20), default="running")  # running | ok | error
    found = Column(Integer, default=0)  # ile ogłoszeń pasowało do branży
    added = Column(Integer, default=0)
    updated = Column(Integer, default=0)
    message = Column(Text)
