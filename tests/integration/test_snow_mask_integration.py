"""
Integration tests for snow mask generation.

These tests use real GeoTIFF files and verify end-to-end workflows.
"""

import pytest
import numpy as np
import rasterio
from pathlib import Path
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from data_handler.models import Base, AOI, SentinelProduct, DownloadStatus, SnowMask
from data_handler.snow_mask import (
    calculate_ndsi,
    apply_threshold,
    process_product_snow_mask,
    read_bands_from_geotiff,
    save_snow_mask,
    get_mask_output_path
)
from data_handler.repositories import SnowMaskRepository


@pytest.fixture
def integration_db_session():
    """Create in-memory database for integration tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def create_synthetic_geotiff(file_path: Path, width: int = 100, height: int = 100):
    """Create a synthetic 2-band GeoTIFF for testing.

    Creates realistic B03 and B11 bands with known snow patterns.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Create synthetic bands
    # Top half: high B03, low B11 (snow-like: high NDSI)
    # Bottom half: low B03, high B11 (no snow: low NDSI)
    band_green = np.zeros((height, width), dtype=np.uint16)
    band_swir = np.zeros((height, width), dtype=np.uint16)

    # Snow region (top half)
    band_green[:height//2, :] = 8000  # High green reflectance
    band_swir[:height//2, :] = 2000   # Low SWIR reflectance

    # No-snow region (bottom half)
    band_green[height//2:, :] = 2000  # Low green reflectance
    band_swir[height//2:, :] = 8000   # High SWIR reflectance

    # Simple transform (not spatially accurate, just for testing)
    from rasterio.transform import from_bounds
    transform = from_bounds(-4.1, 55.9, -3.9, 56.1, width, height)

    # Write GeoTIFF
    with rasterio.open(
        file_path,
        'w',
        driver='GTiff',
        height=height,
        width=width,
        count=2,
        dtype=np.uint16,
        crs='EPSG:4326',
        transform=transform
    ) as dst:
        dst.write(band_green, 1)
        dst.write(band_swir, 2)


@pytest.mark.integration
def test_end_to_end_snow_mask_synthetic_data(integration_db_session, tmp_path):
    """Test end-to-end snow mask generation with synthetic GeoTIFF."""
    # 1. Create synthetic GeoTIFF
    geotiff_path = tmp_path / "test_product.tif"
    create_synthetic_geotiff(geotiff_path)

    # 2. Set up database
    aoi = AOI(
        name="test_aoi",
        center_lat=56.0,
        center_lon=-4.0,
        geometry='{"type": "Polygon", "coordinates": [[[-4.1, 55.9], [-3.9, 55.9], [-3.9, 56.1], [-4.1, 56.1], [-4.1, 55.9]]]}'
    )
    integration_db_session.add(aoi)
    integration_db_session.commit()

    product = SentinelProduct(
        aoi_id=aoi.id,
        product_id="S2A_SYNTHETIC_TEST",
        acquisition_dt=datetime(2024, 1, 15),
        cloud_cover=5.0,
        geometry='{"type": "Point", "coordinates": [-4.0, 56.0]}'
    )
    integration_db_session.add(product)
    integration_db_session.commit()

    download = DownloadStatus(
        product_id=product.id,
        status="downloaded",
        local_path=str(geotiff_path)
    )
    integration_db_session.add(download)
    integration_db_session.commit()

    # 3. Process product
    mask_output_dir = tmp_path / "masks"
    success, error_msg, result = process_product_snow_mask(
        integration_db_session,
        product.id,
        ndsi_threshold=0.4,
        save_mask=True
    )

    # 4. Verify processing
    assert success is True
    assert error_msg is None
    assert result is not None

    # 5. Verify results
    # With our synthetic data:
    # Top half: NDSI = (8000 - 2000) / (8000 + 2000) = 0.6 (snow)
    # Bottom half: NDSI = (2000 - 8000) / (2000 + 8000) = -0.6 (no snow)
    # So we expect ~50% snow coverage with threshold 0.4
    assert 45.0 <= result["snow_pct"] <= 55.0

    # 6. Verify database record
    snow_mask_repo = SnowMaskRepository(integration_db_session)
    mask_record = snow_mask_repo.get_by_product_and_threshold(product.id, 0.4)
    assert mask_record is not None
    assert mask_record.total_pixels == 10000
    assert 4500 <= mask_record.snow_pixels <= 5500

    # 7. Verify download status updated
    integration_db_session.refresh(download)
    assert download.status == "processed"

    # 8. Verify mask file exists and is valid
    mask_path = Path(result["mask_path"])
    assert mask_path.exists()

    with rasterio.open(mask_path) as src:
        assert src.count == 1  # Single band
        assert src.dtypes[0] == 'uint8'
        mask_data = src.read(1)
        unique_values = set(np.unique(mask_data))
        assert unique_values.issubset({0, 1})  # Only 0 and 1 values


@pytest.mark.integration
def test_multiple_thresholds_same_product(integration_db_session, tmp_path):
    """Test processing same product with different thresholds."""
    # 1. Create synthetic GeoTIFF
    geotiff_path = tmp_path / "test_product.tif"
    create_synthetic_geotiff(geotiff_path)

    # 2. Set up database
    aoi = AOI(
        name="test_aoi",
        center_lat=56.0,
        center_lon=-4.0,
        geometry='{"type": "Polygon", "coordinates": [[[-4.1, 55.9], [-3.9, 55.9], [-3.9, 56.1], [-4.1, 56.1], [-4.1, 55.9]]]}'
    )
    integration_db_session.add(aoi)
    integration_db_session.commit()

    product = SentinelProduct(
        aoi_id=aoi.id,
        product_id="S2A_MULTI_THRESHOLD_TEST",
        acquisition_dt=datetime(2024, 1, 15),
        cloud_cover=5.0,
        geometry='{"type": "Point", "coordinates": [-4.0, 56.0]}'
    )
    integration_db_session.add(product)
    integration_db_session.commit()

    download = DownloadStatus(
        product_id=product.id,
        status="downloaded",
        local_path=str(geotiff_path)
    )
    integration_db_session.add(download)
    integration_db_session.commit()

    # 3. Process with multiple thresholds
    thresholds = [0.3, 0.4, 0.5]
    results = {}

    for threshold in thresholds:
        # Reset download status for each run
        download.status = "downloaded"
        integration_db_session.commit()

        success, error_msg, result = process_product_snow_mask(
            integration_db_session,
            product.id,
            ndsi_threshold=threshold,
            save_mask=True
        )

        assert success is True
        results[threshold] = result

    # 4. Verify different thresholds produce different results
    # Higher threshold should result in lower snow coverage
    assert results[0.3]["snow_pct"] >= results[0.4]["snow_pct"]
    assert results[0.4]["snow_pct"] >= results[0.5]["snow_pct"]

    # 5. Verify database has all three records
    snow_mask_repo = SnowMaskRepository(integration_db_session)
    masks = snow_mask_repo.get_by_product(product.id)
    assert len(masks) == 3
    assert {m.ndsi_threshold for m in masks} == set(thresholds)

    # 6. Verify different mask files exist
    for threshold in thresholds:
        mask_path = Path(results[threshold]["mask_path"])
        assert mask_path.exists()
        assert f"_ndsi{threshold:.1f}.tif" in str(mask_path)


@pytest.mark.integration
def test_round_trip_read_write(tmp_path):
    """Test reading and writing GeoTIFF files preserves data correctly."""
    # 1. Create synthetic GeoTIFF
    input_path = tmp_path / "input.tif"
    create_synthetic_geotiff(input_path, width=50, height=50)

    # 2. Read bands
    band_green, band_swir, metadata = read_bands_from_geotiff(input_path)

    # 3. Calculate NDSI and create mask
    ndsi = calculate_ndsi(band_green, band_swir)
    snow_mask = apply_threshold(ndsi, threshold=0.4)

    # 4. Save mask
    output_path = tmp_path / "output_mask.tif"
    save_snow_mask(snow_mask, output_path, metadata)

    # 5. Read back and verify
    with rasterio.open(output_path) as src:
        # Check metadata preserved
        assert src.crs == metadata["crs"]
        assert src.transform == metadata["transform"]
        assert src.width == metadata["width"]
        assert src.height == metadata["height"]

        # Check data
        mask_read = src.read(1)
        np.testing.assert_array_equal(mask_read, snow_mask)

        # Check data type
        assert src.dtypes[0] == 'uint8'

        # Check values
        assert set(np.unique(mask_read)).issubset({0, 1})
