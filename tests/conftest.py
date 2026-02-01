"""Shared pytest fixtures for all tests."""

import pytest
from data_handler.database import create_db_engine, init_database, get_session_factory
from data_handler.repositories import AOIRepository


@pytest.fixture
def in_memory_db():
    """Create an in-memory database engine with initialized schema.

    This fixture provides a fresh in-memory SQLite database for each test.
    The database is automatically cleaned up after the test completes.

    Returns:
        SQLAlchemy Engine instance with all tables created

    Example:
        >>> def test_something(in_memory_db):
        ...     SessionFactory = get_session_factory(in_memory_db)
        ...     session = SessionFactory()
        ...     # ... use session ...
        ...     session.close()
    """
    engine = create_db_engine(in_memory=True)
    init_database(engine)
    return engine


@pytest.fixture
def db_with_aois(in_memory_db):
    """Create an in-memory database pre-populated with AOIs.

    This fixture extends in_memory_db by seeding it with the two standard
    AOIs (Ben Nevis and Ben Macdui) from the aoi module.

    Returns:
        Tuple of (engine, session) where session has AOIs already created

    Example:
        >>> def test_something(db_with_aois):
        ...     engine, session = db_with_aois
        ...     aoi_repo = AOIRepository(session)
        ...     ben_nevis = aoi_repo.get_by_name('Ben Nevis')
        ...     # ... use AOIs ...
        ...     session.close()
    """
    from data_handler.aoi import get_aois
    from data_handler.discovery import seed_aois_from_geodataframe

    SessionFactory = get_session_factory(in_memory_db)
    session = SessionFactory()

    # Seed AOIs
    aois_gdf = get_aois()
    seed_aois_from_geodataframe(session, aois_gdf)

    yield in_memory_db, session

    # Cleanup
    session.close()
