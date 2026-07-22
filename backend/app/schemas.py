"""Schematy odpowiedzi API (Pydantic v2)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TenderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    external_id: str
    title: str
    description: Optional[str] = None
    buyer_name: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    order_type: Optional[str] = None
    notice_type: Optional[str] = None
    url: Optional[str] = None
    tender_url: Optional[str] = None
    publication_date: Optional[datetime] = None
    submission_deadline: Optional[datetime] = None
    value_amount: Optional[float] = None
    value_currency: Optional[str] = None
    cpv_codes: list[str] = []
    matched_keywords: list[str] = []
    created_at: Optional[datetime] = None


class TenderList(BaseModel):
    items: list[TenderOut]
    total: int
    page: int
    pages: int
    page_size: int


class LastRun(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    status: str
    found: int = 0
    added: int = 0
    updated: int = 0
    message: Optional[str] = None


class StatsOut(BaseModel):
    total: int
    new_24h: int
    new_7d: int
    closing_7d: int
    sources: dict[str, int]
    last_run: Optional[LastRun] = None
    last_runs: dict[str, LastRun] = {}
