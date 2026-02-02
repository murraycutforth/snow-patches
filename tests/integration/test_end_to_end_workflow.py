"""
End-to-end integration test for the complete workflow:
Discovery → Database → Download → Load → Plot

This test verifies the entire pipeline from searching for products to plotting images.
It uses winter 2024 data (Dec 2023 - Feb 2024) with 50% cloud cover threshold.

To run this test:
    export SH_CLIENT_ID="your_client_id"
    export SH_CLIENT_SECRET="your_client_secret"
    pytest tests/integration/test_end_to_end_workflow.py -v -m integration -s

Note: This test downloads real satellite imagery and may take several minutes to complete.
"""

import pytest
import os
from pathlib import Path
from datetime import datetime
import rasterio
import numpy as np
import matplotlib.pyplot as plt
from sqlalchemy import create_engine
from shapely.geometry import box

from data_handler.discovery import create_sh_config, find_sentinel_products
from data_handler.database import get_session_factory
from data_handler.models import Base
from data_handler.repositories import AOIRepository, SentinelProductRepository, DownloadStatusRepository
from data_handler.download import download_product
from data_handler.notebook_utils import get_winter_date_range
from sentinelhub import BBox, CRS


@pytest.fixture
def integration_db_session(tmp_path):
    """Create temporary database for integration tests."""
    db_path = tmp_path / "test_e2e.db"
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
def test_end_to_end_discover_download_load_plot(integration_db_session, sh_config, tmp_path):
    """
    Complete end-to-end integration test:
    1. Create AOI in database
    2. Discover Sentinel-2 products for winter 2024 (50% cloud cover)
    3. Insert discovered products into database
    4. Download products as GeoTIFF files
    5. Load downloaded images from disk
    6. Plot images to verify visualization works

    This test uses winter 2024 (Dec 2023 - Feb 2024) which has historical data
    guaranteed to be available.
    """
    print("\n" + "="*80)
    print("Starting End-to-End Workflow Test")
    print("="*80)

    # -------------------------------------------------------------------------
    # Step 1: Create AOI in database
    # -------------------------------------------------------------------------
    print("\n[1/6] Creating AOI in database...")
    aoi_repo = AOIRepository(integration_db_session)
    aoi = aoi_repo.create(
        name='ben_nevis',
        center_lat=56.7969,
        center_lon=-5.0036,
        geometry='POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))',
        size_km=10.0
    )
    print(f"  ✓ Created AOI: {aoi.name} (ID: {aoi.id})")
    print(f"    Center: ({aoi.center_lat:.4f}°N, {aoi.center_lon:.4f}°E)")

    # -------------------------------------------------------------------------
    # Step 2: Discover products for winter 2024
    # -------------------------------------------------------------------------
    print("\n[2/6] Discovering Sentinel-2 products for winter 2024...")

    # Get winter date range (Dec 2023 - Feb 2024)
    start_date, end_date = get_winter_date_range(2024)
    print(f"  Date range: {start_date.date()} to {end_date.date()}")

    # Create shapely polygon for search area (±0.05 degrees = ~5km)
    min_lon = aoi.center_lon - 0.05
    min_lat = aoi.center_lat - 0.05
    max_lon = aoi.center_lon + 0.05
    max_lat = aoi.center_lat + 0.05
    aoi_polygon = box(min_lon, min_lat, max_lon, max_lat)

    # Search for products with 50% cloud cover threshold
    max_cloud_cover = 50.0
    print(f"  Cloud cover threshold: {max_cloud_cover}%")
    print(f"  Searching...")

    products_df = find_sentinel_products(
        config=sh_config,
        bbox=aoi_polygon,
        start_date=start_date,
        end_date=end_date,
        max_cloud_cover=max_cloud_cover
    )

    print(f"  ✓ Found {len(products_df)} products")

    if len(products_df) == 0:
        pytest.skip("No products found for winter 2024 with 50% cloud cover")

    # Show first few products
    print(f"\n  Sample products:")
    for idx, row in products_df.head(3).iterrows():
        print(f"    - {row['date'].date()}: {row['product_id'][:50]}... (Cloud: {row['cloud_cover']:.1f}%)")

    # -------------------------------------------------------------------------
    # Step 3: Insert products into database
    # -------------------------------------------------------------------------
    print("\n[3/6] Inserting products into database...")
    product_repo = SentinelProductRepository(integration_db_session)
    status_repo = DownloadStatusRepository(integration_db_session)

    # Limit to first 3 products to keep test reasonably fast
    products_to_insert = products_df.head(3)
    inserted_products = []

    for _, row in products_to_insert.iterrows():
        # Create product record
        product = product_repo.create(
            product_id=row['product_id'],
            aoi_id=aoi.id,
            acquisition_dt=row['date'],
            cloud_cover=row['cloud_cover'],
            geometry=str(row.get('geometry', '{}'))
        )

        # Create download status record
        status = status_repo.create(product_id=product.id, status='pending')

        inserted_products.append(product)
        print(f"  ✓ Inserted: {row['date'].date()} (Cloud: {row['cloud_cover']:.1f}%)")

    print(f"  Total inserted: {len(inserted_products)} products")

    # -------------------------------------------------------------------------
    # Step 4: Download products to GeoTIFF files
    # -------------------------------------------------------------------------
    print("\n[4/6] Downloading products as GeoTIFF files...")
    downloaded_files = []

    for idx, product in enumerate(inserted_products, 1):
        print(f"  [{idx}/{len(inserted_products)}] Downloading {product.acquisition_dt.date()}...", end=" ")

        success, error, file_path = download_product(
            integration_db_session,
            product.id,
            output_dir=tmp_path,
            config=sh_config
        )

        if success:
            print(f"✓ {file_path.name}")
            downloaded_files.append((product, file_path))
        else:
            print(f"✗ Failed: {error[:80] if error else 'Unknown error'}...")

    print(f"  Successfully downloaded: {len(downloaded_files)}/{len(inserted_products)} products")

    if len(downloaded_files) == 0:
        pytest.fail("No products were successfully downloaded")

    # -------------------------------------------------------------------------
    # Step 5: Load downloaded images from disk
    # -------------------------------------------------------------------------
    print("\n[5/6] Loading images from disk...")
    loaded_images = []

    for product, file_path in downloaded_files:
        with rasterio.open(file_path) as src:
            # Read both bands (B03 Green and B11 SWIR)
            b03 = src.read(1)  # Green band
            b11 = src.read(2)  # SWIR band

            # Store metadata
            image_data = {
                'product': product,
                'file_path': file_path,
                'b03': b03,
                'b11': b11,
                'date': product.acquisition_dt,
                'cloud_cover': product.cloud_cover,
                'width': src.width,
                'height': src.height,
                'crs': src.crs,
                'bounds': src.bounds
            }
            loaded_images.append(image_data)

            print(f"  ✓ Loaded {product.acquisition_dt.date()}: {src.width}×{src.height} px, CRS: {src.crs}")

    # -------------------------------------------------------------------------
    # Step 6: Plot images to verify visualization works
    # -------------------------------------------------------------------------
    print("\n[6/6] Plotting images...")

    # Create figure with subplots for each image
    n_images = len(loaded_images)
    ncols = min(3, n_images)
    nrows = (n_images + ncols - 1) // ncols

    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 5, nrows * 5))
    fig.suptitle(f'Downloaded Sentinel-2 Images - Winter 2024 - {aoi.name}',
                 fontsize=14, fontweight='bold')

    # Flatten axes for easier indexing
    if n_images == 1:
        axes = [axes]
    else:
        axes = axes.flatten() if hasattr(axes, 'flatten') else axes

    for idx, img_data in enumerate(loaded_images):
        ax = axes[idx]

        # Display B03 (Green band) as grayscale with enhanced brightness
        # Sentinel-2 L2A values are in range 0-10000, normalize to 0-1
        b03_normalized = np.clip(img_data['b03'] / 3000.0, 0, 1)  # Brightness factor ~3

        ax.imshow(b03_normalized, cmap='gray', aspect='equal')
        ax.set_title(f"{img_data['date'].strftime('%Y-%m-%d')}\nCloud: {img_data['cloud_cover']:.1f}%",
                    fontsize=10, fontweight='bold')
        ax.set_xlabel(f"{img_data['width']}×{img_data['height']} px", fontsize=8)
        ax.set_xticks([])
        ax.set_yticks([])

    # Hide unused subplots
    for idx in range(n_images, len(axes)):
        axes[idx].axis('off')

    plt.tight_layout()

    # Save plot to file
    output_plot = tmp_path / 'test_plot.png'
    plt.savefig(output_plot, dpi=150, bbox_inches='tight')
    print(f"  ✓ Saved plot to: {output_plot}")

    # Close figure to free memory
    plt.close(fig)

    # -------------------------------------------------------------------------
    # Verification
    # -------------------------------------------------------------------------
    print("\n" + "="*80)
    print("End-to-End Test Summary")
    print("="*80)
    print(f"  AOIs created:          1")
    print(f"  Products discovered:   {len(products_df)}")
    print(f"  Products inserted:     {len(inserted_products)}")
    print(f"  Products downloaded:   {len(downloaded_files)}")
    print(f"  Images loaded:         {len(loaded_images)}")
    print(f"  Plot created:          ✓")
    print("="*80)

    # Verify all steps completed successfully
    assert aoi.id is not None, "AOI creation failed"
    assert len(products_df) > 0, "Product discovery found no results"
    assert len(inserted_products) > 0, "Product insertion failed"
    assert len(downloaded_files) > 0, "Product download failed"
    assert len(loaded_images) == len(downloaded_files), "Image loading failed"
    assert output_plot.exists(), "Plot creation failed"
    assert output_plot.stat().st_size > 10000, "Plot file is suspiciously small"

    print("\n✓ All workflow steps completed successfully!")


@pytest.mark.integration
def test_workflow_with_rgb_visualization(integration_db_session, sh_config, tmp_path):
    """
    Alternative end-to-end test using RGB visualization from notebook_utils.

    This test demonstrates downloading RGB images directly for visualization
    rather than using the B03+B11 production download pipeline.
    """
    from data_handler.notebook_utils import download_rgb_image, plot_sentinel_images

    print("\n" + "="*80)
    print("RGB Visualization Workflow Test")
    print("="*80)

    # Create AOI
    print("\n[1/4] Creating AOI...")
    aoi_repo = AOIRepository(integration_db_session)
    aoi = aoi_repo.create(
        name='ben_nevis',
        center_lat=56.7969,
        center_lon=-5.0036,
        geometry='POLYGON((-5.1 56.7, -4.9 56.7, -4.9 56.9, -5.1 56.9, -5.1 56.7))',
        size_km=10.0
    )
    print(f"  ✓ Created AOI: {aoi.name}")

    # Discover products
    print("\n[2/4] Discovering products for winter 2024...")
    start_date, end_date = get_winter_date_range(2024)

    # Create shapely polygon for search
    min_lon = aoi.center_lon - 0.05
    min_lat = aoi.center_lat - 0.05
    max_lon = aoi.center_lon + 0.05
    max_lat = aoi.center_lat + 0.05
    aoi_polygon = box(min_lon, min_lat, max_lon, max_lat)

    products_df = find_sentinel_products(
        config=sh_config,
        bbox=aoi_polygon,
        start_date=start_date,
        end_date=end_date,
        max_cloud_cover=50.0
    )
    print(f"  ✓ Found {len(products_df)} products")

    if len(products_df) == 0:
        pytest.skip("No products found for winter 2024")

    # Download RGB images (limit to 2 for speed)
    print("\n[3/4] Downloading RGB images...")
    images = []
    products_to_download = products_df.head(2)

    # Create BBox for downloads
    bbox = BBox(
        bbox=[min_lon, min_lat, max_lon, max_lat],
        crs=CRS.WGS84
    )

    for idx, (_, product) in enumerate(products_to_download.iterrows(), 1):
        print(f"  [{idx}/{len(products_to_download)}] {product['date'].date()}...", end=" ")
        try:
            rgb_image = download_rgb_image(
                config=sh_config,
                bbox=bbox,
                date=product['date'],
                product_id=product['product_id'],
                resolution=20  # Use 20m for faster download
            )
            images.append({
                'image': rgb_image,
                'date': product['date'],
                'cloud_cover': product['cloud_cover']
            })
            print(f"✓ {rgb_image.shape}")
        except Exception as e:
            print(f"✗ {str(e)[:80]}...")

    if len(images) == 0:
        pytest.fail("No RGB images downloaded successfully")

    print(f"  Successfully downloaded: {len(images)} RGB images")

    # Plot using notebook utils
    print("\n[4/4] Creating plot...")
    fig = plot_sentinel_images(
        images=images,
        aoi_name=aoi.name,
        bbox=bbox,
        ncols=2,
        brightness_factor=3.5,
        dpi=150
    )

    # Save plot
    output_plot = tmp_path / 'rgb_plot.png'
    fig.savefig(output_plot, dpi=150, bbox_inches='tight')
    plt.close(fig)

    print(f"  ✓ Saved RGB plot to: {output_plot}")

    # Verify
    assert len(images) > 0, "No images downloaded"
    assert output_plot.exists(), "Plot not created"
    assert output_plot.stat().st_size > 10000, "Plot file too small"

    print("\n✓ RGB visualization workflow completed successfully!")
