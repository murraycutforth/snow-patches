"""Tests for database initialization and engine creation."""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from data_handler.database import create_db_engine, init_database, get_session_factory


class TestCreateDbEngine:
    """Tests for create_db_engine function."""

    def test_creates_engine_with_in_memory_mode(self):
        """Test that in-memory mode creates a valid SQLite engine."""
        engine = create_db_engine(in_memory=True)

        assert isinstance(engine, Engine)
        assert 'sqlite:///:memory:' in str(engine.url)

    def test_creates_engine_with_file_path(self, tmp_path):
        """Test that file path mode creates engine pointing to file."""
        db_file = tmp_path / "test.db"
        engine = create_db_engine(db_path=str(db_file))

        assert isinstance(engine, Engine)
        assert str(db_file) in str(engine.url)

    def test_echo_parameter_is_respected(self):
        """Test that echo parameter is passed to engine."""
        engine = create_db_engine(in_memory=True, echo=True)
        assert engine.echo is True

        engine = create_db_engine(in_memory=True, echo=False)
        assert engine.echo is False

    def test_requires_either_db_path_or_in_memory(self):
        """Test that either db_path or in_memory must be specified."""
        with pytest.raises(ValueError, match="Either db_path or in_memory must be specified"):
            create_db_engine()

    def test_db_path_and_in_memory_are_mutually_exclusive(self):
        """Test that db_path and in_memory cannot both be specified."""
        with pytest.raises(ValueError, match="Cannot specify both db_path and in_memory"):
            create_db_engine(db_path="test.db", in_memory=True)


class TestInitDatabase:
    """Tests for init_database function."""

    def test_creates_all_tables(self):
        """Test that init_database creates all expected tables."""
        engine = create_db_engine(in_memory=True)
        init_database(engine)

        inspector = inspect(engine)
        tables = inspector.get_table_names()

        assert 'aois' in tables
        assert 'sentinel_products' in tables
        assert 'download_status' in tables
        assert 'snow_masks' in tables

    def test_aois_table_schema(self):
        """Test that aois table has correct columns."""
        engine = create_db_engine(in_memory=True)
        init_database(engine)

        inspector = inspect(engine)
        columns = {col['name']: col for col in inspector.get_columns('aois')}

        assert 'id' in columns
        assert 'name' in columns
        assert 'center_lat' in columns
        assert 'center_lon' in columns
        assert 'geometry' in columns
        assert 'size_km' in columns
        assert 'created_at' in columns

    def test_sentinel_products_table_schema(self):
        """Test that sentinel_products table has correct columns."""
        engine = create_db_engine(in_memory=True)
        init_database(engine)

        inspector = inspect(engine)
        columns = {col['name']: col for col in inspector.get_columns('sentinel_products')}

        assert 'id' in columns
        assert 'product_id' in columns
        assert 'aoi_id' in columns
        assert 'acquisition_dt' in columns
        assert 'cloud_cover' in columns
        assert 'geometry' in columns
        assert 'discovered_at' in columns

    def test_download_status_table_schema(self):
        """Test that download_status table has correct columns."""
        engine = create_db_engine(in_memory=True)
        init_database(engine)

        inspector = inspect(engine)
        columns = {col['name']: col for col in inspector.get_columns('download_status')}

        assert 'id' in columns
        assert 'product_id' in columns
        assert 'status' in columns
        assert 'local_path' in columns
        assert 'file_size_mb' in columns
        assert 'download_start' in columns
        assert 'download_end' in columns
        assert 'error_msg' in columns
        assert 'retry_count' in columns
        assert 'updated_at' in columns

    def test_snow_masks_table_schema(self):
        """Test that snow_masks table has correct columns."""
        engine = create_db_engine(in_memory=True)
        init_database(engine)

        inspector = inspect(engine)
        columns = {col['name']: col for col in inspector.get_columns('snow_masks')}

        assert 'id' in columns
        assert 'product_id' in columns
        assert 'ndsi_threshold' in columns
        assert 'snow_pixels' in columns
        assert 'total_pixels' in columns
        assert 'snow_pct' in columns
        assert 'mask_path' in columns
        assert 'processing_dt' in columns


class TestForeignKeyConstraints:
    """Tests for foreign key constraints."""

    def test_foreign_keys_are_enabled(self):
        """Test that SQLite foreign key constraints are enabled."""
        engine = create_db_engine(in_memory=True)
        init_database(engine)

        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA foreign_keys"))
            fk_status = result.fetchone()[0]
            assert fk_status == 1, "Foreign keys should be enabled"


class TestGetSessionFactory:
    """Tests for get_session_factory function."""

    def test_returns_sessionmaker(self):
        """Test that get_session_factory returns a sessionmaker."""
        engine = create_db_engine(in_memory=True)
        init_database(engine)

        session_factory = get_session_factory(engine)
        session = session_factory()

        # Should be able to execute a simple query
        result = session.execute(text("SELECT 1"))
        assert result.fetchone()[0] == 1

        session.close()

    def test_session_is_bound_to_engine(self):
        """Test that created sessions are bound to the correct engine."""
        engine = create_db_engine(in_memory=True)
        init_database(engine)

        session_factory = get_session_factory(engine)
        session = session_factory()

        assert session.bind == engine

        session.close()
