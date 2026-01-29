"""Data discovery module for querying Sentinel-2 satellite imagery.

This module provides functionality to search for available Sentinel-2 scenes
from the Copernicus Data Space Ecosystem using the sentinelhub package.

Authentication:
    The sentinelhub library requires Copernicus Data Space credentials.
    These should be set as environment variables or in the SentinelHub config:
        - SH_CLIENT_ID: Your OAuth2 client ID
        - SH_CLIENT_SECRET: Your OAuth2 client secret

    You can register for free at: https://dataspace.copernicus.eu/

    Example usage:
        export SH_CLIENT_ID="your_client_id"
        export SH_CLIENT_SECRET="your_client_secret"

    Or configure using sentinelhub CLI:
        sentinelhub.config --sh_client_id <your_client_id> --sh_client_secret <your_client_secret>
"""

import os
from datetime import datetime
from typing import Optional, List, Dict, Any

import pandas as pd
from sentinelhub import (
    SHConfig,
    DataCollection,
    BBox,
    CRS,
    SentinelHubCatalog,
    filter_times,
)
from shapely.geometry.base import BaseGeometry


def create_sh_config(
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    instance_id: Optional[str] = None
) -> SHConfig:
    """Create and configure a SentinelHub configuration instance.

    Args:
        client_id: OAuth2 client ID. If None, reads from SH_CLIENT_ID environment
                   variable or sentinelhub config.
        client_secret: OAuth2 client secret. If None, reads from SH_CLIENT_SECRET
                       environment variable or sentinelhub config.
        instance_id: Optional instance ID for Sentinel Hub services (not required
                     for Copernicus Data Space).

    Returns:
        A configured SHConfig instance

    Raises:
        ValueError: If credentials are not provided and environment variables are not set

    Example:
        >>> config = create_sh_config()  # Uses environment variables
        >>> # Or explicitly provide credentials:
        >>> config = create_sh_config(client_id='id', client_secret='secret')
    """
    # Create config instance
    config = SHConfig()

    # Use environment variables if credentials not provided
    if client_id is None:
        client_id = os.getenv('SH_CLIENT_ID')
    if client_secret is None:
        client_secret = os.getenv('SH_CLIENT_SECRET')

    # Set credentials if provided
    if client_id and client_secret:
        config.sh_client_id = client_id
        config.sh_client_secret = client_secret

    # Configure for Copernicus Data Space Ecosystem (CDSE)
    # These are the endpoints for the free CDSE service
    config.sh_base_url = "https://sh.dataspace.copernicus.eu"
    config.sh_token_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

    # Set instance ID if provided
    if instance_id:
        config.instance_id = instance_id

    # Validate that we have credentials
    if not config.sh_client_id or not config.sh_client_secret:
        raise ValueError(
            "Copernicus Data Space credentials not found. Please provide client_id "
            "and client_secret as arguments or set SH_CLIENT_ID and SH_CLIENT_SECRET "
            "environment variables. Register at: https://dataspace.copernicus.eu/"
        )

    return config


def find_sentinel_products(
    config: SHConfig,
    aoi_geometry: BaseGeometry,
    start_date: datetime,
    end_date: datetime,
    max_cloud_cover: float = 20.0,
    data_collection: DataCollection = DataCollection.SENTINEL2_L2A
) -> pd.DataFrame:
    """Query the Copernicus Data Space for Sentinel-2 products matching criteria.

    This function searches for Sentinel-2 Level-2A (Bottom-of-Atmosphere reflectance)
    products that intersect with the given Area of Interest, fall within the specified
    date range, and meet the cloud cover threshold.

    Args:
        config: A configured SHConfig instance with valid credentials
        aoi_geometry: A Shapely geometry (Polygon or MultiPolygon) defining the
                      Area of Interest
        start_date: Start of the date range to search (inclusive)
        end_date: End of the date range to search (inclusive)
        max_cloud_cover: Maximum acceptable cloud cover percentage (0-100).
                         Products with higher cloud cover will be filtered out.
                         Default: 20.0
        data_collection: Sentinel data collection to search. Default: SENTINEL2_L2A
                         Options:
                         - DataCollection.SENTINEL2_L2A: Level-2A BOA reflectance
                         - DataCollection.SENTINEL2_L1C: Level-1C TOA reflectance

    Returns:
        A pandas DataFrame containing the filtered products. Each row represents
        one satellite scene with columns including:
            - id: Product identifier
            - date: Acquisition datetime
            - cloud_cover: Cloud cover percentage (0-100)
            - geometry: Product footprint geometry
            - product_id: Full product ID

        Returns an empty DataFrame with the expected columns if no products are found.

    Example:
        >>> from shapely.geometry import Polygon
        >>> from datetime import datetime
        >>> aoi = Polygon([(-5.1, 56.7), (-5.0, 56.7), (-5.0, 56.8), (-5.1, 56.8)])
        >>> config = create_sh_config()
        >>> products = find_sentinel_products(
        ...     config=config,
        ...     aoi_geometry=aoi,
        ...     start_date=datetime(2024, 1, 1),
        ...     end_date=datetime(2024, 1, 31),
        ...     max_cloud_cover=15.0
        ... )
        >>> print(f"Found {len(products)} suitable scenes")
    """
    # Convert shapely geometry to BBox
    # Get bounds in WGS84 (EPSG:4326)
    bounds = aoi_geometry.bounds  # (minx, miny, maxx, maxy)
    bbox = BBox(bbox=bounds, crs=CRS.WGS84)

    # Create catalog instance
    catalog = SentinelHubCatalog(config=config)

    # Define time range as string tuple
    time_interval = (start_date.isoformat(), end_date.isoformat())

    # Search for products
    search_iterator = catalog.search(
        collection=data_collection,
        bbox=bbox,
        time=time_interval,
        fields={
            "include": ["id", "properties.datetime", "properties.eo:cloud_cover"],
            "exclude": []
        },
    )

    # Collect all results
    results = list(search_iterator)

    # Convert results to DataFrame
    if results:
        products_data = []
        for item in results:
            # Extract properties
            properties = item.get('properties', {})

            # Get cloud cover
            cloud_cover = properties.get('eo:cloud_cover')

            # Filter by cloud cover
            if cloud_cover is not None and cloud_cover <= max_cloud_cover:
                products_data.append({
                    'id': item.get('id'),
                    'date': pd.to_datetime(properties.get('datetime')),
                    'cloud_cover': cloud_cover,
                    'geometry': item.get('geometry'),
                    'product_id': properties.get('productIdentifier', item.get('id')),
                })

        # Create DataFrame
        if products_data:
            products_df = pd.DataFrame(products_data)
        else:
            # Return empty DataFrame with expected columns
            products_df = pd.DataFrame(columns=[
                'id', 'date', 'cloud_cover', 'geometry', 'product_id'
            ])
    else:
        # Return empty DataFrame with expected column structure
        products_df = pd.DataFrame(columns=[
            'id', 'date', 'cloud_cover', 'geometry', 'product_id'
        ])

    return products_df


def summarize_products(products_df: pd.DataFrame) -> dict:
    """Generate a summary of discovered products.

    Args:
        products_df: DataFrame returned by find_sentinel_products()

    Returns:
        A dictionary containing summary statistics:
            - total_products: Total number of products found
            - date_range: Tuple of (earliest, latest) acquisition dates
            - avg_cloud_cover: Average cloud cover percentage
            - min_cloud_cover: Minimum cloud cover percentage
            - max_cloud_cover: Maximum cloud cover percentage

    Example:
        >>> summary = summarize_products(products_df)
        >>> print(f"Found {summary['total_products']} products")
        >>> print(f"Cloud cover range: {summary['min_cloud_cover']:.1f}% - "
        ...       f"{summary['max_cloud_cover']:.1f}%")
    """
    if products_df.empty:
        return {
            'total_products': 0,
            'date_range': (None, None),
            'avg_cloud_cover': None,
            'min_cloud_cover': None,
            'max_cloud_cover': None
        }

    return {
        'total_products': len(products_df),
        'date_range': (
            products_df['date'].min(),
            products_df['date'].max()
        ),
        'avg_cloud_cover': products_df['cloud_cover'].mean(),
        'min_cloud_cover': products_df['cloud_cover'].min(),
        'max_cloud_cover': products_df['cloud_cover'].max()
    }
