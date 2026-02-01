"""
Example workflow for snow mask generation from downloaded Sentinel-2 products.

This script demonstrates:
1. Connecting to the database
2. Finding downloaded products ready for processing
3. Processing products with user-specified NDSI threshold
4. Displaying results and statistics
5. Tips for visualization

Usage:
    PYTHONPATH=. python examples/snow_mask_workflow.py

Requirements:
    - Database must exist (created by init_workflow.py)
    - Products must be downloaded (via download_workflow.py)
"""

from pathlib import Path
from sqlalchemy.orm import sessionmaker
from data_handler.database import get_engine, get_session_context_manager
from data_handler.repositories import DownloadStatusRepository, SnowMaskRepository, SentinelProductRepository
from data_handler.snow_mask import process_downloaded_products, DEFAULT_NDSI_THRESHOLD


def display_downloaded_products(session):
    """Display products available for snow mask processing."""
    download_repo = DownloadStatusRepository(session)
    product_repo = SentinelProductRepository(session)

    downloaded = download_repo.get_by_status("downloaded")

    if not downloaded:
        print("No downloaded products found.")
        print("Run download_workflow.py first to download imagery.")
        return False

    print(f"\nFound {len(downloaded)} downloaded products ready for processing:")
    print("-" * 100)
    print(f"{'ID':<5} {'Product':<50} {'Date':<12} {'Cloud%':<8} {'Size (MB)':<10}")
    print("-" * 100)

    for download in downloaded:
        product = product_repo.get_by_id(download.product_id)
        if product:
            date_str = product.acquisition_dt.strftime("%Y-%m-%d")
            size_mb = download.file_size_mb if download.file_size_mb else 0.0
            print(f"{product.id:<5} {product.product_id[:48]:<50} {date_str:<12} "
                  f"{product.cloud_cover:<8.1f} {size_mb:<10.1f}")

    print("-" * 100)
    return True


def get_user_threshold():
    """Prompt user for NDSI threshold."""
    print(f"\nNDSI Threshold Configuration")
    print(f"Default threshold: {DEFAULT_NDSI_THRESHOLD}")
    print(f"Valid range: 0.0 to 1.0")
    print(f"  - Higher values (e.g., 0.5): More conservative, only bright snow")
    print(f"  - Lower values (e.g., 0.3): More inclusive, may include partial snow")

    while True:
        user_input = input(f"\nEnter threshold (or press Enter for default {DEFAULT_NDSI_THRESHOLD}): ").strip()

        if not user_input:
            return DEFAULT_NDSI_THRESHOLD

        try:
            threshold = float(user_input)
            if 0.0 <= threshold <= 1.0:
                return threshold
            else:
                print("  Error: Threshold must be between 0.0 and 1.0")
        except ValueError:
            print("  Error: Please enter a valid number")


def get_processing_options():
    """Get user options for processing."""
    print("\nProcessing Options:")

    # Save masks option
    while True:
        save_input = input("Save mask files to disk? (y/n, default=y): ").strip().lower()
        if not save_input or save_input == 'y':
            save_masks = True
            break
        elif save_input == 'n':
            save_masks = False
            print("  Note: Only statistics will be saved to database")
            break
        else:
            print("  Please enter 'y' or 'n'")

    # Limit option
    while True:
        limit_input = input("Limit number of products to process (press Enter for all): ").strip()
        if not limit_input:
            limit = None
            break
        try:
            limit = int(limit_input)
            if limit > 0:
                break
            else:
                print("  Error: Limit must be positive")
        except ValueError:
            print("  Error: Please enter a valid number")

    return save_masks, limit


def display_results(session):
    """Display snow mask processing results."""
    snow_mask_repo = SnowMaskRepository(session)
    product_repo = SentinelProductRepository(session)

    masks = snow_mask_repo.get_all()

    if not masks:
        print("\nNo snow masks found in database.")
        return

    print(f"\n\nProcessing Results ({len(masks)} masks generated):")
    print("-" * 120)
    print(f"{'ID':<5} {'Product':<40} {'Date':<12} {'Cloud%':<8} {'Threshold':<10} {'Snow%':<8} {'Mask Path'}")
    print("-" * 120)

    for mask in masks:
        product = product_repo.get_by_id(mask.product_id)
        if product:
            date_str = product.acquisition_dt.strftime("%Y-%m-%d")
            mask_path_str = Path(mask.mask_path).name if mask.mask_path else "N/A"
            print(f"{mask.id:<5} {product.product_id[:38]:<40} {date_str:<12} "
                  f"{product.cloud_cover:<8.1f} {mask.ndsi_threshold:<10.2f} "
                  f"{mask.snow_pct:<8.1f} {mask_path_str}")

    print("-" * 120)


def display_visualization_tips():
    """Display tips for visualizing snow masks."""
    print("\n" + "=" * 80)
    print("Visualization Tips")
    print("=" * 80)

    print("\nOption 1: View masks with QGIS")
    print("  1. Open QGIS")
    print("  2. Add raster layer: data/snow_masks/{aoi}/{year}/{month}/*.tif")
    print("  3. Style: Use 'Paletted/Unique values' with 0=transparent, 1=white/blue")

    print("\nOption 2: Python visualization with matplotlib")
    print("""
import rasterio
import matplotlib.pyplot as plt
from pathlib import Path

# Read mask
mask_path = Path("data/snow_masks/ben_nevis/2024/01/S2A_..._ndsi0.4.tif")
with rasterio.open(mask_path) as src:
    mask = src.read(1)
    extent = [src.bounds.left, src.bounds.right, src.bounds.bottom, src.bounds.top]

# Plot
fig, ax = plt.subplots(figsize=(10, 10))
im = ax.imshow(mask, cmap='Blues', extent=extent, vmin=0, vmax=1)
ax.set_title(f"Snow Mask: {mask_path.name}")
ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")
plt.colorbar(im, ax=ax, label="Snow (0=no, 1=yes)")
plt.show()
""")

    print("\nOption 3: Compare multiple thresholds")
    print("""
# Process same product with different thresholds
thresholds = [0.3, 0.4, 0.5]
# Then compare masks side-by-side to see sensitivity
""")

    print("\nOption 4: Time series analysis")
    print("""
from data_handler.repositories import SnowMaskRepository
import pandas as pd

# Extract time series data
masks = snow_mask_repo.get_all()
data = []
for mask in masks:
    product = product_repo.get_by_id(mask.product_id)
    data.append({
        'date': product.acquisition_dt,
        'snow_pct': mask.snow_pct,
        'cloud_cover': product.cloud_cover,
        'aoi': product.aoi.name
    })

df = pd.DataFrame(data).sort_values('date')

# Plot time series
import matplotlib.pyplot as plt
for aoi in df['aoi'].unique():
    aoi_data = df[df['aoi'] == aoi]
    plt.plot(aoi_data['date'], aoi_data['snow_pct'], marker='o', label=aoi)

plt.xlabel('Date')
plt.ylabel('Snow Coverage (%)')
plt.title('Snow Coverage Over Time')
plt.legend()
plt.grid(True)
plt.show()
""")

    print("=" * 80)


def main():
    """Main workflow."""
    print("=" * 80)
    print("Snow Mask Generation Workflow")
    print("=" * 80)

    # Check database exists
    db_path = Path("data/snow_patches.db")
    if not db_path.exists():
        print(f"\nError: Database not found at {db_path}")
        print("Run init_workflow.py first to create the database.")
        return

    # Connect to database
    engine = get_engine(str(db_path))
    SessionLocal = sessionmaker(bind=engine)

    with get_session_context_manager(SessionLocal)() as session:
        # 1. Display downloaded products
        has_products = display_downloaded_products(session)
        if not has_products:
            return

        # 2. Get user configuration
        threshold = get_user_threshold()
        save_masks, limit = get_processing_options()

        # 3. Confirm processing
        print(f"\nProcessing Configuration:")
        print(f"  NDSI Threshold: {threshold}")
        print(f"  Save masks: {save_masks}")
        print(f"  Limit: {limit if limit else 'None (process all)'}")

        confirm = input("\nProceed with processing? (y/n): ").strip().lower()
        if confirm != 'y':
            print("Processing cancelled.")
            return

        # 4. Process products
        print("\nProcessing products...")
        print("-" * 80)

        results = process_downloaded_products(
            session,
            ndsi_threshold=threshold,
            save_masks=save_masks,
            limit=limit
        )

        # 5. Display summary
        print("-" * 80)
        print(f"\nProcessing Summary:")
        print(f"  Success: {results['success']}")
        print(f"  Failed: {results['failed']}")
        print(f"  Skipped: {results['skipped']}")

        if results['failed'] > 0:
            print("\nNote: Check error messages above for details on failures")

        # 6. Display results table
        display_results(session)

        # 7. Show visualization tips
        if results['success'] > 0:
            display_visualization_tips()

            if save_masks:
                print(f"\nSnow mask files saved to: data/snow_masks/")
                print("Database records updated with statistics and file paths")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nWorkflow interrupted by user.")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
