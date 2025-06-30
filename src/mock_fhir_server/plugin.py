"""
Pytest plugin for FHIR server mocking
"""

import pytest
from .mock_server import MockFHIRServer


@pytest.fixture
def mock_fhir_server():
    """Pytest fixture that provides a MockFHIRServer instance"""
    server = MockFHIRServer()
    yield server
    server.reset()


@pytest.fixture
def fhir_server_with_requests_mock(requests_mock, mock_fhir_server):
    """Pytest fixture that provides a MockFHIRServer with requests-mock integration"""
    mock_fhir_server.start_mock(requests_mock)
    yield mock_fhir_server
    mock_fhir_server.stop_mock()