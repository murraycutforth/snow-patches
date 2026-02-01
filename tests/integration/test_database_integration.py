"""Integration tests for database with file-based storage.

These tests use a real SQLite file (in a temp directory) to test
the full database workflow end-to-end.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from data_handler.database import create_db_engine, init_database, get_session_factory
from data_handler.aoi import get_aois
from data_handler.discovery import seed_aois_from_geodataframe
from data_handler.repositories import AOIRepository, SentinelProductRepository


@pytest.mark.integration
class TestDatabaseFileIntegration:
    """Integration tests using file-based database."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary directory for test database."""
        temp_dir = tempfile.mkdtemp()
        db_path = Path(temp_dir) / "test_snow_patches.db"
        yield db_path
        # Cleanup
        shutil.rmtree(temp_dir)

    def test_full_database_workflow(self, temp_db_path):
        """Test complete workflow: init -> seed AOIs -> query."""
        # Initialize database
        engine = create_db_engine(db_path=str(temp_db_path))
        init_database(engine)

        # Verify database file was created
        assert temp_db_path.exists()

        # Create session
        SessionFactory = get_session_factory(engine)
        session = SessionFactory()

        try:
            # Seed AOIs
            aois_gdf = get_aois()
            created, skipped = seed_aois_from_geodataframe(session, aois_gdf)

            assert created == 2
            assert skipped == 0

            # Query AOIs
            aoi_repo = AOIRepository(session)
            all_aois = aoi_repo.get_all()

            assert len(all_aois) == 2
            assert set(a.name for a in all_aois) == {'Ben Nevis', 'Ben Macdui'}

            # Verify AOI data
            ben_nevis = aoi_repo.get_by_name('Ben Nevis')
            assert ben_nevis is not None
            assert ben_nevis.center_lat == pytest.approx(56.7969, abs=0.01)
            assert ben_nevis.center_lon == pytest.approx(-5.0036, abs=0.01)
            assert ben_nevis.size_km == 10.0

        finally:
            session.close()

    def test_database_persistence(self, temp_db_path):
        """Test that data persists across sessions."""
        # First session: create and seed
        engine = create_db_engine(db_path=str(temp_db_path))
        init_database(engine)

        SessionFactory = get_session_factory(engine)
        session1 = SessionFactory()

        aois_gdf = get_aois()
        seed_aois_from_geodataframe(session1, aois_gdf)
        session1.close()

        # Second session: verify data persists
        session2 = SessionFactory()
        try:
            aoi_repo = AOIRepository(session2)
            all_aois = aoi_repo.get_all()

            assert len(all_aois) == 2
            assert set(a.name for a in all_aois) == {'Ben Nevis', 'Ben Macdui'}
        finally:
            session2.close()

    def test_product_workflow_without_discovery(self, temp_db_path):
        """Test product repository with mock data (no API calls)."""
        # Initialize and seed
        engine = create_db_engine(db_path=str(temp_db_path))
        init_database(engine)

        SessionFactory = get_session_factory(engine)
        session = SessionFactory()

        try:
            # Seed AOIs
            aois_gdf = get_aois()
            seed_aois_from_geodataframe(session, aois_gdf)

            # Get Ben Nevis AOI
            aoi_repo = AOIRepository(session)
            ben_nevis = aoi_repo.get_by_name('Ben Nevis')

            # Create mock products
            product_repo = SentinelProductRepository(session)

            product1 = product_repo.create(
                product_id='S2A_TEST_PRODUCT_1',
                aoi_id=ben_nevis.id,
                acquisition_dt=datetime(2024, 1, 15, 11, 30, 0),
                cloud_cover=15.5,
                geometry='{"type": "Polygon", "coordinates": []}'
            )

            product2 = product_repo.create(
                product_id='S2A_TEST_PRODUCT_2',
                aoi_id=ben_nevis.id,
                acquisition_dt=datetime(2024, 1, 20, 11, 30, 0),
                cloud_cover=5.0,
                geometry='{"type": "Polygon", "coordinates": []}'
            )

            # Query products
            all_products = product_repo.get_by_aoi(ben_nevis.id)
            assert len(all_products) == 2

            # Query with filters
            clear_products = product_repo.get_by_aoi(
                ben_nevis.id,
                max_cloud_cover=10.0
            )
            assert len(clear_products) == 1
            assert clear_products[0].cloud_cover == 5.0

            date_filtered = product_repo.get_by_aoi(
                ben_nevis.id,
                start_date=datetime(2024, 1, 18),
                end_date=datetime(2024, 1, 31)
            )
            assert len(date_filtered) == 1
            assert date_filtered[0].acquisition_dt.day == 20

        finally:
            session.close()

    def test_foreign_key_constraints_enforced(self, temp_db_path):
        """Test that foreign key constraints are properly enforced."""
        engine = create_db_engine(db_path=str(temp_db_path))
        init_database(engine)

        SessionFactory = get_session_factory(engine)
        session = SessionFactory()

        try:
            product_repo = SentinelProductRepository(session)

            # Try to create product with non-existent AOI
            from sqlalchemy.exc import IntegrityError
            with pytest.raises(IntegrityError):
                product_repo.create(
                    product_id='S2A_TEST_PRODUCT',
                    aoi_id=999,  # Non-existent AOI
                    acquisition_dt=datetime(2024, 1, 15),
                    cloud_cover=10.0,
                    geometry='{}'
                )

        finally:
            session.close()

    def test_idempotent_initialization(self, temp_db_path):
        """Test that init_database can be called multiple times safely."""
        engine = create_db_engine(db_path=str(temp_db_path))

        # First initialization
        init_database(engine)

        SessionFactory = get_session_factory(engine)
        session = SessionFactory()

        # Add data
        aois_gdf = get_aois()
        seed_aois_from_geodataframe(session, aois_gdf)
        session.close()

        # Second initialization (should not error or lose data)
        init_database(engine)

        # Verify data still exists
        session = SessionFactory()
        try:
            aoi_repo = AOIRepository(session)
            all_aois = aoi_repo.get_all()
            assert len(all_aois) == 2
        finally:
            session.close()
