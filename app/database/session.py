import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

logger = logging.getLogger("taskforge.database")

# Configure database engine dynamically based on dialect
is_sqlite = settings.DATABASE_URL.startswith("sqlite")

if is_sqlite:
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False
    )
else:
    # PostgreSQL / MySQL with production connection pooling
    engine = create_engine(
        settings.DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_pre_ping=settings.DB_POOL_PRE_PING,
        echo=False
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_sqlite_columns():
    """Lightweight migration helper ensuring newly added columns exist in existing SQLite databases."""
    if not is_sqlite:
        return

    with engine.connect() as conn:
        try:
            # Check approval_requests columns
            res = conn.execute(text("PRAGMA table_info(approval_requests)")).fetchall()
            existing_cols = {row[1] for row in res}
            new_approval_cols = [
                ("requesting_user", "VARCHAR(100) DEFAULT 'operator@taskforge.ai'"),
                ("assigned_reviewer", "VARCHAR(100) DEFAULT 'REVIEWER'"),
                ("risk_level", "VARCHAR(20) DEFAULT 'HIGH'"),
                ("expires_at", "DATETIME"),
                ("execution_status", "VARCHAR(50) DEFAULT 'pending'")
            ]
            for col_name, col_type in new_approval_cols:
                if col_name not in existing_cols and existing_cols:
                    conn.execute(text(f"ALTER TABLE approval_requests ADD COLUMN {col_name} {col_type}"))

            # Check execution_logs columns
            res_logs = conn.execute(text("PRAGMA table_info(execution_logs)")).fetchall()
            log_cols = {row[1] for row in res_logs}
            new_log_cols = [
                ("actor", "VARCHAR(100) DEFAULT 'system'"),
                ("outcome", "VARCHAR(50) DEFAULT 'SUCCESS'")
            ]
            for col_name, col_type in new_log_cols:
                if col_name not in log_cols and log_cols:
                    conn.execute(text(f"ALTER TABLE execution_logs ADD COLUMN {col_name} {col_type}"))

            # Check workflows columns
            res_wfs = conn.execute(text("PRAGMA table_info(workflows)")).fetchall()
            wf_cols = {row[1] for row in res_wfs}
            if "template_id" not in wf_cols and wf_cols:
                conn.execute(text("ALTER TABLE workflows ADD COLUMN template_id VARCHAR(50)"))

            conn.commit()
        except Exception as e:
            logger.debug("SQLite column check skipped or pre-table creation: %s", e)


def init_db():
    from app.database import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns()
