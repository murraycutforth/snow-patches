# Visualization Notebook Guide

## Overview

The `notebooks/demo_visualization.ipynb` notebook provides an interactive demonstration of the snow patches monitoring system. It showcases:

1. **Interactive AOI Visualization** - View monitoring areas on a folium map
2. **Data Discovery** - Find Sentinel-2 imagery for winter 2024/2025
3. **Image Visualization** - Download and display true-color satellite images

## Requirements

### Credentials

You'll need free Copernicus Data Space credentials:

1. Register at: https://dataspace.copernicus.eu/
2. Navigate to: Account Settings → API Credentials
3. Create new OAuth2 credentials
4. Set environment variables:
   ```bash
   export SH_CLIENT_ID="your_client_id"
   export SH_CLIENT_SECRET="your_client_secret"
   ```

### Python Dependencies

All required packages are in `requirements.txt`. If you haven't already:

```bash
pip install -r requirements.txt

# Optional: Install Jupyter if needed
pip install jupyter jupyterlab
```

## Running the Notebook

### Using Jupyter Notebook
```bash
jupyter notebook notebooks/demo_visualization.ipynb
```

### Using JupyterLab
```bash
jupyter lab notebooks/demo_visualization.ipynb
```

### Using VS Code
Open the `.ipynb` file in VS Code and select your Python kernel.

## Notebook Structure

### Section 1: Interactive Map
- Loads AOI definitions for Ben Nevis and Ben Macdui
- Creates an interactive folium map with clickable regions
- **Output**: Interactive map showing 10km × 10km monitoring areas

### Section 2: Data Discovery
- Searches for Sentinel-2 products from winter 2024/2025
- Filters by cloud cover (≤ 50%)
- Displays product summaries and metadata
- **Output**: DataFrame of available satellite images

### Section 3: Image Visualization
- Downloads true-color RGB images for **all AOIs**
- Enhances brightness for better visibility
- Creates multi-panel plots with:
  - Latitude/longitude coordinate labels
  - Equal aspect ratio
  - High DPI (150) for crisp rendering
  - Date and cloud cover annotations
- **Output**: High-quality grid plots for each AOI showing winter conditions

## Customization Options

### Change Cloud Cover Threshold
```python
max_cloud_cover = 30.0  # More restrictive (default: 50.0)
```

### Adjust Number of Images Per AOI
```python
max_images_per_aoi = 12  # Download up to 12 images per AOI (default: 9)
```

### Change Image Resolution
```python
resolution = 10  # Higher quality but slower (default: 20m)
```

### Adjust Brightness Enhancement
```python
brightness_factor = 5.0  # More enhancement (default: 3.5)
```

### Customize Plot DPI
```python
# In the notebook import cell, change:
plt.rcParams['figure.dpi'] = 200  # Higher resolution (default: 150)
plt.rcParams['savefig.dpi'] = 400  # For saving images (default: 300)
```

### Change Grid Layout
```python
# In the plotting cell, modify:
ncols = 4  # 4 columns instead of 3 for wider displays
```

## Utility Functions

The notebook uses functions from `data_handler/notebook_utils.py`:

### `create_aoi_map(aois_gdf)`
- **Input**: GeoDataFrame with AOI geometries
- **Output**: folium.Map object
- **Purpose**: Create interactive web map

### `get_winter_date_range(winter_year)`
- **Input**: Year (e.g., 2025 for winter 2024/2025)
- **Output**: Tuple of (start_date, end_date)
- **Purpose**: Define winter season (Dec-Feb)

### `download_rgb_image(config, bbox, date, product_id, resolution)`
- **Input**: SentinelHub config, bounding box, date, product ID
- **Output**: numpy array (H, W, 3) with RGB values
- **Purpose**: Download true-color satellite image

### `plot_sentinel_images(images, aoi_name, bbox, ncols, figsize, brightness_factor, dpi)`
- **Input**: List of image dictionaries, optional BBox for coordinate labels
- **Output**: matplotlib Figure with lat/lon axes
- **Purpose**: Create high-quality multi-panel visualization
- **New features**:
  - Automatic lat/lon coordinate labels when bbox provided
  - Equal aspect ratio for accurate geographic representation
  - Configurable DPI for print-quality output
  - Auto-calculated figure size based on number of images

## Testing

All utility functions have comprehensive unit tests:

```bash
# Run notebook utility tests
pytest tests/test_notebook_utils.py -v

# All tests (16 tests)
pytest tests/test_notebook_utils.py
```

## Troubleshooting

### "No products found"
- Check date range (winter 2024/2025 may have limited clear-sky imagery)
- Increase `max_cloud_cover` threshold
- Verify AOI covers Scotland (not Antarctica!)

### "Credentials not found"
- Ensure environment variables are set in the terminal where you launch Jupyter
- For Jupyter, you may need to restart the kernel after setting variables
- Check credentials at: https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings

### "401 Unauthorized" errors during download
- This usually means the notebook is trying to use the commercial Sentinel Hub endpoint instead of the free Copernicus Data Space endpoint
- Make sure you're using the latest version of `notebook_utils.py` which uses `SENTINEL2_L2A_CDSE`
- Verify your config is pointing to the correct endpoint:
  ```python
  print(config.sh_base_url)  # Should be: https://sh.dataspace.copernicus.eu
  ```
- Try restarting the Jupyter kernel and re-running all cells from the top

### "No data returned for product"
- Some products may be unavailable or still processing
- The notebook will skip failed downloads and continue with others
- Try reducing image resolution or using a smaller bbox

### Images appear too dark/bright
- Adjust `brightness_factor` parameter (typical range: 2.0 - 5.0)
- Sentinel-2 L2A images are often dark due to atmospheric correction
- Snow-covered areas typically appear bright even with low enhancement

### Slow downloads
- Use coarser resolution (e.g., `resolution=20` or `resolution=60`)
- Reduce number of images (`max_images=3`)
- Check internet connection speed

## Performance Notes

- **Download time**: ~10-30 seconds per image (depends on resolution and internet speed)
- **Resolution settings**:
  - 10m: High quality, large files, slower downloads
  - 20m: Good balance (recommended for demos)
  - 60m: Fast downloads, lower quality
- **Memory usage**: ~50-200 MB per image (increases with resolution)

## Next Steps

After running this notebook, you can:

1. Apply snow detection (NDSI threshold) - see `snow_mask.py`
2. Build time-series analysis of snow coverage
3. Compare snow extent between different years
4. Export results to database for long-term tracking

See `examples/snow_mask_workflow.py` for snow detection pipeline.

## Support

- **Issues**: https://github.com/anthropics/claude-code/issues
- **Copernicus Support**: https://dataspace.copernicus.eu/support
- **sentinelhub-py docs**: https://sentinelhub-py.readthedocs.io/
