"""
Database engine and session management for the Salon Payments Ops platform.
Supports local SQLite development and PostgreSQL (e.g. Cloud SQL) in production.
"""

import os
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session
from .models import Base

DEFAULT_DB_URL = os.getenv("DATABASE_URL", "sqlite:///./salon_payments.db")


def get_engine(db_url: str = DEFAULT_DB_URL) -> Engine:
    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(db_url, connect_args=connect_args)


_engine: Engine = get_engine()
SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def init_db(engine: Engine = _engine) -> None:
    """Create all tables if they do not exist."""
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_db_session(engine: Engine = _engine) -> Generator[Session, None, None]:
    """Provide a transactional database session."""
    session = Session(bind=engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
