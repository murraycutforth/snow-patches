"""
Example: Sentinel-2 Data Download Workflow

This script demonstrates the complete workflow for downloading Sentinel-2 imagery:
1. Connect to database
2. Find pending products
3. Download products
4. Display results

Requirements:
- Database with discovered products (run discover_products.py first)
- Sentinel Hub credentials in environment variables:
  export SH_CLIENT_ID="your_client_id"
  export SH_CLIENT_SECRET="your_client_secret"

Usage:
    PYTHONPATH=. python examples/download_workflow.py
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_handler.database import create_db_engine, get_session_factory
from data_handler.download import download_pending_products, download_product
from data_handler.repositories import DownloadStatusRepository
from data_handler.discovery import create_sh_config


def main():
    """Run the download workflow."""
    print("=" * 70)
    print("Sentinel-2 Data Download Workflow")
    print("=" * 70)
    print()

    # Step 1: Check for credentials
    print("[1/5] Checking Sentinel Hub credentials...")
    client_id = os.getenv('SH_CLIENT_ID')
    client_secret = os.getenv('SH_CLIENT_SECRET')

    if not client_id or not client_secret:
        print("ERROR: Sentinel Hub credentials not found!")
        print("Please set environment variables:")
        print("  export SH_CLIENT_ID='your_client_id'")
        print("  export SH_CLIENT_SECRET='your_client_secret'")
        print()
        print("Get credentials at: https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings")
        sys.exit(1)

    print(f"✓ Found credentials (Client ID: {client_id[:8]}...)")
    config = create_sh_config(client_id, client_secret)
    print()

    # Step 2: Connect to database
    print("[2/5] Connecting to database...")
    db_path = Path('data/snow_patches.db')

    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        print("Please run discover_products.py first to create and populate the database.")
        sys.exit(1)

    engine = create_db_engine(db_path=str(db_path))
    SessionFactory = get_session_factory(engine)
    session = SessionFactory()
    print(f"✓ Connected to database: {db_path}")
    print()

    # Step 3: Check for pending products
    print("[3/5] Finding pending products...")
    status_repo = DownloadStatusRepository(session)
    pending_statuses = status_repo.get_pending()

    if not pending_statuses:
        print("No pending products found in database.")
        print("All products may already be downloaded or failed.")
        print()
        print("Summary of existing download statuses:")

        from data_handler.models import DownloadStatus
        all_statuses = session.query(DownloadStatus).all()

        if not all_statuses:
            print("  No download status records found.")
            print("  Run discover_products.py to populate the database.")
        else:
            from collections import Counter
            status_counts = Counter(s.status for s in all_statuses)
            for status_name, count in status_counts.items():
                print(f"  {status_name}: {count}")

        session.close()
        return

    print(f"✓ Found {len(pending_statuses)} pending products")
    print()

    # Display pending products
    print("Pending products:")
    for i, download_status in enumerate(pending_statuses[:5], 1):  # Show first 5
        product = download_status.product
        print(f"  {i}. {product.product_id}")
        print(f"     AOI: {product.aoi.name}")
        print(f"     Date: {product.acquisition_dt.strftime('%Y-%m-%d')}")
        print(f"     Cloud cover: {product.cloud_cover:.1f}%")

    if len(pending_statuses) > 5:
        print(f"  ... and {len(pending_statuses) - 5} more")
    print()

    # Step 4: Download products
    print("[4/5] Downloading products...")
    print(f"Starting downloads at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print()

    # Download first 3 products as example (to avoid quota issues)
    limit = min(3, len(pending_statuses))
    print(f"Downloading {limit} product(s) (use limit parameter to download more)...")
    print()

    try:
        results = download_pending_products(session, limit=limit, config=config)

        # Step 5: Display results
        print()
        print("[5/5] Download Results")
        print("-" * 70)
        print(f"Success:  {results['success']}")
        print(f"Failed:   {results['failed']}")
        print(f"Skipped:  {results['skipped']}")
        print(f"Total:    {results['success'] + results['failed'] + results['skipped']}")
        print()

        # Show downloaded files
        if results['success'] > 0:
            print("Downloaded files:")
            from data_handler.models import DownloadStatus
            downloaded = session.query(DownloadStatus).filter_by(status='downloaded').all()

            for download_status in downloaded[:limit]:
                product = download_status.product
                file_size_mb = download_status.file_size_mb or 0
                print(f"  • {product.product_id}")
                print(f"    Path: {download_status.local_path}")
                print(f"    Size: {file_size_mb:.2f} MB")
                print(f"    Downloaded: {download_status.download_end.strftime('%Y-%m-%d %H:%M:%S')}")
                print()

        # Show failed downloads
        if results['failed'] > 0:
            print("Failed downloads:")
            from data_handler.models import DownloadStatus
            failed = session.query(DownloadStatus).filter_by(status='failed').all()

            for download_status in failed[:5]:
                product = download_status.product
                error_msg = download_status.error_msg or "Unknown error"
                print(f"  • {product.product_id}")
                print(f"    Error: {error_msg}")
                print()

    except Exception as e:
        print(f"ERROR during download: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

    print("=" * 70)
    print("Download workflow complete!")
    print()
    print("Next steps:")
    print("  1. Verify downloaded files in data/sentinel2/")
    print("  2. Run snow mask generation (Phase 5 - coming soon)")
    print("=" * 70)


if __name__ == '__main__':
    main()
