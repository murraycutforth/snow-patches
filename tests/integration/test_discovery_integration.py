"""Integration tests for Sentinel-2 data discovery with real API calls.

These tests require valid Copernicus Data Space credentials set as
environment variables:
    - SH_CLIENT_ID: Your OAuth2 client ID
    - SH_CLIENT_SECRET: Your OAuth2 client secret

Register for free at: https://dataspace.copernicus.eu/

To run these tests:
    pytest tests/integration/ -v -m integration

To skip these tests:
    pytest tests/ -v -m "not integration"
"""

import os
from datetime import datetime, timedelta

import pandas as pd
import pytest
from sentinelhub import SHConfig, DataCollection

from data_handler.aoi import get_aois
from data_handler.discovery import create_sh_config, find_sentinel_products, summarize_products


# Check if credentials are available
credentials_available = bool(
    os.getenv('SH_CLIENT_ID') and os.getenv('SH_CLIENT_SECRET')
)

skip_reason = (
    "Copernicus Data Space credentials not available. Set SH_CLIENT_ID and "
    "SH_CLIENT_SECRET environment variables to run integration tests. "
    "Register at: https://dataspace.copernicus.eu/"
)


@pytest.mark.integration
class TestSentinelHubIntegration:
    """Integration tests using the real Copernicus Data Space API.

    These tests verify that our code correctly interacts with the actual
    Copernicus Data Space Ecosystem service using sentinelhub.
    """

    @pytest.mark.skipif(not credentials_available, reason=skip_reason)
    def test_create_sh_config_with_env_vars(self):
        """Test creating SHConfig instance using environment variables."""
        # Act: Create config instance
        config = create_sh_config()

        # Assert: Verify we got a valid config instance
        assert isinstance(config, SHConfig), \
            "Should return a SHConfig instance"
        assert config.sh_client_id is not None, \
            "Config should have client_id"
        assert config.sh_client_secret is not None, \
            "Config should have client_secret"

    @pytest.mark.skipif(not credentials_available, reason=skip_reason)
    def test_create_sh_config_with_explicit_credentials(self):
        """Test creating SHConfig instance with explicit credentials."""
        # Arrange: Get credentials from environment
        client_id = os.getenv('SH_CLIENT_ID')
        client_secret = os.getenv('SH_CLIENT_SECRET')

        # Act: Create config instance with explicit credentials
        config = create_sh_config(client_id=client_id, client_secret=client_secret)

        # Assert: Verify we got a valid config instance
        assert isinstance(config, SHConfig), \
            "Should return a SHConfig instance"
        assert config.sh_client_id == client_id, \
            "Config should have the provided client_id"

    def test_create_sh_config_without_credentials(self, monkeypatch):
        """Test that missing credentials raise appropriate error."""
        # Arrange: Temporarily remove credentials from environment
        monkeypatch.delenv('SH_CLIENT_ID', raising=False)
        monkeypatch.delenv('SH_CLIENT_SECRET', raising=False)

        # Act & Assert: Should raise ValueError
        with pytest.raises(ValueError, match="Copernicus Data Space credentials not found"):
            create_sh_config()

    @pytest.mark.skipif(not credentials_available, reason=skip_reason)
    def test_find_products_ben_nevis_real_api(self):
        """Test finding Sentinel-2 products for Ben Nevis using real API.

        This test performs an actual query to the Copernicus Data Space for
        Ben Nevis region. It uses a short, recent time window to ensure
        the test completes quickly while still finding some results.
        """
        # Arrange: Get Ben Nevis AOI
        aois = get_aois()
        ben_nevis = aois[aois['name'] == 'Ben Nevis'].iloc[0]
        aoi_geometry = ben_nevis['geometry']

        # Use a date range from recent past (2-3 months ago)
        end_date = datetime.now() - timedelta(days=60)
        start_date = end_date - timedelta(days=30)

        # Create config instance
        config = create_sh_config()

        # Act: Search for products
        print(f"\n   Querying Copernicus Data Space for Ben Nevis...")
        print(f"   Date range: {start_date.date()} to {end_date.date()}")

        products_df = find_sentinel_products(
            config=config,
            aoi_geometry=aoi_geometry,
            start_date=start_date,
            end_date=end_date,
            max_cloud_cover=30.0  # Use higher threshold to ensure we get results
        )

        # Assert: Verify we got valid results
        assert isinstance(products_df, pd.DataFrame), \
            "Should return a DataFrame"

        if not products_df.empty:
            print(f"   Found {len(products_df)} products")

            # Verify DataFrame structure
            expected_columns = {'id', 'date', 'cloud_cover', 'geometry', 'product_id'}
            assert expected_columns.issubset(products_df.columns), \
                f"DataFrame should contain expected columns: {expected_columns}"

            # Verify data types and values
            assert all(products_df['cloud_cover'] <= 30.0), \
                "All products should have cloud cover <= 30%"

            # Verify dates are within expected range
            # Convert to timezone-aware for comparison (API returns UTC)
            import pytz
            start_date_utc = pytz.UTC.localize(start_date)
            end_date_utc = pytz.UTC.localize(end_date + timedelta(days=1))

            assert all(products_df['date'] >= start_date_utc), \
                "All products should be after start date"
            assert all(products_df['date'] <= end_date_utc), \
                "All products should be before end date"

            # Display sample product info
            sample = products_df.iloc[0]
            print(f"   Sample product: {sample['product_id']}")
            print(f"   Acquisition: {sample['date']}")
            print(f"   Cloud cover: {sample['cloud_cover']:.1f}%")
        else:
            print(f"   No products found (this is OK for integration test)")

    @pytest.mark.skipif(not credentials_available, reason=skip_reason)
    def test_find_products_ben_macdui_real_api(self):
        """Test finding Sentinel-2 products for Ben Macdui using real API."""
        # Arrange: Get Ben Macdui AOI
        aois = get_aois()
        ben_macdui = aois[aois['name'] == 'Ben Macdui'].iloc[0]
        aoi_geometry = ben_macdui['geometry']

        # Use a date range from recent past
        end_date = datetime.now() - timedelta(days=60)
        start_date = end_date - timedelta(days=30)

        # Create config instance
        config = create_sh_config()

        # Act: Search for products
        print(f"\n   Querying Copernicus Data Space for Ben Macdui...")
        print(f"   Date range: {start_date.date()} to {end_date.date()}")

        products_df = find_sentinel_products(
            config=config,
            aoi_geometry=aoi_geometry,
            start_date=start_date,
            end_date=end_date,
            max_cloud_cover=30.0
        )

        # Assert: Verify we got valid results
        assert isinstance(products_df, pd.DataFrame), \
            "Should return a DataFrame"

        if not products_df.empty:
            print(f"   Found {len(products_df)} products")

            # Verify cloud cover filtering worked
            assert all(products_df['cloud_cover'] <= 30.0), \
                "All products should have cloud cover <= 30%"

            # Display sample product info
            sample = products_df.iloc[0]
            print(f"   Sample product: {sample['product_id']}")
            print(f"   Cloud cover: {sample['cloud_cover']:.1f}%")
        else:
            print(f"   No products found (this is OK for integration test)")

    @pytest.mark.skipif(not credentials_available, reason=skip_reason)
    def test_cloud_cover_filtering_real_api(self):
        """Test that cloud cover filtering works correctly with real API data."""
        # Arrange: Get an AOI
        aois = get_aois()
        aoi_geometry = aois.iloc[0]['geometry']

        # Use a wider date range to get more products
        end_date = datetime.now() - timedelta(days=60)
        start_date = end_date - timedelta(days=60)

        config = create_sh_config()

        # Act: Query with strict cloud cover threshold
        strict_threshold = 10.0
        print(f"\n   Testing cloud cover filtering with {strict_threshold}% threshold...")

        strict_products = find_sentinel_products(
            config=config,
            aoi_geometry=aoi_geometry,
            start_date=start_date,
            end_date=end_date,
            max_cloud_cover=strict_threshold
        )

        # Act: Query with relaxed cloud cover threshold
        relaxed_threshold = 50.0
        relaxed_products = find_sentinel_products(
            config=config,
            aoi_geometry=aoi_geometry,
            start_date=start_date,
            end_date=end_date,
            max_cloud_cover=relaxed_threshold
        )

        # Assert: Relaxed threshold should return >= products than strict threshold
        print(f"   Strict threshold ({strict_threshold}%): {len(strict_products)} products")
        print(f"   Relaxed threshold ({relaxed_threshold}%): {len(relaxed_products)} products")

        assert len(relaxed_products) >= len(strict_products), \
            "Relaxed threshold should return same or more products than strict threshold"

        # Verify all strict products meet the threshold
        if not strict_products.empty:
            assert all(strict_products['cloud_cover'] <= strict_threshold), \
                f"All products should have cloud cover <= {strict_threshold}%"

        # Verify all relaxed products meet the threshold
        if not relaxed_products.empty:
            assert all(relaxed_products['cloud_cover'] <= relaxed_threshold), \
                f"All products should have cloud cover <= {relaxed_threshold}%"

    @pytest.mark.skipif(not credentials_available, reason=skip_reason)
    def test_summarize_products_real_api(self):
        """Test the summarize_products function with real API data."""
        # Arrange: Get products
        aois = get_aois()
        aoi_geometry = aois.iloc[0]['geometry']

        end_date = datetime.now() - timedelta(days=60)
        start_date = end_date - timedelta(days=30)

        config = create_sh_config()

        products_df = find_sentinel_products(
            config=config,
            aoi_geometry=aoi_geometry,
            start_date=start_date,
            end_date=end_date,
            max_cloud_cover=40.0
        )

        # Act: Generate summary
        summary = summarize_products(products_df)

        # Assert: Verify summary structure
        assert isinstance(summary, dict), "Summary should be a dictionary"
        assert 'total_products' in summary, "Summary should include total_products"
        assert 'date_range' in summary, "Summary should include date_range"
        assert 'avg_cloud_cover' in summary, "Summary should include avg_cloud_cover"

        # Verify summary values
        assert summary['total_products'] == len(products_df), \
            "Summary total should match DataFrame length"

        if not products_df.empty:
            print(f"\n   Summary:")
            print(f"   Total products: {summary['total_products']}")
            print(f"   Date range: {summary['date_range'][0].date()} to {summary['date_range'][1].date()}")
            print(f"   Cloud cover: {summary['min_cloud_cover']:.1f}% - {summary['max_cloud_cover']:.1f}%")
            print(f"   Avg cloud cover: {summary['avg_cloud_cover']:.1f}%")

            assert summary['date_range'][0] is not None, \
                "Date range start should not be None when products exist"
            assert summary['date_range'][1] is not None, \
                "Date range end should not be None when products exist"
            assert summary['avg_cloud_cover'] is not None, \
                "Avg cloud cover should not be None when products exist"

    @pytest.mark.skipif(not credentials_available, reason=skip_reason)
    def test_no_results_for_empty_date_range(self):
        """Test behavior when date range has no available products."""
        # Arrange: Use a very short date range in the far past
        # (before Sentinel-2 was operational - launched June 2015)
        aois = get_aois()
        aoi_geometry = aois.iloc[0]['geometry']

        start_date = datetime(2010, 1, 1)
        end_date = datetime(2010, 1, 2)

        config = create_sh_config()

        # Act: Query for products
        print(f"\n   Querying for products before Sentinel-2 launch...")
        products_df = find_sentinel_products(
            config=config,
            aoi_geometry=aoi_geometry,
            start_date=start_date,
            end_date=end_date,
            max_cloud_cover=100.0
        )

        # Assert: Should return empty DataFrame
        assert isinstance(products_df, pd.DataFrame), \
            "Should return a DataFrame even when no products found"
        assert products_df.empty, \
            "Should return empty DataFrame for date range before Sentinel-2"
        assert 'id' in products_df.columns, \
            "Empty DataFrame should still have expected columns"

        print(f"   Correctly returned empty DataFrame (0 products)")
