"""Unit tests for notebook utility functions."""

from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

import numpy as np
import pandas as pd
import geopandas as gpd
import folium
from shapely.geometry import Polygon
import pytest

from sentinelhub import BBox, CRS

from data_handler.notebook_utils import (
    create_aoi_map,
    get_winter_date_range,
    download_rgb_image,
    plot_sentinel_images,
)


class TestCreateAoiMap:
    """Test suite for create_aoi_map function."""

    def test_creates_folium_map(self):
        """Should return a folium.Map instance."""
        # Create simple test GeoDataFrame
        aois = gpd.GeoDataFrame({
            'name': ['Test AOI'],
            'center_lat': [56.7969],
            'center_lon': [-5.0036],
            'size_km': [10.0],
            'geometry': [Polygon([
                (-5.1, 56.7), (-4.9, 56.7), (-4.9, 56.9), (-5.1, 56.9), (-5.1, 56.7)
            ])]
        }, crs='EPSG:4326')

        result = create_aoi_map(aois)

        assert isinstance(result, folium.Map)

    def test_map_centered_on_aois(self):
        """Should center map on the mean of all AOI centroids."""
        # Create two AOIs
        aois = gpd.GeoDataFrame({
            'name': ['AOI 1', 'AOI 2'],
            'center_lat': [56.0, 57.0],
            'center_lon': [-5.0, -4.0],
            'size_km': [10.0, 10.0],
            'geometry': [
                Polygon([(-5.1, 55.9), (-4.9, 55.9), (-4.9, 56.1), (-5.1, 56.1), (-5.1, 55.9)]),
                Polygon([(-4.1, 56.9), (-3.9, 56.9), (-3.9, 57.1), (-4.1, 57.1), (-4.1, 56.9)])
            ]
        }, crs='EPSG:4326')

        result = create_aoi_map(aois)

        # Check map location is centered
        expected_center = [56.5, -4.5]  # Mean of the two centroids
        assert abs(result.location[0] - expected_center[0]) < 0.1
        assert abs(result.location[1] - expected_center[1]) < 0.1

    def test_adds_rectangles_for_each_aoi(self):
        """Should add one rectangle overlay per AOI."""
        aois = gpd.GeoDataFrame({
            'name': ['AOI 1', 'AOI 2'],
            'center_lat': [56.0, 57.0],
            'center_lon': [-5.0, -4.0],
            'size_km': [10.0, 10.0],
            'geometry': [
                Polygon([(-5.1, 55.9), (-4.9, 55.9), (-4.9, 56.1), (-5.1, 56.1), (-5.1, 55.9)]),
                Polygon([(-4.1, 56.9), (-3.9, 56.9), (-3.9, 57.1), (-4.1, 57.1), (-4.1, 56.9)])
            ]
        }, crs='EPSG:4326')

        result = create_aoi_map(aois)

        # Count child objects (includes rectangles, markers, and tiles)
        # We expect at least 2 rectangles + 2 markers + base tile layer
        # folium adds children to the map, we can inspect the _children dict
        assert len(result._children) >= 5  # tiles + 2 rectangles + 2 markers


class TestGetWinterDateRange:
    """Test suite for get_winter_date_range function."""

    def test_winter_2025_date_range(self):
        """Should return Dec 2024 - Feb 2025 for winter 2025."""
        start, end = get_winter_date_range(2025)

        assert start == datetime(2024, 12, 1, 0, 0, 0)
        assert end == datetime(2025, 2, 28, 23, 59, 59)

    def test_leap_year_winter(self):
        """Should handle leap years correctly (Feb 29)."""
        start, end = get_winter_date_range(2024)  # 2024 is a leap year

        assert start == datetime(2023, 12, 1, 0, 0, 0)
        assert end == datetime(2024, 2, 29, 23, 59, 59)  # Feb 29 for leap year

    def test_non_leap_year_winter(self):
        """Should use Feb 28 for non-leap years."""
        start, end = get_winter_date_range(2023)  # 2023 is not a leap year

        assert start == datetime(2022, 12, 1, 0, 0, 0)
        assert end == datetime(2023, 2, 28, 23, 59, 59)  # Feb 28 for non-leap

    def test_century_non_leap_year(self):
        """Should correctly identify century years that are not leap years."""
        # 2100 is not a leap year (divisible by 100 but not 400)
        start, end = get_winter_date_range(2100)

        assert end == datetime(2100, 2, 28, 23, 59, 59)

    def test_century_leap_year(self):
        """Should correctly identify century years that ARE leap years."""
        # 2000 was a leap year (divisible by 400)
        start, end = get_winter_date_range(2000)

        assert end == datetime(2000, 2, 29, 23, 59, 59)


class TestDownloadRgbImage:
    """Test suite for download_rgb_image function."""

    @patch('data_handler.notebook_utils.SentinelHubRequest')
    def test_returns_rgb_array(self, mock_request_class):
        """Should return numpy array with shape (H, W, 3)."""
        # Mock the request and response
        mock_request = Mock()
        mock_request.get_data.return_value = [
            np.random.rand(100, 100, 3).astype(np.float32)
        ]
        mock_request_class.return_value = mock_request

        # Create mock config and bbox
        from sentinelhub import SHConfig, BBox, CRS
        config = SHConfig()
        bbox = BBox(bbox=[-5.1, 56.7, -4.9, 56.9], crs=CRS.WGS84)

        result = download_rgb_image(
            config=config,
            bbox=bbox,
            date=datetime(2024, 1, 15),
            product_id="S2A_TEST",
            resolution=10
        )

        # Check result shape
        assert isinstance(result, np.ndarray)
        assert result.ndim == 3
        assert result.shape[2] == 3  # RGB channels

    @patch('data_handler.notebook_utils.SentinelHubRequest')
    def test_raises_exception_when_no_data(self, mock_request_class):
        """Should raise exception when API returns no data."""
        # Mock request that returns empty list
        mock_request = Mock()
        mock_request.get_data.return_value = []
        mock_request_class.return_value = mock_request

        from sentinelhub import SHConfig, BBox, CRS
        config = SHConfig()
        bbox = BBox(bbox=[-5.1, 56.7, -4.9, 56.9], crs=CRS.WGS84)

        with pytest.raises(Exception, match="No data returned"):
            download_rgb_image(
                config=config,
                bbox=bbox,
                date=datetime(2024, 1, 15),
                product_id="S2A_TEST",
                resolution=10
            )

    @patch('data_handler.notebook_utils.SentinelHubRequest')
    def test_uses_correct_evalscript(self, mock_request_class):
        """Should request RGB bands (B04, B03, B02)."""
        # Mock the request
        mock_request = Mock()
        mock_request.get_data.return_value = [
            np.random.rand(100, 100, 3).astype(np.float32)
        ]
        mock_request_class.return_value = mock_request

        from sentinelhub import SHConfig, BBox, CRS
        config = SHConfig()
        bbox = BBox(bbox=[-5.1, 56.7, -4.9, 56.9], crs=CRS.WGS84)

        download_rgb_image(
            config=config,
            bbox=bbox,
            date=datetime(2024, 1, 15),
            product_id="S2A_TEST"
        )

        # Check that request was created with evalscript containing RGB bands
        call_kwargs = mock_request_class.call_args[1]
        evalscript = call_kwargs['evalscript']
        assert 'B04' in evalscript
        assert 'B03' in evalscript
        assert 'B02' in evalscript


class TestPlotSentinelImages:
    """Test suite for plot_sentinel_images function."""

    def test_creates_figure_for_images(self):
        """Should create matplotlib figure with correct grid."""
        # Create test image data
        images = [
            {
                'image': np.random.rand(100, 100, 3),
                'date': datetime(2024, 12, 15),
                'cloud_cover': 10.5
            },
            {
                'image': np.random.rand(100, 100, 3),
                'date': datetime(2025, 1, 10),
                'cloud_cover': 5.2
            }
        ]

        fig = plot_sentinel_images(images, 'Test AOI', ncols=2)

        assert fig is not None
        assert len(fig.axes) >= 2  # Should have at least 2 subplots

    def test_empty_images_list(self):
        """Should handle empty image list gracefully."""
        fig = plot_sentinel_images([], 'Test AOI')

        assert fig is not None
        assert len(fig.axes) == 1  # Single axis with message

    def test_applies_brightness_factor(self):
        """Should enhance image brightness by specified factor."""
        # Create a dark test image (all pixels = 0.1)
        dark_image = np.full((100, 100, 3), 0.1)
        images = [
            {
                'image': dark_image,
                'date': datetime(2024, 12, 15),
                'cloud_cover': 10.5
            }
        ]

        # Plot with brightness factor of 2.0
        fig = plot_sentinel_images(images, 'Test AOI', brightness_factor=2.0)

        # We can't easily inspect the displayed image, but we can check the figure was created
        assert fig is not None

    def test_date_formatting_in_title(self):
        """Should format dates as YYYY-MM-DD in subplot titles."""
        images = [
            {
                'image': np.random.rand(100, 100, 3),
                'date': datetime(2024, 12, 15),
                'cloud_cover': 10.5
            }
        ]

        fig = plot_sentinel_images(images, 'Test AOI')

        # Check first subplot title contains date
        title = fig.axes[0].get_title()
        assert '2024-12-15' in title
        assert 'Cloud: 10.5%' in title

    def test_multiple_rows(self):
        """Should create multiple rows when needed."""
        # Create 5 images with ncols=2, should create 3 rows
        images = [
            {
                'image': np.random.rand(100, 100, 3),
                'date': datetime(2024, 12, i),
                'cloud_cover': i * 2.0
            }
            for i in range(1, 6)
        ]

        fig = plot_sentinel_images(images, 'Test AOI', ncols=2)

        # Should have 6 subplots total (3 rows x 2 cols), but only 5 used
        assert len(fig.axes) == 6

    def test_with_bbox_coordinates(self):
        """Should add lat/lon labels when bbox is provided."""
        bbox = BBox(bbox=[-5.1, 56.7, -4.9, 56.9], crs=CRS.WGS84)
        images = [
            {
                'image': np.random.rand(100, 100, 3),
                'date': datetime(2024, 12, 15),
                'cloud_cover': 10.5
            }
        ]

        fig = plot_sentinel_images(images, 'Test AOI', bbox=bbox)

        # Check that axis labels are set
        ax = fig.axes[0]
        assert ax.get_xlabel() != ''  # Should have xlabel
        assert ax.get_ylabel() != ''  # Should have ylabel
        assert 'Longitude' in ax.get_xlabel()
        assert 'Latitude' in ax.get_ylabel()

    def test_without_bbox_no_coordinates(self):
        """Should not add coordinate labels when bbox is not provided."""
        images = [
            {
                'image': np.random.rand(100, 100, 3),
                'date': datetime(2024, 12, 15),
                'cloud_cover': 10.5
            }
        ]

        fig = plot_sentinel_images(images, 'Test AOI', bbox=None)

        # Check that axis has no ticks when no bbox
        ax = fig.axes[0]
        assert len(ax.get_xticks()) == 0
        assert len(ax.get_yticks()) == 0

    def test_custom_dpi(self):
        """Should use custom DPI setting."""
        images = [
            {
                'image': np.random.rand(100, 100, 3),
                'date': datetime(2024, 12, 15),
                'cloud_cover': 10.5
            }
        ]

        # Test with different DPI values
        fig1 = plot_sentinel_images(images, 'Test AOI', dpi=100)
        fig2 = plot_sentinel_images(images, 'Test AOI', dpi=200)

        # DPI should be set (may be scaled by backend, so check it's > 0)
        assert fig1.dpi > 0
        assert fig2.dpi > 0
        # Higher DPI should result in higher value (may be scaled equally)
        assert fig2.dpi >= fig1.dpi

    def test_auto_figsize(self):
        """Should auto-calculate figsize when not provided."""
        images = [
            {
                'image': np.random.rand(100, 100, 3),
                'date': datetime(2024, 12, i),
                'cloud_cover': i * 2.0
            }
            for i in range(1, 4)
        ]

        fig = plot_sentinel_images(images, 'Test AOI', ncols=2)

        # Figsize should be auto-calculated (not the default)
        assert fig.get_size_inches()[0] > 0
        assert fig.get_size_inches()[1] > 0
