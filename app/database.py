"""Database configuration and request-scoped sessions."""
import os
from collections.abc import Generator
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
_database_url = os.getenv("DATABASE_URL")
if not _database_url:
    raise RuntimeError("Set DATABASE_URL in .env to your Neon PostgreSQL connection string.")

# Neon supplies postgresql:// URLs. Select psycopg 3 explicitly and require TLS.
_url = make_url(_database_url)
if _url.drivername in {"postgres", "postgresql"}:
    _url = _url.set(drivername="postgresql+psycopg")
if _url.drivername.startswith("postgresql") and "sslmode" not in _url.query:
    _url = _url.update_query_dict({"sslmode": "require"})
DATABASE_URL = _url
_connect_args = {"check_same_thread": False} if _url.drivername == "sqlite" else {}

engine = create_engine(
    _url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    pool_recycle=300,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
