"""
Test configuration and shared fixtures
"""

import pytest
import sys
import os

# Add the parent directory to the path so tests can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from mock_fhir_server.mock_server import MockFHIRServer


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


@pytest.fixture
def sample_patient_data():
    """Sample patient data for testing"""
    return {
        "resourceType": "Patient",
        "identifier": [{
            "system": "http://example.org/mrn",
            "value": "12345"
        }],
        "name": [{
            "family": "Smith",
            "given": ["John"]
        }],
        "gender": "male",
        "birthDate": "1980-01-01"
    }


@pytest.fixture
def sample_observation_data():
    """Sample observation data for testing"""
    return {
        "resourceType": "Observation",
        "status": "final",
        "code": {
            "coding": [{
                "system": "http://loinc.org",
                "code": "8867-4",
                "display": "Heart rate"
            }]
        },
        "valueQuantity": {
            "value": 80,
            "unit": "beats/minute",
            "system": "http://unitsofmeasure.org",
            "code": "/min"
        }
    }