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
import json
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

import pandas as pd
import geopandas as gpd
from sentinelhub import (
    SHConfig,
    DataCollection,
    BBox,
    CRS,
    SentinelHubCatalog,
    filter_times,
)
from shapely.geometry.base import BaseGeometry
from sqlalchemy.orm import Session


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


def seed_aois_from_geodataframe(
    session: Session,
    aois_gdf: gpd.GeoDataFrame,
    size_km: float = 10.0
) -> Tuple[int, int]:
    """Seed AOIs from a GeoDataFrame into the database.

    This function populates the AOI table from a GeoDataFrame (typically
    from aoi.get_aois()). It extracts center coordinates from geometry
    centroids and converts geometries to WKT format for storage.

    Args:
        session: SQLAlchemy session instance
        aois_gdf: GeoDataFrame with 'name' and 'geometry' columns
        size_km: Size of each AOI in kilometers (default 10.0)

    Returns:
        Tuple of (created_count, skipped_count)

    Example:
        >>> from data_handler.aoi import get_aois
        >>> from data_handler.database import create_db_engine, init_database, get_session_factory
        >>>
        >>> engine = create_db_engine(db_path='data/snow_patches.db')
        >>> init_database(engine)
        >>> session = get_session_factory(engine)()
        >>>
        >>> aois_gdf = get_aois()
        >>> created, skipped = seed_aois_from_geodataframe(session, aois_gdf)
        >>> print(f"Created {created} AOIs, skipped {skipped}")
        >>> session.close()
    """
    from data_handler.repositories import AOIRepository

    aoi_repo = AOIRepository(session)

    created_count = 0
    skipped_count = 0

    for _, row in aois_gdf.iterrows():
        name = row['name']

        # Skip if AOI already exists
        if aoi_repo.exists(name):
            skipped_count += 1
            continue

        # Extract center coordinates from centroid
        centroid = row['geometry'].centroid
        center_lat = centroid.y
        center_lon = centroid.x

        # Convert geometry to WKT string
        geometry_wkt = row['geometry'].wkt

        # Create AOI
        aoi_repo.create(
            name=name,
            center_lat=center_lat,
            center_lon=center_lon,
            geometry=geometry_wkt,
            size_km=size_km
        )
        created_count += 1

    return created_count, skipped_count


def save_products_to_db(
    session: Session,
    products_df: pd.DataFrame,
    aoi_name: str
) -> Tuple[int, int]:
    """Save discovered products to the database.

    This function takes a DataFrame of products (from find_sentinel_products())
    and saves them to the database, linked to the specified AOI.

    Args:
        session: SQLAlchemy session instance
        products_df: DataFrame with columns: id, product_id, date, cloud_cover, geometry
        aoi_name: Name of the AOI these products belong to

    Returns:
        Tuple of (created_count, skipped_count)

    Raises:
        ValueError: If the specified AOI is not found in the database

    Example:
        >>> from data_handler.discovery import find_sentinel_products, save_products_to_db
        >>> from data_handler.database import create_db_engine, init_database, get_session_factory
        >>> from datetime import datetime
        >>>
        >>> # Setup database and session
        >>> engine = create_db_engine(db_path='data/snow_patches.db')
        >>> session = get_session_factory(engine)()
        >>>
        >>> # Discover products
        >>> config = create_sh_config()
        >>> aoi = ... # Get AOI geometry
        >>> products_df = find_sentinel_products(
        ...     config, aoi, datetime(2024, 1, 1), datetime(2024, 1, 31)
        ... )
        >>>
        >>> # Save to database
        >>> created, skipped = save_products_to_db(session, products_df, 'Ben Nevis')
        >>> print(f"Saved {created} products, skipped {skipped} duplicates")
        >>> session.close()
    """
    from data_handler.repositories import AOIRepository, SentinelProductRepository

    aoi_repo = AOIRepository(session)
    product_repo = SentinelProductRepository(session)

    # Get the AOI
    aoi = aoi_repo.get_by_name(aoi_name)
    if aoi is None:
        raise ValueError(f"AOI '{aoi_name}' not found in database. Please seed AOIs first.")

    # Convert DataFrame to list of dictionaries for bulk creation
    products_data = []
    for _, row in products_df.iterrows():
        # Convert pandas Timestamp to Python datetime
        acquisition_dt = row['date'].to_pydatetime() if hasattr(row['date'], 'to_pydatetime') else row['date']

        # Convert geometry dict to JSON string
        if isinstance(row['geometry'], dict):
            geometry_str = json.dumps(row['geometry'])
        else:
            geometry_str = str(row['geometry'])

        products_data.append({
            'product_id': row['product_id'],
            'aoi_id': aoi.id,
            'acquisition_dt': acquisition_dt,
            'cloud_cover': row['cloud_cover'],
            'geometry': geometry_str
        })

    # Use bulk creation with deduplication
    created_count, skipped_count = product_repo.bulk_create_if_not_exists(products_data)

    return created_count, skipped_count
