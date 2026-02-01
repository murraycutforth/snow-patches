# Claude.md - Project Context for AI Assistance

## Project Summary

This is a Python-based data pipeline for monitoring snow cover in the Scottish Highlands using Sentinel-2 satellite imagery. The project tracks two specific regions (Ben Nevis and Ben Macdui) and is being built following Test-Driven Development (TDD) principles.

**Current Status**: Early development - AOI definition and data discovery components are complete. Next phases include database design, data download/processing, and snow mask generation.

**Total Code**: ~1,200 lines of Python (source + tests + examples)

## Core Technologies

- **Python 3.13**: Primary language
- **Sentinel-2 Data**: Copernicus Data Space Ecosystem
- **Key Dependencies**:
  - `sentinelhub`: Satellite data catalog access (OAuth2 authentication)
  - `geopandas`: Geospatial data handling
  - `pytest`: Testing framework

## Project Structure

```
snow-patches/
├── data_handler/              # Main source code package
│   ├── __init__.py           # Package initialization (v0.1.0)
│   ├── aoi.py                # Area of Interest (AOI) definitions
│   └── discovery.py          # Sentinel-2 product discovery
├── tests/                    # Test suite (12 unit tests passing)
│   ├── test_aoi_handler.py   # AOI functionality tests
│   ├── test_data_discovery.py # Discovery unit tests (mocked)
│   └── integration/
│       └── test_discovery_integration.py # Real API tests
├── examples/
│   └── discover_products.py  # Usage demonstration
├── README.md                 # User-facing documentation
├── TESTING.md                # Test execution guide
├── MIGRATION.md              # sentinelsat → sentinelhub migration notes
├── INTEGRATION_TEST_RESULTS.md # Latest test results
├── requirements.txt          # Python dependencies
├── pytest.ini                # Pytest configuration
└── .env.example              # Template for environment variables
```

## Key Modules

### `data_handler/aoi.py`
Defines Areas of Interest (AOI) for the two mountain regions:
- Creates 10km x 10km bounding boxes
- Uses WGS 84 coordinate system (EPSG:4326)
- Returns GeoDataFrame with geometry and metadata
- **Key function**: `get_scottish_highlands_aois() -> GeoDataFrame`

### `data_handler/discovery.py`
Queries Copernicus Data Space for Sentinel-2 imagery:
- OAuth2 authentication via environment variables
- Filters by date range, cloud cover, and spatial extent
- Returns structured pandas DataFrame
- **Key functions**:
  - `create_sh_config(client_id, client_secret) -> SHConfig`
  - `find_sentinel_products(config, bbox, start_date, end_date, max_cloud_cover) -> DataFrame`

### `data_handler/snow_mask.py`
Generates binary snow masks from Sentinel-2 imagery using NDSI:
- Calculates NDSI = (B03 - B11) / (B03 + B11 + epsilon)
- Applies configurable threshold (default: 0.4)
- Saves masks as single-band GeoTIFF files
- Tracks statistics in database (snow_pixels, total_pixels, snow_pct)
- **Key functions**:
  - `calculate_ndsi(band_green, band_swir, epsilon) -> ndarray` - Pure NumPy NDSI calculation
  - `apply_threshold(ndsi, threshold) -> ndarray` - Binary classification
  - `calculate_snow_statistics(snow_mask) -> Dict` - Compute coverage statistics
  - `process_product_snow_mask(session, product_db_id, ndsi_threshold, save_mask) -> Tuple` - Process single product
  - `process_downloaded_products(session, ndsi_threshold, save_masks, limit) -> Dict` - Batch processing

## Development Workflow

### TDD Approach
1. Write tests first to define expected behavior
2. Implement minimal code to make tests pass
3. Refactor while keeping tests green

### Testing Strategy
- **Unit Tests**: Fast, mocked external dependencies, run frequently
- **Integration Tests**: Real API calls, require credentials, run before commits
- Use `pytest -m "not integration"` for quick unit-only runs
- Use `pytest -v` for all tests

### Environment Setup
```bash
# Required for data discovery features
export SH_CLIENT_ID="your_client_id"
export SH_CLIENT_SECRET="your_client_secret"
```

Get credentials from: https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings

## Code Conventions

### Style Guidelines
- Follow PEP 8 for Python code style
- Use type hints where appropriate
- Write docstrings for public functions
- Keep functions focused and single-purpose

### Testing Patterns
- Mock external API calls in unit tests using `unittest.mock`
- Use `@pytest.mark.integration` for tests requiring credentials
- Skip integration tests gracefully when credentials unavailable
- Test edge cases (empty results, date boundaries, etc.)

### Geospatial Conventions
- Always use WGS 84 (EPSG:4326) for input coordinates
- Store geometries as GeoJSON-compatible structures
- Include both lat/lon and geometry in DataFrames for convenience

## Common Development Tasks

### Running Tests
```bash
# All tests
pytest tests/ -v

# Unit tests only (fast)
pytest tests/ -v -m "not integration"

# Integration tests only
pytest tests/integration/ -v -m integration

# With coverage
pytest tests/ --cov=data_handler --cov-report=html
```

### Adding New Features
1. Create test file in `tests/test_<feature>.py`
2. Write failing tests for expected behavior
3. Implement feature in `data_handler/<feature>.py`
4. Run tests until all pass
5. Add example usage to `examples/` if appropriate
6. Update README.md with new functionality

### Cleaning Up
```bash
# Remove Python cache files
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -name "*.pyc" -delete
find . -name ".DS_Store" -delete
```

## Important Context

### Recent Migration
The project recently migrated from `sentinelsat` (deprecated) to `sentinelhub` (active). Key changes:
- Authentication: username/password → OAuth2 client credentials
- API endpoint: SciHub → Copernicus Data Space Ecosystem
- See MIGRATION.md for full details

### Data Schemas

**Sentinel-2 Product DataFrame:**
- `id`: Unique product identifier
- `product_id`: Full product name
- `date`: Acquisition timestamp
- `cloud_cover`: Cloud coverage percentage (0-100)
- `geometry`: GeoJSON geometry

**Snow Mask Results:**
- `snow_pixels`: Number of pixels classified as snow (int)
- `total_pixels`: Total number of pixels in image (int)
- `snow_pct`: Snow coverage percentage (float)
- `mask_path`: Optional path to saved GeoTIFF file
- `ndsi_threshold`: Threshold value used for classification

### Coordinate Reference
- **Ben Nevis**: 56.7969°N, 5.0036°W
- **Ben Macdui**: 57.0704°N, 3.6691°W
- Each AOI is 10km x 10km centered on these coordinates

## Next Development Steps

The project follows a phased approach:

- [x] **Phase 1**: AOI Definition
- [x] **Phase 2**: Data Discovery
- [x] **Phase 3**: Database Schema Design
- [x] **Phase 4**: Data Download & Processing
- [x] **Phase 5**: Snow Mask Generation (NDSI calculation)
- [ ] **Phase 6**: Workflow Automation

## Tips for AI Assistance

1. **Always run tests** after making changes: `pytest tests/ -v -m "not integration"`
2. **Write tests first** when adding new features (TDD approach)
3. **Avoid over-engineering**: Keep it simple and focused
4. **Check existing patterns**: Follow the style in `aoi.py` and `discovery.py`
5. **Update documentation**: Keep README.md and docstrings current
6. **Don't commit credentials**: Use environment variables only
7. **Mock external APIs**: Unit tests should never make real network calls
8. **Test edge cases**: Empty results, invalid inputs, missing credentials

## Troubleshooting

### Tests Failing
- Check if it's a unit test (should never fail due to network) or integration test
- Verify environment variables are set for integration tests
- Run `pytest -v` for detailed output

### Import Errors
- Ensure virtual environment is activated
- Run `pip install -r requirements.txt`

### API Authentication Errors
- Verify credentials at https://dataspace.copernicus.eu/
- Check environment variables: `echo $SH_CLIENT_ID`
- Integration tests will skip if credentials missing (expected behavior)

## Resources

- Copernicus Data Space: https://dataspace.copernicus.eu/
- sentinelhub-py Documentation: https://sentinelhub-py.readthedocs.io/
- Sentinel-2 Mission Info: https://sentinels.copernicus.eu/web/sentinel/missions/sentinel-2
- PyTest Documentation: https://docs.pytest.org/
