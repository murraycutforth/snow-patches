# Snow Patches Notebooks

Interactive Jupyter notebooks demonstrating the complete snow-patches pipeline.

## Available Notebooks

### `snow_coverage_analysis_demo.ipynb`

**Comprehensive demonstration of the entire workflow** from database initialization through snow mask analysis and visualization.

**Features:**
- 🗄️ Database setup and AOI definition
- 🔍 Sentinel-2 product discovery
- ⬇️ Satellite data download (B03 + B11 bands)
- ❄️ NDSI calculation and snow mask generation
- 📊 Rich visualizations with matplotlib
- 📈 Time series analysis of snow coverage
- 📉 Comparative analysis between mountain regions

**What You'll See:**
- Side-by-side comparisons of:
  - B03 (Green) and B11 (SWIR) bands
  - Continuous NDSI maps (values from -1 to 1)
  - Binary snow masks (0=no snow, 1=snow)
- Time series plots showing snow coverage trends
- Statistical summaries and box plots
- Cloud cover vs snow coverage analysis

**Requirements:**
- Jupyter Notebook or JupyterLab
- All dependencies from `requirements.txt`
- Optional: Copernicus Data Space credentials for real data
  - Without credentials: Uses synthetic demonstration data
  - With credentials: Downloads real Sentinel-2 imagery

## Getting Started

### 1. Install Jupyter

```bash
pip install jupyter
# or
pip install jupyterlab
```

### 2. Launch Notebook

```bash
# From project root
cd notebooks
jupyter notebook snow_coverage_analysis_demo.ipynb

# Or with JupyterLab
jupyter lab
```

### 3. Run Cells

Execute cells in order from top to bottom. The notebook will:
1. Check for Sentinel Hub credentials
2. Use real data if available, synthetic data otherwise
3. Generate impressive visualizations automatically

## Using Real Data

To use real Sentinel-2 imagery instead of synthetic data:

### 1. Get Credentials

1. Register at: https://dataspace.copernicus.eu/
2. Create OAuth2 credentials: https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings

### 2. Set Environment Variables

**Before launching Jupyter:**

```bash
export SH_CLIENT_ID="your_client_id"
export SH_CLIENT_SECRET="your_client_secret"

# Then launch Jupyter
jupyter notebook
```

**Or set in notebook:**

```python
import os
os.environ['SH_CLIENT_ID'] = 'your_client_id'
os.environ['SH_CLIENT_SECRET'] = 'your_client_secret'
```

### 3. Quota Considerations

**Free tier provides:**
- 1000 Processing Units (PU) per minute
- Generous monthly quota

**This demo uses:**
- ~1-2 PU per image (10km × 10km area)
- Limited to 5 products by default
- Customize `limit` parameter to download more

## Synthetic Data Mode

When credentials are not available, the notebook automatically:
- Creates realistic synthetic GeoTIFF files
- Simulates seasonal snow patterns
- Generates elevation-based snow distribution
- Adds cloud cover effects
- Produces identical analysis outputs

**Synthetic data benefits:**
- No API quota consumption
- Instant execution
- Predictable results for demonstrations
- Ideal for testing and development

## Notebook Structure

1. **Imports and Setup** - Load libraries and configure plotting
2. **Database Initialization** - Create SQLite database
3. **AOI Definition** - Define Ben Nevis and Ben Macdui regions
4. **Product Discovery** - Search for Sentinel-2 imagery
5. **Data Download** - Retrieve satellite data
6. **Snow Mask Generation** - Calculate NDSI and create masks
7. **Visualization** - Display comprehensive analysis
8. **Time Series Analysis** - Track snow coverage over time
9. **Statistical Analysis** - Summary statistics and comparisons
10. **Export Results** - Save to CSV

## Output Examples

The notebook generates:

### Individual Scene Analysis
- 4-panel layout per scene:
  - B03 (Green) band with color scale
  - B11 (SWIR) band with color scale
  - Continuous NDSI map with threshold line
  - Binary snow mask with legend
  - Statistics panel with metadata

### Time Series Plots
- Snow coverage over time (line plot)
- Cloud cover over time (line plot)
- Box plots comparing regions
- Scatter plots (snow vs cloud cover)

### Summary Statistics
- Per-AOI statistics (mean, min, max, std dev)
- Date ranges and scene counts
- Cloud cover summaries

### Exported Data
- CSV file: `data/results/snow_coverage_analysis.csv`
- Columns: date, aoi, snow_pct, cloud_cover, total_pixels, snow_pixels

## Customization

### Modify Search Parameters

```python
# In cell 3 (Product Discovery)
start_date = datetime(2024, 1, 1)
end_date = datetime(2024, 12, 31)  # Extend to full year
max_cloud_cover = 50.0  # Increase for more products
```

### Change NDSI Threshold

```python
# In cell 5 (Snow Mask Generation)
results = process_downloaded_products(
    session=session,
    ndsi_threshold=0.3,  # More inclusive (0.3 vs 0.4)
    save_masks=True,
    limit=None
)
```

### Adjust Visualization

```python
# In cell 6 (Visualization)
max_to_visualize = 12  # Show more scenes
```

### Download More Products

```python
# In cell 4 (Download)
results = download_pending_products(
    session=session,
    config=config,
    limit=20,  # Increase from 5
    max_retries=2
)
```

## Troubleshooting

### ImportError: No module named 'data_handler'

**Solution:** Make sure you're running from the project root or the notebook directory.

The notebook automatically adds the parent directory to the path:
```python
sys.path.insert(0, os.path.abspath('..'))
```

### Credentials Not Found

**Expected behavior:** The notebook will use synthetic data automatically.

To use real data, set environment variables before launching Jupyter.

### Out of Memory

**Solution:** Reduce the number of products:
```python
limit=3  # Process fewer products
```

Or use smaller date ranges.

### Slow Execution

**Synthetic data:** Should be fast (<1 minute total)
**Real data:** Download time depends on network speed and quota

## Tips

1. **Start with synthetic data** to verify the notebook works
2. **Use real data** for actual analysis
3. **Limit products** when testing (5-10 products)
4. **Save outputs** before closing (CSV export in cell 10)
5. **Restart kernel** if you want to start fresh
6. **Check quota** at: https://shapps.dataspace.copernicus.eu/dashboard/#/

## Further Development

Extend this notebook by:
- Adding more AOIs (e.g., other Scottish peaks)
- Comparing multiple years
- Testing different NDSI thresholds
- Correlating with temperature/precipitation data
- Creating animated time series
- Building interactive plots with plotly
- Adding machine learning classification

## Support

For issues or questions:
- Check project README.md
- See TESTING.md for test execution
- Review CLAUDE.md for development guidelines
- Open an issue on GitHub

---

**Happy analyzing! ❄️🏔️**
