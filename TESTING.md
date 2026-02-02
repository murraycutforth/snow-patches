# Testing Guide

This project uses a comprehensive testing strategy with both unit tests and integration tests.

## Test Categories

### Unit Tests
- **Location**: `tests/test_*.py`
- **Requirements**: None (all external services are mocked, uses in-memory SQLite)
- **Speed**: Fast (< 2 seconds)
- **Purpose**: Verify code logic and behavior in isolation

### Integration Tests
- **Location**: `tests/integration/test_*.py`
- **Requirements**:
  - Valid Copernicus credentials (for API tests)
  - File system access (for database tests)
  - Jupyter kernel installed (for notebook tests)
- **Speed**: Slower (API calls and file I/O take time)
- **Purpose**: Verify correct interaction with real external services and file-based databases
- **Marker**: `@pytest.mark.integration`

### Notebook Integration Tests
- **Location**: `tests/integration/test_notebook_execution.py`
- **Requirements**:
  - Jupyter and nbconvert installed
  - `snow-patches` Jupyter kernel registered
- **Speed**: Slow (~20-30 seconds per notebook)
- **Purpose**: Verify Jupyter notebooks execute end-to-end without errors
- **Marker**: `@pytest.mark.integration`

## Running Tests

### Run All Tests (Unit + Integration)
```bash
pytest tests/ -v
```

### Run Only Unit Tests (Skip Integration)
```bash
pytest tests/ -v -m "not integration"
```

### Run Only Integration Tests
```bash
pytest tests/integration/ -v -m integration
```

### Run Tests for Specific Module
```bash
# AOI tests only
pytest tests/test_aoi_handler.py -v

# Discovery tests only
pytest tests/test_data_discovery.py -v

# Download tests only (unit tests, fast)
pytest tests/test_download.py -v -m "not integration"

# Database tests only
pytest tests/test_database.py tests/test_models.py tests/test_repositories.py -v

# Discovery + Database integration tests
pytest tests/test_discovery_db_integration.py -v

# Integration tests only
pytest tests/integration/ -v -m integration

# Notebook integration tests only
pytest tests/integration/test_notebook_execution.py -v -m integration
```

### Run with Coverage Report
```bash
pip install pytest-cov
pytest tests/ --cov=data_handler --cov-report=html
```

## Setting Up Integration Tests

Integration tests require Copernicus Data Space Ecosystem credentials (OAuth2).

### 1. Register for Free Account
Visit: https://dataspace.copernicus.eu/

### 2. Create OAuth2 Credentials
Visit: https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings

### 3. Set Environment Variables

**Linux/macOS:**
```bash
export SH_CLIENT_ID="your_client_id"
export SH_CLIENT_SECRET="your_client_secret"
```

**Windows (PowerShell):**
```powershell
$env:SH_CLIENT_ID="your_client_id"
$env:SH_CLIENT_SECRET="your_client_secret"
```

**Windows (Command Prompt):**
```cmd
set SH_CLIENT_ID=your_client_id
set SH_CLIENT_SECRET=your_client_secret
```

### 4. Verify Credentials
```bash
echo $SH_CLIENT_ID  # Should print your client ID
```

### 5. Run Integration Tests
```bash
pytest tests/integration/ -v -m integration
```

**Important:** Download integration tests consume quota from your Sentinel Hub account.
The free tier provides generous limits (1000 Processing Units per minute), but be
mindful when running tests frequently.

## Test Behavior

### Integration Tests Without Credentials
If credentials are not set, integration tests will be **skipped automatically**:

```
tests/integration/test_download_integration.py::test_end_to_end_download_real_product
SKIPPED (Sentinel Hub credentials not found in environment)
```

This is expected behavior and allows the test suite to run in CI/CD environments without credentials.

### Integration Tests With Credentials
When credentials are available, tests will:
1. Connect to the real Sentinel Hub API
2. Download actual Sentinel-2 imagery (B03 + B11 bands)
3. Verify GeoTIFF file structure (2 bands, UINT16, correct CRS)
4. Validate database status updates
5. Display download results

**Note:** Download integration tests consume Processing Units from your quota.
Each test downloads a small AOI (~10km × 10km) which typically uses ~1-2 PU.

## Continuous Integration

For CI/CD pipelines (e.g., GitHub Actions), you can:

1. **Run unit tests only** (no credentials needed):
   ```bash
   pytest tests/ -v -m "not integration"
   ```

2. **Store credentials as secrets** and run all tests:
   ```yaml
   env:
     SH_CLIENT_ID: ${{ secrets.SH_CLIENT_ID }}
     SH_CLIENT_SECRET: ${{ secrets.SH_CLIENT_SECRET }}
   ```

## Test Markers Reference

| Marker | Description | Usage |
|--------|-------------|-------|
| `integration` | Tests that call external APIs or use file systems | `pytest -m integration` |
| `unit` | Fast isolated tests with mocked dependencies | `pytest -m unit` |
| `slow` | Tests that take >30 seconds (notebooks, real downloads) | `pytest -m "not slow"` |

**Note**: The `slow` marker is used for tests that are particularly time-consuming:
- Notebook execution with real data: 10-20 minutes
- Full pipeline integration tests: 5-10 minutes
- Use `pytest -m "not slow"` to skip these during rapid development

## Troubleshooting

### Integration Tests Fail with Authentication Error
- Verify credentials are correct
- Check if your account is active
- Ensure environment variables are set in current shell

### Integration Tests Timeout
- Check your internet connection
- Copernicus Hub may be experiencing high traffic
- Try running tests again later

### No Products Found in Integration Tests
- This is normal and tests handle it gracefully
- The date range used may not have suitable imagery
- Tests verify structure even with 0 results

## Database Testing

The project uses both in-memory and file-based SQLite databases for testing.

### In-Memory Database (Unit Tests)
- Used in: `test_database.py`, `test_models.py`, `test_repositories.py`, `test_discovery_db_integration.py`
- Created fresh for each test via `in_memory_db` fixture in `conftest.py`
- Fast and isolated - no file system interaction
- Automatically cleaned up after each test

### File-Based Database (Integration Tests)
- Used in: `tests/integration/test_database_integration.py`
- Creates temporary SQLite files in a temp directory
- Tests real persistence and multiple sessions
- Verifies foreign key constraints and migrations

### Database Fixtures

The `tests/conftest.py` file provides shared fixtures:

```python
# Create empty in-memory database
def test_something(in_memory_db):
    engine = in_memory_db
    # ... use engine ...

# Create in-memory database pre-populated with AOIs
def test_with_aois(db_with_aois):
    engine, session = db_with_aois
    # AOIs already exist in session
```

### Running Database Tests

```bash
# All database unit tests (fast)
pytest tests/test_database.py tests/test_models.py tests/test_repositories.py -v

# Database integration tests (file-based)
pytest tests/integration/test_database_integration.py -v -m integration

# Discovery + Database integration
pytest tests/test_discovery_db_integration.py -v
```

## Notebook Testing

The project includes automated testing for Jupyter notebooks to ensure they execute correctly.

### Notebook Test Setup

1. **Install Jupyter kernel**:
   ```bash
   # Activate your conda environment
   conda activate snow-patches

   # Install ipykernel
   pip install ipykernel

   # Register kernel
   python -m ipykernel install --user --name snow-patches --display-name "Python (snow-patches)"
   ```

2. **Verify kernel installation**:
   ```bash
   jupyter kernelspec list
   # Should show 'snow-patches' in the list
   ```

### Running Notebook Tests

```bash
# Run all notebook tests
pytest tests/integration/test_notebook_execution.py -v -m integration

# Run specific test
pytest tests/integration/test_notebook_execution.py::test_snow_coverage_analysis_demo_executes -v

# Run with output visible
pytest tests/integration/test_notebook_execution.py -v -s
```

### What the Tests Verify

1. **Execution Test** (`test_snow_coverage_analysis_demo_executes`):
   - Notebook executes without Python errors
   - All code cells complete successfully
   - No exceptions are raised

2. **Output Validation Test** (`test_notebook_produces_expected_outputs`):
   - Database is initialized
   - AOIs are defined
   - Products are discovered (synthetic or real)
   - Snow masks are generated
   - Visualizations are created

3. **Real Data Test** (`test_notebook_with_real_credentials`):
   - Only runs if `SH_CLIENT_ID` and `SH_CLIENT_SECRET` are set
   - Verifies notebook works with real Sentinel Hub API
   - Downloads and processes actual satellite imagery
   - Marked as `@pytest.mark.slow` (takes 10-20 minutes)

### Test Output

When tests pass, you'll see:
```
================================================================================
NOTEBOOK EXECUTION SUMMARY
================================================================================
Total code cells: 20
Cells with errors: 0
Cells with success indicators: 10

✅ Notebook executed successfully!
================================================================================

PASSED
```

### Troubleshooting Notebook Tests

**Error: "No such kernel named python3"**
- Solution: Install and register the Jupyter kernel (see setup above)

**Error: "jupyter: command not found"**
- Solution: Install Jupyter: `pip install jupyter nbconvert`

**Timeout errors**
- Default timeout is 600 seconds (10 minutes)
- Increase for slow systems or real data downloads
- Edit `ExecutePreprocessor.timeout` in test file

**Notebooks fail but work in Jupyter**
- Check kernel name matches: `snow-patches`
- Verify all dependencies are installed in the conda environment
- Check for cells that depend on interactive input

## Alembic Migrations

Database schema changes are managed with Alembic migrations.

### Common Alembic Commands

```bash
# Apply all migrations to create/update database
alembic upgrade head

# Create a new migration after model changes
alembic revision --autogenerate -m "Description of changes"

# Rollback last migration
alembic downgrade -1

# Show current migration version
alembic current

# Show migration history
alembic history
```

### Testing Migrations

The integration tests verify that:
1. Migrations can be applied successfully
2. Tables are created with correct schema
3. Foreign key constraints are enforced
4. Data persists across sessions

## Best Practices

1. **Run unit tests frequently** during development (they're fast)
2. **Run integration tests before committing** to ensure API compatibility
3. **Don't commit credentials** to version control
4. **Use markers** to selectively run test subsets
5. **Check test output** for warnings and deprecations
6. **Use in-memory databases** for unit tests to keep them fast
7. **Test migrations** in a separate test database before applying to production
