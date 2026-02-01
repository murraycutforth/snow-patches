"""Example: End-to-end database workflow.

This script demonstrates the complete database workflow:
1. Initialize database
2. Seed AOIs from geodataframe
3. Discover Sentinel-2 products
4. Save products to database
5. Query products from database

This example requires valid Copernicus Data Space credentials:
    export SH_CLIENT_ID="your_client_id"
    export SH_CLIENT_SECRET="your_client_secret"

Register at: https://dataspace.copernicus.eu/
"""

import os
from datetime import datetime
from pathlib import Path

# Import database components
from data_handler.database import create_db_engine, init_database, get_session_factory

# Import data discovery and AOI components
from data_handler.aoi import get_aois
from data_handler.discovery import (
    create_sh_config,
    find_sentinel_products,
    seed_aois_from_geodataframe,
    save_products_to_db
)

# Import repositories for querying
from data_handler.repositories import AOIRepository, SentinelProductRepository


def main():
    """Run the complete database workflow."""

    # ========================================
    # Step 1: Initialize Database
    # ========================================
    print("Step 1: Initializing database...")

    # Create data directory if it doesn't exist
    data_dir = Path('data')
    data_dir.mkdir(exist_ok=True)

    # Create database engine and initialize schema
    db_path = data_dir / 'snow_patches.db'
    engine = create_db_engine(db_path=str(db_path))
    init_database(engine)

    # Create session factory
    SessionFactory = get_session_factory(engine)
    session = SessionFactory()

    print(f"✓ Database initialized at: {db_path}")

    # ========================================
    # Step 2: Seed AOIs
    # ========================================
    print("\nStep 2: Seeding AOIs...")

    # Get AOIs from aoi module
    aois_gdf = get_aois()
    print(f"  Found {len(aois_gdf)} AOIs: {', '.join(aois_gdf['name'].tolist())}")

    # Seed AOIs into database
    created, skipped = seed_aois_from_geodataframe(session, aois_gdf)
    print(f"✓ Created {created} AOIs, skipped {skipped} (already existed)")

    # ========================================
    # Step 3: Query AOIs from Database
    # ========================================
    print("\nStep 3: Querying AOIs from database...")

    aoi_repo = AOIRepository(session)
    all_aois = aoi_repo.get_all()

    for aoi in all_aois:
        print(f"  - {aoi.name}:")
        print(f"    Center: ({aoi.center_lat:.4f}, {aoi.center_lon:.4f})")
        print(f"    Size: {aoi.size_km} km")

    # ========================================
    # Step 4: Discover Sentinel-2 Products
    # ========================================
    print("\nStep 4: Discovering Sentinel-2 products...")
    print("  (This step requires valid credentials)")

    # Check if credentials are available
    if not os.getenv('SH_CLIENT_ID') or not os.getenv('SH_CLIENT_SECRET'):
        print("  ⚠️  Skipping product discovery - credentials not set")
        print("  To enable discovery, set SH_CLIENT_ID and SH_CLIENT_SECRET")
        session.close()
        return

    try:
        # Create SentinelHub config
        config = create_sh_config()

        # Discover products for each AOI
        for _, aoi_row in aois_gdf.iterrows():
            aoi_name = aoi_row['name']
            aoi_geometry = aoi_row['geometry']

            print(f"\n  Discovering products for {aoi_name}...")

            # Search for products in January 2024 with max 20% cloud cover
            products_df = find_sentinel_products(
                config=config,
                aoi_geometry=aoi_geometry,
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 1, 31),
                max_cloud_cover=20.0
            )

            print(f"    Found {len(products_df)} products")

            if len(products_df) > 0:
                # Save products to database
                created, skipped = save_products_to_db(session, products_df, aoi_name)
                print(f"    Saved {created} products, skipped {skipped} duplicates")

                # Show sample products
                print(f"    Sample products:")
                for _, product in products_df.head(3).iterrows():
                    print(f"      - {product['date'].strftime('%Y-%m-%d')}: "
                          f"{product['cloud_cover']:.1f}% cloud cover")

        print("\n✓ Product discovery complete")

    except ValueError as e:
        print(f"  ⚠️  Error: {e}")
        print("  Make sure credentials are set correctly")
        session.close()
        return

    # ========================================
    # Step 5: Query Products from Database
    # ========================================
    print("\nStep 5: Querying products from database...")

    product_repo = SentinelProductRepository(session)

    for aoi in all_aois:
        # Get all products for this AOI
        all_products = product_repo.get_by_aoi(aoi.id)
        print(f"\n  {aoi.name}: {len(all_products)} total products")

        if len(all_products) > 0:
            # Get products with low cloud cover
            clear_products = product_repo.get_by_aoi(
                aoi.id,
                max_cloud_cover=10.0
            )
            print(f"    - {len(clear_products)} with <10% cloud cover")

            # Get products in specific date range
            winter_products = product_repo.get_by_aoi(
                aoi.id,
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 1, 15)
            )
            print(f"    - {len(winter_products)} in first half of January")

            # Show sample product details
            sample = all_products[0]
            print(f"    Sample product:")
            print(f"      ID: {sample.product_id}")
            print(f"      Date: {sample.acquisition_dt.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"      Cloud cover: {sample.cloud_cover:.1f}%")

    # ========================================
    # Step 6: Database Statistics
    # ========================================
    print("\n" + "="*60)
    print("Database Statistics:")
    print("="*60)

    total_products = 0
    for aoi in all_aois:
        count = len(product_repo.get_by_aoi(aoi.id))
        total_products += count
        print(f"  {aoi.name}: {count} products")

    print(f"\n  Total products in database: {total_products}")
    print(f"  Database location: {db_path}")
    print(f"  Database size: {db_path.stat().st_size / 1024:.1f} KB")

    # ========================================
    # Cleanup
    # ========================================
    session.close()
    print("\n✓ Workflow complete!")


if __name__ == '__main__':
    main()
