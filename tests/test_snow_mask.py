"""
Unit tests for snow mask generation module.

Tests cover NDSI calculation, threshold application, statistics calculation,
and file path generation. Uses mocked I/O operations.
"""

import pytest
import numpy as np
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from data_handler.snow_mask import (
    calculate_ndsi,
    apply_threshold,
    calculate_snow_statistics,
    get_mask_output_path,
    DEFAULT_NDSI_THRESHOLD,
    EPSILON,
    MASK_DTYPE,
    InvalidBandDataError,
)
from data_handler.models import Base, AOI, SentinelProduct, DownloadStatus, SnowMask
from data_handler.repositories import SnowMaskRepository


class TestCalculateNDSI:
    """Test NDSI calculation function."""

    def test_calculate_ndsi_known_values(self):
        """Test NDSI calculation with hand-calculated values."""
        # B03 = [100, 200], B11 = [50, 100]
        # NDSI = (B03 - B11) / (B03 + B11)
        # NDSI[0] = (100 - 50) / (100 + 50) = 50 / 150 = 0.333...
        # NDSI[1] = (200 - 100) / (200 + 100) = 100 / 300 = 0.333...
        band_green = np.array([[100, 200]], dtype=np.float32)
        band_swir = np.array([[50, 100]], dtype=np.float32)

        ndsi = calculate_ndsi(band_green, band_swir)

        expected = np.array([[0.333333, 0.333333]], dtype=np.float32)
        np.testing.assert_array_almost_equal(ndsi, expected, decimal=5)

    def test_calculate_ndsi_all_zeros(self):
        """Test NDSI with all-zero arrays."""
        band_green = np.zeros((10, 10), dtype=np.float32)
        band_swir = np.zeros((10, 10), dtype=np.float32)

        ndsi = calculate_ndsi(band_green, band_swir)

        # With epsilon, NDSI = (0 - 0) / (0 + 0 + epsilon) = 0
        assert ndsi.shape == (10, 10)
        np.testing.assert_array_almost_equal(ndsi, np.zeros((10, 10)), decimal=5)

    def test_calculate_ndsi_prevents_division_by_zero(self):
        """Test that epsilon prevents division by zero."""
        # Create case where B03 + B11 = 0 (shouldn't crash)
        band_green = np.array([[0]], dtype=np.float32)
        band_swir = np.array([[0]], dtype=np.float32)

        ndsi = calculate_ndsi(band_green, band_swir, epsilon=1e-8)

        # Should return finite value
        assert np.isfinite(ndsi).all()

    def test_calculate_ndsi_shape_mismatch(self):
        """Test that mismatched shapes raise ValueError."""
        band_green = np.zeros((10, 10), dtype=np.float32)
        band_swir = np.zeros((10, 5), dtype=np.float32)

        with pytest.raises(ValueError, match="Shape mismatch"):
            calculate_ndsi(band_green, band_swir)

    def test_calculate_ndsi_result_range(self):
        """Test that NDSI values are in [-1, 1] range."""
        # Create realistic band values
        band_green = np.random.randint(0, 10000, size=(50, 50)).astype(np.float32)
        band_swir = np.random.randint(0, 10000, size=(50, 50)).astype(np.float32)

        ndsi = calculate_ndsi(band_green, band_swir)

        assert ndsi.min() >= -1.0
        assert ndsi.max() <= 1.0


class TestApplyThreshold:
    """Test threshold application function."""

    def test_apply_threshold_default(self):
        """Test threshold application with default value (0.4)."""
        ndsi = np.array([[-0.5, 0.2, 0.5, 0.8]], dtype=np.float32)

        mask = apply_threshold(ndsi)

        expected = np.array([[0, 0, 1, 1]], dtype=MASK_DTYPE)
        np.testing.assert_array_equal(mask, expected)

    def test_apply_threshold_custom(self):
        """Test threshold application with custom value."""
        ndsi = np.array([[0.3, 0.5, 0.7]], dtype=np.float32)

        mask = apply_threshold(ndsi, threshold=0.6)

        expected = np.array([[0, 0, 1]], dtype=MASK_DTYPE)
        np.testing.assert_array_equal(mask, expected)

    def test_apply_threshold_boundary_values(self):
        """Test behavior at exact threshold value."""
        ndsi = np.array([[0.39, 0.40, 0.41]], dtype=np.float32)

        mask = apply_threshold(ndsi, threshold=0.4)

        # Values > threshold should be 1
        expected = np.array([[0, 0, 1]], dtype=MASK_DTYPE)
        np.testing.assert_array_equal(mask, expected)

    def test_apply_threshold_output_dtype(self):
        """Test that output is UINT8."""
        ndsi = np.random.rand(10, 10).astype(np.float32)

        mask = apply_threshold(ndsi)

        assert mask.dtype == MASK_DTYPE


class TestCalculateStatistics:
    """Test snow statistics calculation."""

    def test_calculate_snow_statistics_full_coverage(self):
        """Test with 100% snow coverage."""
        snow_mask = np.ones((100, 100), dtype=MASK_DTYPE)

        stats = calculate_snow_statistics(snow_mask)

        assert stats["snow_pixels"] == 10000
        assert stats["total_pixels"] == 10000
        assert stats["snow_pct"] == 100.0

    def test_calculate_snow_statistics_zero_coverage(self):
        """Test with 0% snow coverage."""
        snow_mask = np.zeros((100, 100), dtype=MASK_DTYPE)

        stats = calculate_snow_statistics(snow_mask)

        assert stats["snow_pixels"] == 0
        assert stats["total_pixels"] == 10000
        assert stats["snow_pct"] == 0.0

    def test_calculate_snow_statistics_partial(self):
        """Test with partial snow coverage."""
        snow_mask = np.zeros((100, 100), dtype=MASK_DTYPE)
        snow_mask[:50, :] = 1  # 50% coverage

        stats = calculate_snow_statistics(snow_mask)

        assert stats["snow_pixels"] == 5000
        assert stats["total_pixels"] == 10000
        assert stats["snow_pct"] == 50.0

    def test_calculate_snow_statistics_return_types(self):
        """Test that return types are correct."""
        snow_mask = np.random.randint(0, 2, size=(10, 10), dtype=MASK_DTYPE)

        stats = calculate_snow_statistics(snow_mask)

        assert isinstance(stats, dict)
        assert isinstance(stats["snow_pixels"], int)
        assert isinstance(stats["total_pixels"], int)
        assert isinstance(stats["snow_pct"], float)


class TestGetMaskOutputPath:
    """Test mask output path generation."""

    def test_returns_correct_structure(self):
        """Test hierarchical path structure."""
        product_id = "S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T144648"
        aoi_name = "ben_nevis"
        date = datetime(2024, 1, 15, 11, 33, 21)
        threshold = 0.4

        path = get_mask_output_path(product_id, aoi_name, date, threshold,
                                    base_dir=Path("/tmp/test"))

        expected = Path("/tmp/test/ben_nevis/2024/01/S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T144648_ndsi0.4.tif")
        assert path == expected

    def test_includes_threshold_in_filename(self):
        """Test that threshold is included in filename."""
        product_id = "test_product"
        path = get_mask_output_path(product_id, "test_aoi", datetime(2024, 1, 1),
                                    0.5, base_dir=Path("/tmp"))

        assert "_ndsi0.5.tif" in str(path)

    def test_handles_different_thresholds(self):
        """Test that different thresholds produce different filenames."""
        product_id = "test_product"
        aoi_name = "test_aoi"
        date = datetime(2024, 1, 1)

        path1 = get_mask_output_path(product_id, aoi_name, date, 0.4, Path("/tmp"))
        path2 = get_mask_output_path(product_id, aoi_name, date, 0.5, Path("/tmp"))

        assert path1 != path2
        assert "_ndsi0.4.tif" in str(path1)
        assert "_ndsi0.5.tif" in str(path2)


class TestSnowMaskRepository:
    """Test SnowMaskRepository CRUD operations."""

    @pytest.fixture
    def db_session(self):
        """Create in-memory database session for testing."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()

        # Seed with test data
        aoi = AOI(
            name="test_aoi",
            center_lat=56.0,
            center_lon=-4.0,
            geometry='{"type": "Polygon", "coordinates": [[[-4.1, 55.9], [-3.9, 55.9], [-3.9, 56.1], [-4.1, 56.1], [-4.1, 55.9]]]}'
        )
        session.add(aoi)
        session.commit()

        product = SentinelProduct(
            aoi_id=aoi.id,
            product_id="test_product_123",
            acquisition_dt=datetime(2024, 1, 1),
            cloud_cover=10.0,
            geometry='{"type": "Point", "coordinates": [0, 0]}'
        )
        session.add(product)
        session.commit()

        yield session
        session.close()

    def test_create_snow_mask_record(self, db_session):
        """Test creating snow mask record."""
        repo = SnowMaskRepository(db_session)

        mask = repo.create(
            product_id=1,
            ndsi_threshold=0.4,
            snow_pixels=5000,
            total_pixels=10000,
            snow_pct=50.0,
            mask_path="/tmp/test.tif"
        )

        assert mask.id is not None
        assert mask.product_id == 1
        assert mask.ndsi_threshold == 0.4
        assert mask.snow_pct == 50.0

    def test_get_by_product_and_threshold(self, db_session):
        """Test retrieving mask by product and threshold."""
        repo = SnowMaskRepository(db_session)
        repo.create(1, 0.4, 5000, 10000, 50.0)

        mask = repo.get_by_product_and_threshold(1, 0.4)

        assert mask is not None
        assert mask.ndsi_threshold == 0.4

    def test_get_by_product_multiple_thresholds(self, db_session):
        """Test retrieving all masks for a product."""
        repo = SnowMaskRepository(db_session)
        repo.create(1, 0.4, 5000, 10000, 50.0)
        repo.create(1, 0.5, 4000, 10000, 40.0)

        masks = repo.get_by_product(1)

        assert len(masks) == 2
        thresholds = {m.ndsi_threshold for m in masks}
        assert thresholds == {0.4, 0.5}

    def test_exists_method(self, db_session):
        """Test exists method."""
        repo = SnowMaskRepository(db_session)
        repo.create(1, 0.4, 5000, 10000, 50.0)

        assert repo.exists(1, 0.4) is True
        assert repo.exists(1, 0.5) is False

    def test_unique_constraint_violation(self, db_session):
        """Test that duplicate (product_id, threshold) raises error."""
        repo = SnowMaskRepository(db_session)
        repo.create(1, 0.4, 5000, 10000, 50.0)

        with pytest.raises(Exception):  # SQLAlchemy IntegrityError
            repo.create(1, 0.4, 6000, 10000, 60.0)
            db_session.commit()


class TestProcessProductSnowMask:
    """Test process_product_snow_mask function with mocked I/O."""

    @pytest.fixture
    def db_session(self):
        """Create in-memory database with test data."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()

        # Create test data
        aoi = AOI(
            name="test_aoi",
            center_lat=56.0,
            center_lon=-4.0,
            geometry='{"type": "Polygon", "coordinates": [[[-4.1, 55.9], [-3.9, 55.9], [-3.9, 56.1], [-4.1, 56.1], [-4.1, 55.9]]]}'
        )
        session.add(aoi)
        session.commit()

        product = SentinelProduct(
            aoi_id=aoi.id,
            product_id="S2A_TEST_PRODUCT",
            acquisition_dt=datetime(2024, 1, 1),
            cloud_cover=10.0,
            geometry='{"type": "Point", "coordinates": [0, 0]}'
        )
        session.add(product)
        session.commit()

        download = DownloadStatus(
            product_id=product.id,
            status="downloaded",
            local_path="/tmp/test.tif"
        )
        session.add(download)
        session.commit()

        yield session
        session.close()

    @patch('data_handler.snow_mask.read_bands_from_geotiff')
    @patch('data_handler.snow_mask.save_snow_mask')
    def test_process_product_success(self, mock_save, mock_read, db_session):
        """Test successful product processing."""
        from data_handler.snow_mask import process_product_snow_mask

        # Mock band data
        band_green = np.ones((100, 100), dtype=np.float32) * 200
        band_swir = np.ones((100, 100), dtype=np.float32) * 100
        metadata = {"crs": "EPSG:32630", "transform": None}
        mock_read.return_value = (band_green, band_swir, metadata)

        success, error_msg, result = process_product_snow_mask(db_session, 1, 0.4, True)

        assert success is True
        assert error_msg is None
        assert result is not None
        assert "snow_pct" in result

    @patch('data_handler.snow_mask.read_bands_from_geotiff')
    def test_updates_download_status_to_processing(self, mock_read, db_session):
        """Test that download status is updated to 'processing'."""
        from data_handler.snow_mask import process_product_snow_mask

        band_green = np.ones((100, 100), dtype=np.float32) * 200
        band_swir = np.ones((100, 100), dtype=np.float32) * 100
        mock_read.return_value = (band_green, band_swir, {})

        # Get initial status
        download = db_session.query(DownloadStatus).filter_by(product_id=1).first()
        assert download.status == "downloaded"

        process_product_snow_mask(db_session, 1, 0.4, False)

        # Should be updated to processed
        db_session.refresh(download)
        assert download.status == "processed"

    @patch('data_handler.snow_mask.read_bands_from_geotiff')
    def test_creates_snow_mask_record(self, mock_read, db_session):
        """Test that SnowMask record is created."""
        from data_handler.snow_mask import process_product_snow_mask

        band_green = np.ones((100, 100), dtype=np.float32) * 200
        band_swir = np.ones((100, 100), dtype=np.float32) * 100
        mock_read.return_value = (band_green, band_swir, {})

        process_product_snow_mask(db_session, 1, 0.4, False)

        mask_record = db_session.query(SnowMask).filter_by(product_id=1).first()
        assert mask_record is not None
        assert mask_record.ndsi_threshold == 0.4

    @patch('data_handler.snow_mask.read_bands_from_geotiff')
    @patch('data_handler.snow_mask.save_snow_mask')
    def test_save_mask_parameter(self, mock_save, mock_read, db_session):
        """Test that save_mask parameter controls file saving."""
        from data_handler.snow_mask import process_product_snow_mask

        band_green = np.ones((100, 100), dtype=np.float32) * 200
        band_swir = np.ones((100, 100), dtype=np.float32) * 100
        mock_read.return_value = (band_green, band_swir, {})

        # Test with save_mask=True
        process_product_snow_mask(db_session, 1, 0.4, save_mask=True)
        assert mock_save.called

        # Test with save_mask=False
        mock_save.reset_mock()
        process_product_snow_mask(db_session, 1, 0.5, save_mask=False)
        assert not mock_save.called

    @patch('data_handler.snow_mask.read_bands_from_geotiff')
    def test_handles_file_not_found(self, mock_read, db_session):
        """Test handling of missing file."""
        from data_handler.snow_mask import process_product_snow_mask

        mock_read.side_effect = FileNotFoundError("File not found")

        success, error_msg, result = process_product_snow_mask(db_session, 1, 0.4, True)

        assert success is False
        assert error_msg is not None
        assert result is None


class TestProcessDownloadedProducts:
    """Test batch processing function."""

    @pytest.fixture
    def db_session(self):
        """Create in-memory database with multiple products."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()

        # Create test data
        aoi = AOI(
            name="test_aoi",
            center_lat=56.0,
            center_lon=-4.0,
            geometry='{"type": "Polygon", "coordinates": [[[-4.1, 55.9], [-3.9, 55.9], [-3.9, 56.1], [-4.1, 56.1], [-4.1, 55.9]]]}'
        )
        session.add(aoi)
        session.commit()

        for i in range(5):
            product = SentinelProduct(
                aoi_id=aoi.id,
                product_id=f"TEST_PRODUCT_{i}",
                acquisition_dt=datetime(2024, 1, i+1),
                cloud_cover=10.0,
                geometry='{"type": "Point", "coordinates": [0, 0]}'
            )
            session.add(product)
            session.commit()

            download = DownloadStatus(
                product_id=product.id,
                status="downloaded",
                local_path=f"/tmp/test_{i}.tif"
            )
            session.add(download)

        session.commit()
        yield session
        session.close()

    @patch('data_handler.snow_mask.process_product_snow_mask')
    def test_finds_downloaded_products(self, mock_process, db_session):
        """Test that function finds downloaded products."""
        from data_handler.snow_mask import process_downloaded_products

        mock_process.return_value = (True, None, {"snow_pct": 50.0})

        result = process_downloaded_products(db_session, 0.4, False)

        assert mock_process.call_count == 5

    @patch('data_handler.snow_mask.process_product_snow_mask')
    def test_processes_multiple_products(self, mock_process, db_session):
        """Test processing multiple products."""
        from data_handler.snow_mask import process_downloaded_products

        mock_process.return_value = (True, None, {"snow_pct": 50.0})

        result = process_downloaded_products(db_session, 0.4, False)

        assert result["success"] == 5
        assert result["failed"] == 0

    @patch('data_handler.snow_mask.process_product_snow_mask')
    def test_handles_mixed_success_failure(self, mock_process, db_session):
        """Test handling of mixed success/failure."""
        from data_handler.snow_mask import process_downloaded_products

        # Alternate success and failure
        mock_process.side_effect = [
            (True, None, {}),
            (False, "Error", None),
            (True, None, {}),
            (False, "Error", None),
            (True, None, {}),
        ]

        result = process_downloaded_products(db_session, 0.4, False)

        assert result["success"] == 3
        assert result["failed"] == 2

    @patch('data_handler.snow_mask.process_product_snow_mask')
    def test_respects_limit_parameter(self, mock_process, db_session):
        """Test that limit parameter is respected."""
        from data_handler.snow_mask import process_downloaded_products

        mock_process.return_value = (True, None, {})

        result = process_downloaded_products(db_session, 0.4, False, limit=3)

        assert mock_process.call_count == 3
