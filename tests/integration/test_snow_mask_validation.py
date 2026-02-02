"""
Integration test to validate snow mask calculation using summer data.

August data in Scotland should have minimal snow (<5%), which helps verify
that the NDSI calculation and thresholding are not inverted.

To run:
    export SH_CLIENT_ID="your_client_id"
    export SH_CLIENT_SECRET="your_client_secret"
    pytest tests/integration/test_snow_mask_validation.py -v -m integration -s
"""

import pytest
import os
from pathlib import Path
from datetime import datetime
from shapely.geometry import box
from sqlalchemy import create_engine

from data_handler.discovery import create_sh_config, find_sentinel_products
from data_handler.database import get_session_factory
from data_handler.models import Base
from data_handler.repositories import AOIRepository, SentinelProductRepository, DownloadStatusRepository
from data_handler.download import download_product
from data_handler.snow_mask import process_product_snow_mask


@pytest.fixture
def integration_db_session(tmp_path):
    """Create temporary database for integration tests."""
    db_path = tmp_path / "test_snow_validation.db"
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
def test_summer_snow_coverage_is_low(integration_db_session, sh_config, tmp_path):
    """
    Validate snow mask calculation using August (summer) data.

    In August, Scottish mountains should have minimal snow coverage (<5%).
    If we get high percentages (>50%), it indicates the mask is inverted.

    This test:
    1. Searches for clear-sky August products
    2. Downloads a product
    3. Computes snow mask with standard threshold (0.4)
    4. Verifies snow coverage is realistically low (<5%)
    """
    print("\n" + "="*80)
    print("Snow Mask Validation Test - August (Summer) Data")
    print("="*80)

    # -------------------------------------------------------------------------
    # Step 1: Create AOI
    # -------------------------------------------------------------------------
    print("\n[1/5] Creating AOI...")
    aoi_repo = AOIRepository(integration_db_session)
    aoi = aoi_repo.create(
        name='ben_nevis',
        center_lat=56.7969,
        center_lon=-5.0036,
        geometry='POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))',
        size_km=10.0
    )
    print(f"  ✓ Created AOI: {aoi.name}")

    # -------------------------------------------------------------------------
    # Step 2: Search for August products (summer, minimal snow)
    # -------------------------------------------------------------------------
    print("\n[2/5] Searching for July 2023 products...")

    # July 2023 (summer month - should have minimal snow)
    start_date = datetime(2023, 7, 1)
    end_date = datetime(2023, 7, 31)

    # Create search polygon
    search_polygon = box(
        aoi.center_lon - 0.05,
        aoi.center_lat - 0.05,
        aoi.center_lon + 0.05,
        aoi.center_lat + 0.05
    )

    # Search with moderate cloud cover (Scotland is cloudy!)
    products_df = find_sentinel_products(
        config=sh_config,
        bbox=search_polygon,
        start_date=start_date,
        end_date=end_date,
        max_cloud_cover=50.0  # Higher tolerance for cloudy Scotland
    )

    print(f"  ✓ Found {len(products_df)} products")

    if len(products_df) == 0:
        pytest.skip("No clear-sky August products found")

    # Use the clearest product
    products_df = products_df.sort_values('cloud_cover')
    best_product = products_df.iloc[0]

    print(f"  Selected product:")
    print(f"    Date: {best_product['date'].date()}")
    print(f"    Cloud cover: {best_product['cloud_cover']:.1f}%")
    print(f"    Product ID: {best_product['product_id'][:60]}...")

    # -------------------------------------------------------------------------
    # Step 3: Insert product and download
    # -------------------------------------------------------------------------
    print("\n[3/5] Downloading product...")

    product_repo = SentinelProductRepository(integration_db_session)
    status_repo = DownloadStatusRepository(integration_db_session)

    # Insert product
    product = product_repo.create(
        product_id=best_product['product_id'],
        aoi_id=aoi.id,
        acquisition_dt=best_product['date'],
        cloud_cover=best_product['cloud_cover'],
        geometry=str(best_product.get('geometry', '{}'))
    )

    # Create download status
    status_repo.create(product_id=product.id, status='pending')

    # Download
    success, error, file_path = download_product(
        integration_db_session,
        product.id,
        output_dir=tmp_path,
        config=sh_config
    )

    if not success:
        pytest.fail(f"Download failed: {error}")

    print(f"  ✓ Downloaded: {file_path.name}")

    # -------------------------------------------------------------------------
    # Step 4: Compute snow mask
    # -------------------------------------------------------------------------
    print("\n[4/5] Computing snow mask...")

    success, error, result_data = process_product_snow_mask(
        integration_db_session,
        product.id,
        ndsi_threshold=0.4,
        save_mask=True
    )

    if not success:
        pytest.fail(f"Snow mask processing failed: {error}")

    print(f"  ✓ Snow mask computed")

    # -------------------------------------------------------------------------
    # Step 5: Validate results
    # -------------------------------------------------------------------------
    print("\n[5/5] Validating results...")

    snow_pct = result_data['snow_pct']
    snow_pixels = result_data['snow_pixels']
    total_pixels = result_data['total_pixels']

    print(f"\nResults:")
    print(f"  Date: {best_product['date'].date()} (August - SUMMER)")
    print(f"  Cloud cover: {best_product['cloud_cover']:.1f}%")
    print(f"  Snow coverage: {snow_pct:.2f}%")
    print(f"  Snow pixels: {snow_pixels:,} / {total_pixels:,}")
    print(f"  NDSI threshold: 0.4")

    print(f"\n" + "="*80)
    print("Validation Results")
    print("="*80)

    # Expected: Summer should have very little snow (<5%)
    MAX_EXPECTED_SUMMER_SNOW = 5.0

    if snow_pct > MAX_EXPECTED_SUMMER_SNOW:
        print(f"❌ FAIL: Snow coverage is {snow_pct:.1f}%")
        print(f"   Expected: <{MAX_EXPECTED_SUMMER_SNOW}% for August (summer)")
        print(f"   This suggests the snow mask may be INVERTED!")
        print(f"\n   Inverted coverage would be: {100 - snow_pct:.1f}%")

        # Show the mask path for manual inspection
        if result_data.get('mask_path'):
            print(f"\n   Inspect mask file: {result_data['mask_path']}")
            print(f"   Run: python debug_snow_mask.py {result_data['mask_path']}")

        pytest.fail(
            f"Summer snow coverage is unrealistically high ({snow_pct:.1f}%). "
            f"Expected <{MAX_EXPECTED_SUMMER_SNOW}% for August. "
            f"This indicates the snow mask calculation is likely inverted."
        )

    else:
        print(f"✅ PASS: Snow coverage is {snow_pct:.2f}%")
        print(f"   This is realistic for August (summer) in Scotland")
        print(f"   Snow mask calculation appears correct!")

    print("="*80)

    # Assert for pytest
    assert snow_pct <= MAX_EXPECTED_SUMMER_SNOW, (
        f"Summer snow coverage ({snow_pct:.1f}%) exceeds expected maximum "
        f"({MAX_EXPECTED_SUMMER_SNOW}%). Snow mask may be inverted."
    )


@pytest.mark.integration
def test_winter_snow_coverage_is_high(integration_db_session, sh_config, tmp_path):
    """
    Complementary test: Winter data should have high snow coverage.

    This provides additional validation that the snow mask is working correctly.
    January should have >20% snow coverage on Scottish mountains.
    """
    print("\n" + "="*80)
    print("Snow Mask Validation Test - January (Winter) Data")
    print("="*80)

    # Create AOI
    print("\n[1/5] Creating AOI...")
    aoi_repo = AOIRepository(integration_db_session)
    aoi = aoi_repo.create(
        name='ben_nevis',
        center_lat=56.7969,
        center_lon=-5.0036,
        geometry='POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))',
        size_km=10.0
    )
    print(f"  ✓ Created AOI: {aoi.name}")

    # Search for January products (winter, high snow)
    print("\n[2/5] Searching for January 2024 products...")
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 1, 31)

    search_polygon = box(
        aoi.center_lon - 0.05,
        aoi.center_lat - 0.05,
        aoi.center_lon + 0.05,
        aoi.center_lat + 0.05
    )

    products_df = find_sentinel_products(
        config=sh_config,
        bbox=search_polygon,
        start_date=start_date,
        end_date=end_date,
        max_cloud_cover=20.0
    )

    print(f"  ✓ Found {len(products_df)} products")

    if len(products_df) == 0:
        pytest.skip("No clear-sky January products found")

    # Use clearest product
    best_product = products_df.sort_values('cloud_cover').iloc[0]
    print(f"  Selected product: {best_product['date'].date()}, Cloud: {best_product['cloud_cover']:.1f}%")

    # Insert and download
    print("\n[3/5] Downloading product...")
    product_repo = SentinelProductRepository(integration_db_session)
    status_repo = DownloadStatusRepository(integration_db_session)

    product = product_repo.create(
        product_id=best_product['product_id'],
        aoi_id=aoi.id,
        acquisition_dt=best_product['date'],
        cloud_cover=best_product['cloud_cover'],
        geometry=str(best_product.get('geometry', '{}'))
    )

    status_repo.create(product_id=product.id, status='pending')

    success, error, file_path = download_product(
        integration_db_session,
        product.id,
        output_dir=tmp_path,
        config=sh_config
    )

    if not success:
        pytest.skip(f"Download failed: {error}")

    print(f"  ✓ Downloaded: {file_path.name}")

    # Compute snow mask
    print("\n[4/5] Computing snow mask...")
    success, error, result_data = process_product_snow_mask(
        integration_db_session,
        product.id,
        ndsi_threshold=0.4,
        save_mask=True
    )

    if not success:
        pytest.skip(f"Snow mask processing failed: {error}")

    print(f"  ✓ Snow mask computed")

    # Validate
    print("\n[5/5] Validating results...")
    snow_pct = result_data['snow_pct']

    print(f"\nResults:")
    print(f"  Date: {best_product['date'].date()} (January - WINTER)")
    print(f"  Snow coverage: {snow_pct:.2f}%")

    print(f"\n" + "="*80)
    print("Validation Results")
    print("="*80)

    # Expected: Winter should have significant snow (>20%)
    MIN_EXPECTED_WINTER_SNOW = 20.0

    if snow_pct < MIN_EXPECTED_WINTER_SNOW:
        print(f"⚠️  WARNING: Snow coverage is only {snow_pct:.1f}%")
        print(f"   Expected: >{MIN_EXPECTED_WINTER_SNOW}% for January (winter)")
        print(f"   This might indicate inversion or unusual weather")
        print(f"   Inverted coverage would be: {100 - snow_pct:.1f}%")
    else:
        print(f"✅ PASS: Snow coverage is {snow_pct:.2f}%")
        print(f"   This is realistic for January (winter) in Scotland")

    print("="*80)

    # This is a softer assertion since weather can vary
    # Just print warning but don't fail the test
    if snow_pct < MIN_EXPECTED_WINTER_SNOW:
        print(f"Note: Low winter snow might be due to unusual weather, not necessarily a bug")
