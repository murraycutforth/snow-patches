"""Tests for discovery.py database integration functions."""

import pytest
import json
from datetime import datetime
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon
from data_handler.database import create_db_engine, init_database, get_session_factory
from data_handler.discovery import seed_aois_from_geodataframe, save_products_to_db
from data_handler.repositories import AOIRepository, SentinelProductRepository
from data_handler.aoi import get_aois


@pytest.fixture
def db_session():
    """Create an in-memory database session for testing."""
    engine = create_db_engine(in_memory=True)
    init_database(engine)
    SessionFactory = get_session_factory(engine)
    session = SessionFactory()
    yield session
    session.close()


@pytest.fixture
def sample_geodataframe():
    """Create a sample GeoDataFrame similar to output from aoi.py."""
    data = {
        'name': ['Ben Nevis', 'Ben Macdui'],
        'geometry': [
            Polygon([(-5.1, 56.7), (-4.9, 56.7), (-4.9, 56.9), (-5.1, 56.9), (-5.1, 56.7)]),
            Polygon([(-3.7, 57.0), (-3.6, 57.0), (-3.6, 57.1), (-3.7, 57.1), (-3.7, 57.0)])
        ]
    }
    return gpd.GeoDataFrame(data, crs="EPSG:4326")


@pytest.fixture
def sample_products_df():
    """Create a sample products DataFrame similar to output from find_sentinel_products."""
    return pd.DataFrame([
        {
            'id': 'item_1',
            'product_id': 'S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219',
            'date': pd.Timestamp('2024-01-15 11:33:21'),
            'cloud_cover': 15.5,
            'geometry': {'type': 'Polygon', 'coordinates': [[[-5.1, 56.7], [-4.9, 56.7], [-4.9, 56.9], [-5.1, 56.9], [-5.1, 56.7]]]}
        },
        {
            'id': 'item_2',
            'product_id': 'S2A_MSIL2A_20240120T113321_N0510_R080_T30VVJ_20240120T145219',
            'date': pd.Timestamp('2024-01-20 11:33:21'),
            'cloud_cover': 25.0,
            'geometry': {'type': 'Polygon', 'coordinates': [[[-5.1, 56.7], [-4.9, 56.7], [-4.9, 56.9], [-5.1, 56.9], [-5.1, 56.7]]]}
        }
    ])


class TestSeedAoisFromGeoDataFrame:
    """Tests for seed_aois_from_geodataframe function."""

    def test_seeds_aois_from_geodataframe(self, db_session, sample_geodataframe):
        """Test that AOIs are correctly seeded from GeoDataFrame."""
        created, skipped = seed_aois_from_geodataframe(db_session, sample_geodataframe)

        assert created == 2
        assert skipped == 0

        # Verify AOIs are in database
        aoi_repo = AOIRepository(db_session)
        all_aois = aoi_repo.get_all()

        assert len(all_aois) == 2
        assert set(a.name for a in all_aois) == {'Ben Nevis', 'Ben Macdui'}

    def test_extracts_center_coordinates_from_geometry(self, db_session, sample_geodataframe):
        """Test that center coordinates are correctly extracted from geometry."""
        seed_aois_from_geodataframe(db_session, sample_geodataframe)

        aoi_repo = AOIRepository(db_session)
        ben_nevis = aoi_repo.get_by_name('Ben Nevis')

        # Center should be approximately the centroid
        assert ben_nevis.center_lat is not None
        assert ben_nevis.center_lon is not None
        # Rough check that center is within bounds
        assert 56.7 < ben_nevis.center_lat < 56.9
        assert -5.1 < ben_nevis.center_lon < -4.9

    def test_stores_geometry_as_wkt(self, db_session, sample_geodataframe):
        """Test that geometry is stored as WKT string."""
        seed_aois_from_geodataframe(db_session, sample_geodataframe)

        aoi_repo = AOIRepository(db_session)
        ben_nevis = aoi_repo.get_by_name('Ben Nevis')

        # Should be a WKT string starting with "POLYGON"
        assert isinstance(ben_nevis.geometry, str)
        assert ben_nevis.geometry.startswith('POLYGON')

    def test_skips_existing_aois(self, db_session, sample_geodataframe):
        """Test that existing AOIs are not duplicated."""
        # First seed
        created1, skipped1 = seed_aois_from_geodataframe(db_session, sample_geodataframe)
        assert created1 == 2
        assert skipped1 == 0

        # Try to seed again
        created2, skipped2 = seed_aois_from_geodataframe(db_session, sample_geodataframe)
        assert created2 == 0
        assert skipped2 == 2

        # Should still only have 2 AOIs
        aoi_repo = AOIRepository(db_session)
        assert len(aoi_repo.get_all()) == 2

    def test_works_with_real_aoi_data(self, db_session):
        """Test with actual AOI data from aoi.py."""
        aois_gdf = get_aois()
        created, skipped = seed_aois_from_geodataframe(db_session, aois_gdf)

        assert created == 2
        assert skipped == 0

        # Verify structure matches expected
        aoi_repo = AOIRepository(db_session)
        ben_nevis = aoi_repo.get_by_name('Ben Nevis')

        assert ben_nevis is not None
        assert ben_nevis.size_km == 10.0
        assert 56.0 < ben_nevis.center_lat < 57.0
        assert -6.0 < ben_nevis.center_lon < -4.0


class TestSaveProductsToDb:
    """Tests for save_products_to_db function."""

    def test_saves_products_to_database(self, db_session, sample_geodataframe, sample_products_df):
        """Test that products are correctly saved to database."""
        # First seed AOI
        seed_aois_from_geodataframe(db_session, sample_geodataframe)

        # Save products
        created, skipped = save_products_to_db(db_session, sample_products_df, 'Ben Nevis')

        assert created == 2
        assert skipped == 0

        # Verify products in database
        aoi_repo = AOIRepository(db_session)
        product_repo = SentinelProductRepository(db_session)

        ben_nevis = aoi_repo.get_by_name('Ben Nevis')
        products = product_repo.get_by_aoi(ben_nevis.id)

        assert len(products) == 2

    def test_converts_date_to_datetime(self, db_session, sample_geodataframe, sample_products_df):
        """Test that pandas Timestamp is converted to datetime."""
        seed_aois_from_geodataframe(db_session, sample_geodataframe)
        save_products_to_db(db_session, sample_products_df, 'Ben Nevis')

        product_repo = SentinelProductRepository(db_session)
        product = product_repo.get_by_product_id(
            'S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219'
        )

        assert isinstance(product.acquisition_dt, datetime)
        assert product.acquisition_dt.year == 2024
        assert product.acquisition_dt.month == 1
        assert product.acquisition_dt.day == 15

    def test_converts_geometry_to_json_string(self, db_session, sample_geodataframe, sample_products_df):
        """Test that geometry dict is converted to JSON string."""
        seed_aois_from_geodataframe(db_session, sample_geodataframe)
        save_products_to_db(db_session, sample_products_df, 'Ben Nevis')

        product_repo = SentinelProductRepository(db_session)
        product = product_repo.get_by_product_id(
            'S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219'
        )

        # Should be stored as JSON string
        assert isinstance(product.geometry, str)
        # Should be valid JSON
        geometry_dict = json.loads(product.geometry)
        assert geometry_dict['type'] == 'Polygon'

    def test_skips_duplicate_products(self, db_session, sample_geodataframe, sample_products_df):
        """Test that duplicate products are not created."""
        seed_aois_from_geodataframe(db_session, sample_geodataframe)

        # First save
        created1, skipped1 = save_products_to_db(db_session, sample_products_df, 'Ben Nevis')
        assert created1 == 2
        assert skipped1 == 0

        # Try to save again
        created2, skipped2 = save_products_to_db(db_session, sample_products_df, 'Ben Nevis')
        assert created2 == 0
        assert skipped2 == 2

        # Should still only have 2 products
        aoi_repo = AOIRepository(db_session)
        product_repo = SentinelProductRepository(db_session)
        ben_nevis = aoi_repo.get_by_name('Ben Nevis')
        assert len(product_repo.get_by_aoi(ben_nevis.id)) == 2

    def test_raises_error_if_aoi_not_found(self, db_session, sample_products_df):
        """Test that ValueError is raised if AOI doesn't exist."""
        with pytest.raises(ValueError, match="AOI 'Non-existent' not found"):
            save_products_to_db(db_session, sample_products_df, 'Non-existent')

    def test_handles_empty_dataframe(self, db_session, sample_geodataframe):
        """Test that empty DataFrame is handled gracefully."""
        seed_aois_from_geodataframe(db_session, sample_geodataframe)

        empty_df = pd.DataFrame(columns=['id', 'product_id', 'date', 'cloud_cover', 'geometry'])
        created, skipped = save_products_to_db(db_session, empty_df, 'Ben Nevis')

        assert created == 0
        assert skipped == 0
