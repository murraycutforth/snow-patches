# Testing Guide

This project uses a comprehensive testing strategy with both unit tests and integration tests.

## Test Categories

### Unit Tests
- **Location**: `tests/test_*.py`
- **Requirements**: None (all external services are mocked)
- **Speed**: Fast (< 2 seconds)
- **Purpose**: Verify code logic and behavior in isolation

### Integration Tests
- **Location**: `tests/integration/test_*.py`
- **Requirements**: Valid Copernicus credentials
- **Speed**: Slower (API calls take time)
- **Purpose**: Verify correct interaction with real external services
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

# Integration tests only
pytest tests/integration/test_discovery_integration.py -v
```

### Run with Coverage Report
```bash
pip install pytest-cov
pytest tests/ --cov=data_handler --cov-report=html
```

## Setting Up Integration Tests

Integration tests require Copernicus Open Access Hub credentials.

### 1. Register for Free Account
Visit: https://scihub.copernicus.eu/dhus/#/self-registration

### 2. Set Environment Variables

**Linux/macOS:**
```bash
export COPERNICUS_USERNAME="your_username"
export COPERNICUS_PASSWORD="your_password"
```

**Windows (PowerShell):**
```powershell
$env:COPERNICUS_USERNAME="your_username"
$env:COPERNICUS_PASSWORD="your_password"
```

**Windows (Command Prompt):**
```cmd
set COPERNICUS_USERNAME=your_username
set COPERNICUS_PASSWORD=your_password
```

### 3. Verify Credentials
```bash
echo $COPERNICUS_USERNAME  # Should print your username
```

### 4. Run Integration Tests
```bash
pytest tests/integration/ -v -m integration
```

## Test Behavior

### Integration Tests Without Credentials
If credentials are not set, integration tests will be **skipped automatically**:

```
tests/integration/test_discovery_integration.py::TestSentinelAPIIntegration::test_find_products_ben_nevis_real_api
SKIPPED (Copernicus credentials not available...)
```

This is expected behavior and allows the test suite to run in CI/CD environments without credentials.

### Integration Tests With Credentials
When credentials are available, tests will:
1. Connect to the real Copernicus API
2. Query for actual Sentinel-2 products
3. Verify data structure and filtering
4. Display sample results

## Continuous Integration

For CI/CD pipelines (e.g., GitHub Actions), you can:

1. **Run unit tests only** (no credentials needed):
   ```bash
   pytest tests/ -v -m "not integration"
   ```

2. **Store credentials as secrets** and run all tests:
   ```yaml
   env:
     COPERNICUS_USERNAME: ${{ secrets.COPERNICUS_USERNAME }}
     COPERNICUS_PASSWORD: ${{ secrets.COPERNICUS_PASSWORD }}
   ```

## Test Markers Reference

| Marker | Description | Usage |
|--------|-------------|-------|
| `integration` | Tests that call external APIs | `pytest -m integration` |
| `unit` | Fast isolated tests | `pytest -m unit` |
| `slow` | Tests that take >1 second | `pytest -m "not slow"` |

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

## Best Practices

1. **Run unit tests frequently** during development (they're fast)
2. **Run integration tests before committing** to ensure API compatibility
3. **Don't commit credentials** to version control
4. **Use markers** to selectively run test subsets
5. **Check test output** for warnings and deprecations
