"""Integration tests package.

These tests interact with real external services (e.g., Copernicus API)
and require valid credentials to be set as environment variables.

To run integration tests:
    pytest tests/integration/ -v -m integration

To skip integration tests:
    pytest tests/ -v -m "not integration"
"""
