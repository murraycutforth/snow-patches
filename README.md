# Snow Patches Data Pipeline

Automated system for downloading, processing, and storing Sentinel-2 satellite imagery for snow cover analysis in the Scottish Highlands.

## Project Overview

This project monitors snow cover trends over time for two specific regions:
- **Ben Nevis** (56.7969° N, 5.0036° W)
- **Ben Macdui** (57.0704° N, 3.6691° W)

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

To use the Sentinel-2 data discovery features, you need Copernicus Data Space credentials:

1. Register for free at: https://dataspace.copernicus.eu/
2. Create OAuth2 credentials at: https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings
3. Set environment variables:
```bash
export SH_CLIENT_ID="your_client_id"
export SH_CLIENT_SECRET="your_client_secret"
```

## Running Tests

```bash
pytest tests/ -v
```

## Database Setup

The project uses SQLite with SQLAlchemy ORM for data persistence. To initialize the database:

```bash
# Initialize database schema using Alembic
alembic upgrade head

# Or use the Python API
python -c "from data_handler.database import create_db_engine, init_database; engine = create_db_engine(db_path='data/snow_patches.db'); init_database(engine)"
```

## Usage Examples

See the `examples/` directory for usage demonstrations:

```bash
# Discover Sentinel-2 products (requires credentials)
PYTHONPATH=. python examples/discover_products.py

# Complete database workflow (init, seed, query)
PYTHONPATH=. python examples/database_workflow.py

# Download Sentinel-2 imagery (requires credentials)
PYTHONPATH=. python examples/download_workflow.py

# Generate snow masks from downloaded imagery
PYTHONPATH=. python examples/snow_mask_workflow.py
```

## Project Structure

```
snow-patches/
├── data_handler/              # Core data handling modules
│   ├── __init__.py
│   ├── aoi.py                # Area of Interest definitions
│   ├── discovery.py          # Sentinel-2 product discovery
│   ├── download.py           # Sentinel-2 data download (B03 + B11 bands)
│   ├── snow_mask.py          # Snow mask generation (NDSI calculation)
│   ├── database.py           # Database engine and session management
│   ├── models.py             # SQLAlchemy ORM models
│   └── repositories.py       # Data access layer (repository pattern)
├── tests/                    # Test suite
│   ├── test_aoi_handler.py
│   ├── test_data_discovery.py
│   ├── test_download.py      # Download functionality tests
│   ├── test_snow_mask.py     # Snow mask generation tests
│   ├── test_database.py
│   ├── test_models.py
│   ├── test_repositories.py
│   ├── test_discovery_db_integration.py
│   ├── conftest.py           # Shared test fixtures
│   └── integration/          # Integration tests
│       ├── test_database_integration.py
│       ├── test_download_integration.py
│       └── test_snow_mask_integration.py
├── examples/                 # Usage examples
│   ├── discover_products.py
│   ├── database_workflow.py  # Complete workflow demo
│   ├── download_workflow.py  # Download workflow demo
│   └── snow_mask_workflow.py # Snow mask generation workflow
├── alembic/                  # Database migration scripts
│   ├── versions/
│   └── env.py
├── data/                     # Database storage (gitignored)
│   └── snow_patches.db
├── requirements.txt          # Python dependencies
├── alembic.ini              # Alembic configuration
└── README.md                # This file
```

## Development Methodology

This project follows Test-Driven Development (TDD) principles:
1. Write tests first to define expected behavior
2. Implement code to make tests pass
3. Refactor while keeping tests green

## Completed Steps

- [x] **Step 1**: AOI Definition and Project Setup
  - Define 10km x 10km bounding boxes for both mountain regions
  - Create GeoDataFrame with WGS 84 (EPSG:4326) coordinate system
  - Comprehensive test coverage for AOI functionality

- [x] **Step 2**: Data Discovery
  - Query Copernicus Data Space Ecosystem for Sentinel-2 scenes
  - Use sentinelhub package for modern OAuth2 authentication
  - Filter products by date range and cloud cover percentage
  - Convert API results to structured DataFrames
  - Mock external API calls for fast, reliable testing
  - OAuth2 authentication via environment variables

- [x] **Step 3**: Database Schema Design
  - SQLite database with SQLAlchemy ORM
  - Four tables: AOIs, Sentinel Products, Download Status, Snow Masks
  - Repository pattern for data access
  - Alembic migrations for schema management
  - Comprehensive test coverage (unit + integration tests)
  - Functions to seed AOIs and save products to database

- [x] **Step 4**: Data Download & Processing
  - Download B03 (Green) and B11 (SWIR-1) bands as multi-band GeoTIFF
  - File organization: `data/sentinel2/{aoi_name}/{year}/{month}/{product_id}.tif`
  - Database status tracking (pending → downloaded/failed)
  - Retry logic with exponential backoff for network errors
  - Batch download functionality
  - 26 unit tests + 2 integration tests
  - Example workflow script for end-to-end download

## Database Schema

The database consists of four tables:

1. **aois**: Areas of Interest (Ben Nevis, Ben Macdui)
   - Stores bounding box geometry, center coordinates, and metadata

2. **sentinel_products**: Discovered Sentinel-2 imagery products
   - Links to AOI, stores acquisition date, cloud cover, and geometry
   - Unique constraint on product_id for deduplication

3. **download_status**: Tracks download and processing status
   - One-to-one relationship with sentinel_products
   - Status values: pending, downloaded, failed, processing, processed
   - Stores local file path, file size, download timestamps, and error messages

4. **snow_masks**: Snow cover analysis results (for Phase 5)
   - Links to products, stores NDSI threshold and snow coverage metrics
   - Unique constraint on (product_id, ndsi_threshold) for multiple threshold testing

## Download Workflow

The download module (`data_handler/download.py`) provides functions for downloading Sentinel-2 imagery:

```python
from data_handler.database import create_db_engine, get_session_factory
from data_handler.download import download_product, download_pending_products
from data_handler.discovery import create_sh_config

# Setup
engine = create_db_engine(db_path='data/snow_patches.db')
session = get_session_factory(engine)()
config = create_sh_config(client_id, client_secret)

# Download single product
success, error, file_path = download_product(session, product_id=1, config=config)

# Download all pending products
results = download_pending_products(session, limit=10, config=config)
print(f"Success: {results['success']}, Failed: {results['failed']}")

session.close()
```

**Key Features:**
- Downloads B03 (Green, 10m) and B11 (SWIR-1, 20m→10m) bands as GeoTIFF
- Hierarchical file organization by AOI, year, and month
- Automatic database status tracking
- Resumable downloads (skips already downloaded products)
- Error handling with retry logic

**Output Format:**
- Multi-band GeoTIFF with 2 bands (B03, B11)
- UINT16 data type (preserves full Sentinel-2 range)
- 10m spatial resolution
- LZW compression for efficient storage
- File path: `data/sentinel2/{aoi_name}/{year}/{month}/{product_id}.tif`

## Snow Mask Generation

The snow mask module (`data_handler/snow_mask.py`) generates binary snow masks from downloaded Sentinel-2 imagery using NDSI (Normalized Difference Snow Index):

```python
from data_handler.database import create_db_engine, get_session_factory
from data_handler.snow_mask import process_product_snow_mask, process_downloaded_products

# Setup
engine = create_db_engine(db_path='data/snow_patches.db')
session = get_session_factory(engine)()

# Process single product
success, error, result = process_product_snow_mask(
    session,
    product_db_id=1,
    ndsi_threshold=0.4,
    save_mask=True
)

print(f"Snow coverage: {result['snow_pct']:.1f}%")

# Batch process all downloaded products
results = process_downloaded_products(
    session,
    ndsi_threshold=0.4,
    save_masks=True,
    limit=10
)
print(f"Success: {results['success']}, Failed: {results['failed']}")

session.close()
```

**Key Features:**
- NDSI calculation: `(B03 - B11) / (B03 + B11)` with configurable threshold
- Binary classification (0 = no snow, 1 = snow)
- Multiple thresholds supported per product (e.g., 0.3, 0.4, 0.5)
- Database tracking with statistics (snow_pixels, total_pixels, snow_pct)
- Optional mask file saving
- Automatic status workflow: downloaded → processing → processed

**Output Format:**
- Single-band GeoTIFF with binary mask (0/1)
- UINT8 data type (minimal storage)
- Preserves spatial reference from input
- LZW compression
- File path: `data/snow_masks/{aoi_name}/{year}/{month}/{product_id}_ndsi{threshold}.tif`

**Interactive Workflow:**
```bash
PYTHONPATH=. python examples/snow_mask_workflow.py
```

This interactive script:
- Lists downloaded products
- Prompts for NDSI threshold (default: 0.4)
- Configures save options
- Processes products with progress display
- Shows results table with snow coverage statistics
- Provides visualization tips

## Next Steps

- [x] **Phase 5**: Snow Mask Generation (NDSI calculation)
- [ ] **Phase 6**: Workflow Automation
