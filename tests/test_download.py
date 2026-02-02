"""
Unit tests for data_handler/download.py

Tests the download functionality with mocked network calls and in-memory database.
All tests are fast (<5 seconds total) and don't make real API calls.
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, mock_open
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sentinelhub import SHConfig
from data_handler.download import (
    get_output_path,
    create_download_request,
    download_product,
    download_pending_products,
    DownloadError,
    AuthenticationError,
    ProductNotFoundError,
    QuotaExceededError,
    SENTINEL2_BANDS_EVALSCRIPT,
    DEFAULT_RESOLUTION,
)
from data_handler.models import Base, AOI, SentinelProduct, DownloadStatus
from data_handler.repositories import (
    AOIRepository,
    SentinelProductRepository,
    DownloadStatusRepository,
)


# ============================================================================
# Test Path Generation
# ============================================================================

class TestGetOutputPath:
    """Test suite for get_output_path() function."""

    def test_returns_correct_structure(self, tmp_path):
        """Test that path follows base_dir/aoi_name/YYYY/MM/product_id.tif structure."""
        product_id = "S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219"
        aoi_name = "ben_nevis"
        acquisition_date = datetime(2024, 1, 15, 11, 33, 21)

        result = get_output_path(product_id, aoi_name, acquisition_date, base_dir=tmp_path)

        expected = tmp_path / "ben_nevis" / "2024" / "01" / f"{product_id}.tif"
        assert result == expected

    def test_includes_aoi_name_in_path(self, tmp_path):
        """Test that AOI name is correctly included in path."""
        product_id = "S2B_MSIL2A_20240125T113321_N0510_R080_T30VVJ_20240125T145219"
        aoi_name = "ben_macdui"
        acquisition_date = datetime(2024, 1, 25)

        result = get_output_path(product_id, aoi_name, acquisition_date, base_dir=tmp_path)

        assert "ben_macdui" in str(result)
        assert result.parent.parent.parent.name == "ben_macdui"

    def test_includes_year_and_month(self, tmp_path):
        """Test that year and month are correctly extracted from acquisition_date."""
        product_id = "S2A_MSIL2A_20240315T113321_N0510_R080_T30VVJ_20240315T145219"
        aoi_name = "ben_nevis"
        acquisition_date = datetime(2024, 3, 15)

        result = get_output_path(product_id, aoi_name, acquisition_date, base_dir=tmp_path)

        assert "2024" in str(result)
        assert "03" in str(result)  # Month should be zero-padded
        assert result.parent.name == "03"
        assert result.parent.parent.name == "2024"

    def test_creates_parent_directories(self, tmp_path):
        """Test that parent directories are created if they don't exist."""
        product_id = "S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219"
        aoi_name = "ben_nevis"
        acquisition_date = datetime(2024, 1, 15)

        # Verify directories don't exist before call
        expected_dir = tmp_path / "ben_nevis" / "2024" / "01"
        assert not expected_dir.exists()

        result = get_output_path(product_id, aoi_name, acquisition_date, base_dir=tmp_path)

        # Parent directory should now exist
        assert result.parent.exists()
        assert result.parent.is_dir()

    def test_handles_special_characters_in_product_id(self, tmp_path):
        """Test that special characters in product_id are preserved in filename."""
        # Sentinel-2 product IDs contain underscores - ensure they're preserved
        product_id = "S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219"
        aoi_name = "ben_nevis"
        acquisition_date = datetime(2024, 1, 15)

        result = get_output_path(product_id, aoi_name, acquisition_date, base_dir=tmp_path)

        assert result.stem == product_id
        assert result.suffix == ".tif"

    def test_uses_default_base_dir(self, monkeypatch):
        """Test that default base_dir is 'data/sentinel2'."""
        product_id = "S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219"
        aoi_name = "ben_nevis"
        acquisition_date = datetime(2024, 1, 15)

        # Don't create directories for this test
        with patch('pathlib.Path.mkdir'):
            result = get_output_path(product_id, aoi_name, acquisition_date)

        assert str(result).startswith("data/sentinel2")

    def test_handles_different_months(self, tmp_path):
        """Test that month is always zero-padded to 2 digits."""
        product_id = "S2A_MSIL2A_20240615T113321_N0510_R080_T30VVJ_20240615T145219"
        aoi_name = "ben_nevis"

        # Test single-digit month (January)
        result_jan = get_output_path(
            product_id, aoi_name, datetime(2024, 1, 15), base_dir=tmp_path
        )
        assert "/01/" in str(result_jan)

        # Test double-digit month (December)
        result_dec = get_output_path(
            product_id, aoi_name, datetime(2024, 12, 15), base_dir=tmp_path
        )
        assert "/12/" in str(result_dec)

    def test_handles_different_aois(self, tmp_path):
        """Test that different AOI names create separate directories."""
        product_id = "S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219"
        acquisition_date = datetime(2024, 1, 15)

        result_nevis = get_output_path(
            product_id, "ben_nevis", acquisition_date, base_dir=tmp_path
        )
        result_macdui = get_output_path(
            product_id, "ben_macdui", acquisition_date, base_dir=tmp_path
        )

        assert "ben_nevis" in str(result_nevis)
        assert "ben_macdui" in str(result_macdui)
        assert result_nevis != result_macdui


# ============================================================================
# Test Request Creation
# ============================================================================

class TestCreateDownloadRequest:
    """Test suite for create_download_request() function."""

    @patch('data_handler.download.SentinelHubRequest')
    def test_returns_sentinelhub_request(self, mock_request_class, mock_config):
        """Test that function returns a SentinelHubRequest instance."""
        from sentinelhub import BBox, CRS

        bbox = BBox(bbox=[-5.1, 56.7, -4.9, 56.9], crs=CRS.WGS84)
        time_interval = ('2024-01-15', '2024-01-16')
        product_id = "S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219"

        # Mock the return value
        mock_request_class.return_value = Mock()

        result = create_download_request(product_id, bbox, time_interval, config=mock_config)

        # Verify SentinelHubRequest was called
        assert mock_request_class.called
        assert result == mock_request_class.return_value

    @patch('data_handler.download.SentinelHubRequest')
    def test_evalscript_includes_b03_and_b11(self, mock_request_class, mock_config):
        """Test that evalscript requests B03 (Green) and B11 (SWIR-1) bands."""
        from sentinelhub import BBox, CRS

        bbox = BBox(bbox=[-5.1, 56.7, -4.9, 56.9], crs=CRS.WGS84)
        time_interval = ('2024-01-15', '2024-01-16')
        product_id = "S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219"

        create_download_request(product_id, bbox, time_interval, config=mock_config)

        # Get the call arguments
        call_kwargs = mock_request_class.call_args[1]
        evalscript = call_kwargs.get('evalscript')

        assert evalscript is not None
        assert 'B03' in evalscript
        assert 'B11' in evalscript
        assert evalscript == SENTINEL2_BANDS_EVALSCRIPT

    @patch('data_handler.download.SentinelHubRequest.output_response')
    @patch('data_handler.download.SentinelHubRequest')
    def test_output_format_is_tiff(self, mock_request_class, mock_output_response, mock_config):
        """Test that output format is set to GeoTIFF (MimeType.TIFF)."""
        from sentinelhub import BBox, CRS, MimeType

        bbox = BBox(bbox=[-5.1, 56.7, -4.9, 56.9], crs=CRS.WGS84)
        time_interval = ('2024-01-15', '2024-01-16')
        product_id = "S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219"

        create_download_request(product_id, bbox, time_interval, config=mock_config)

        # Verify output_response was called with TIFF format
        mock_output_response.assert_called_once_with('default', MimeType.TIFF)

    @patch('data_handler.download.SentinelHubRequest.input_data')
    @patch('data_handler.download.SentinelHubRequest')
    def test_bbox_and_time_interval_passed_correctly(self, mock_request_class, mock_input_data, mock_config):
        """Test that bbox and time_interval are correctly passed to request."""
        from sentinelhub import BBox, CRS
        from data_handler.download import SENTINEL2_L2A_CDSE

        bbox = BBox(bbox=[-5.1, 56.7, -4.9, 56.9], crs=CRS.WGS84)
        time_interval = ('2024-01-15T00:00:00', '2024-01-16T00:00:00')
        product_id = "S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219"

        create_download_request(product_id, bbox, time_interval, config=mock_config)

        # Get the call arguments for main request
        call_kwargs = mock_request_class.call_args[1]

        # Verify bbox is passed
        assert call_kwargs.get('bbox') == bbox

        # Verify input_data was called with correct time_interval
        mock_input_data.assert_called_once_with(
            data_collection=SENTINEL2_L2A_CDSE,
            time_interval=time_interval,
        )

    @patch('data_handler.download.SentinelHubRequest')
    def test_resolution_set_to_10m(self, mock_request_class, mock_config):
        """Test that size is calculated correctly for 10m default resolution."""
        from sentinelhub import BBox, CRS

        bbox = BBox(bbox=[-5.1, 56.7, -4.9, 56.9], crs=CRS.WGS84)
        time_interval = ('2024-01-15', '2024-01-16')
        product_id = "S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219"

        create_download_request(product_id, bbox, time_interval, config=mock_config)

        # Get the call arguments
        call_kwargs = mock_request_class.call_args[1]

        # Now we use size parameter instead of resolution
        size = call_kwargs.get('size')
        assert size is not None
        assert isinstance(size, tuple)
        assert len(size) == 2
        # Size should be reasonable (pixels for the bbox at 10m resolution)
        # For a 0.2 degree bbox (~20km), at 10m resolution we expect ~2000 pixels
        assert 500 < size[0] < 3000
        assert 500 < size[1] < 3000

    @patch('data_handler.download.SentinelHubRequest')
    def test_custom_resolution(self, mock_request_class, mock_config):
        """Test that custom resolution can be specified."""
        from sentinelhub import BBox, CRS

        bbox = BBox(bbox=[-5.1, 56.7, -4.9, 56.9], crs=CRS.WGS84)
        time_interval = ('2024-01-15', '2024-01-16')
        product_id = "S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219"

        create_download_request(product_id, bbox, time_interval, resolution=20, config=mock_config)

        # Get the call arguments
        call_kwargs = mock_request_class.call_args[1]
        size_or_resolution = call_kwargs.get('size') or call_kwargs.get('resolution')

        assert size_or_resolution is not None

    @patch('data_handler.download.SentinelHubRequest')
    def test_uses_provided_config(self, mock_request_class, mock_config):
        """Test that provided SHConfig is used."""
        from sentinelhub import BBox, CRS

        bbox = BBox(bbox=[-5.1, 56.7, -4.9, 56.9], crs=CRS.WGS84)
        time_interval = ('2024-01-15', '2024-01-16')
        product_id = "S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219"

        create_download_request(product_id, bbox, time_interval, config=mock_config)

        # Get the call arguments
        call_kwargs = mock_request_class.call_args[1]

        assert call_kwargs.get('config') == mock_config


# ============================================================================
# Fixtures for Database Testing
# ============================================================================

@pytest.fixture
def mock_config():
    """Create a mock SHConfig for testing."""
    config = SHConfig()
    config.sh_client_id = "test_client_id"
    config.sh_client_secret = "test_client_secret"
    config.sh_base_url = "https://sh.dataspace.copernicus.eu"
    config.sh_token_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    return config


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)

    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()


@pytest.fixture
def sample_product_in_db(db_session):
    """Create a sample product in the database for testing."""
    # Create AOI first
    aoi_repo = AOIRepository(db_session)
    aoi = aoi_repo.create(
        name='ben_nevis',
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

    # Create download status (pending)
    status_repo = DownloadStatusRepository(db_session)
    status = status_repo.create(
        product_id=product.id,
        status='pending'
    )

    return product, status, aoi


# ============================================================================
# Test Download Function - Success Cases
# ============================================================================

class TestDownloadProductSuccess:
    """Test suite for download_product() success scenarios."""

    @patch('data_handler.download.create_download_request')
    @patch('data_handler.download.Path.stat')
    @patch('rasterio.open')
    def test_creates_file_at_correct_path(
        self, mock_rasterio, mock_stat, mock_create_request, db_session, sample_product_in_db, tmp_path, mock_config
    ):
        """Test that download creates file at correct hierarchical path."""
        product, status, aoi = sample_product_in_db

        # Mock the download request and response
        mock_request = Mock()
        mock_request.get_data.return_value = [np.zeros((100, 100, 2), dtype=np.uint16)]
        mock_create_request.return_value = mock_request

        # Mock rasterio file writing
        mock_file = MagicMock()
        mock_rasterio.return_value.__enter__.return_value = mock_file

        # Mock file stat for size calculation
        mock_stat.return_value.st_size = 4 * 1024 * 1024  # 4 MB

        # Execute download
        success, error, file_path = download_product(
            db_session, product.id, output_dir=tmp_path, config=mock_config
        )

        # Debug output
        if not success:
            print(f"Download failed: {error}")

        # Verify success
        assert success is True, f"Download failed with error: {error}"
        assert error is None
        assert file_path is not None

        # Verify path structure: tmp_path/ben_nevis/2024/01/product_id.tif
        expected_path = tmp_path / "ben_nevis" / "2024" / "01" / f"{product.product_id}.tif"
        assert file_path == expected_path

    @patch('data_handler.download.create_download_request')
    @patch('data_handler.download.Path.stat')
    @patch('rasterio.open')
    def test_updates_database_status_to_downloaded(
        self, mock_rasterio, mock_stat, mock_create_request, db_session, sample_product_in_db, tmp_path, mock_config
    ):
        """Test that database status is updated to 'downloaded' on success."""
        product, status, aoi = sample_product_in_db

        # Mock the download
        mock_request = Mock()
        mock_request.get_data.return_value = [np.zeros((100, 100, 2), dtype=np.uint16)]
        mock_create_request.return_value = mock_request

        mock_file = MagicMock()
        mock_rasterio.return_value.__enter__.return_value = mock_file

        mock_stat.return_value.st_size = 4 * 1024 * 1024

        # Execute download
        success, error, file_path = download_product(
            db_session, product.id, output_dir=tmp_path, config=mock_config
        )

        # Refresh status from database
        db_session.refresh(status)

        # Verify status updated
        assert status.status == 'downloaded'
        assert success is True

    @patch('data_handler.download.create_download_request')
    @patch('data_handler.download.Path.stat')
    @patch('rasterio.open')
    def test_populates_metadata_fields(
        self, mock_rasterio, mock_stat, mock_create_request, db_session, sample_product_in_db, tmp_path, mock_config
    ):
        """Test that local_path, file_size_mb, download_start/end are populated."""
        product, status, aoi = sample_product_in_db

        # Mock the download
        mock_request = Mock()
        mock_request.get_data.return_value = [np.zeros((100, 100, 2), dtype=np.uint16)]
        mock_create_request.return_value = mock_request

        mock_file = MagicMock()
        mock_rasterio.return_value.__enter__.return_value = mock_file

        mock_stat.return_value.st_size = 4 * 1024 * 1024

        # Execute download
        success, error, file_path = download_product(
            db_session, product.id, output_dir=tmp_path, config=mock_config
        )

        # Refresh status from database
        db_session.refresh(status)

        # Verify metadata fields
        assert status.local_path is not None
        assert str(file_path) in status.local_path
        assert status.file_size_mb is not None
        assert status.file_size_mb >= 0
        assert status.download_start is not None
        assert status.download_end is not None
        assert status.download_end >= status.download_start

    @patch('data_handler.download.create_download_request')
    @patch('data_handler.download.Path.stat')
    @patch('rasterio.open')
    def test_returns_success_tuple(
        self, mock_rasterio, mock_stat, mock_create_request, db_session, sample_product_in_db, tmp_path
    ):
        """Test that function returns (True, None, file_path) on success."""
        product, status, aoi = sample_product_in_db

        # Mock the download
        mock_request = Mock()
        mock_request.get_data.return_value = [np.zeros((100, 100, 2), dtype=np.uint16)]
        mock_create_request.return_value = mock_request

        mock_file = MagicMock()
        mock_rasterio.return_value.__enter__.return_value = mock_file

        mock_stat.return_value.st_size = 4 * 1024 * 1024

        # Execute download
        result = download_product(db_session, product.id, output_dir=tmp_path, config=mock_config)

        # Verify return value format
        assert isinstance(result, tuple)
        assert len(result) == 3
        success, error, file_path = result
        assert success is True
        assert error is None
        assert file_path is not None
        assert isinstance(file_path, Path)

    @patch('data_handler.download.create_download_request')
    def test_skips_if_already_downloaded(
        self, mock_create_request, db_session, sample_product_in_db, tmp_path, mock_config
    ):
        """Test that download is skipped if status is already 'downloaded'."""
        product, status, aoi = sample_product_in_db

        # Update status to 'downloaded'
        status_repo = DownloadStatusRepository(db_session)
        status_repo.update_status(status.id, status='downloaded', local_path='/fake/path.tif')

        # Execute download
        success, error, file_path = download_product(
            db_session, product.id, output_dir=tmp_path, config=mock_config
        )

        # Verify download was skipped (no request created)
        mock_create_request.assert_not_called()

        # Result should indicate skip (could be success=True with existing path)
        assert success is True
        assert error is None

    @patch('data_handler.download.create_download_request')
    @patch('data_handler.download.Path.stat')
    @patch('rasterio.open')
    def test_sets_download_start_before_download(
        self, mock_rasterio, mock_stat, mock_create_request, db_session, sample_product_in_db, tmp_path
    ):
        """Test that download_start timestamp is set before the actual download."""
        product, status, aoi = sample_product_in_db

        # Verify download_start is initially None
        assert status.download_start is None

        # Mock the download
        mock_request = Mock()
        mock_request.get_data.return_value = [np.zeros((100, 100, 2), dtype=np.uint16)]
        mock_create_request.return_value = mock_request

        mock_file = MagicMock()
        mock_rasterio.return_value.__enter__.return_value = mock_file

        mock_stat.return_value.st_size = 4 * 1024 * 1024

        # Execute download
        download_product(db_session, product.id, output_dir=tmp_path, config=mock_config)

        # Refresh and verify download_start was set
        db_session.refresh(status)
        assert status.download_start is not None


# ============================================================================
# Test Download Function - Error Cases
# ============================================================================

class TestDownloadProductErrors:
    """Test suite for download_product() error scenarios."""

    # Tests will be implemented in the next step
    pass


# ============================================================================
# Test Batch Download
# ============================================================================

class TestDownloadPendingProducts:
    """Test suite for download_pending_products() function."""

    @patch('data_handler.download.download_product')
    def test_finds_pending_records(self, mock_download, db_session, sample_product_in_db, tmp_path, mock_config):
        """Test that function finds and processes pending records."""
        product, status, aoi = sample_product_in_db

        # Mock download_product to succeed
        mock_download.return_value = (True, None, Path('/fake/path.tif'))

        # Execute batch download
        results = download_pending_products(db_session, config=mock_config)

        # Verify download_product was called for the pending product
        assert mock_download.call_count >= 1

    @patch('data_handler.download.download_product')
    def test_processes_multiple_products(self, mock_download, db_session, tmp_path, mock_config):
        """Test that batch download processes multiple products."""
        # Create multiple pending products
        aoi_repo = AOIRepository(db_session)
        aoi = aoi_repo.create(
            name='ben_nevis',
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry='POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))',
            size_km=10.0
        )

        product_repo = SentinelProductRepository(db_session)
        status_repo = DownloadStatusRepository(db_session)

        # Create 3 products with pending status
        for i in range(3):
            product = product_repo.create(
                product_id=f'S2A_MSIL2A_2024011{i}T113321_N0510_R080_T30VVJ_2024011{i}T145219',
                aoi_id=aoi.id,
                acquisition_dt=datetime(2024, 1, 10 + i),
                cloud_cover=15.5,
                geometry='{"type": "Polygon", "coordinates": []}'
            )
            status_repo.create(product_id=product.id, status='pending')

        # Mock download_product to succeed
        mock_download.return_value = (True, None, Path('/fake/path.tif'))

        # Execute batch download
        results = download_pending_products(db_session, config=mock_config)

        # Verify all 3 products were processed
        assert mock_download.call_count == 3
        assert results['success'] == 3

    @patch('data_handler.download.download_product')
    def test_returns_summary_dict(self, mock_download, db_session, sample_product_in_db, tmp_path, mock_config):
        """Test that function returns summary dictionary with counts."""
        product, status, aoi = sample_product_in_db

        # Mock download_product to succeed
        mock_download.return_value = (True, None, Path('/fake/path.tif'))

        # Execute batch download
        results = download_pending_products(db_session, config=mock_config)

        # Verify return value structure
        assert isinstance(results, dict)
        assert 'success' in results
        assert 'failed' in results
        assert 'skipped' in results
        assert results['success'] + results['failed'] + results['skipped'] >= 1

    @patch('data_handler.download.download_product')
    def test_handles_mixed_success_and_failure(self, mock_download, db_session, tmp_path, mock_config):
        """Test that batch download correctly counts successes and failures."""
        # Create multiple pending products
        aoi_repo = AOIRepository(db_session)
        aoi = aoi_repo.create(
            name='ben_nevis',
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry='POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))',
            size_km=10.0
        )

        product_repo = SentinelProductRepository(db_session)
        status_repo = DownloadStatusRepository(db_session)

        # Create 3 products
        for i in range(3):
            product = product_repo.create(
                product_id=f'S2A_MSIL2A_2024011{i}T113321_N0510_R080_T30VVJ_2024011{i}T145219',
                aoi_id=aoi.id,
                acquisition_dt=datetime(2024, 1, 10 + i),
                cloud_cover=15.5,
                geometry='{"type": "Polygon", "coordinates": []}'
            )
            status_repo.create(product_id=product.id, status='pending')

        # Mock download_product: first two succeed, third fails
        mock_download.side_effect = [
            (True, None, Path('/fake/path1.tif')),
            (True, None, Path('/fake/path2.tif')),
            (False, 'Network error', None),
        ]

        # Execute batch download
        results = download_pending_products(db_session, config=mock_config)

        # Verify counts
        assert results['success'] == 2
        assert results['failed'] == 1

    @patch('data_handler.download.download_product')
    def test_respects_limit_parameter(self, mock_download, db_session, tmp_path, mock_config):
        """Test that limit parameter restricts number of downloads."""
        # Create multiple pending products
        aoi_repo = AOIRepository(db_session)
        aoi = aoi_repo.create(
            name='ben_nevis',
            center_lat=56.7969,
            center_lon=-5.0036,
            geometry='POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))',
            size_km=10.0
        )

        product_repo = SentinelProductRepository(db_session)
        status_repo = DownloadStatusRepository(db_session)

        # Create 5 products
        for i in range(5):
            product = product_repo.create(
                product_id=f'S2A_MSIL2A_2024011{i}T113321_N0510_R080_T30VVJ_2024011{i}T145219',
                aoi_id=aoi.id,
                acquisition_dt=datetime(2024, 1, 10 + i),
                cloud_cover=15.5,
                geometry='{"type": "Polygon", "coordinates": []}'
            )
            status_repo.create(product_id=product.id, status='pending')

        # Mock download_product to succeed
        mock_download.return_value = (True, None, Path('/fake/path.tif'))

        # Execute batch download with limit=2
        results = download_pending_products(db_session, limit=2, config=mock_config)

        # Verify only 2 were processed
        assert mock_download.call_count == 2
        assert results['success'] <= 2

    @patch('data_handler.download.download_product')
    def test_accepts_max_retries_parameter(self, mock_download, db_session, sample_product_in_db, mock_config):
        """Test that function accepts max_retries parameter.

        This reproduces the notebook usage pattern where max_retries is specified.
        """
        product, status, aoi = sample_product_in_db

        # Mock download_product to succeed
        mock_download.return_value = (True, None, Path('/fake/path.tif'))

        # Execute with max_retries parameter (as used in notebook)
        results = download_pending_products(
            session=db_session,
            config=mock_config,
            limit=5,
            max_retries=2
        )

        # Should complete without error
        assert 'success' in results
        assert 'failed' in results
        assert 'skipped' in results
