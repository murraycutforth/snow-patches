"""Tests for repository data access layer."""

import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from data_handler.database import create_db_engine, init_database, get_session_factory
from data_handler.models import AOI, SentinelProduct, DownloadStatus
from data_handler.repositories import AOIRepository, SentinelProductRepository, DownloadStatusRepository


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
def sample_aoi_data():
    """Sample AOI data for testing."""
    return {
        'name': 'Ben Nevis',
        'center_lat': 56.7969,
        'center_lon': -5.0036,
        'geometry': 'POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))',
        'size_km': 10.0
    }


class TestAOIRepository:
    """Tests for AOIRepository."""

    def test_create_aoi(self, db_session, sample_aoi_data):
        """Test creating an AOI record."""
        repo = AOIRepository(db_session)
        aoi = repo.create(**sample_aoi_data)

        assert aoi.id is not None
        assert aoi.name == sample_aoi_data['name']
        assert aoi.center_lat == sample_aoi_data['center_lat']
        assert aoi.center_lon == sample_aoi_data['center_lon']

    def test_get_by_name(self, db_session, sample_aoi_data):
        """Test retrieving AOI by name."""
        repo = AOIRepository(db_session)
        created = repo.create(**sample_aoi_data)

        retrieved = repo.get_by_name('Ben Nevis')

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == 'Ben Nevis'

    def test_get_by_name_returns_none_if_not_found(self, db_session):
        """Test that get_by_name returns None for non-existent AOI."""
        repo = AOIRepository(db_session)
        result = repo.get_by_name('Non-existent')

        assert result is None

    def test_get_all(self, db_session):
        """Test retrieving all AOIs."""
        repo = AOIRepository(db_session)

        # Create multiple AOIs
        repo.create(
            name='Ben Nevis',
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry='POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))',
            size_km=10.0
        )
        repo.create(
            name='Ben Macdui',
            center_lat=57.0704,
            center_lon=-3.6691,
            geometry='POLYGON((-3.7 57.0, -3.6 57.0, -3.6 57.1, -3.7 57.1, -3.7 57.0))',
            size_km=10.0
        )

        all_aois = repo.get_all()

        assert len(all_aois) == 2
        assert set(a.name for a in all_aois) == {'Ben Nevis', 'Ben Macdui'}

    def test_exists_returns_true_if_aoi_exists(self, db_session, sample_aoi_data):
        """Test that exists returns True for existing AOI."""
        repo = AOIRepository(db_session)
        repo.create(**sample_aoi_data)

        assert repo.exists('Ben Nevis') is True

    def test_exists_returns_false_if_aoi_does_not_exist(self, db_session):
        """Test that exists returns False for non-existent AOI."""
        repo = AOIRepository(db_session)

        assert repo.exists('Non-existent') is False

    def test_unique_name_constraint_violation(self, db_session, sample_aoi_data):
        """Test that creating duplicate AOI name raises IntegrityError."""
        repo = AOIRepository(db_session)
        repo.create(**sample_aoi_data)

        # Try to create another AOI with same name
        with pytest.raises(IntegrityError):
            repo.create(**sample_aoi_data)


class TestSentinelProductRepository:
    """Tests for SentinelProductRepository."""

    @pytest.fixture
    def aoi_with_products(self, db_session):
        """Create an AOI with sample products for testing."""
        aoi_repo = AOIRepository(db_session)
        aoi = aoi_repo.create(
            name='Ben Nevis',
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry='POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))',
            size_km=10.0
        )

        product_repo = SentinelProductRepository(db_session)

        # Create products with varying dates and cloud cover
        product_repo.create(
            product_id='S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219',
            aoi_id=aoi.id,
            acquisition_dt=datetime(2024, 1, 15, 11, 33, 21),
            cloud_cover=15.5,
            geometry='{"type": "Polygon", "coordinates": []}'
        )
        product_repo.create(
            product_id='S2A_MSIL2A_20240120T113321_N0510_R080_T30VVJ_20240120T145219',
            aoi_id=aoi.id,
            acquisition_dt=datetime(2024, 1, 20, 11, 33, 21),
            cloud_cover=45.0,
            geometry='{"type": "Polygon", "coordinates": []}'
        )
        product_repo.create(
            product_id='S2A_MSIL2A_20240125T113321_N0510_R080_T30VVJ_20240125T145219',
            aoi_id=aoi.id,
            acquisition_dt=datetime(2024, 1, 25, 11, 33, 21),
            cloud_cover=5.0,
            geometry='{"type": "Polygon", "coordinates": []}'
        )

        return aoi

    def test_create_product(self, db_session):
        """Test creating a product."""
        # Create AOI first
        aoi_repo = AOIRepository(db_session)
        aoi = aoi_repo.create(
            name='Ben Nevis',
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry='POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))',
            size_km=10.0
        )

        # Create product
        product_repo = SentinelProductRepository(db_session)
        product = product_repo.create(
            product_id='S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219',
            aoi_id=aoi.id,
            acquisition_dt=datetime(2024, 1, 15, 11, 33, 21),
            cloud_cover=15.5,
            geometry='{"type": "Polygon", "coordinates": []}'
        )

        assert product.id is not None
        assert product.product_id == 'S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219'
        assert product.aoi_id == aoi.id

    def test_get_by_product_id(self, db_session, aoi_with_products):
        """Test retrieving product by product_id."""
        product_repo = SentinelProductRepository(db_session)
        product = product_repo.get_by_product_id('S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219')

        assert product is not None
        assert product.product_id == 'S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219'

    def test_get_by_product_id_returns_none_if_not_found(self, db_session):
        """Test that get_by_product_id returns None for non-existent product."""
        product_repo = SentinelProductRepository(db_session)
        result = product_repo.get_by_product_id('NON_EXISTENT')

        assert result is None

    def test_exists_returns_true_if_product_exists(self, db_session, aoi_with_products):
        """Test that exists returns True for existing product."""
        product_repo = SentinelProductRepository(db_session)

        assert product_repo.exists('S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219') is True

    def test_exists_returns_false_if_product_does_not_exist(self, db_session):
        """Test that exists returns False for non-existent product."""
        product_repo = SentinelProductRepository(db_session)

        assert product_repo.exists('NON_EXISTENT') is False

    def test_get_by_id(self, db_session, aoi_with_products):
        """Test retrieving product by database ID."""
        product_repo = SentinelProductRepository(db_session)

        # First get a product to know its ID
        product = product_repo.get_by_product_id('S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219')
        product_id = product.id

        # Now retrieve by ID
        result = product_repo.get_by_id(product_id)

        assert result is not None
        assert result.id == product_id
        assert result.product_id == 'S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219'

    def test_get_by_id_returns_none_if_not_found(self, db_session):
        """Test that get_by_id returns None for non-existent ID."""
        product_repo = SentinelProductRepository(db_session)
        result = product_repo.get_by_id(99999)

        assert result is None

    def test_get_by_aoi(self, db_session, aoi_with_products):
        """Test retrieving all products for an AOI."""
        product_repo = SentinelProductRepository(db_session)
        products = product_repo.get_by_aoi(aoi_with_products.id)

        assert len(products) == 3

    def test_get_by_aoi_with_date_filter(self, db_session, aoi_with_products):
        """Test retrieving products filtered by date range."""
        product_repo = SentinelProductRepository(db_session)
        products = product_repo.get_by_aoi(
            aoi_with_products.id,
            start_date=datetime(2024, 1, 18),
            end_date=datetime(2024, 1, 31)
        )

        assert len(products) == 2
        # Should get products from Jan 20 and Jan 25
        product_dates = [p.acquisition_dt.day for p in products]
        assert 20 in product_dates
        assert 25 in product_dates
        assert 15 not in product_dates

    def test_get_by_aoi_with_cloud_cover_filter(self, db_session, aoi_with_products):
        """Test retrieving products filtered by cloud cover."""
        product_repo = SentinelProductRepository(db_session)
        products = product_repo.get_by_aoi(
            aoi_with_products.id,
            max_cloud_cover=20.0
        )

        assert len(products) == 2
        # Should get products with 15.5% and 5% cloud cover
        assert all(p.cloud_cover <= 20.0 for p in products)

    def test_get_by_aoi_with_combined_filters(self, db_session, aoi_with_products):
        """Test retrieving products with multiple filters."""
        product_repo = SentinelProductRepository(db_session)
        products = product_repo.get_by_aoi(
            aoi_with_products.id,
            start_date=datetime(2024, 1, 18),
            end_date=datetime(2024, 1, 31),
            max_cloud_cover=20.0
        )

        assert len(products) == 1
        # Should only get product from Jan 25 with 5% cloud cover
        assert products[0].acquisition_dt.day == 25
        assert products[0].cloud_cover == 5.0

    def test_bulk_create_if_not_exists(self, db_session):
        """Test bulk creation with deduplication."""
        # Create AOI
        aoi_repo = AOIRepository(db_session)
        aoi = aoi_repo.create(
            name='Ben Nevis',
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry='POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))',
            size_km=10.0
        )

        product_repo = SentinelProductRepository(db_session)

        # Create initial products
        products_data = [
            {
                'product_id': 'PRODUCT_1',
                'aoi_id': aoi.id,
                'acquisition_dt': datetime(2024, 1, 15),
                'cloud_cover': 10.0,
                'geometry': '{}'
            },
            {
                'product_id': 'PRODUCT_2',
                'aoi_id': aoi.id,
                'acquisition_dt': datetime(2024, 1, 16),
                'cloud_cover': 20.0,
                'geometry': '{}'
            }
        ]

        created, skipped = product_repo.bulk_create_if_not_exists(products_data)

        assert created == 2
        assert skipped == 0

        # Try to add same products again plus one new one
        products_data_2 = [
            {
                'product_id': 'PRODUCT_1',  # Already exists
                'aoi_id': aoi.id,
                'acquisition_dt': datetime(2024, 1, 15),
                'cloud_cover': 10.0,
                'geometry': '{}'
            },
            {
                'product_id': 'PRODUCT_3',  # New product
                'aoi_id': aoi.id,
                'acquisition_dt': datetime(2024, 1, 17),
                'cloud_cover': 30.0,
                'geometry': '{}'
            }
        ]

        created, skipped = product_repo.bulk_create_if_not_exists(products_data_2)

        assert created == 1  # Only PRODUCT_3 was created
        assert skipped == 1  # PRODUCT_1 was skipped

        # Verify total count
        all_products = product_repo.get_by_aoi(aoi.id)
        assert len(all_products) == 3


class TestDownloadStatusRepository:
    """Tests for DownloadStatusRepository."""

    @pytest.fixture
    def product_with_status(self, db_session):
        """Create product with download status for testing."""
        # Create AOI
        aoi_repo = AOIRepository(db_session)
        aoi = aoi_repo.create(
            name='Ben Nevis',
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry='POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))',
            size_km=10.0
        )

        # Create product
        product_repo = SentinelProductRepository(db_session)
        product = product_repo.create(
            product_id='S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219',
            aoi_id=aoi.id,
            acquisition_dt=datetime(2024, 1, 15, 11, 33, 21),
            cloud_cover=15.5,
            geometry='{"type": "Polygon", "coordinates": []}'
        )

        # Create download status
        status_repo = DownloadStatusRepository(db_session)
        status = status_repo.create(
            product_id=product.id,
            status='pending'
        )

        return {'product': product, 'status': status}

    def test_create_download_status(self, db_session):
        """Test creating a download status record."""
        # Create AOI and product
        aoi_repo = AOIRepository(db_session)
        aoi = aoi_repo.create(
            name='Ben Nevis',
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry='POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))',
            size_km=10.0
        )

        product_repo = SentinelProductRepository(db_session)
        product = product_repo.create(
            product_id='S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219',
            aoi_id=aoi.id,
            acquisition_dt=datetime(2024, 1, 15, 11, 33, 21),
            cloud_cover=15.5,
            geometry='{"type": "Polygon", "coordinates": []}'
        )

        # Create status
        status_repo = DownloadStatusRepository(db_session)
        status = status_repo.create(
            product_id=product.id,
            status='pending'
        )

        assert status.id is not None
        assert status.product_id == product.id
        assert status.status == 'pending'
        assert status.retry_count == 0

    def test_update_status(self, db_session, product_with_status):
        """Test updating download status."""
        status_repo = DownloadStatusRepository(db_session)
        status = product_with_status['status']

        updated = status_repo.update_status(
            status.id,
            status='downloaded',
            local_path='/path/to/file.SAFE',
            file_size_mb=1024.5,
            download_start=datetime(2024, 1, 15, 10, 0, 0),
            download_end=datetime(2024, 1, 15, 10, 30, 0)
        )

        assert updated.status == 'downloaded'
        assert updated.local_path == '/path/to/file.SAFE'
        assert updated.file_size_mb == 1024.5

    def test_get_pending(self, db_session):
        """Test retrieving pending downloads."""
        # Create AOI
        aoi_repo = AOIRepository(db_session)
        aoi = aoi_repo.create(
            name='Ben Nevis',
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry='POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))',
            size_km=10.0
        )

        # Create products with different statuses
        product_repo = SentinelProductRepository(db_session)
        status_repo = DownloadStatusRepository(db_session)

        for i, status_value in enumerate(['pending', 'downloaded', 'pending', 'failed']):
            product = product_repo.create(
                product_id=f'PRODUCT_{i}',
                aoi_id=aoi.id,
                acquisition_dt=datetime(2024, 1, 15 + i),
                cloud_cover=10.0,
                geometry='{}'
            )
            status_repo.create(
                product_id=product.id,
                status=status_value
            )

        # Get pending statuses
        pending = status_repo.get_pending()

        assert len(pending) == 2
        assert all(s.status == 'pending' for s in pending)
