"""Utility functions for polished demo notebook.

This module provides high-level workflow functions for the snow patches monitoring demo.
All complex logic is contained here to keep the notebook clean and focused on results.
"""

from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import rasterio
from sqlalchemy.orm import Session
from sqlalchemy import func
from shapely.geometry import box

from data_handler.database import create_db_engine, init_database, get_session_factory
from data_handler.models import AOI, SentinelProduct, DownloadStatus, SnowMask
from data_handler.repositories import AOIRepository, SentinelProductRepository, DownloadStatusRepository
from data_handler.aoi import get_aois
from data_handler.discovery import find_sentinel_products, create_sh_config
from data_handler.download import download_product
from data_handler.snow_mask import process_product_snow_mask
from data_handler.notebook_utils import get_winter_date_range


# ============================================================================
# Database Setup
# ============================================================================

def setup_database_and_aois(
    db_path: str = "data/snow_patches_demo.db",
    aoi_names: Optional[List[str]] = None
) -> Tuple[Session, List[AOI]]:
    """Initialize database and insert AOI definitions.

    Creates database with schema, loads AOI definitions from aoi.py,
    and inserts them into the database.

    Args:
        db_path: Path to SQLite database file
        aoi_names: Optional list of AOI names to insert (default: all AOIs)

    Returns:
        Tuple of (session, list of AOI records)

    Example:
        >>> session, aois = setup_database_and_aois()
        >>> print(f"Created database with {len(aois)} AOIs")
    """
    # Create parent directory if it doesn't exist
    db_path_obj = Path(db_path)
    db_path_obj.parent.mkdir(parents=True, exist_ok=True)

    # Create database engine and initialize schema
    engine = create_db_engine(db_path=db_path, echo=False)
    init_database(engine)

    # Create session
    SessionFactory = get_session_factory(engine)
    session = SessionFactory()

    # Load AOI definitions from aoi.py
    aois_gdf = get_aois()

    # Filter by names if specified
    if aoi_names:
        aois_gdf = aois_gdf[aois_gdf['name'].isin(aoi_names)]

    # Insert AOIs into database
    aoi_repo = AOIRepository(session)
    aoi_records = []

    for _, row in aois_gdf.iterrows():
        # Check if AOI already exists
        if not aoi_repo.exists(row['name']):
            aoi = aoi_repo.create(
                name=row['name'],
                center_lat=row['center_lat'],
                center_lon=row['center_lon'],
                geometry=row['geometry'].wkt,
                size_km=row['size_km']
            )
            aoi_records.append(aoi)
        else:
            # Retrieve existing AOI
            aoi = aoi_repo.get_by_name(row['name'])
            aoi_records.append(aoi)

    return session, aoi_records


# ============================================================================
# Data Discovery and Download
# ============================================================================

def discover_and_download_winter_data(
    session: Session,
    config,
    winter_year: int,
    max_cloud_cover: float = 30.0,
    aoi_names: Optional[List[str]] = None,
    limit_per_aoi: Optional[int] = None
) -> Dict[str, any]:
    """Discover and download Sentinel-2 data for winter season.

    Complete workflow:
    1. Query AOIs from database
    2. Get winter date range
    3. Discover products for each AOI
    4. Insert products into database
    5. Download products as GeoTIFF files
    6. Return summary statistics

    Args:
        session: SQLAlchemy database session
        config: SentinelHub configuration
        winter_year: Year of winter (e.g., 2024 for winter 2023/2024)
        max_cloud_cover: Maximum cloud cover percentage (default: 30%)
        aoi_names: Optional list of AOI names to process (default: all)
        limit_per_aoi: Optional limit on products to download per AOI

    Returns:
        Dictionary with statistics:
        {
            'aois_processed': int,
            'products_discovered': int,
            'products_inserted': int,
            'products_downloaded': int,
            'products_failed': int,
            'details': {aoi_name: {...}}
        }

    Example:
        >>> from data_handler.discovery import create_sh_config
        >>> config = create_sh_config()
        >>> stats = discover_and_download_winter_data(
        ...     session, config, winter_year=2024, max_cloud_cover=30.0
        ... )
        >>> print(f"Downloaded {stats['products_downloaded']} products")
    """
    # Initialize statistics
    stats = {
        'aois_processed': 0,
        'products_discovered': 0,
        'products_inserted': 0,
        'products_downloaded': 0,
        'products_failed': 0,
        'details': {}
    }

    # Get winter date range
    start_date, end_date = get_winter_date_range(winter_year)

    # Query AOIs from database
    aoi_repo = AOIRepository(session)
    if aoi_names:
        aois = [aoi_repo.get_by_name(name) for name in aoi_names]
        aois = [aoi for aoi in aois if aoi is not None]
    else:
        aois = aoi_repo.get_all()

    # Process each AOI
    product_repo = SentinelProductRepository(session)
    status_repo = DownloadStatusRepository(session)

    for aoi in aois:
        aoi_stats = {
            'products_discovered': 0,
            'products_inserted': 0,
            'products_downloaded': 0,
            'products_failed': 0
        }

        print(f"\n{'='*80}")
        print(f"Processing AOI: {aoi.name}")
        print(f"{'='*80}")
        print(f"  Center: ({aoi.center_lat:.4f}°N, {aoi.center_lon:.4f}°E)")
        print(f"  Date range: {start_date.date()} to {end_date.date()}")
        print(f"  Cloud threshold: {max_cloud_cover}%")

        # Create search polygon (±0.05 degrees ≈ 5km)
        search_polygon = box(
            aoi.center_lon - 0.05,
            aoi.center_lat - 0.05,
            aoi.center_lon + 0.05,
            aoi.center_lat + 0.05
        )

        # Discover products
        print(f"  Discovering products...")
        try:
            products_df = find_sentinel_products(
                config=config,
                bbox=search_polygon,
                start_date=start_date,
                end_date=end_date,
                max_cloud_cover=max_cloud_cover
            )
            aoi_stats['products_discovered'] = len(products_df)
            print(f"  ✓ Found {len(products_df)} products")
        except Exception as e:
            print(f"  ✗ Discovery failed: {str(e)[:100]}")
            stats['details'][aoi.name] = aoi_stats
            continue

        if len(products_df) == 0:
            print(f"  No products found for {aoi.name}")
            stats['details'][aoi.name] = aoi_stats
            continue

        # Apply limit if specified
        if limit_per_aoi:
            products_df = products_df.head(limit_per_aoi)
            print(f"  Limited to {len(products_df)} products")

        # Insert products into database
        print(f"  Inserting products into database...")
        for _, row in products_df.iterrows():
            # Check if product already exists
            existing = product_repo.get_by_product_id(row['product_id'])
            if existing:
                print(f"    - {row['date'].date()}: Already exists (Cloud: {row['cloud_cover']:.1f}%)")
                continue

            # Create product record
            product = product_repo.create(
                product_id=row['product_id'],
                aoi_id=aoi.id,
                acquisition_dt=row['date'],
                cloud_cover=row['cloud_cover'],
                geometry=str(row.get('geometry', '{}'))
            )

            # Create download status
            status_repo.create(product_id=product.id, status='pending')
            aoi_stats['products_inserted'] += 1
            print(f"    ✓ {row['date'].date()}: Inserted (Cloud: {row['cloud_cover']:.1f}%)")

        # Download products
        if aoi_stats['products_inserted'] > 0:
            print(f"  Downloading {aoi_stats['products_inserted']} products...")

            # Get pending downloads for this AOI
            pending = session.query(DownloadStatus).join(SentinelProduct).filter(
                SentinelProduct.aoi_id == aoi.id,
                DownloadStatus.status == 'pending'
            ).all()

            for idx, status in enumerate(pending, 1):
                product = status.product
                print(f"    [{idx}/{len(pending)}] {product.acquisition_dt.date()}...", end=" ")

                success, error, file_path = download_product(
                    session,
                    product.id,
                    config=config
                )

                if success:
                    print(f"✓ {file_path.name if file_path else 'OK'}")
                    aoi_stats['products_downloaded'] += 1
                else:
                    print(f"✗ {error[:60] if error else 'Unknown error'}...")
                    aoi_stats['products_failed'] += 1

        # Update overall statistics
        stats['aois_processed'] += 1
        stats['products_discovered'] += aoi_stats['products_discovered']
        stats['products_inserted'] += aoi_stats['products_inserted']
        stats['products_downloaded'] += aoi_stats['products_downloaded']
        stats['products_failed'] += aoi_stats['products_failed']
        stats['details'][aoi.name] = aoi_stats

    return stats


# ============================================================================
# B03 Visualization
# ============================================================================

def load_b03_images_from_db(
    session: Session,
    aoi_name: Optional[str] = None,
    limit: Optional[int] = None
) -> List[Dict]:
    """Load B03 (Green) band images from downloaded products in database.

    Args:
        session: SQLAlchemy database session
        aoi_name: Optional AOI name to filter by
        limit: Optional limit on number of images to load

    Returns:
        List of dictionaries with keys:
        - 'b03': numpy array of B03 band
        - 'date': acquisition datetime
        - 'cloud_cover': cloud cover percentage
        - 'aoi_name': AOI name
        - 'width': image width in pixels
        - 'height': image height in pixels
        - 'file_path': path to GeoTIFF file

    Example:
        >>> images = load_b03_images_from_db(session, aoi_name='ben_nevis', limit=10)
        >>> print(f"Loaded {len(images)} images")
    """
    # Query downloaded products (include both 'downloaded' and 'processed' status)
    query = session.query(SentinelProduct, DownloadStatus).join(
        DownloadStatus
    ).filter(
        DownloadStatus.status.in_(['downloaded', 'processed'])
    )

    if aoi_name:
        query = query.join(AOI).filter(AOI.name == aoi_name)

    query = query.order_by(SentinelProduct.acquisition_dt)

    if limit:
        query = query.limit(limit)

    results = query.all()

    # Load B03 band from each GeoTIFF
    images_data = []
    for product, status in results:
        if not status.local_path or not Path(status.local_path).exists():
            continue

        try:
            with rasterio.open(status.local_path) as src:
                b03 = src.read(1)  # Band 1 is B03 (Green)

                images_data.append({
                    'b03': b03,
                    'date': product.acquisition_dt,
                    'cloud_cover': product.cloud_cover,
                    'aoi_name': product.aoi.name,
                    'width': src.width,
                    'height': src.height,
                    'file_path': status.local_path
                })
        except Exception as e:
            print(f"Warning: Failed to load {status.local_path}: {str(e)[:100]}")
            continue

    return images_data


def plot_b03_images(
    images_data: List[Dict],
    title: str = "Sentinel-2 B03 (Green Band) Images",
    ncols: int = 3,
    brightness_factor: float = 3.0,
    dpi: int = 150
) -> Figure:
    """Create grid plot of B03 band images.

    Args:
        images_data: List of image dictionaries from load_b03_images_from_db()
        title: Figure title
        ncols: Number of columns in grid
        brightness_factor: Brightness enhancement factor (default: 3.0)
        dpi: Figure DPI

    Returns:
        matplotlib Figure

    Example:
        >>> images = load_b03_images_from_db(session, aoi_name='ben_nevis')
        >>> fig = plot_b03_images(images, title="Ben Nevis - Winter 2024")
        >>> plt.show()
    """
    n_images = len(images_data)

    if n_images == 0:
        fig, ax = plt.subplots(figsize=(10, 6), dpi=dpi)
        ax.text(0.5, 0.5, 'No images to display',
                ha='center', va='center', fontsize=16)
        ax.axis('off')
        return fig

    # Calculate grid dimensions
    nrows = (n_images + ncols - 1) // ncols

    # Create figure
    figsize = (ncols * 5, nrows * 5)
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, dpi=dpi)
    fig.suptitle(title, fontsize=16, fontweight='bold')

    # Flatten axes
    if n_images == 1:
        axes = [axes]
    axes_flat = axes.flatten() if isinstance(axes, np.ndarray) else [axes]

    # Plot each image
    for idx, img_data in enumerate(images_data):
        ax = axes_flat[idx]

        # Normalize and enhance brightness
        # Sentinel-2 L2A: 0-10000 range, normalize to 0-1
        b03_normalized = np.clip(img_data['b03'] / 10000.0 * brightness_factor, 0, 1)

        ax.imshow(b03_normalized, cmap='gray', aspect='equal')
        ax.set_title(
            f"{img_data['date'].strftime('%Y-%m-%d')}\n"
            f"Cloud: {img_data['cloud_cover']:.1f}%",
            fontsize=11, fontweight='bold'
        )
        ax.set_xlabel(f"{img_data['width']}×{img_data['height']} px", fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])

    # Hide unused subplots
    for idx in range(n_images, len(axes_flat)):
        axes_flat[idx].axis('off')

    plt.tight_layout()
    return fig


def plot_b03_with_coordinates(
    images_data: List[Dict],
    title: str = "Sentinel-2 B03 (Green Band) with Coordinates",
    ncols: int = 2,
    brightness_factor: float = 3.0,
    dpi: int = 100
) -> Figure:
    """Create grid plot of B03 band images with lat/lon axes.

    Args:
        images_data: List of image dictionaries from load_b03_images_from_db()
        title: Figure title
        ncols: Number of columns in grid
        brightness_factor: Brightness enhancement factor (default: 3.0)
        dpi: Figure DPI

    Returns:
        matplotlib Figure

    Example:
        >>> images = load_b03_images_from_db(session, aoi_name='ben_nevis', limit=6)
        >>> fig = plot_b03_with_coordinates(images, title="Ben Nevis - B03 Band")
        >>> plt.show()
    """
    n_images = len(images_data)

    if n_images == 0:
        fig, ax = plt.subplots(figsize=(10, 6), dpi=dpi)
        ax.text(0.5, 0.5, 'No images to display',
                ha='center', va='center', fontsize=16)
        ax.axis('off')
        return fig

    # Calculate grid dimensions
    nrows = (n_images + ncols - 1) // ncols

    # Create figure
    figsize = (ncols * 6, nrows * 5)
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, dpi=dpi)
    fig.suptitle(title, fontsize=16, fontweight='bold')

    # Flatten axes
    if n_images == 1:
        axes = [axes]
    axes_flat = axes.flatten() if isinstance(axes, np.ndarray) else [axes]

    # Plot each image with geospatial coordinates
    for idx, img_data in enumerate(images_data):
        ax = axes_flat[idx]

        # Normalize and enhance brightness
        b03_normalized = np.clip(img_data['b03'] / 10000.0 * brightness_factor, 0, 1)

        # Load geotransform from file
        try:
            with rasterio.open(img_data['file_path']) as src:
                bounds = src.bounds  # (left, bottom, right, top) in CRS units
                extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]

                # Display with geographic extent
                ax.imshow(b03_normalized, cmap='gray', aspect='equal', extent=extent, origin='upper')

                # Add coordinate labels
                ax.set_xlabel('Longitude (°E)', fontsize=10)
                ax.set_ylabel('Latitude (°N)', fontsize=10)
                ax.tick_params(labelsize=8)

                # Format tick labels with degree symbols
                ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:.3f}°'))
                ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, p: f'{y:.3f}°'))

        except Exception as e:
            # Fallback to pixel coordinates if geotransform fails
            ax.imshow(b03_normalized, cmap='gray', aspect='equal')
            ax.set_xticks([])
            ax.set_yticks([])

        # Add title with date and cloud cover
        ax.set_title(
            f"{img_data['date'].strftime('%Y-%m-%d')}\n"
            f"Cloud: {img_data['cloud_cover']:.1f}% | {img_data['aoi_name']}",
            fontsize=10, fontweight='bold'
        )

    # Hide unused subplots
    for idx in range(n_images, len(axes_flat)):
        axes_flat[idx].axis('off')

    plt.tight_layout()
    return fig


# ============================================================================
# Snow Mask Computation and Visualization
# ============================================================================

def compute_snow_masks_for_aoi(
    session: Session,
    aoi_name: str,
    ndsi_threshold: float = 0.4,
    save_masks: bool = True
) -> Dict[str, any]:
    """Compute snow masks for all downloaded products of an AOI.

    Args:
        session: SQLAlchemy database session
        aoi_name: Name of AOI to process
        ndsi_threshold: NDSI threshold for snow classification (default: 0.4)
        save_masks: Whether to save masks as GeoTIFF files

    Returns:
        Dictionary with statistics:
        {
            'products_processed': int,
            'products_failed': int,
            'total_snow_pixels': int,
            'avg_snow_pct': float
        }

    Example:
        >>> stats = compute_snow_masks_for_aoi(session, 'ben_nevis', ndsi_threshold=0.4)
        >>> print(f"Processed {stats['products_processed']} products")
    """
    print(f"\n{'='*80}")
    print(f"Computing snow masks for: {aoi_name}")
    print(f"{'='*80}")
    print(f"  NDSI threshold: {ndsi_threshold}")
    print(f"  Save masks: {save_masks}")

    # Query downloaded products for this AOI
    products = session.query(SentinelProduct).join(AOI).join(DownloadStatus).filter(
        AOI.name == aoi_name,
        DownloadStatus.status == 'downloaded'
    ).order_by(SentinelProduct.acquisition_dt).all()

    print(f"  Found {len(products)} downloaded products")

    if len(products) == 0:
        return {
            'products_processed': 0,
            'products_failed': 0,
            'total_snow_pixels': 0,
            'avg_snow_pct': 0.0
        }

    # Process each product
    stats = {
        'products_processed': 0,
        'products_failed': 0,
        'total_snow_pixels': 0,
        'snow_percentages': []
    }

    for idx, product in enumerate(products, 1):
        print(f"  [{idx}/{len(products)}] {product.acquisition_dt.date()}...", end=" ")

        try:
            success, error, result_data = process_product_snow_mask(
                session,
                product.id,
                ndsi_threshold=ndsi_threshold,
                save_mask=save_masks
            )

            if success:
                # Get snow mask statistics
                snow_mask = session.query(SnowMask).filter_by(product_id=product.id).first()
                if snow_mask:
                    print(f"✓ Snow: {snow_mask.snow_pct:.1f}%")
                    stats['products_processed'] += 1
                    stats['total_snow_pixels'] += snow_mask.snow_pixels
                    stats['snow_percentages'].append(snow_mask.snow_pct)
                else:
                    print(f"✗ No mask record created")
                    stats['products_failed'] += 1
            else:
                print(f"✗ {error[:60] if error else 'Unknown error'}")
                stats['products_failed'] += 1

        except Exception as e:
            print(f"✗ {str(e)[:60]}")
            stats['products_failed'] += 1

    # Calculate average
    if stats['snow_percentages']:
        stats['avg_snow_pct'] = np.mean(stats['snow_percentages'])
    else:
        stats['avg_snow_pct'] = 0.0

    print(f"\n  Summary:")
    print(f"    Processed: {stats['products_processed']}")
    print(f"    Failed: {stats['products_failed']}")
    print(f"    Average snow coverage: {stats['avg_snow_pct']:.1f}%")

    return stats


def load_snow_masks_from_db(
    session: Session,
    aoi_name: Optional[str] = None,
    limit: Optional[int] = None
) -> List[Dict]:
    """Load snow mask images from database.

    Args:
        session: SQLAlchemy database session
        aoi_name: Optional AOI name to filter by
        limit: Optional limit on number of masks to load

    Returns:
        List of dictionaries with mask data and metadata

    Example:
        >>> masks = load_snow_masks_from_db(session, aoi_name='ben_nevis')
        >>> print(f"Loaded {len(masks)} snow masks")
    """
    # Query snow masks
    query = session.query(SnowMask, SentinelProduct).join(SentinelProduct)

    if aoi_name:
        query = query.join(AOI).filter(AOI.name == aoi_name)

    query = query.order_by(SentinelProduct.acquisition_dt)

    if limit:
        query = query.limit(limit)

    results = query.all()

    # Load masks from disk
    masks_data = []
    for snow_mask, product in results:
        if not snow_mask.mask_path or not Path(snow_mask.mask_path).exists():
            continue

        try:
            with rasterio.open(snow_mask.mask_path) as src:
                mask = src.read(1)  # Single band

                masks_data.append({
                    'mask': mask,
                    'date': product.acquisition_dt,
                    'cloud_cover': product.cloud_cover,
                    'aoi_name': product.aoi.name,
                    'snow_pct': snow_mask.snow_pct,
                    'snow_pixels': snow_mask.snow_pixels,
                    'total_pixels': snow_mask.total_pixels,
                    'width': src.width,
                    'height': src.height,
                    'file_path': snow_mask.mask_path
                })
        except Exception as e:
            print(f"Warning: Failed to load {snow_mask.mask_path}: {str(e)[:100]}")
            continue

    return masks_data


def plot_snow_masks(
    masks_data: List[Dict],
    title: str = "Snow Masks (NDSI Classification)",
    ncols: int = 3,
    dpi: int = 150
) -> Figure:
    """Create grid plot of snow masks.

    Args:
        masks_data: List of mask dictionaries from load_snow_masks_from_db()
        title: Figure title
        ncols: Number of columns in grid
        dpi: Figure DPI

    Returns:
        matplotlib Figure

    Example:
        >>> masks = load_snow_masks_from_db(session, aoi_name='ben_nevis')
        >>> fig = plot_snow_masks(masks, title="Ben Nevis Snow Masks")
        >>> plt.show()
    """
    n_masks = len(masks_data)

    if n_masks == 0:
        fig, ax = plt.subplots(figsize=(10, 6), dpi=dpi)
        ax.text(0.5, 0.5, 'No snow masks to display',
                ha='center', va='center', fontsize=16)
        ax.axis('off')
        return fig

    # Calculate grid dimensions
    nrows = (n_masks + ncols - 1) // ncols

    # Create figure
    figsize = (ncols * 5, nrows * 5)
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, dpi=dpi)
    fig.suptitle(title, fontsize=16, fontweight='bold')

    # Flatten axes
    if n_masks == 1:
        axes = [axes]
    axes_flat = axes.flatten() if isinstance(axes, np.ndarray) else [axes]

    # Plot each mask
    for idx, mask_data in enumerate(masks_data):
        ax = axes_flat[idx]

        # Display mask (0=no snow, 1=snow) with blue colormap
        ax.imshow(mask_data['mask'], cmap='Blues', aspect='equal', vmin=0, vmax=1)
        ax.set_title(
            f"{mask_data['date'].strftime('%Y-%m-%d')}\n"
            f"Snow: {mask_data['snow_pct']:.1f}% | Cloud: {mask_data['cloud_cover']:.1f}%",
            fontsize=10, fontweight='bold'
        )
        ax.set_xlabel(f"{mask_data['snow_pixels']:,} / {mask_data['total_pixels']:,} px", fontsize=8)
        ax.set_xticks([])
        ax.set_yticks([])

    # Hide unused subplots
    for idx in range(n_masks, len(axes_flat)):
        axes_flat[idx].axis('off')

    plt.tight_layout()
    return fig


# ============================================================================
# Snow Trend Analysis
# ============================================================================

def analyze_snow_trends(
    session: Session,
    aoi_name: Optional[str] = None
) -> pd.DataFrame:
    """Analyze snow coverage trends over time.

    Args:
        session: SQLAlchemy database session
        aoi_name: Optional AOI name to filter by

    Returns:
        DataFrame with columns:
        - date: acquisition date
        - aoi_name: AOI name
        - snow_pct: snow coverage percentage
        - snow_pixels: number of snow pixels
        - total_pixels: total image pixels
        - cloud_cover: cloud cover percentage

    Example:
        >>> trends = analyze_snow_trends(session, aoi_name='ben_nevis')
        >>> print(trends.head())
    """
    # Query snow masks with product info
    query = session.query(
        SentinelProduct.acquisition_dt,
        AOI.name,
        SnowMask.snow_pct,
        SnowMask.snow_pixels,
        SnowMask.total_pixels,
        SentinelProduct.cloud_cover
    ).join(SnowMask).join(AOI)

    if aoi_name:
        query = query.filter(AOI.name == aoi_name)

    query = query.order_by(SentinelProduct.acquisition_dt)

    # Convert to DataFrame
    results = query.all()

    if not results:
        return pd.DataFrame(columns=[
            'date', 'aoi_name', 'snow_pct', 'snow_pixels', 'total_pixels', 'cloud_cover'
        ])

    df = pd.DataFrame(results, columns=[
        'date', 'aoi_name', 'snow_pct', 'snow_pixels', 'total_pixels', 'cloud_cover'
    ])

    return df


def plot_snow_trends(
    trends_df: pd.DataFrame,
    title: str = "Snow Coverage Trends",
    figsize: Tuple[int, int] = (12, 6),
    dpi: int = 150
) -> Figure:
    """Create time series plot of snow coverage trends.

    Args:
        trends_df: DataFrame from analyze_snow_trends()
        title: Figure title
        figsize: Figure size in inches
        dpi: Figure DPI

    Returns:
        matplotlib Figure

    Example:
        >>> trends = analyze_snow_trends(session, aoi_name='ben_nevis')
        >>> fig = plot_snow_trends(trends, title="Ben Nevis Snow Trends")
        >>> plt.show()
    """
    if len(trends_df) == 0:
        fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
        ax.text(0.5, 0.5, 'No trend data to display',
                ha='center', va='center', fontsize=16)
        ax.axis('off')
        return fig

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize, dpi=dpi)
    fig.suptitle(title, fontsize=16, fontweight='bold')

    # Group by AOI if multiple AOIs present
    aois = trends_df['aoi_name'].unique()

    # Plot 1: Snow coverage percentage over time
    for aoi_name in aois:
        aoi_data = trends_df[trends_df['aoi_name'] == aoi_name]
        ax1.plot(aoi_data['date'], aoi_data['snow_pct'],
                marker='o', label=aoi_name, linewidth=2, markersize=6)

    ax1.set_ylabel('Snow Coverage (%)', fontsize=12, fontweight='bold')
    ax1.set_xlabel('Date', fontsize=12)
    ax1.grid(True, alpha=0.3)
    ax1.legend()
    ax1.set_ylim(0, 100)

    # Plot 2: Cloud cover over time
    for aoi_name in aois:
        aoi_data = trends_df[trends_df['aoi_name'] == aoi_name]
        ax2.plot(aoi_data['date'], aoi_data['cloud_cover'],
                marker='s', label=aoi_name, linewidth=2, markersize=6, alpha=0.7)

    ax2.set_ylabel('Cloud Cover (%)', fontsize=12, fontweight='bold')
    ax2.set_xlabel('Date', fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.legend()
    ax2.set_ylim(0, 100)

    plt.tight_layout()
    return fig
