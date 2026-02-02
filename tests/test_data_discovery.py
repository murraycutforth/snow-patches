"""Tests for the data discovery module.

This module tests the functionality for querying the Copernicus Data Space
to find available Sentinel-2 scenes for a given AOI and date range.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from shapely.geometry import Polygon
from sentinelhub import SHConfig, DataCollection

from data_handler.discovery import create_sh_config, find_sentinel_products


class TestSentinelHubProductDiscovery:
    """Test suite for Sentinel-2 product discovery functionality using sentinelhub."""

    @pytest.fixture
    def sample_aoi(self):
        """Create a sample AOI polygon for testing."""
        # Simple 0.1 degree x 0.1 degree box
        return Polygon([
            (-5.1, 56.7),
            (-5.0, 56.7),
            (-5.0, 56.8),
            (-5.1, 56.8),
            (-5.1, 56.7)
        ])

    @pytest.fixture
    def mock_catalog_results(self):
        """Create mock catalog search results from SentinelHubCatalog.

        Returns a list of product dictionaries matching the STAC format
        returned by sentinelhub catalog search.
        """
        results = [
            # Product 1: Low cloud cover (should be included)
            {
                'id': 'S2A_MSIL2A_20240115T113331_N0510_R080_T30VVK_20240115T140825',
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [[
                        [-5.1, 56.7],
                        [-5.0, 56.7],
                        [-5.0, 56.8],
                        [-5.1, 56.8],
                        [-5.1, 56.7]
                    ]]
                },
                'properties': {
                    'datetime': '2024-01-15T11:33:31Z',
                    'eo:cloud_cover': 5.23,
                    'productIdentifier': 'S2A_MSIL2A_20240115T113331_N0510_R080_T30VVK_20240115T140825'
                }
            },
            # Product 2: High cloud cover (should be filtered out)
            {
                'id': 'S2B_MSIL2A_20240120T113339_N0510_R080_T30VVK_20240120T133521',
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [[
                        [-5.1, 56.7],
                        [-5.0, 56.7],
                        [-5.0, 56.8],
                        [-5.1, 56.8],
                        [-5.1, 56.7]
                    ]]
                },
                'properties': {
                    'datetime': '2024-01-20T11:33:39Z',
                    'eo:cloud_cover': 50.87,
                    'productIdentifier': 'S2B_MSIL2A_20240120T113339_N0510_R080_T30VVK_20240120T133521'
                }
            },
            # Product 3: Moderate cloud cover (should be included)
            {
                'id': 'S2A_MSIL2A_20240125T113331_N0510_R080_T30VVK_20240125T141023',
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [[
                        [-5.1, 56.7],
                        [-5.0, 56.7],
                        [-5.0, 56.8],
                        [-5.1, 56.8],
                        [-5.1, 56.7]
                    ]]
                },
                'properties': {
                    'datetime': '2024-01-25T11:33:31Z',
                    'eo:cloud_cover': 15.42,
                    'productIdentifier': 'S2A_MSIL2A_20240125T113331_N0510_R080_T30VVK_20240125T141023'
                }
            }
        ]
        return results

    @pytest.fixture
    def mock_config(self):
        """Create a mock SHConfig for testing."""
        config = MagicMock(spec=SHConfig)
        config.sh_client_id = 'test_client_id'
        config.sh_client_secret = 'test_client_secret'
        return config

    def test_create_sh_config_with_env_vars(self, mocker):
        """Test creating SHConfig using environment variables."""
        # Arrange: Mock environment variables
        mocker.patch.dict('os.environ', {
            'SH_CLIENT_ID': 'test_id',
            'SH_CLIENT_SECRET': 'test_secret'
        })

        # Act
        config = create_sh_config()

        # Assert
        assert isinstance(config, SHConfig)
        assert config.sh_client_id == 'test_id'
        assert config.sh_client_secret == 'test_secret'

    def test_create_sh_config_with_explicit_credentials(self):
        """Test creating SHConfig with explicit credentials."""
        # Act
        config = create_sh_config(
            client_id='explicit_id',
            client_secret='explicit_secret'
        )

        # Assert
        assert isinstance(config, SHConfig)
        assert config.sh_client_id == 'explicit_id'
        assert config.sh_client_secret == 'explicit_secret'

    def test_create_sh_config_without_credentials(self, mocker):
        """Test that missing credentials raise appropriate error."""
        # Arrange: Ensure no credentials in environment
        mocker.patch.dict('os.environ', {}, clear=True)

        # Act & Assert
        with pytest.raises(ValueError, match="Copernicus Data Space credentials not found"):
            create_sh_config()

    @patch('data_handler.discovery.SentinelHubCatalog')
    def test_find_sentinel_products_success(
        self, mock_catalog_class, mock_config, sample_aoi, mock_catalog_results
    ):
        """Test successful product discovery with cloud cover filtering."""
        # Arrange: Mock the catalog search
        mock_catalog_instance = MagicMock()
        mock_catalog_class.return_value = mock_catalog_instance
        mock_catalog_instance.search.return_value = iter(mock_catalog_results)

        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)
        max_cloud_cover = 20.0

        # Act
        result_df = find_sentinel_products(
            config=mock_config,
            aoi_geometry=sample_aoi,
            start_date=start_date,
            end_date=end_date,
            max_cloud_cover=max_cloud_cover
        )

        # Assert: Catalog was created with config
        mock_catalog_class.assert_called_once_with(config=mock_config)

        # Assert: Search was called
        assert mock_catalog_instance.search.called

        # Assert: Check return type
        assert isinstance(result_df, pd.DataFrame)

        # Assert: Check cloud cover filtering (should have 2 products <= 20%)
        assert len(result_df) == 2
        assert all(result_df['cloud_cover'] <= max_cloud_cover)

        # Assert: High cloud cover product was filtered out
        high_cloud_id = 'S2B_MSIL2A_20240120T113339_N0510_R080_T30VVK_20240120T133521'
        assert high_cloud_id not in result_df['id'].values

        # Assert: Expected columns are present
        expected_columns = {'id', 'date', 'cloud_cover', 'geometry', 'product_id'}
        assert expected_columns.issubset(result_df.columns)

    @patch('data_handler.discovery.SentinelHubCatalog')
    def test_find_sentinel_products_empty_result(
        self, mock_catalog_class, mock_config, sample_aoi
    ):
        """Test behavior when no products are found."""
        # Arrange: Mock empty search result
        mock_catalog_instance = MagicMock()
        mock_catalog_class.return_value = mock_catalog_instance
        mock_catalog_instance.search.return_value = iter([])

        # Act
        result_df = find_sentinel_products(
            config=mock_config,
            aoi_geometry=sample_aoi,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            max_cloud_cover=20.0
        )

        # Assert
        assert isinstance(result_df, pd.DataFrame)
        assert len(result_df) == 0
        assert 'id' in result_df.columns

    @patch('data_handler.discovery.SentinelHubCatalog')
    def test_find_sentinel_products_all_filtered_by_cloud_cover(
        self, mock_catalog_class, mock_config, sample_aoi, mock_catalog_results
    ):
        """Test when all products are filtered out due to high cloud cover."""
        # Arrange
        mock_catalog_instance = MagicMock()
        mock_catalog_class.return_value = mock_catalog_instance
        mock_catalog_instance.search.return_value = iter(mock_catalog_results)

        # Act: Use very strict cloud cover threshold
        result_df = find_sentinel_products(
            config=mock_config,
            aoi_geometry=sample_aoi,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            max_cloud_cover=1.0  # Will filter out all products
        )

        # Assert
        assert len(result_df) == 0

    @patch('data_handler.discovery.SentinelHubCatalog')
    def test_find_sentinel_products_bbox_conversion(
        self, mock_catalog_class, mock_config, sample_aoi
    ):
        """Test that AOI geometry is correctly converted to BBox."""
        # Arrange
        mock_catalog_instance = MagicMock()
        mock_catalog_class.return_value = mock_catalog_instance
        mock_catalog_instance.search.return_value = iter([])

        # Act
        find_sentinel_products(
            config=mock_config,
            aoi_geometry=sample_aoi,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            max_cloud_cover=20.0
        )

        # Assert: Search was called with bbox parameter
        call_kwargs = mock_catalog_instance.search.call_args[1]
        assert 'bbox' in call_kwargs

        # BBox should match AOI bounds
        from sentinelhub import BBox
        assert isinstance(call_kwargs['bbox'], BBox)

    @patch('data_handler.discovery.SentinelHubCatalog')
    def test_find_sentinel_products_data_collection(
        self, mock_catalog_class, mock_config, sample_aoi
    ):
        """Test that the correct data collection is used."""
        # Arrange
        mock_catalog_instance = MagicMock()
        mock_catalog_class.return_value = mock_catalog_instance
        mock_catalog_instance.search.return_value = iter([])

        # Act
        find_sentinel_products(
            config=mock_config,
            aoi_geometry=sample_aoi,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            max_cloud_cover=20.0,
            data_collection=DataCollection.SENTINEL2_L2A
        )

        # Assert: Search was called with correct collection
        call_kwargs = mock_catalog_instance.search.call_args[1]
        assert call_kwargs['collection'] == DataCollection.SENTINEL2_L2A

    @patch('data_handler.discovery.SentinelHubCatalog')
    def test_find_sentinel_products_accepts_bbox_parameter(
        self, mock_catalog_class, mock_config, sample_aoi, mock_catalog_results
    ):
        """Test that function accepts 'bbox' as an alias for 'aoi_geometry'.

        This test reproduces the error from the notebook where bbox is used
        instead of aoi_geometry. The function should accept both parameter names.
        """
        # Arrange
        mock_catalog_instance = MagicMock()
        mock_catalog_class.return_value = mock_catalog_instance
        mock_catalog_instance.search.return_value = iter(mock_catalog_results)

        # Act: Call with 'bbox' parameter (as used in notebook)
        result_df = find_sentinel_products(
            config=mock_config,
            bbox=sample_aoi,  # Using 'bbox' instead of 'aoi_geometry'
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            max_cloud_cover=20.0
        )

        # Assert: Should work without error
        assert isinstance(result_df, pd.DataFrame)
        assert len(result_df) == 2  # Two products with cloud cover <= 20%
