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

## Usage Examples

See the `examples/` directory for usage demonstrations:

```bash
python examples/discover_products.py
```

## Project Structure

```
snow-patches/
├── data_handler/          # Core data handling modules
│   ├── __init__.py
│   ├── aoi.py            # Area of Interest definitions
│   └── discovery.py      # Sentinel-2 product discovery
├── tests/                # Test suite
│   ├── __init__.py
│   ├── test_aoi_handler.py
│   └── test_data_discovery.py
├── examples/             # Usage examples
│   └── discover_products.py
├── requirements.txt      # Python dependencies
└── README.md            # This file
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

## Next Steps

- [ ] **Step 3**: Database Schema Design
- [ ] **Step 4**: Data Download & Processing
- [ ] **Step 5**: Snow Mask Generation (NDSI calculation)
- [ ] **Step 6**: Workflow Automation
