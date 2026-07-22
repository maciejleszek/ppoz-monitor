"""Połączenie z bazą: PostgreSQL na Render, SQLite lokalnie (fallback)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

url = settings.database_url
# Render potrafi zwrócić schemat "postgres://", którego SQLAlchemy 2.x nie przyjmuje.
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}

engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """Zależność FastAPI — sesja na czas jednego żądania."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
