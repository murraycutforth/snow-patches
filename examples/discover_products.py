"""Example script demonstrating Sentinel-2 product discovery.

This script shows how to use the AOI and discovery modules together to find
available Sentinel-2 scenes for the Scottish Highland regions using the
Copernicus Data Space Ecosystem.

Before running:
    1. Register for a free account at https://dataspace.copernicus.eu/
    2. Create OAuth2 credentials at: https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings
    3. Set environment variables:
       export SH_CLIENT_ID="your_client_id"
       export SH_CLIENT_SECRET="your_client_secret"

Usage:
    python examples/discover_products.py
"""

from datetime import datetime, timedelta

from data_handler.aoi import get_aois
from data_handler.discovery import create_sh_config, find_sentinel_products, summarize_products


def main():
    """Discover Sentinel-2 products for Ben Nevis and Ben Macdui."""
    print("=" * 80)
    print("Sentinel-2 Product Discovery for Scottish Highlands")
    print("Using Copernicus Data Space Ecosystem")
    print("=" * 80)

    # Step 1: Get Areas of Interest
    print("\n1. Loading Areas of Interest...")
    aois = get_aois()
    print(f"   ✓ Loaded {len(aois)} AOIs: {', '.join(aois['name'].values)}")

    # Step 2: Create SentinelHub configuration
    print("\n2. Connecting to Copernicus Data Space...")
    try:
        config = create_sh_config()
        print("   ✓ Successfully authenticated")
    except ValueError as e:
        print(f"   ✗ Error: {e}")
        print("\n   Please set SH_CLIENT_ID and SH_CLIENT_SECRET environment variables.")
        print("   Register at: https://dataspace.copernicus.eu/")
        return

    # Step 3: Define search parameters
    # Search for products from the last 30 days with max 20% cloud cover
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    max_cloud_cover = 20.0

    print(f"\n3. Search Parameters:")
    print(f"   Date Range: {start_date.date()} to {end_date.date()}")
    print(f"   Max Cloud Cover: {max_cloud_cover}%")

    # Step 4: Search for products for each AOI
    print(f"\n4. Searching for products...")

    for idx, aoi_row in aois.iterrows():
        aoi_name = aoi_row['name']
        aoi_geom = aoi_row['geometry']

        print(f"\n   {aoi_name}:")
        print(f"   {'─' * 60}")

        # Query for products
        products_df = find_sentinel_products(
            config=config,
            aoi_geometry=aoi_geom,
            start_date=start_date,
            end_date=end_date,
            max_cloud_cover=max_cloud_cover
        )

        if products_df.empty:
            print(f"   No products found matching criteria")
            continue

        # Display summary
        summary = summarize_products(products_df)
        print(f"   Found: {summary['total_products']} products")
        print(f"   Date Range: {summary['date_range'][0].date()} to {summary['date_range'][1].date()}")
        print(f"   Cloud Cover: {summary['min_cloud_cover']:.1f}% - {summary['max_cloud_cover']:.1f}%")
        print(f"   Avg Cloud Cover: {summary['avg_cloud_cover']:.1f}%")

        # Display individual products
        print(f"\n   Products:")
        for _, product in products_df.iterrows():
            print(f"     • {product['date'].date()} | "
                  f"Cloud: {product['cloud_cover']:5.1f}% | "
                  f"{product['product_id'][:50]}...")

    print("\n" + "=" * 80)
    print("Discovery complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
