"""Tests for the AOI (Area of Interest) handler module.

This module tests the functionality for defining and managing Areas of Interest
for the Ben Nevis and Ben Macdui snow cover analysis project.
"""

import pytest
import geopandas as gpd
from shapely.geometry import Polygon

from data_handler.aoi import get_aois


class TestAOIDefinition:
    """Test suite for AOI definition functionality."""

    def test_define_aois(self):
        """Test that get_aois() returns a properly structured GeoDataFrame.

        This test verifies:
        1. The return type is a GeoDataFrame
        2. The GeoDataFrame contains exactly two geometries (Ben Nevis and Ben Macdui)
        3. Required columns ('name', 'geometry') are present
        4. The CRS is set to WGS 84 (EPSG:4326)
        """
        # Act: Call the function to get AOIs
        aois = get_aois()

        # Assert: Check return type
        assert isinstance(aois, gpd.GeoDataFrame), \
            "get_aois() should return a GeoDataFrame"

        # Assert: Check number of geometries
        assert len(aois) == 2, \
            f"Expected 2 AOIs, but got {len(aois)}"

        # Assert: Check required columns exist
        assert 'name' in aois.columns, \
            "GeoDataFrame should have a 'name' column"
        assert 'geometry' in aois.columns, \
            "GeoDataFrame should have a 'geometry' column"

        # Assert: Check CRS is WGS 84
        assert aois.crs is not None, \
            "GeoDataFrame should have a CRS defined"
        assert aois.crs.to_epsg() == 4326, \
            f"Expected CRS EPSG:4326, but got EPSG:{aois.crs.to_epsg()}"

    def test_aoi_names(self):
        """Test that the AOIs have the correct names."""
        # Act
        aois = get_aois()

        # Assert: Check that both expected names are present
        names = set(aois['name'].values)
        expected_names = {'Ben Nevis', 'Ben Macdui'}
        assert names == expected_names, \
            f"Expected names {expected_names}, but got {names}"

    def test_aoi_geometries_are_polygons(self):
        """Test that all AOI geometries are Polygon objects."""
        # Act
        aois = get_aois()

        # Assert: Check that all geometries are Polygons
        for idx, row in aois.iterrows():
            assert isinstance(row['geometry'], Polygon), \
                f"Geometry for {row['name']} should be a Polygon, got {type(row['geometry'])}"

    def test_aoi_size_approximately_10km(self):
        """Test that AOI bounding boxes are approximately 10km x 10km.

        This test converts to a metric CRS and checks that the area is roughly
        100 km² (10km x 10km), allowing for some tolerance due to projection distortions.
        """
        # Act
        aois = get_aois()

        # Convert to a suitable metric CRS for area calculation
        # EPSG:27700 (British National Grid) is appropriate for Scotland
        aois_metric = aois.to_crs(epsg=27700)

        # Assert: Check that areas are approximately 100 km² (100,000,000 m²)
        expected_area = 100_000_000  # 100 km² in m²
        tolerance = 0.15  # Allow 15% tolerance for projection effects

        for idx, row in aois_metric.iterrows():
            area = row['geometry'].area
            lower_bound = expected_area * (1 - tolerance)
            upper_bound = expected_area * (1 + tolerance)
            assert lower_bound <= area <= upper_bound, \
                f"{row['name']} area {area/1e6:.2f} km² is outside expected range " \
                f"[{lower_bound/1e6:.2f}, {upper_bound/1e6:.2f}] km²"
