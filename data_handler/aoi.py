"""AOI (Area of Interest) handler module.

This module provides functionality for defining and managing Areas of Interest
for satellite imagery analysis. It defines bounding boxes for Scottish mountain
regions where snow cover will be monitored.
"""

import math
from typing import List, Tuple

import geopandas as gpd
from shapely.geometry import Polygon


def create_bbox_around_point(
    center_lat: float,
    center_lon: float,
    size_km: float = 10.0
) -> Polygon:
    """Create a square bounding box around a center point.

    Args:
        center_lat: Latitude of the center point in decimal degrees
        center_lon: Longitude of the center point in decimal degrees
        size_km: Side length of the square bounding box in kilometers (default: 10.0)

    Returns:
        A Polygon object representing the bounding box in EPSG:4326 coordinates

    Note:
        The bounding box is created by calculating the approximate degree offsets
        for the specified distance. This uses a simple spherical Earth approximation
        which is suitable for small areas (< 100 km).
    """
    # Convert half the size from kilometers to degrees
    # At the equator, 1 degree latitude ≈ 111.32 km
    # For longitude, it varies with latitude: 1 degree lon ≈ 111.32 * cos(latitude) km
    half_size_km = size_km / 2.0

    # Calculate latitude offset (constant regardless of longitude)
    # 1 degree latitude ≈ 111.32 km
    km_per_degree_lat = 111.32
    lat_offset = half_size_km / km_per_degree_lat

    # Calculate longitude offset (varies with latitude)
    # 1 degree longitude ≈ 111.32 * cos(latitude) km
    lat_radians = math.radians(center_lat)
    km_per_degree_lon = km_per_degree_lat * math.cos(lat_radians)
    lon_offset = half_size_km / km_per_degree_lon

    # Create the bounding box coordinates
    # Order: bottom-left, bottom-right, top-right, top-left, bottom-left (closed polygon)
    min_lon = center_lon - lon_offset
    max_lon = center_lon + lon_offset
    min_lat = center_lat - lat_offset
    max_lat = center_lat + lat_offset

    bbox_coords = [
        (min_lon, min_lat),  # Bottom-left
        (max_lon, min_lat),  # Bottom-right
        (max_lon, max_lat),  # Top-right
        (min_lon, max_lat),  # Top-left
        (min_lon, min_lat),  # Close the polygon
    ]

    return Polygon(bbox_coords)


def get_aois() -> gpd.GeoDataFrame:
    """Get Areas of Interest (AOIs) for the snow cover monitoring project.

    Returns a GeoDataFrame containing square bounding boxes (10km x 10km)
    around two Scottish mountain peaks: Ben Nevis and Ben Macdui.

    Returns:
        A GeoDataFrame with the following columns:
            - name: Name of the area (str)
            - geometry: Polygon representing the bounding box
        The GeoDataFrame uses the WGS 84 coordinate system (EPSG:4326).

    Example:
        >>> aois = get_aois()
        >>> print(aois)
                name                                           geometry
        0  Ben Nevis  POLYGON ((-5.09374 56.75203, -5.09374 56.8418...
        1  Ben Macdui  POLYGON ((-3.76920 57.02553, -3.76920 57.1152...
    """
    # Define the areas of interest with their center coordinates
    aoi_definitions: List[Tuple[str, float, float]] = [
        ("Ben Nevis", 56.7969, -5.0036),   # Name, Latitude, Longitude
        ("Ben Macdui", 57.0704, -3.6691),  # Name, Latitude, Longitude
    ]

    # Create bounding boxes for each AOI
    aoi_data = []
    for name, lat, lon in aoi_definitions:
        bbox = create_bbox_around_point(lat, lon, size_km=10.0)
        aoi_data.append({
            "name": name,
            "geometry": bbox
        })

    # Create a GeoDataFrame with the AOI data
    gdf = gpd.GeoDataFrame(
        aoi_data,
        crs="EPSG:4326"  # WGS 84 coordinate reference system
    )

    return gdf
