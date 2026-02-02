# Polished Demo Notebook Guide

## Overview

The `notebooks/demo_polished.ipynb` notebook provides a complete, production-ready demonstration of the Scottish Highlands snow patches monitoring system. It showcases the entire workflow from data acquisition to trend analysis.

## Features

### 1. Interactive AOI Visualization 🗺️
- Displays monitoring areas on an interactive folium map
- Shows 10km × 10km regions centered on Scottish peaks
- Click on regions to see details (coordinates, size)

### 2. Database Setup & Data Download 📡
- Initializes SQLite database with full schema
- Discovers Sentinel-2 products for winter season
- Downloads multi-band GeoTIFF files (B03 Green + B11 SWIR)
- Tracks download status in database
- Configurable cloud cover threshold and image limits

### 3. Raw Data Visualization 🖼️
- Loads B03 (Green) band from downloaded imagery
- Creates grid plots with date and cloud cover annotations
- Brightness enhancement for better visibility
- High-resolution output (150 DPI)

### 4. Snow Detection ❄️
- Computes NDSI (Normalized Difference Snow Index)
- Applies threshold-based snow classification
- Saves binary snow masks as GeoTIFF files
- Tracks statistics in database (snow pixels, coverage %)

### 5. Trend Analysis 📊
- Time series plots of snow coverage over winter
- Multi-AOI comparison capabilities
- Cloud cover tracking alongside snow data
- Statistical summaries and data tables

## Requirements

### Credentials

You need free Copernicus Data Space credentials:

1. Register at: https://dataspace.copernicus.eu/
2. Navigate to: Account Settings → API Credentials
3. Create new OAuth2 credentials
4. Set environment variables:
   ```bash
   export SH_CLIENT_ID="your_client_id"
   export SH_CLIENT_SECRET="your_client_secret"
   ```

### Python Dependencies

All required packages are in `requirements.txt`:

```bash
pip install -r requirements.txt
```

Key dependencies:
- `sentinelhub` - Satellite data access
- `rasterio` - GeoTIFF I/O
- `geopandas` - Geospatial operations
- `matplotlib` - Plotting
- `folium` - Interactive maps
- `sqlalchemy` - Database ORM

## Running the Notebook

### Using Jupyter Notebook

```bash
# Ensure credentials are set
export SH_CLIENT_ID="your_client_id"
export SH_CLIENT_SECRET="your_client_secret"

# Launch notebook
jupyter notebook notebooks/demo_polished.ipynb
```

### Using JupyterLab

```bash
# With credentials
jupyter lab notebooks/demo_polished.ipynb
```

### Using VS Code

1. Open `notebooks/demo_polished.ipynb` in VS Code
2. Select your Python kernel
3. Ensure credentials are in environment or set in terminal before launching VS Code

## Configuration Parameters

The notebook has several configurable parameters in the **Configuration** cell:

```python
WINTER_YEAR = 2024          # Winter season to analyze (2024 = Dec 2023 - Feb 2024)
MAX_CLOUD_COVER = 30.0      # Maximum cloud cover % for data quality
NDSI_THRESHOLD = 0.4        # NDSI threshold for snow classification
LIMIT_PER_AOI = 10          # Maximum images to download per AOI
DB_PATH = "data/snow_patches_demo.db"  # Database location
```

### Recommended Settings

**For quick demo (5-10 minutes):**
```python
WINTER_YEAR = 2024
MAX_CLOUD_COVER = 30.0
LIMIT_PER_AOI = 5
```

**For comprehensive analysis (30-60 minutes):**
```python
WINTER_YEAR = 2024
MAX_CLOUD_COVER = 50.0
LIMIT_PER_AOI = None  # No limit
```

**For multi-year analysis:**
Run the notebook multiple times with different `WINTER_YEAR` values, then use a separate analysis script to compare years.

## Notebook Structure

### Section 1: Setup
- Import modules
- Configure matplotlib settings
- Minimal code required

### Section 2: Configuration
- Set analysis parameters
- Single cell with all configurable values

### Section 3: AOI Visualization
- Load AOI definitions
- Display interactive map
- **Output:** Folium map widget

### Section 4: Database & Download
- Initialize database with schema
- Configure Sentinel Hub API
- Discover and download winter data
- **Output:** Progress logs, download statistics

### Section 5: Raw Data Visualization
- Load B03 bands from database
- Plot grayscale imagery
- **Output:** Grid of satellite images

### Section 6: Snow Detection
- Compute NDSI-based snow masks
- Visualize binary classifications
- **Output:** Grid of snow masks with statistics

### Section 7: Trend Analysis
- Query time series data
- Plot snow coverage over time
- **Output:** Line plots with trends

### Section 8: Multi-AOI Comparison
- Process multiple AOIs
- Compare trends across regions
- **Output:** Multi-line comparison plots

## Data Flow

```
┌─────────────────────┐
│ Copernicus API      │
│ (Sentinel-2 Data)   │
└──────────┬──────────┘
           │
           │ discover_and_download_winter_data()
           ▼
┌─────────────────────┐
│ SQLite Database     │
│ - AOIs              │
│ - Products          │
│ - Download Status   │
│ - Snow Masks        │
└──────────┬──────────┘
           │
           │ load_b03_images_from_db()
           ▼
┌─────────────────────┐
│ GeoTIFF Files       │
│ - B03 (Green)       │
│ - B11 (SWIR)        │
│ - Snow Masks        │
└──────────┬──────────┘
           │
           │ plot_*() functions
           ▼
┌─────────────────────┐
│ Visualizations      │
│ - Maps              │
│ - Image Grids       │
│ - Trend Plots       │
└─────────────────────┘
```

## Utility Functions

All complex logic is in `data_handler/demo_utils.py`:

### Database Management
- `setup_database_and_aois()` - Initialize DB and AOIs

### Data Acquisition
- `discover_and_download_winter_data()` - Complete download workflow

### Visualization
- `load_b03_images_from_db()` - Load B03 bands from files
- `plot_b03_images()` - Create B03 grid plots

### Snow Analysis
- `compute_snow_masks_for_aoi()` - NDSI processing
- `load_snow_masks_from_db()` - Load mask files
- `plot_snow_masks()` - Visualize snow masks

### Trend Analysis
- `analyze_snow_trends()` - Extract time series data
- `plot_snow_trends()` - Create trend plots

## Output Files

The notebook generates several outputs:

### Database
- `data/snow_patches_demo.db` - SQLite database with all metadata

### GeoTIFF Files
- `data/sentinel2/{aoi_name}/{year}/{month}/{product_id}.tif` - Downloaded imagery
- `data/snow_masks/{aoi_name}/{year}/{month}/{product_id}_snow_mask.tif` - Snow masks

### In-Notebook Outputs
- Interactive folium maps
- Matplotlib figures (not saved by default)

To save figures, add after each plot:
```python
fig.savefig('output_name.png', dpi=300, bbox_inches='tight')
```

## Performance Notes

### Download Times
- **Per image**: 10-30 seconds (depends on resolution and network)
- **10 images**: 2-5 minutes
- **Full winter season**: 10-30 minutes (20-60 images typical)

### Processing Times
- **Snow mask computation**: 1-2 seconds per image
- **Plotting**: < 1 second per figure
- **Database queries**: < 1 second

### Disk Space
- **Per image (B03+B11)**: 5-20 MB (compressed GeoTIFF)
- **Per snow mask**: 1-5 MB (binary, compressed)
- **10 images + masks**: ~100-250 MB
- **Full season**: 500 MB - 2 GB

### Memory Usage
- **Notebook baseline**: ~100 MB
- **Per image loaded**: 10-50 MB
- **Peak memory**: ~500 MB - 1 GB for typical runs

## Troubleshooting

### "No products found"
- **Cause**: Date range or AOI has limited clear-sky imagery
- **Solution**: Increase `MAX_CLOUD_COVER` or try different `WINTER_YEAR`

### "401 Unauthorized" errors
- **Cause**: Invalid or missing credentials
- **Solution**: Verify credentials at https://dataspace.copernicus.eu/
- Check environment variables: `echo $SH_CLIENT_ID`

### "Database is locked"
- **Cause**: Another process accessing database
- **Solution**: Close other notebook instances or restart kernel

### "File not found" when loading images
- **Cause**: Download failed or file was moved
- **Solution**: Re-run download step or check file paths in database

### Images appear all black
- **Cause**: No data in image or extreme cloud cover
- **Solution**: Check cloud cover values, filter out high-cloud images

### Slow downloads
- **Cause**: Network congestion or API throttling
- **Solution**:
  - Reduce `LIMIT_PER_AOI`
  - Use coarser resolution (modify download.py resolution parameter)
  - Run during off-peak hours

## Customization

### Add New AOIs

Edit `data_handler/aoi.py`:

```python
# Add new AOI definition
new_aoi = {
    'name': 'cairngorm',
    'center_lat': 57.1147,
    'center_lon': -3.6681,
    'size_km': 10.0
}
```

### Change NDSI Threshold

Modify in Configuration cell:
```python
NDSI_THRESHOLD = 0.3  # More sensitive (more pixels classified as snow)
NDSI_THRESHOLD = 0.5  # Less sensitive (fewer pixels classified as snow)
```

Typical range: 0.3 - 0.5

### Adjust Image Resolution

Currently fixed at 10m in `download.py`. To change, modify:
```python
DEFAULT_RESOLUTION = 20  # Faster downloads, lower quality
DEFAULT_RESOLUTION = 10  # Standard (current)
```

### Add Custom Visualizations

Create new plotting functions in `demo_utils.py` following existing patterns:

```python
def plot_custom_analysis(data, **kwargs):
    fig, ax = plt.subplots()
    # Your plotting code here
    return fig
```

## Advanced Usage

### Batch Processing Multiple Winters

```python
for year in [2023, 2024, 2025]:
    stats = discover_and_download_winter_data(
        session, config, winter_year=year,
        max_cloud_cover=30.0
    )
    # Process each year...
```

### Export Data for External Analysis

```python
# Export trends to CSV
trends_df = analyze_snow_trends(session)
trends_df.to_csv('snow_trends.csv', index=False)

# Export to Excel with formatting
with pd.ExcelWriter('snow_analysis.xlsx') as writer:
    trends_df.to_excel(writer, sheet_name='Trends', index=False)
```

### Automated Reporting

```python
from datetime import datetime

# Generate report
report_date = datetime.now().strftime('%Y-%m-%d')
fig.savefig(f'reports/snow_report_{report_date}.png', dpi=300)
```

## Integration with Other Tools

### Web Dashboard
- Export database to cloud storage
- Use Streamlit or Dash for interactive dashboard
- Schedule periodic updates with cron

### GIS Software
- Load GeoTIFF files in QGIS or ArcGIS
- Perform spatial analysis
- Create publication-quality maps

### Climate Data
- Join snow data with weather stations
- Correlate with temperature/precipitation
- Use pandas merge on date column

## Next Steps

After running this demo:

1. **Explore the database**:
   ```bash
   sqlite3 data/snow_patches_demo.db
   .tables
   SELECT * FROM aoi;
   ```

2. **Run integration tests**:
   ```bash
   pytest tests/integration/ -v -m integration
   ```

3. **Read the implementation**:
   - `data_handler/demo_utils.py` - All workflow functions
   - `data_handler/snow_mask.py` - NDSI calculation
   - `data_handler/download.py` - Data acquisition

4. **Customize for your needs**:
   - Modify AOI definitions
   - Adjust thresholds
   - Add new visualizations

## Support

- **Issues**: https://github.com/anthropics/claude-code/issues
- **Copernicus Support**: https://dataspace.copernicus.eu/support
- **sentinelhub-py docs**: https://sentinelhub-py.readthedocs.io/

---

*Last updated: 2025-02-02*
