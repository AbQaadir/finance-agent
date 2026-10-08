"""
Database engine and session management for the Salon Payments Ops platform.
Supports local SQLite development and production PostgreSQL (e.g. Google Cloud SQL)
with enterprise connection pooling and health checks.
"""

import os
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, Engine, text
from sqlalchemy.orm import sessionmaker, Session
from .models import Base
from libs.config import settings


def get_engine(db_url: str = settings.database_url) -> Engine:
    connect_args = {}
    engine_kwargs = {}

    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    elif db_url.startswith("postgresql"):
        # Production PostgreSQL connection pooling parameters
        engine_kwargs["pool_size"] = settings.db_pool_size
        engine_kwargs["max_overflow"] = settings.db_max_overflow
        engine_kwargs["pool_pre_ping"] = True  # Automatically re-connect dead connections
        engine_kwargs["pool_recycle"] = 1800    # Recycle connections after 30 minutes

    return create_engine(
        db_url,
        connect_args=connect_args,
        **engine_kwargs,
    )


_engine: Engine = get_engine()
SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def init_db(engine: Engine = _engine) -> None:
    """Create all tables if they do not exist."""
    Base.metadata.create_all(bind=engine)


def check_db_health(engine: Engine = _engine) -> bool:
    """Readiness probe to verify database connectivity."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


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
