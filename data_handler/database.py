"""Database engine and session management."""

from sqlalchemy import create_engine, event, Engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Optional


def create_db_engine(
    db_path: Optional[str] = None,
    echo: bool = False,
    in_memory: bool = False
) -> Engine:
    """Create SQLAlchemy engine for SQLite database.

    Args:
        db_path: Path to SQLite database file. If None, must use in_memory=True.
        echo: If True, SQL statements will be logged to stdout.
        in_memory: If True, creates an in-memory database (for testing).

    Returns:
        SQLAlchemy Engine instance.

    Raises:
        ValueError: If neither db_path nor in_memory is specified, or if both are specified.

    Examples:
        >>> # Create file-based database
        >>> engine = create_db_engine(db_path='data/snow_patches.db')

        >>> # Create in-memory database for testing
        >>> engine = create_db_engine(in_memory=True)
    """
    # Validate parameters
    if not db_path and not in_memory:
        raise ValueError("Either db_path or in_memory must be specified")

    if db_path and in_memory:
        raise ValueError("Cannot specify both db_path and in_memory")

    # Construct database URL
    if in_memory:
        db_url = "sqlite:///:memory:"
    else:
        db_url = f"sqlite:///{db_path}"

    # Create engine
    engine = create_engine(db_url, echo=echo)

    # Enable foreign key constraints (SQLite disables by default)
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def init_database(engine: Engine) -> None:
    """Initialize database by creating all tables.

    This function creates all tables defined in the ORM models.
    It is idempotent - safe to call multiple times.

    Args:
        engine: SQLAlchemy Engine instance.

    Examples:
        >>> engine = create_db_engine(db_path='data/snow_patches.db')
        >>> init_database(engine)
    """
    from data_handler.models import Base

    Base.metadata.create_all(engine)


def get_session_factory(engine: Engine) -> sessionmaker:
    """Get a sessionmaker factory bound to the given engine.

    Args:
        engine: SQLAlchemy Engine instance.

    Returns:
        sessionmaker that creates Session instances.

    Examples:
        >>> engine = create_db_engine(db_path='data/snow_patches.db')
        >>> init_database(engine)
        >>> SessionFactory = get_session_factory(engine)
        >>> session = SessionFactory()
        >>> # ... use session ...
        >>> session.close()
    """
    return sessionmaker(bind=engine)
