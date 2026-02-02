"""Utility functions for Jupyter notebook demonstrations.

This module provides helper functions for creating interactive visualizations
and downloading satellite imagery for demonstration purposes.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from pathlib import Path

import folium
import geopandas as gpd
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from sentinelhub import (
    SHConfig,
    SentinelHubRequest,
    BBox,
    CRS,
    MimeType,
    DataCollection as _DataCollection,
)

# Define Copernicus Data Space Ecosystem data collection
# This ensures we use the free CDSE endpoint, not the commercial Sentinel Hub
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


def create_aoi_map(aois_gdf: gpd.GeoDataFrame) -> folium.Map:
    """Create an interactive folium map showing Areas of Interest.

    Creates a map centered on the AOIs with rectangle overlays showing
    each bounding box. Each AOI is labeled with its name and has a popup
    showing details.

    Args:
        aois_gdf: GeoDataFrame with 'name', 'geometry', and optionally
                 'center_lat', 'center_lon' columns

    Returns:
        folium.Map object ready to display in Jupyter notebook

    Example:
        >>> from data_handler.aoi import get_aois
        >>> aois = get_aois()
        >>> m = create_aoi_map(aois)
        >>> m  # Display in notebook
    """
    # Calculate center point for the map (midpoint of all AOIs)
    # Use pre-defined center coordinates to avoid CRS warning
    if 'center_lat' in aois_gdf.columns and 'center_lon' in aois_gdf.columns:
        center_lat = aois_gdf['center_lat'].mean()
        center_lon = aois_gdf['center_lon'].mean()
    else:
        # Fallback to geometry centroids if center coordinates not available
        # Use WGS84 coordinates directly (acceptable for map centering)
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            center_lat = aois_gdf.geometry.centroid.y.mean()
            center_lon = aois_gdf.geometry.centroid.x.mean()

    # Create base map
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=8,
        tiles='OpenStreetMap'
    )

    # Add each AOI as a rectangle
    for _, row in aois_gdf.iterrows():
        # Get bounding box coordinates
        bounds = row['geometry'].bounds  # (minx, miny, maxx, maxy)

        # Create rectangle bounds for folium (sw and ne corners)
        sw_corner = [bounds[1], bounds[0]]  # [lat, lon]
        ne_corner = [bounds[3], bounds[2]]  # [lat, lon]

        # Create popup text
        popup_text = f"""
        <b>{row['name']}</b><br>
        Size: {row.get('size_km', 'N/A')} km²<br>
        Center: ({row.get('center_lat', 'N/A'):.4f}, {row.get('center_lon', 'N/A'):.4f})
        """

        # Add rectangle to map
        folium.Rectangle(
            bounds=[sw_corner, ne_corner],
            color='blue',
            fill=True,
            fillColor='lightblue',
            fillOpacity=0.3,
            weight=2,
            popup=folium.Popup(popup_text, max_width=300)
        ).add_to(m)

        # Add marker at center
        center_point = row['geometry'].centroid
        folium.Marker(
            location=[center_point.y, center_point.x],
            popup=row['name'],
            tooltip=row['name'],
            icon=folium.Icon(color='blue', icon='mountain')
        ).add_to(m)

    return m


def get_winter_date_range(winter_year: int) -> Tuple[datetime, datetime]:
    """Get date range for a winter season (Dec-Feb).

    Winter is defined as December of the previous year through February
    of the given year. For example, winter 2024/2025 runs from
    2024-12-01 to 2025-02-28.

    Args:
        winter_year: The ending year of the winter season
                    (e.g., 2025 for winter 2024/2025)

    Returns:
        Tuple of (start_date, end_date) as datetime objects

    Example:
        >>> start, end = get_winter_date_range(2025)
        >>> print(start, end)
        2024-12-01 00:00:00 2025-02-28 23:59:59
    """
    start_date = datetime(winter_year - 1, 12, 1)

    # February end date (handle leap years)
    # Check if it's a leap year
    is_leap = (winter_year % 4 == 0 and winter_year % 100 != 0) or (winter_year % 400 == 0)
    feb_last_day = 29 if is_leap else 28

    end_date = datetime(winter_year, 2, feb_last_day, 23, 59, 59)

    return start_date, end_date


def download_rgb_image(
    config: SHConfig,
    bbox: BBox,
    date: datetime,
    product_id: str,
    resolution: int = 10
) -> np.ndarray:
    """Download true-color RGB image from Sentinel-2.

    Downloads B04 (Red), B03 (Green), and B02 (Blue) bands for
    creating natural color composite images.

    Args:
        config: Configured SentinelHub instance
        bbox: Bounding box for the area
        date: Acquisition date
        product_id: Sentinel-2 product identifier
        resolution: Spatial resolution in meters (default: 10m)

    Returns:
        numpy array with shape (height, width, 3) containing RGB values
        in range [0, 1] (float32)

    Raises:
        Exception: If download fails or no data is returned

    Example:
        >>> from sentinelhub import BBox, CRS
        >>> from data_handler.discovery import create_sh_config
        >>> config = create_sh_config()
        >>> bbox = BBox(bbox=[-5.1, 56.7, -4.9, 56.9], crs=CRS.WGS84)
        >>> img = download_rgb_image(config, bbox, datetime(2024, 1, 15), "S2A_...")
        >>> print(img.shape)  # (height, width, 3)
    """
    # Create evalscript for RGB bands
    evalscript = """
    //VERSION=3
    function setup() {
        return {
            input: [{
                bands: ["B04", "B03", "B02"],
                units: "DN"
            }],
            output: {
                bands: 3,
                sampleType: "FLOAT32"
            }
        };
    }

    function evaluatePixel(sample) {
        // Return RGB values normalized to [0, 1]
        // Sentinel-2 L2A values are in range 0-10000
        return [sample.B04 / 10000, sample.B03 / 10000, sample.B02 / 10000];
    }
    """

    # Create time interval for the specific date
    time_start = date.strftime("%Y-%m-%dT00:00:00")
    time_end = date.strftime("%Y-%m-%dT23:59:59")

    # Calculate image size based on bbox
    import math
    bbox_width = bbox.max_x - bbox.min_x
    bbox_height = bbox.max_y - bbox.min_y

    # Approximate meters per degree at latitude ~56°
    meters_per_deg_lon = 62000
    meters_per_deg_lat = 111000

    width_m = bbox_width * meters_per_deg_lon
    height_m = bbox_height * meters_per_deg_lat

    size_x = math.ceil(width_m / resolution)
    size_y = math.ceil(height_m / resolution)

    # Create request using Copernicus Data Space data collection
    request = SentinelHubRequest(
        evalscript=evalscript,
        input_data=[
            SentinelHubRequest.input_data(
                data_collection=SENTINEL2_L2A_CDSE,
                time_interval=(time_start, time_end),
            )
        ],
        responses=[
            SentinelHubRequest.output_response('default', MimeType.TIFF)
        ],
        bbox=bbox,
        size=(size_x, size_y),
        config=config,
    )

    # Download data
    data = request.get_data()

    if not data or len(data) == 0:
        raise Exception(f"No data returned for product {product_id} on {date}")

    # Return RGB array (already normalized to [0, 1])
    return data[0]


def plot_sentinel_images(
    images: List[Dict],
    aoi_name: str,
    bbox: Optional[BBox] = None,
    ncols: int = 3,
    figsize: Optional[Tuple[int, int]] = None,
    brightness_factor: float = 3.0,
    dpi: int = 150
) -> Figure:
    """Create a grid plot of Sentinel-2 RGB images.

    Displays multiple satellite images in a grid layout with dates
    annotated on each subplot. Optionally adds lat/lon coordinate labels
    if bbox is provided.

    Args:
        images: List of dicts with keys:
               - 'image': numpy array (H, W, 3) with RGB values in [0, 1]
               - 'date': datetime object
               - 'cloud_cover': float (cloud cover percentage)
        aoi_name: Name of the Area of Interest (for title)
        bbox: Optional BBox object for adding lat/lon coordinate labels
        ncols: Number of columns in the grid (default: 3)
        figsize: Figure size as (width, height) in inches. If None, auto-calculated
                based on number of images
        brightness_factor: Multiplier to enhance image brightness (default: 3.0).
                          Sentinel-2 images are often dark, so we multiply pixel
                          values to make features more visible.
        dpi: Dots per inch for the figure (default: 150)

    Returns:
        matplotlib Figure object

    Example:
        >>> from sentinelhub import BBox, CRS
        >>> bbox = BBox(bbox=[-5.1, 56.7, -4.9, 56.9], crs=CRS.WGS84)
        >>> images = [
        ...     {'image': img1, 'date': datetime(2024, 12, 15), 'cloud_cover': 10.5},
        ...     {'image': img2, 'date': datetime(2025, 1, 10), 'cloud_cover': 5.2}
        ... ]
        >>> fig = plot_sentinel_images(images, 'Ben Nevis', bbox=bbox)
        >>> plt.show()
    """
    n_images = len(images)

    if n_images == 0:
        # Create empty figure with message
        default_figsize = figsize if figsize else (10, 6)
        fig, ax = plt.subplots(figsize=default_figsize, dpi=dpi)
        ax.text(0.5, 0.5, 'No images to display',
                ha='center', va='center', fontsize=16)
        ax.axis('off')
        return fig

    # Calculate grid dimensions
    nrows = (n_images + ncols - 1) // ncols  # Ceiling division

    # Auto-calculate figure size if not provided
    if figsize is None:
        # Each subplot gets roughly 5x5 inches
        figsize = (ncols * 5, nrows * 5)

    # Create figure and subplots
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, dpi=dpi)
    fig.suptitle(f'Sentinel-2 RGB Images - {aoi_name}', fontsize=16, fontweight='bold')

    # Flatten axes array for easier iteration
    if nrows == 1 and ncols == 1:
        axes = np.array([axes])
    axes_flat = axes.flatten() if isinstance(axes, np.ndarray) else [axes]

    # Plot each image
    for idx, img_data in enumerate(images):
        ax = axes_flat[idx]

        # Get image and enhance brightness
        img = img_data['image']
        img_enhanced = np.clip(img * brightness_factor, 0, 1)

        # Display image with equal aspect ratio
        if bbox is not None:
            # Use extent to map image to lat/lon coordinates
            extent = [bbox.min_x, bbox.max_x, bbox.min_y, bbox.max_y]
            ax.imshow(img_enhanced, extent=extent, aspect='equal')

            # Add coordinate labels
            ax.set_xlabel('Longitude (°E)', fontsize=9)
            ax.set_ylabel('Latitude (°N)', fontsize=9)

            # Format tick labels to show degrees
            ax.tick_params(labelsize=8)

            # Format coordinate labels with degree symbol
            ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:.3f}°'))
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, p: f'{y:.3f}°'))
        else:
            # Display without coordinates
            ax.imshow(img_enhanced, aspect='equal')
            ax.set_xticks([])
            ax.set_yticks([])

        # Add date and cloud cover as title
        date_str = img_data['date'].strftime('%Y-%m-%d')
        cloud_cover = img_data['cloud_cover']
        ax.set_title(f'{date_str}\nCloud: {cloud_cover:.1f}%', fontsize=11, fontweight='bold')

    # Hide empty subplots
    for idx in range(n_images, len(axes_flat)):
        axes_flat[idx].axis('off')

    plt.tight_layout()
    return fig
