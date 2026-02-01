"""
Snow mask generation module.

This module provides functions for:
- Calculating NDSI (Normalized Difference Snow Index) from Sentinel-2 bands
- Applying threshold to generate binary snow masks
- Computing snow coverage statistics
- Processing downloaded products to create snow masks
- Saving masks as GeoTIFF files

Key workflow:
1. Read B03 (green) and B11 (SWIR) bands from downloaded GeoTIFF
2. Calculate NDSI = (B03 - B11) / (B03 + B11 + epsilon)
3. Apply threshold to create binary mask (0=no snow, 1=snow)
4. Calculate statistics (snow_pixels, total_pixels, snow_pct)
5. Save mask to hierarchical file structure
6. Update database with SnowMask record
"""

import numpy as np
import rasterio
from pathlib import Path
from datetime import datetime
from typing import Dict, Tuple, Optional, Any
from sqlalchemy.orm import Session

from data_handler.models import SentinelProduct, DownloadStatus, SnowMask
from data_handler.repositories import SentinelProductRepository, DownloadStatusRepository, SnowMaskRepository


# Constants
DEFAULT_NDSI_THRESHOLD = 0.4
EPSILON = 1e-8
MASK_DTYPE = np.uint8


# Custom Exceptions
class SnowMaskError(Exception):
    """Base exception for snow mask operations."""
    pass


class InvalidBandDataError(SnowMaskError):
    """Raised when band data is invalid."""
    pass


def calculate_ndsi(band_green: np.ndarray, band_swir: np.ndarray, epsilon: float = EPSILON) -> np.ndarray:
    """
    Calculate NDSI (Normalized Difference Snow Index) from B03 and B11 bands.

    NDSI = (B03 - B11) / (B03 + B11 + epsilon)

    Args:
        band_green: Green band (B03) as numpy array
        band_swir: SWIR-1 band (B11) as numpy array
        epsilon: Small value to prevent division by zero (default: 1e-8)

    Returns:
        NDSI array with values in range [-1, 1]

    Raises:
        ValueError: If band shapes don't match
    """
    if band_green.shape != band_swir.shape:
        raise ValueError(f"Shape mismatch: band_green {band_green.shape} != band_swir {band_swir.shape}")

    # Convert to float for calculation
    green = band_green.astype(np.float32)
    swir = band_swir.astype(np.float32)

    # Calculate NDSI with epsilon to prevent division by zero
    numerator = green - swir
    denominator = green + swir + epsilon

    ndsi = numerator / denominator

    return ndsi


def apply_threshold(ndsi: np.ndarray, threshold: float = DEFAULT_NDSI_THRESHOLD) -> np.ndarray:
    """
    Apply threshold to NDSI to generate binary snow mask.

    Args:
        ndsi: NDSI array (float values)
        threshold: Threshold value (default: 0.4). Values > threshold are classified as snow.

    Returns:
        Binary mask as UINT8 (0=no snow, 1=snow)
    """
    snow_mask = (ndsi > threshold).astype(MASK_DTYPE)
    return snow_mask


def calculate_snow_statistics(snow_mask: np.ndarray) -> Dict[str, int | float]:
    """
    Calculate snow coverage statistics from binary mask.

    Args:
        snow_mask: Binary snow mask (0=no snow, 1=snow)

    Returns:
        Dictionary with:
            - snow_pixels: Number of snow pixels (int)
            - total_pixels: Total number of pixels (int)
            - snow_pct: Snow coverage percentage (float)
    """
    snow_pixels = int(np.sum(snow_mask))
    total_pixels = int(snow_mask.size)
    snow_pct = float((snow_pixels / total_pixels) * 100.0) if total_pixels > 0 else 0.0

    return {
        "snow_pixels": snow_pixels,
        "total_pixels": total_pixels,
        "snow_pct": snow_pct
    }


def get_mask_output_path(
    product_id: str,
    aoi_name: str,
    acquisition_date: datetime,
    ndsi_threshold: float,
    base_dir: Path = Path("data/snow_masks")
) -> Path:
    """
    Generate hierarchical output path for snow mask file.

    Structure: {base_dir}/{aoi_name}/{year}/{month}/{product_id}_ndsi{threshold}.tif

    Args:
        product_id: Sentinel-2 product ID
        aoi_name: Area of Interest name
        acquisition_date: Product acquisition date
        ndsi_threshold: NDSI threshold used
        base_dir: Base directory for snow masks (default: data/snow_masks)

    Returns:
        Path object for mask file
    """
    year = acquisition_date.strftime("%Y")
    month = acquisition_date.strftime("%m")

    # Format threshold for filename (e.g., 0.4 -> "0.4")
    threshold_str = f"{ndsi_threshold:.1f}"

    filename = f"{product_id}_ndsi{threshold_str}.tif"

    output_path = base_dir / aoi_name / year / month / filename

    return output_path


def read_bands_from_geotiff(file_path: Path) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """
    Read B03 and B11 bands from downloaded GeoTIFF.

    Args:
        file_path: Path to GeoTIFF file

    Returns:
        Tuple of (band_green, band_swir, metadata)
        - band_green: B03 band as numpy array
        - band_swir: B11 band as numpy array
        - metadata: Dict with CRS, transform, etc.

    Raises:
        FileNotFoundError: If file doesn't exist
        InvalidBandDataError: If file doesn't have required bands
    """
    if not file_path.exists():
        raise FileNotFoundError(f"GeoTIFF file not found: {file_path}")

    with rasterio.open(file_path) as src:
        if src.count < 2:
            raise InvalidBandDataError(f"GeoTIFF must have at least 2 bands, found {src.count}")

        # Read bands (B03 is band 1, B11 is band 2 in our downloaded files)
        band_green = src.read(1)
        band_swir = src.read(2)

        # Extract metadata
        metadata = {
            "crs": src.crs,
            "transform": src.transform,
            "width": src.width,
            "height": src.height,
            "dtype": src.dtypes[0]
        }

    return band_green, band_swir, metadata


def save_snow_mask(snow_mask: np.ndarray, output_path: Path, metadata: Dict[str, Any]) -> None:
    """
    Save binary snow mask as single-band GeoTIFF.

    Args:
        snow_mask: Binary mask array (UINT8)
        output_path: Path to save file
        metadata: Metadata dict with CRS, transform, etc.

    Raises:
        IOError: If file cannot be written
    """
    # Create parent directories if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write single-band GeoTIFF
    with rasterio.open(
        output_path,
        'w',
        driver='GTiff',
        height=snow_mask.shape[0],
        width=snow_mask.shape[1],
        count=1,
        dtype=MASK_DTYPE,
        crs=metadata.get("crs"),
        transform=metadata.get("transform"),
        compress='lzw'
    ) as dst:
        dst.write(snow_mask, 1)


def process_product_snow_mask(
    session: Session,
    product_db_id: int,
    ndsi_threshold: float = DEFAULT_NDSI_THRESHOLD,
    save_mask: bool = True
) -> Tuple[bool, Optional[str], Optional[Dict]]:
    """
    Process single product to generate snow mask and update database.

    Workflow:
    1. Fetch product and verify download status
    2. Update DownloadStatus to 'processing'
    3. Read B03/B11 from GeoTIFF
    4. Calculate NDSI and apply threshold
    5. Calculate statistics
    6. Save mask (if save_mask=True)
    7. Create SnowMask record
    8. Update DownloadStatus to 'processed'

    Args:
        session: SQLAlchemy database session
        product_db_id: Database ID of product to process
        ndsi_threshold: NDSI threshold for snow classification
        save_mask: Whether to save mask to file (default: True)

    Returns:
        Tuple of (success, error_message, result_data)
        - success: True if processing succeeded
        - error_message: Error description if failed, None otherwise
        - result_data: Dict with statistics if succeeded, None otherwise
    """
    product_repo = SentinelProductRepository(session)
    download_repo = DownloadStatusRepository(session)
    snow_mask_repo = SnowMaskRepository(session)

    try:
        # 1. Fetch product
        product = product_repo.get_by_id(product_db_id)
        if not product:
            return False, f"Product {product_db_id} not found", None

        # Get download status
        download_status = download_repo.get_by_product_id(product_db_id)
        if not download_status:
            return False, f"No download status for product {product_db_id}", None

        if download_status.status != "downloaded":
            return False, f"Product not downloaded (status: {download_status.status})", None

        # Get AOI for path generation
        aoi = product.aoi
        if not aoi:
            return False, f"Product {product_db_id} has no associated AOI", None

        # 2. Update status to processing
        download_status.status = "processing"
        session.commit()

        # 3. Read bands from GeoTIFF
        file_path = Path(download_status.local_path)
        band_green, band_swir, metadata = read_bands_from_geotiff(file_path)

        # 4. Calculate NDSI and apply threshold
        ndsi = calculate_ndsi(band_green, band_swir)
        snow_mask = apply_threshold(ndsi, threshold=ndsi_threshold)

        # 5. Calculate statistics
        stats = calculate_snow_statistics(snow_mask)

        # 6. Save mask if requested
        mask_path = None
        if save_mask:
            mask_path = get_mask_output_path(
                product.product_id,
                aoi.name,
                product.acquisition_dt,
                ndsi_threshold
            )
            save_snow_mask(snow_mask, mask_path, metadata)

        # 7. Create SnowMask record
        snow_mask_record = snow_mask_repo.create(
            product_id=product_db_id,
            ndsi_threshold=ndsi_threshold,
            snow_pixels=stats["snow_pixels"],
            total_pixels=stats["total_pixels"],
            snow_pct=stats["snow_pct"],
            mask_path=str(mask_path) if mask_path else None
        )

        # 8. Update status to processed
        download_status.status = "processed"
        session.commit()

        result = {
            "product_id": product.product_id,
            "snow_pct": stats["snow_pct"],
            "snow_pixels": stats["snow_pixels"],
            "total_pixels": stats["total_pixels"],
            "mask_path": str(mask_path) if mask_path else None
        }

        return True, None, result

    except FileNotFoundError as e:
        session.rollback()
        return False, f"File error: {str(e)}", None

    except InvalidBandDataError as e:
        session.rollback()
        return False, f"Band data error: {str(e)}", None

    except Exception as e:
        session.rollback()
        return False, f"Processing error: {str(e)}", None


def process_downloaded_products(
    session: Session,
    ndsi_threshold: float = DEFAULT_NDSI_THRESHOLD,
    save_masks: bool = True,
    limit: Optional[int] = None
) -> Dict[str, int]:
    """
    Batch process downloaded products to generate snow masks.

    Args:
        session: SQLAlchemy database session
        ndsi_threshold: NDSI threshold for snow classification
        save_masks: Whether to save masks to files
        limit: Maximum number of products to process (None = all)

    Returns:
        Dictionary with processing summary:
            - success: Number of successfully processed products
            - failed: Number of failed products
            - skipped: Number of skipped products
    """
    download_repo = DownloadStatusRepository(session)

    # Find downloaded products
    downloaded = download_repo.get_by_status("downloaded")

    if limit:
        downloaded = downloaded[:limit]

    success_count = 0
    failed_count = 0
    skipped_count = 0

    for download in downloaded:
        success, error_msg, result = process_product_snow_mask(
            session,
            download.product_id,
            ndsi_threshold,
            save_masks
        )

        if success:
            success_count += 1
        else:
            failed_count += 1
            print(f"Failed to process product {download.product_id}: {error_msg}")

    return {
        "success": success_count,
        "failed": failed_count,
        "skipped": skipped_count
    }
