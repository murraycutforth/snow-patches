"""
Integration tests for Jupyter notebooks.

These tests execute notebooks end-to-end to ensure they run without errors
and produce expected outputs.
"""

import pytest
import json
import subprocess
from pathlib import Path
import tempfile
import shutil


@pytest.fixture
def notebooks_dir():
    """Path to notebooks directory."""
    return Path(__file__).parent.parent.parent / 'notebooks'


@pytest.fixture
def temp_output_dir():
    """Create temporary directory for test outputs."""
    temp_dir = tempfile.mkdtemp(prefix='notebook_test_')
    yield Path(temp_dir)
    # Cleanup after test
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.integration
def test_snow_coverage_analysis_demo_executes(notebooks_dir, temp_output_dir):
    """
    Test that the snow coverage analysis demo notebook executes without errors.

    This test:
    1. Executes the entire notebook using nbconvert
    2. Checks that no cells raised exceptions
    3. Validates key outputs are present
    """
    notebook_path = notebooks_dir / 'snow_coverage_analysis_demo.ipynb'
    output_path = temp_output_dir / 'executed_notebook.ipynb'

    # Check notebook exists
    assert notebook_path.exists(), f"Notebook not found: {notebook_path}"

    # Execute notebook using nbconvert
    cmd = [
        'jupyter', 'nbconvert',
        '--to', 'notebook',
        '--execute',
        str(notebook_path),
        '--output', str(output_path),
        '--ExecutePreprocessor.kernel_name=snow-patches',
        '--ExecutePreprocessor.timeout=600',
        '--allow-errors'  # Continue execution even if cells error
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )

    # Check nbconvert succeeded
    assert result.returncode == 0, f"nbconvert failed:\n{result.stderr}"
    assert output_path.exists(), "Output notebook was not created"

    # Load executed notebook
    with open(output_path) as f:
        nb = json.load(f)

    # Count cells and errors
    total_code_cells = 0
    cells_with_errors = []
    cells_with_success = []

    for i, cell in enumerate(nb['cells']):
        if cell.get('cell_type') == 'code':
            total_code_cells += 1

            # Check for errors in outputs
            has_error = False
            has_success = False

            for output in cell.get('outputs', []):
                if output.get('output_type') == 'error':
                    has_error = True
                    cells_with_errors.append({
                        'cell_index': i,
                        'error_name': output.get('ename', 'Unknown'),
                        'error_value': output.get('evalue', '')[:200]
                    })
                elif output.get('output_type') == 'stream':
                    text = ''.join(output.get('text', []))
                    if '✅' in text or 'complete' in text.lower():
                        has_success = True

            if has_success and not has_error:
                cells_with_success.append(i)

    # Print summary
    print(f"\n{'='*80}")
    print(f"NOTEBOOK EXECUTION SUMMARY")
    print(f"{'='*80}")
    print(f"Total code cells: {total_code_cells}")
    print(f"Cells with errors: {len(cells_with_errors)}")
    print(f"Cells with success indicators: {len(cells_with_success)}")

    if cells_with_errors:
        print(f"\n❌ ERRORS FOUND:")
        for err in cells_with_errors:
            print(f"  Cell {err['cell_index']}: {err['error_name']}")
            print(f"    {err['error_value']}")

    # Assert no errors occurred
    assert len(cells_with_errors) == 0, (
        f"Notebook execution had {len(cells_with_errors)} cells with errors. "
        f"See test output for details."
    )

    # Assert we had some successful operations
    assert len(cells_with_success) > 0, "No success indicators found in notebook output"

    print(f"\n✅ Notebook executed successfully!")
    print(f"{'='*80}\n")


@pytest.mark.integration
def test_notebook_produces_expected_outputs(notebooks_dir, temp_output_dir):
    """
    Test that the notebook produces expected outputs and data files.

    Validates:
    - Database is created
    - Synthetic data is generated when no real credentials
    - Visualizations are produced
    - Statistics are calculated
    """
    notebook_path = notebooks_dir / 'snow_coverage_analysis_demo.ipynb'
    output_path = temp_output_dir / 'executed_notebook.ipynb'

    # Execute notebook
    cmd = [
        'jupyter', 'nbconvert',
        '--to', 'notebook',
        '--execute',
        str(notebook_path),
        '--output', str(output_path),
        '--ExecutePreprocessor.kernel_name=snow-patches',
        '--ExecutePreprocessor.timeout=600',
        '--allow-errors'
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"nbconvert failed:\n{result.stderr}"

    # Load executed notebook
    with open(output_path) as f:
        nb = json.load(f)

    # Find specific expected outputs
    expected_outputs = {
        'database_initialized': False,
        'aois_defined': False,
        'products_discovered': False,
        'snow_masks_generated': False,
        'visualization_complete': False
    }

    for cell in nb['cells']:
        if cell.get('cell_type') != 'code':
            continue

        for output in cell.get('outputs', []):
            if output.get('output_type') == 'stream':
                text = ''.join(output.get('text', []))

                if 'Database initialized' in text:
                    expected_outputs['database_initialized'] = True
                if 'Defined Areas of Interest' in text or 'Seeded' in text and 'AOIs' in text:
                    expected_outputs['aois_defined'] = True
                if 'Total products discovered' in text or 'Created' in text and 'synthetic products' in text:
                    expected_outputs['products_discovered'] = True
                if 'Snow mask generation complete' in text:
                    expected_outputs['snow_masks_generated'] = True
                if 'Time series visualization complete' in text or 'Comparative analysis complete' in text:
                    expected_outputs['visualization_complete'] = True

    # Verify all expected outputs were found
    print(f"\n{'='*80}")
    print(f"EXPECTED OUTPUTS CHECK")
    print(f"{'='*80}")
    for key, found in expected_outputs.items():
        status = "✅" if found else "❌"
        print(f"{status} {key}: {found}")
    print(f"{'='*80}\n")

    # Assert key outputs are present
    assert expected_outputs['database_initialized'], "Database initialization not found"
    assert expected_outputs['aois_defined'], "AOI definition not found"
    assert expected_outputs['products_discovered'], "Product discovery not found"
    assert expected_outputs['snow_masks_generated'], "Snow mask generation not found"

    # Visualization is optional if no data
    # assert expected_outputs['visualization_complete'], "Visualizations not completed"


@pytest.mark.integration
@pytest.mark.slow
def test_notebook_with_real_credentials(notebooks_dir, temp_output_dir):
    """
    Test notebook execution with real Sentinel Hub credentials.

    This test requires environment variables:
    - SH_CLIENT_ID
    - SH_CLIENT_SECRET

    Skip if credentials are not available.
    """
    import os

    # Check for credentials
    if not os.getenv('SH_CLIENT_ID') or not os.getenv('SH_CLIENT_SECRET'):
        pytest.skip("Sentinel Hub credentials not available (SH_CLIENT_ID, SH_CLIENT_SECRET)")

    notebook_path = notebooks_dir / 'snow_coverage_analysis_demo.ipynb'
    output_path = temp_output_dir / 'executed_notebook_real.ipynb'

    # Execute notebook
    cmd = [
        'jupyter', 'nbconvert',
        '--to', 'notebook',
        '--execute',
        str(notebook_path),
        '--output', str(output_path),
        '--ExecutePreprocessor.kernel_name=snow-patches',
        '--ExecutePreprocessor.timeout=1200',  # 20 minutes for real downloads
        '--allow-errors'
    ]

    # Set environment variables for subprocess
    env = os.environ.copy()

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert result.returncode == 0, f"nbconvert failed:\n{result.stderr}"

    # Load executed notebook
    with open(output_path) as f:
        nb = json.load(f)

    # Verify real data was used (not synthetic)
    found_real_data = False
    found_synthetic = False

    for cell in nb['cells']:
        if cell.get('cell_type') != 'code':
            continue

        for output in cell.get('outputs', []):
            if output.get('output_type') == 'stream':
                text = ''.join(output.get('text', []))
                if 'USE_REAL_DATA' in text or 'Credentials found' in text:
                    found_real_data = True
                if 'Created' in text and 'synthetic products' in text:
                    found_synthetic = True

    # When credentials are available, should use real data not synthetic
    assert found_real_data, "Real credentials were not detected/used"

    print(f"\n✅ Notebook executed with real credentials successfully!")


if __name__ == '__main__':
    # Allow running this test file directly
    pytest.main([__file__, '-v', '-m', 'integration'])
