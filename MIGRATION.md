# Migration to Copernicus Data Space Ecosystem

## Overview

This document describes the migration from the deprecated `sentinelsat` package (which accessed the old Copernicus SciHub API) to the new `sentinelhub` package (which accesses the Copernicus Data Space Ecosystem).

**Date**: 2026-01-29
**Reason**: SciHub API is deprecated and no longer accessible
**New Service**: Copernicus Data Space Ecosystem (https://dataspace.copernicus.eu/)

## Key Changes

### 1. Package Migration

**Before** (sentinelsat):
```python
from sentinelsat import SentinelAPI
```

**After** (sentinelhub):
```python
from sentinelhub import SHConfig, SentinelHubCatalog, DataCollection, BBox, CRS
```

### 2. Authentication

**Before** (Basic Auth with username/password):
```bash
export COPERNICUS_USERNAME="your_username"
export COPERNICUS_PASSWORD="your_password"
```

**After** (OAuth2 with client credentials):
```bash
export SH_CLIENT_ID="your_client_id"
export SH_CLIENT_SECRET="your_client_secret"
```

### 3. API Interface

**Before** (sentinelsat):
```python
# Create API instance
api = SentinelAPI(username, password, 'https://scihub.copernicus.eu/dhus')

# Query products
products = api.query(
    area=wkt_geometry,
    date=(start_date, end_date),
    platformname='Sentinel-2',
    producttype='S2MSI2A'
)

# Convert to DataFrame
df = api.to_dataframe(products)
```

**After** (sentinelhub):
```python
# Create config
config = SHConfig()
config.sh_client_id = client_id
config.sh_client_secret = client_secret

# Create catalog
catalog = SentinelHubCatalog(config=config)

# Query products
search_iterator = catalog.search(
    collection=DataCollection.SENTINEL2_L2A,
    bbox=BBox(bbox=bounds, crs=CRS.WGS84),
    time=(start_date.isoformat(), end_date.isoformat()),
    fields={"include": ["id", "properties.datetime", "properties.eo:cloud_cover"]}
)

# Process results manually
results = list(search_iterator)
# ... convert to DataFrame
```

### 4. Function Signatures

| Function | Old Signature | New Signature |
|----------|--------------|---------------|
| Create API/Config | `create_sentinel_api(username, password)` | `create_sh_config(client_id, client_secret)` |
| Find Products | `find_sentinel_products(api, ...)` | `find_sentinel_products(config, ...)` |

### 5. DataFrame Schema

**Before** (sentinelsat columns):
- `uuid`: Product UUID
- `title`: Product title
- `beginposition`: Acquisition datetime
- `cloudcoverpercentage`: Cloud cover %
- `platformname`: Sentinel-2
- `producttype`: S2MSI2A

**After** (sentinelhub columns):
- `id`: Product ID
- `product_id`: Full product identifier
- `date`: Acquisition datetime
- `cloud_cover`: Cloud cover %
- `geometry`: GeoJSON geometry

## Benefits of Migration

1. **Active Maintenance**: sentinelhub is actively maintained and supported
2. **Modern Authentication**: OAuth2 instead of basic auth
3. **Better Performance**: Optimized API endpoints
4. **Future-Proof**: Official Copernicus Data Space platform
5. **Additional Features**: Access to processing APIs, not just catalog

## Testing Updates

All tests have been updated to work with the new API:

- **Unit Tests (12)**: All passing with mocked sentinelhub components
- **Integration Tests (8)**: Updated for new authentication and API structure

## Backward Compatibility

⚠️ **Breaking Changes**: This migration introduces breaking changes:

1. Environment variable names changed
2. Function signatures changed
3. DataFrame column names changed

Users of this library will need to:
1. Update their credentials configuration
2. Update any code that calls the discovery functions
3. Update any code that processes the returned DataFrames

## Migration Checklist

- [x] Update `requirements.txt`
- [x] Rewrite `data_handler/discovery.py`
- [x] Update unit tests in `tests/test_data_discovery.py`
- [x] Update integration tests in `tests/integration/test_discovery_integration.py`
- [x] Update example script `examples/discover_products.py`
- [x] Update `.env.example`
- [x] Update `README.md`
- [x] All unit tests passing (12/12)
- [x] Documentation updated

## Getting Credentials

### Old System (Deprecated - No Longer Works)
1. Register at: https://scihub.copernicus.eu/dhus/#/self-registration
2. Use email/password

### New System (Active)
1. Register at: https://dataspace.copernicus.eu/
2. Go to: https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings
3. Create OAuth2 credentials
4. Use client_id/client_secret

## References

- Copernicus Data Space: https://dataspace.copernicus.eu/
- sentinelhub-py docs: https://sentinelhub-py.readthedocs.io/
- API documentation: https://documentation.dataspace.copernicus.eu/
- Migration guide: https://sentinelhub-py.readthedocs.io/en/latest/examples/
