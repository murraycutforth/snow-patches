"""Tests for ORM models."""

import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from data_handler.database import create_db_engine, init_database, get_session_factory
from data_handler.models import AOI, SentinelProduct, DownloadStatus, SnowMask


@pytest.fixture
def db_session():
    """Create an in-memory database session for testing."""
    engine = create_db_engine(in_memory=True)
    init_database(engine)
    SessionFactory = get_session_factory(engine)
    session = SessionFactory()
    yield session
    session.close()


class TestAOIModel:
    """Tests for AOI model."""

    def test_create_aoi(self, db_session):
        """Test creating an AOI record."""
        aoi = AOI(
            name="Ben Nevis",
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry="POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))",
            size_km=10.0
        )
        db_session.add(aoi)
        db_session.commit()

        assert aoi.id is not None
        assert aoi.name == "Ben Nevis"
        assert aoi.center_lat == 56.7969
        assert aoi.center_lon == -5.0036
        assert aoi.size_km == 10.0
        assert isinstance(aoi.created_at, datetime)

    def test_aoi_name_is_unique(self, db_session):
        """Test that AOI names must be unique."""
        aoi1 = AOI(
            name="Ben Nevis",
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry="POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))",
            size_km=10.0
        )
        db_session.add(aoi1)
        db_session.commit()

        # Try to create another AOI with the same name
        aoi2 = AOI(
            name="Ben Nevis",  # Duplicate name
            center_lat=57.0,
            center_lon=-5.0,
            geometry="POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))",
            size_km=10.0
        )
        db_session.add(aoi2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_aoi_has_products_relationship(self, db_session):
        """Test that AOI has a relationship to products."""
        aoi = AOI(
            name="Ben Nevis",
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry="POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))",
            size_km=10.0
        )
        db_session.add(aoi)
        db_session.commit()

        # Access the relationship
        assert hasattr(aoi, 'products')
        assert len(aoi.products) == 0  # No products yet


class TestSentinelProductModel:
    """Tests for SentinelProduct model."""

    def test_create_sentinel_product(self, db_session):
        """Test creating a SentinelProduct record."""
        # First create an AOI
        aoi = AOI(
            name="Ben Nevis",
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry="POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))",
            size_km=10.0
        )
        db_session.add(aoi)
        db_session.commit()

        # Create a product
        product = SentinelProduct(
            product_id="S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219",
            aoi_id=aoi.id,
            acquisition_dt=datetime(2024, 1, 15, 11, 33, 21),
            cloud_cover=15.5,
            geometry='{"type": "Polygon", "coordinates": [[[-5.1, 56.7], [-4.9, 56.7], [-4.9, 56.9], [-5.1, 56.9], [-5.1, 56.7]]]}'
        )
        db_session.add(product)
        db_session.commit()

        assert product.id is not None
        assert product.product_id == "S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219"
        assert product.aoi_id == aoi.id
        assert product.cloud_cover == 15.5
        assert isinstance(product.discovered_at, datetime)

    def test_product_id_is_unique(self, db_session):
        """Test that product_id must be unique."""
        # Create AOI
        aoi = AOI(
            name="Ben Nevis",
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry="POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))",
            size_km=10.0
        )
        db_session.add(aoi)
        db_session.commit()

        # Create first product
        product1 = SentinelProduct(
            product_id="S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219",
            aoi_id=aoi.id,
            acquisition_dt=datetime(2024, 1, 15, 11, 33, 21),
            cloud_cover=15.5,
            geometry='{"type": "Polygon", "coordinates": []}'
        )
        db_session.add(product1)
        db_session.commit()

        # Try to create duplicate product_id
        product2 = SentinelProduct(
            product_id="S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219",  # Duplicate
            aoi_id=aoi.id,
            acquisition_dt=datetime(2024, 1, 16, 11, 33, 21),
            cloud_cover=20.0,
            geometry='{"type": "Polygon", "coordinates": []}'
        )
        db_session.add(product2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_product_requires_aoi_foreign_key(self, db_session):
        """Test that SentinelProduct requires a valid AOI."""
        # Try to create product with non-existent AOI
        product = SentinelProduct(
            product_id="S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219",
            aoi_id=999,  # Non-existent AOI
            acquisition_dt=datetime(2024, 1, 15, 11, 33, 21),
            cloud_cover=15.5,
            geometry='{"type": "Polygon", "coordinates": []}'
        )
        db_session.add(product)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_cloud_cover_check_constraint(self, db_session):
        """Test that cloud_cover is constrained to 0-100 range."""
        # Create AOI
        aoi = AOI(
            name="Ben Nevis",
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry="POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))",
            size_km=10.0
        )
        db_session.add(aoi)
        db_session.commit()

        # Try cloud_cover > 100
        product = SentinelProduct(
            product_id="S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219",
            aoi_id=aoi.id,
            acquisition_dt=datetime(2024, 1, 15, 11, 33, 21),
            cloud_cover=150.0,  # Invalid
            geometry='{"type": "Polygon", "coordinates": []}'
        )
        db_session.add(product)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_product_has_aoi_relationship(self, db_session):
        """Test that SentinelProduct has relationship to AOI."""
        # Create AOI and product
        aoi = AOI(
            name="Ben Nevis",
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry="POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))",
            size_km=10.0
        )
        db_session.add(aoi)
        db_session.commit()

        product = SentinelProduct(
            product_id="S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219",
            aoi_id=aoi.id,
            acquisition_dt=datetime(2024, 1, 15, 11, 33, 21),
            cloud_cover=15.5,
            geometry='{"type": "Polygon", "coordinates": []}'
        )
        db_session.add(product)
        db_session.commit()

        # Test relationship
        assert product.aoi == aoi
        assert product in aoi.products


class TestDownloadStatusModel:
    """Tests for DownloadStatus model."""

    def test_create_download_status(self, db_session):
        """Test creating a DownloadStatus record."""
        # Create AOI and product first
        aoi = AOI(
            name="Ben Nevis",
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry="POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))",
            size_km=10.0
        )
        db_session.add(aoi)
        db_session.commit()

        product = SentinelProduct(
            product_id="S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219",
            aoi_id=aoi.id,
            acquisition_dt=datetime(2024, 1, 15, 11, 33, 21),
            cloud_cover=15.5,
            geometry='{"type": "Polygon", "coordinates": []}'
        )
        db_session.add(product)
        db_session.commit()

        # Create download status
        status = DownloadStatus(
            product_id=product.id,
            status='pending',
            retry_count=0
        )
        db_session.add(status)
        db_session.commit()

        assert status.id is not None
        assert status.product_id == product.id
        assert status.status == 'pending'
        assert status.retry_count == 0
        assert isinstance(status.updated_at, datetime)

    def test_download_status_is_unique_per_product(self, db_session):
        """Test that each product can only have one download status."""
        # Create AOI and product
        aoi = AOI(
            name="Ben Nevis",
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry="POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))",
            size_km=10.0
        )
        db_session.add(aoi)
        db_session.commit()

        product = SentinelProduct(
            product_id="S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219",
            aoi_id=aoi.id,
            acquisition_dt=datetime(2024, 1, 15, 11, 33, 21),
            cloud_cover=15.5,
            geometry='{"type": "Polygon", "coordinates": []}'
        )
        db_session.add(product)
        db_session.commit()

        # Create first status
        status1 = DownloadStatus(
            product_id=product.id,
            status='pending'
        )
        db_session.add(status1)
        db_session.commit()

        # Try to create duplicate status for same product
        status2 = DownloadStatus(
            product_id=product.id,  # Duplicate
            status='downloaded'
        )
        db_session.add(status2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_status_check_constraint(self, db_session):
        """Test that status field only accepts valid values."""
        # Create AOI and product
        aoi = AOI(
            name="Ben Nevis",
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry="POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))",
            size_km=10.0
        )
        db_session.add(aoi)
        db_session.commit()

        product = SentinelProduct(
            product_id="S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219",
            aoi_id=aoi.id,
            acquisition_dt=datetime(2024, 1, 15, 11, 33, 21),
            cloud_cover=15.5,
            geometry='{"type": "Polygon", "coordinates": []}'
        )
        db_session.add(product)
        db_session.commit()

        # Try invalid status value
        status = DownloadStatus(
            product_id=product.id,
            status='invalid_status'  # Not in allowed values
        )
        db_session.add(status)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_valid_status_values(self, db_session):
        """Test that all valid status values are accepted."""
        # Create AOI
        aoi = AOI(
            name="Ben Nevis",
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry="POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))",
            size_km=10.0
        )
        db_session.add(aoi)
        db_session.commit()

        valid_statuses = ['pending', 'downloaded', 'failed', 'processing', 'processed']

        for idx, status_value in enumerate(valid_statuses):
            product = SentinelProduct(
                product_id=f"S2A_MSIL2A_20240115T11332{idx}_N0510_R080_T30VVJ_20240115T145219",
                aoi_id=aoi.id,
                acquisition_dt=datetime(2024, 1, 15, 11, 33, 21),
                cloud_cover=15.5,
                geometry='{"type": "Polygon", "coordinates": []}'
            )
            db_session.add(product)
            db_session.commit()

            status = DownloadStatus(
                product_id=product.id,
                status=status_value
            )
            db_session.add(status)
            db_session.commit()

            assert status.status == status_value


class TestSnowMaskModel:
    """Tests for SnowMask model."""

    def test_create_snow_mask(self, db_session):
        """Test creating a SnowMask record."""
        # Create AOI and product first
        aoi = AOI(
            name="Ben Nevis",
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry="POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))",
            size_km=10.0
        )
        db_session.add(aoi)
        db_session.commit()

        product = SentinelProduct(
            product_id="S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219",
            aoi_id=aoi.id,
            acquisition_dt=datetime(2024, 1, 15, 11, 33, 21),
            cloud_cover=15.5,
            geometry='{"type": "Polygon", "coordinates": []}'
        )
        db_session.add(product)
        db_session.commit()

        # Create snow mask
        mask = SnowMask(
            product_id=product.id,
            ndsi_threshold=0.4,
            snow_pixels=50000,
            total_pixels=100000,
            snow_pct=50.0,
            mask_path='/path/to/mask.tif'
        )
        db_session.add(mask)
        db_session.commit()

        assert mask.id is not None
        assert mask.product_id == product.id
        assert mask.ndsi_threshold == 0.4
        assert mask.snow_pixels == 50000
        assert mask.total_pixels == 100000
        assert mask.snow_pct == 50.0
        assert isinstance(mask.processing_dt, datetime)

    def test_snow_mask_unique_constraint(self, db_session):
        """Test that product_id and ndsi_threshold combination is unique."""
        # Create AOI and product
        aoi = AOI(
            name="Ben Nevis",
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry="POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))",
            size_km=10.0
        )
        db_session.add(aoi)
        db_session.commit()

        product = SentinelProduct(
            product_id="S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219",
            aoi_id=aoi.id,
            acquisition_dt=datetime(2024, 1, 15, 11, 33, 21),
            cloud_cover=15.5,
            geometry='{"type": "Polygon", "coordinates": []}'
        )
        db_session.add(product)
        db_session.commit()

        # Create first mask
        mask1 = SnowMask(
            product_id=product.id,
            ndsi_threshold=0.4,
            snow_pixels=50000,
            total_pixels=100000,
            snow_pct=50.0
        )
        db_session.add(mask1)
        db_session.commit()

        # Try to create duplicate with same product_id and ndsi_threshold
        mask2 = SnowMask(
            product_id=product.id,
            ndsi_threshold=0.4,  # Same threshold
            snow_pixels=60000,
            total_pixels=100000,
            snow_pct=60.0
        )
        db_session.add(mask2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_multiple_thresholds_for_same_product(self, db_session):
        """Test that same product can have multiple masks with different thresholds."""
        # Create AOI and product
        aoi = AOI(
            name="Ben Nevis",
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry="POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))",
            size_km=10.0
        )
        db_session.add(aoi)
        db_session.commit()

        product = SentinelProduct(
            product_id="S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219",
            aoi_id=aoi.id,
            acquisition_dt=datetime(2024, 1, 15, 11, 33, 21),
            cloud_cover=15.5,
            geometry='{"type": "Polygon", "coordinates": []}'
        )
        db_session.add(product)
        db_session.commit()

        # Create masks with different thresholds
        mask1 = SnowMask(
            product_id=product.id,
            ndsi_threshold=0.3,
            snow_pixels=60000,
            total_pixels=100000,
            snow_pct=60.0
        )
        mask2 = SnowMask(
            product_id=product.id,
            ndsi_threshold=0.4,  # Different threshold
            snow_pixels=50000,
            total_pixels=100000,
            snow_pct=50.0
        )
        db_session.add(mask1)
        db_session.add(mask2)
        db_session.commit()

        # Both should succeed
        assert mask1.id is not None
        assert mask2.id is not None
