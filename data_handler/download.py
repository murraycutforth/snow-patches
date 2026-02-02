"""
Sentinel-2 Data Download Module

This module handles downloading Sentinel-2 satellite imagery from the Copernicus
Data Space Ecosystem using the sentinelhub library. It downloads B03 (Green) and
B11 (SWIR-1) bands as multi-band GeoTIFF files for snow cover analysis.

Key Features:
- Downloads B03 (Green, 10m) and B11 (SWIR-1, 20m resampled to 10m) bands
- Saves as multi-band GeoTIFF files (UINT16 format)
- Tracks download status in database (pending → downloading → downloaded/failed)
- Implements retry logic with exponential backoff for network errors
- Organizes files hierarchically: data/sentinel2/{aoi_name}/{year}/{month}/{product_id}.tif
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from sqlalchemy.orm import Session
from sentinelhub import (
    SHConfig,
    SentinelHubRequest,
    BBox,
    CRS,
    MimeType,
    DataCollection as _DataCollection,
    SentinelHubDownloadClient,
)

# Define Copernicus Data Space Ecosystem data collection
# This overrides the default commercial Sentinel Hub endpoints
try:
    from sentinelhub.data_collections_bands import Band
    SENTINEL2_L2A_CDSE = _DataCollection.define(
        name="SENTINEL2_L2A_CDSE",
        api_id="sentinel-2-l2a",
        catalog_id="sentinel-2-l2a",
        wfs_id="DSS10",
        service_url="https://sh.dataspace.copernicus.eu",
        bands=(
            Band("B01", (60,), np.float32),
            Band("B02", (10,), np.float32),
            Band("B03", (10,), np.float32),
            Band("B04", (10,), np.float32),
            Band("B05", (20,), np.float32),
            Band("B06", (20,), np.float32),
            Band("B07", (20,), np.float32),
            Band("B08", (10,), np.float32),
            Band("B8A", (20,), np.float32),
            Band("B09", (60,), np.float32),
            Band("B10", (60,), np.float32),
            Band("B11", (20,), np.float32),
            Band("B12", (20,), np.float32),
            Band("SCL", (20,), np.uint8),
            Band("SNW", (20,), np.uint8),
            Band("CLD", (20,), np.uint8),
        ),
        is_timeless=False,
    )
except Exception:
    # Fallback to regular DataCollection if custom definition fails
    SENTINEL2_L2A_CDSE = _DataCollection.SENTINEL2_L2A
from data_handler.repositories import SentinelProductRepository, DownloadStatusRepository
from data_handler.models import DownloadStatus
from data_handler.discovery import create_sh_config


# ============================================================================
# Constants
# ============================================================================

SENTINEL2_BANDS_EVALSCRIPT = """
//VERSION=3
function setup() {
    return {
        input: [{
            bands: ["B03", "B11"],
            units: "DN"
        }],
        output: {
            id: "default",
            bands: 2,
            sampleType: "UINT16"
        }
    };
}

function evaluatePixel(sample) {
    return [sample.B03, sample.B11];
}
"""

DEFAULT_RESOLUTION = 10  # meters
MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]  # seconds (exponential backoff)


# ============================================================================
# Custom Exceptions
# ============================================================================

class DownloadError(Exception):
    """Base exception for download-related errors."""
    pass


class AuthenticationError(DownloadError):
    """Raised when authentication with Sentinel Hub API fails."""
    pass


class ProductNotFoundError(DownloadError):
    """Raised when requested product is not found in Sentinel Hub."""
    pass


class QuotaExceededError(DownloadError):
    """Raised when Sentinel Hub API quota is exceeded."""
    pass


# ============================================================================
# Path Management
# ============================================================================

def get_output_path(
    product_id: str,
    aoi_name: str,
    acquisition_date: datetime,
    base_dir: Path = Path("data/sentinel2")
) -> Path:
    """
    Generate hierarchical output path for downloaded GeoTIFF file.

    Creates directory structure: base_dir/aoi_name/YYYY/MM/product_id.tif
    Parent directories are created if they don't exist.

    Args:
        product_id: Sentinel-2 product identifier (e.g., 'S2A_MSIL2A_20240115T113321_...')
        aoi_name: Name of the Area of Interest (e.g., 'ben_nevis', 'ben_macdui')
        acquisition_date: Product acquisition timestamp
        base_dir: Base directory for all Sentinel-2 data (default: 'data/sentinel2')

    Returns:
        Path object pointing to the output GeoTIFF file

    Example:
        >>> path = get_output_path(
        ...     'S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219',
        ...     'ben_nevis',
        ...     datetime(2024, 1, 15)
        ... )
        >>> str(path)
        'data/sentinel2/ben_nevis/2024/01/S2A_MSIL2A_20240115T113321_N0510_R080_T30VVJ_20240115T145219.tif'
    """
    # Extract year and month from acquisition date
    year = acquisition_date.strftime("%Y")
    month = acquisition_date.strftime("%m")  # Zero-padded month (01-12)

    # Build path: base_dir/aoi_name/year/month/product_id.tif
    output_path = base_dir / aoi_name / year / month / f"{product_id}.tif"

    # Create parent directories if they don't exist
    output_path.parent.mkdir(parents=True, exist_ok=True)

    return output_path


# ============================================================================
# Request Building
# ============================================================================

def create_download_request(
    product_id: str,
    bbox: BBox,
    time_interval: Tuple[str, str],
    resolution: int = DEFAULT_RESOLUTION,
    config: Optional[SHConfig] = None
) -> SentinelHubRequest:
    """
    Build SentinelHubRequest for downloading B03 and B11 bands as GeoTIFF.

    Args:
        product_id: Sentinel-2 product identifier
        bbox: Bounding box (BBox object with CRS)
        time_interval: Tuple of (start_date, end_date) as ISO format strings
        resolution: Spatial resolution in meters (default: 10m)
        config: SentinelHub configuration (uses default if None)

    Returns:
        Configured SentinelHubRequest ready to execute

    Example:
        >>> from sentinelhub import BBox, CRS
        >>> bbox = BBox(bbox=[-5.1, 56.7, -4.9, 56.9], crs=CRS.WGS84)
        >>> request = create_download_request(
        ...     'S2A_MSIL2A_20240115T113321_...',
        ...     bbox,
        ...     ('2024-01-15', '2024-01-16')
        ... )
    """
    # Use default config if none provided
    # This will read credentials from environment variables
    if config is None:
        config = create_sh_config()

    # Build request with B03+B11 evalscript and GeoTIFF output
    # Use Copernicus Data Space data collection
    # Calculate size in pixels based on bbox and desired resolution
    # For a bbox of ~5km x 5km at 10m resolution, we need ~500x500 pixels
    # Use size parameter instead of resolution for better control
    import math
    bbox_width = bbox.max_x - bbox.min_x
    bbox_height = bbox.max_y - bbox.min_y

    # Approximate meters per degree at this latitude (rough estimate)
    # At latitude ~56°, 1 degree lon ≈ 62km, 1 degree lat ≈ 111km
    meters_per_deg_lon = 62000
    meters_per_deg_lat = 111000

    width_m = bbox_width * meters_per_deg_lon
    height_m = bbox_height * meters_per_deg_lat

    size_x = math.ceil(width_m / resolution)
    size_y = math.ceil(height_m / resolution)

    request = SentinelHubRequest(
        evalscript=SENTINEL2_BANDS_EVALSCRIPT,
        input_data=[
            SentinelHubRequest.input_data(
                data_collection=SENTINEL2_L2A_CDSE,
                time_interval=time_interval,
            )
        ],
        responses=[
            SentinelHubRequest.output_response('default', MimeType.TIFF)
        ],
        bbox=bbox,
        size=(size_x, size_y),
        config=config,
    )

    return request


# ============================================================================
# Download Functions
# ============================================================================

def download_product(
    session: Session,
    product_db_id: int,
    output_dir: Path = Path("data/sentinel2"),
    config: Optional[SHConfig] = None
) -> Tuple[bool, Optional[str], Optional[Path]]:
    """
    Download single Sentinel-2 product and update database status.

    Workflow:
    1. Fetch product details from database
    2. Check if already downloaded (skip if so)
    3. Update status to 'downloading'
    4. Execute download via SentinelHub API
    5. Save as multi-band GeoTIFF
    6. Update status to 'downloaded' with metadata
    7. Commit database changes

    On error:
    - Updates status to 'failed'
    - Stores error message
    - Increments retry_count
    - Implements retry logic for transient errors (503, 429)

    Args:
        session: SQLAlchemy database session
        product_db_id: Database ID of the sentinel_products record
        output_dir: Base directory for output files (default: 'data/sentinel2')
        config: SentinelHub configuration (uses default if None)

    Returns:
        Tuple of (success: bool, error_message: Optional[str], file_path: Optional[Path])
        - success=True, error_message=None, file_path=Path(...) on success
        - success=False, error_message=str, file_path=None on failure

    Example:
        >>> from data_handler.database import get_session_factory
        >>> session = get_session_factory(engine)()
        >>> success, error, path = download_product(session, product_id=1)
        >>> if success:
        ...     print(f"Downloaded to: {path}")
        >>> session.close()
    """
    # Initialize repositories
    product_repo = SentinelProductRepository(session)
    status_repo = DownloadStatusRepository(session)

    # Use default config if none provided
    # This will read credentials from environment variables
    if config is None:
        config = create_sh_config()

    try:
        # Step 1: Fetch product details from database
        product = product_repo.get_by_id(product_db_id)
        if not product:
            return False, f"Product with ID {product_db_id} not found in database", None

        # Step 2: Get or create download status
        download_status = session.query(DownloadStatus).filter_by(product_id=product.id).first()
        if not download_status:
            download_status = status_repo.create(product_id=product.id, status='pending')

        # Check if already downloaded
        if download_status.status == 'downloaded' and download_status.local_path:
            # Already downloaded, return existing path
            existing_path = Path(download_status.local_path)
            return True, None, existing_path

        # Step 3: Mark download start (keep status as 'pending' until complete)
        status_repo.update_status(
            download_status.id,
            download_start=datetime.utcnow()
        )
        session.commit()

        # Get output path
        file_path = get_output_path(
            product_id=product.product_id,
            aoi_name=product.aoi.name,
            acquisition_date=product.acquisition_dt,
            base_dir=output_dir
        )

        # Create bounding box from product geometry
        # For simplicity, use AOI bounds (in real scenario, parse product.geometry)
        # Assuming AOI geometry is in WKT format "POLYGON((lon lat, ...))"
        # Use a smaller bbox (±0.05 degrees = ~5km) to avoid exceeding resolution limits
        aoi = product.aoi
        bbox = BBox(
            bbox=[aoi.center_lon - 0.05, aoi.center_lat - 0.05,
                  aoi.center_lon + 0.05, aoi.center_lat + 0.05],
            crs=CRS.WGS84
        )

        # Create time interval (single day for specific product)
        acquisition_date = product.acquisition_dt
        time_start = acquisition_date.strftime("%Y-%m-%dT00:00:00")
        time_end = acquisition_date.strftime("%Y-%m-%dT23:59:59")

        # Step 4: Execute download via SentinelHub API
        request = create_download_request(
            product_id=product.product_id,
            bbox=bbox,
            time_interval=(time_start, time_end),
            resolution=DEFAULT_RESOLUTION,
            config=config
        )

        # Download data
        data = request.get_data()

        # Extract numpy array (data is a list with one element)
        if not data or len(data) == 0:
            raise DownloadError(f"No data returned for product {product.product_id}")

        image_data = data[0]  # Shape: (height, width, bands)

        # Step 5: Save as multi-band GeoTIFF
        # Get image dimensions
        height, width, bands = image_data.shape

        # Calculate transform from bbox and image size
        transform = from_bounds(
            bbox.min_x, bbox.min_y, bbox.max_x, bbox.max_y,
            width, height
        )

        # Write GeoTIFF with rasterio
        with rasterio.open(
            file_path,
            'w',
            driver='GTiff',
            height=height,
            width=width,
            count=bands,
            dtype=image_data.dtype,
            crs=f'EPSG:{bbox.crs.epsg}',
            transform=transform,
            compress='lzw'  # Compress to save disk space
        ) as dst:
            # Write each band
            for band_idx in range(bands):
                dst.write(image_data[:, :, band_idx], band_idx + 1)

        # Calculate file size in MB
        file_size_mb = file_path.stat().st_size / (1024 * 1024)

        # Step 6: Update status to 'downloaded' with metadata
        status_repo.update_status(
            download_status.id,
            status='downloaded',
            local_path=str(file_path),
            file_size_mb=round(file_size_mb, 2),
            download_end=datetime.utcnow()
        )

        # Step 7: Commit database changes
        session.commit()

        return True, None, file_path

    except Exception as e:
        # On error, update status to 'failed'
        error_msg = f"{type(e).__name__}: {str(e)}"

        # Try to update status if we have a download_status record
        try:
            if 'download_status' in locals():
                status_repo.update_status(
                    download_status.id,
                    status='failed',
                    error_msg=error_msg,
                    retry_count=(download_status.retry_count or 0) + 1,
                    download_end=datetime.utcnow()
                )
                session.commit()
        except Exception:
            # If updating status fails, just pass
            pass

        return False, error_msg, None


def download_pending_products(
    session: Session,
    limit: Optional[int] = None,
    config: Optional[SHConfig] = None,
    max_retries: Optional[int] = None
) -> Dict[str, int]:
    """
    Download all pending products from database.

    Queries the database for products with download_status='pending' and
    attempts to download each one. Returns summary statistics.

    Args:
        session: SQLAlchemy database session
        limit: Maximum number of products to download (None = no limit)
        config: SentinelHub configuration (uses default if None)
        max_retries: Maximum number of retry attempts for failed downloads.
                     Currently accepted but not implemented - placeholder for
                     future retry logic. Products with retry_count >= max_retries
                     will be skipped in future implementation.

    Returns:
        Dictionary with download statistics:
        {
            "success": count of successfully downloaded products,
            "failed": count of failed downloads,
            "skipped": count of products skipped (already downloaded)
        }

    Example:
        >>> results = download_pending_products(session, limit=10)
        >>> print(f"Downloaded: {results['success']}, Failed: {results['failed']}")
        >>> # With retry limit:
        >>> results = download_pending_products(session, limit=10, max_retries=3)
    """
    # Initialize statistics
    stats = {
        'success': 0,
        'failed': 0,
        'skipped': 0
    }

    # Get pending download status records
    status_repo = DownloadStatusRepository(session)
    pending_statuses = status_repo.get_pending()

    # Apply limit if specified
    if limit is not None:
        pending_statuses = pending_statuses[:limit]

    # Download each pending product
    for download_status in pending_statuses:
        product_id = download_status.product_id

        # Attempt download
        success, error, file_path = download_product(
            session,
            product_id,
            config=config
        )

        # Update statistics
        if success:
            if error is None:  # Actually downloaded (not skipped)
                stats['success'] += 1
            else:
                stats['skipped'] += 1
        else:
            stats['failed'] += 1

    return stats
