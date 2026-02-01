"""
Integration tests for Sentinel-2 data download functionality.

These tests make real API calls to Sentinel Hub and require valid credentials.
They are marked with @pytest.mark.integration and are skipped in normal test runs.

To run these tests:
    export SH_CLIENT_ID="your_client_id"
    export SH_CLIENT_SECRET="your_client_secret"
    pytest tests/integration/test_download_integration.py -v -m integration

Note: These tests download real satellite imagery and count against your Sentinel Hub quota.
Use sparingly to avoid quota exhaustion.
"""

import pytest
import os
from pathlib import Path
from datetime import datetime
import rasterio
from sqlalchemy import create_engine

from data_handler.download import download_product
from data_handler.discovery import create_sh_config
from data_handler.database import get_session_factory
from data_handler.models import Base, AOI, SentinelProduct, DownloadStatus
from data_handler.repositories import AOIRepository, SentinelProductRepository, DownloadStatusRepository


@pytest.fixture
def integration_db_session(tmp_path):
    """Create temporary database for integration tests."""
    db_path = tmp_path / "test_integration.db"
    engine = create_engine(f'sqlite:///{db_path}')
    Base.metadata.create_all(engine)

    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()


@pytest.fixture
def sh_config():
    """Get Sentinel Hub configuration from environment variables."""
    client_id = os.getenv('SH_CLIENT_ID')
    client_secret = os.getenv('SH_CLIENT_SECRET')

    if not client_id or not client_secret:
        pytest.skip("Sentinel Hub credentials not found in environment")

    return create_sh_config(client_id, client_secret)


@pytest.mark.integration
def test_end_to_end_download_real_product(integration_db_session, sh_config, tmp_path):
    """
    Integration test: Download a real Sentinel-2 product from Copernicus Data Space.

    This test:
    1. Creates an AOI and product in the database
    2. Downloads real satellite imagery using Sentinel Hub API
    3. Verifies the GeoTIFF file structure
    4. Verifies database status is updated correctly

    Note: This test uses a specific product from 2024. If the product is no longer
    available in the Sentinel Hub archive, the test will fail. Update the product_id
    and dates as needed.
    """
    # Create AOI
    aoi_repo = AOIRepository(integration_db_session)
    aoi = aoi_repo.create(
        name='ben_nevis',
        center_lat=56.7969,
        center_lon=-5.0036,
        geometry='POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))',
        size_km=10.0
    )

    # Create product record
    # Use a recent product that should be available (adjust date as needed)
    product_repo = SentinelProductRepository(integration_db_session)
    product = product_repo.create(
        product_id='S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219',
        aoi_id=aoi.id,
        acquisition_dt=datetime(2024, 1, 15, 11, 33, 21),
        cloud_cover=15.5,
        geometry='{"type": "Polygon", "coordinates": []}'
    )

    # Create download status
    status_repo = DownloadStatusRepository(integration_db_session)
    status = status_repo.create(product_id=product.id, status='pending')

    # Execute download
    success, error, file_path = download_product(
        integration_db_session,
        product.id,
        output_dir=tmp_path,
        config=sh_config
    )

    # Verify download succeeded
    if not success:
        pytest.fail(f"Download failed: {error}")

    assert success is True
    assert error is None
    assert file_path is not None
    assert file_path.exists()

    # Verify GeoTIFF structure
    with rasterio.open(file_path) as src:
        # Should have 2 bands (B03 and B11)
        assert src.count == 2, f"Expected 2 bands, got {src.count}"

        # Check data type (should be UINT16)
        assert src.dtypes[0] == 'uint16', f"Expected uint16, got {src.dtypes[0]}"

        # Check that image has reasonable dimensions
        assert src.width > 0 and src.height > 0
        assert src.width < 2000 and src.height < 2000  # 10km at 10m resolution ≈ 1000x1000

        # Verify CRS is set
        assert src.crs is not None

        # Read bands and verify data ranges
        b03 = src.read(1)
        b11 = src.read(2)

        # Sentinel-2 L2A reflectance values are typically 0-10000,
        # but can exceed this due to atmospheric correction (values up to 65535 are possible)
        assert b03.min() >= 0 and b03.max() <= 65535
        assert b11.min() >= 0 and b11.max() <= 65535
        # Verify we have reasonable data (not all zeros or all max values)
        assert b03.mean() > 0 and b03.mean() < 20000
        assert b11.mean() > 0 and b11.mean() < 20000

    # Verify database status updated
    integration_db_session.refresh(status)
    assert status.status == 'downloaded'
    assert status.local_path == str(file_path)
    assert status.file_size_mb is not None
    assert status.file_size_mb > 0
    assert status.download_start is not None
    assert status.download_end is not None

    print(f"\n✓ Successfully downloaded and verified: {file_path}")
    print(f"  File size: {status.file_size_mb:.2f} MB")
    print(f"  Dimensions: {src.width} x {src.height} pixels")
    print(f"  CRS: {src.crs}")


@pytest.mark.integration
def test_download_handles_no_data_scenario(integration_db_session, sh_config, tmp_path):
    """
    Integration test: Verify handling when no data is returned.

    Note: This test may pass or fail depending on Sentinel Hub's response.
    It's mainly here to demonstrate error handling, but Sentinel Hub may
    return empty data or an error for requests outside data coverage.
    """
    # Create AOI
    aoi_repo = AOIRepository(integration_db_session)
    aoi = aoi_repo.create(
        name='test_aoi',
        center_lat=56.7969,
        center_lon=-5.0036,
        geometry='POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))',
        size_km=10.0
    )

    # Create product with a date before Sentinel-2 was launched (pre-2015)
    product_repo = SentinelProductRepository(integration_db_session)
    product = product_repo.create(
        product_id='S2A_MSIL2A_20100101T000000_TEST',
        aoi_id=aoi.id,
        acquisition_dt=datetime(2010, 1, 1),  # Before Sentinel-2 launch
        cloud_cover=0.0,
        geometry='{"type": "Polygon", "coordinates": []}'
    )

    # Create download status
    status_repo = DownloadStatusRepository(integration_db_session)
    status = status_repo.create(product_id=product.id, status='pending')

    # Attempt download
    success, error, file_path = download_product(
        integration_db_session,
        product.id,
        output_dir=tmp_path,
        config=sh_config
    )

    # The API might return empty data or an error
    # Just verify the function completes and database is updated
    integration_db_session.refresh(status)

    if success:
        print(f"\n✓ Download succeeded (API returned data even for early date)")
        print(f"  File: {file_path}")
        assert status.status == 'downloaded'
    else:
        print(f"\n✓ Download failed as expected for pre-launch date")
        print(f"  Error: {error[:100] if error else 'No error message'}...")
        assert status.status == 'failed'

    # Either outcome is acceptable for this test
    assert status.status in ['downloaded', 'failed']
