# mock-fhir-server

A mock FHIR server for pytest testing with full support for the `fhir-resources` library.

## Installation

### From Git Repository

```bash
poetry add git+https://github.com/KeironO/mock-fhir-server/mock-fhir-server.git
# or
pip install git+https://github.com/KeironO/mock-fhir-server/mock-fhir-server.git
```


## Quick Start

### Basic Usage

```python
import pytest
import requests
from mock_fhir_server import MockFHIRServer

def test_create_patient():
    # Create server instance
    server = MockFHIRServer()

    # Use with requests-mock
    with requests_mock.Mocker() as m:
        server.start_mock(m)

        patient_data = {
            "resourceType": "Patient",
            "name": [{"family": "Nonce", "given": ["Kenneth"]}],
            "gender": "male"
        }

        response = requests.post(f"{server.base_url}/Patient", json=patient_data)
        assert response.status_code == 201

        created_patient = response.json()["created_resource"]
        assert created_patient["name"][0]["family"] == "Smith"
```

### Using Pytest Fixtures

Create a `conftest.py` in your test directory:

```python
# conftest.py
import pytest
from mock_fhir_server.conftest import mock_fhir_server, fhir_server_with_requests_mock

# The fixtures are now available in all your tests
```

Then in your tests:

```python
# test_patient_operations.py
import requests

def test_patient_crud(fhir_server_with_requests_mock):
    server = fhir_server_with_requests_mock

    # Create patient
    patient_data = {
        "resourceType": "Patient",
        "identifier": [{"system": "http://hospital.co.uk/crn", "value": "M123"}],
        "name": [{"family": "Blobby", "given": ["Ms"]}]
    }

    create_response = requests.post(f"{server.base_url}/Patient", json=patient_data)
    assert create_response.status_code == 201
    patient_id = create_response.json()["created_resource"]["id"]

    # Read patient
    read_response = requests.get(f"{server.base_url}/Patient/{patient_id}")
    assert read_response.status_code == 200
    patient = read_response.json()
    assert patient["name"][0]["family"] == "Blobby"

    # Search by identifier
    search_response = requests.get(f"{server.base_url}/Patient?identifier=http://hospital.co.uk/crn|M123")
    bundle = search_response.json()
    assert bundle["total"] == 1
```

### With fhir-resources Models

```python
from fhir.resources.patient import Patient
from fhir.resources.humanname import HumanName
from fhir.resources.identifier import Identifier

def test_with_fhir_models(fhir_server_with_requests_mock):
    server = fhir_server_with_requests_mock

    # Create patient using fhir-resources
    patient = Patient(
        identifier=[
            Identifier(system="http://hospital.co.uk/crn", value="MRN456")
        ],
        name=[
            HumanName(family="Johnson", given=["Dick"])
        ]
    )

    # Validate the model (automatic with fhir-resources)
    assert patient.resourceType == "Patient"

    # Post to mock server
    response = requests.post(
        f"{server.base_url}/Patient",
        json=patient.model_dump()
    )
    assert response.status_code == 201

    # Parse response back to validated model
    created_data = response.json()["created_resource"]
    created_patient = Patient(**created_data)
    assert created_patient.name[0].family == "Johnson"
```

## Advanced Features

### Conditional Operations

```python
def test_conditional_create(fhir_server_with_requests_mock):
    server = fhir_server_with_requests_mock

    patient_data = {
        "resourceType": "Patient",
        "identifier": [{"system": "http://hospital.co.uk/crn", "value": "MRN789"}],
        "name": [{"family": "Is", "given": ["Pen"]}]
    }

    # First create - should succeed
    response1 = requests.post(
        f"{server.base_url}/Patient",
        json=patient_data,
        headers={"If-None-Exist": "identifier=http://hospital.co.uk/crn|MRN789"}
    )
    assert response1.status_code == 201  # Created

    # Second create - should return existing
    response2 = requests.post(
        f"{server.base_url}/Patient",
        json=patient_data,
        headers={"If-None-Exist": "identifier=http://hospital.co.uk/crn|MRN789"}
    )
    assert response2.status_code == 200  # Found existing
```

### Conditional Updates

```python
def test_conditional_update(fhir_server_with_requests_mock):
    server = fhir_server_with_requests_mock

    # Create patient first
    initial_patient = {
        "resourceType": "Patient",
        "identifier": [{"system": "http://hospital.co.uk/crn", "value": "UPDATE123"}],
        "name": [{"family": "Before", "given": ["Update"]}]
    }
    requests.post(f"{server.base_url}/Patient", json=initial_patient)

    # Update using search criteria
    updated_patient = {
        "resourceType": "Patient",
        "identifier": [{"system": "http://hospital.co.uk/crn", "value": "UPDATE123"}],
        "name": [{"family": "After", "given": ["Update"]}],
        "gender": "unknown"
    }

    response = requests.put(
        f"{server.base_url}/Patient?identifier=http://hospital.co.uk/crn|UPDATE123",
        json=updated_patient
    )
    assert response.status_code == 200  # Updated existing
```

### Multiple Resource Types

```python
def test_multiple_resource_types(fhir_server_with_requests_mock):
    server = fhir_server_with_requests_mock

    # Create patient
    patient = {"resourceType": "Patient", "name": [{"family": "Around"}]}
    requests.post(f"{server.base_url}/Patient", json=patient)

    # Create observation
    observation = {
        "resourceType": "Observation",
        "status": "final",
        "code": {"coding": [{"code": "8867-4", "display": "Heart rate"}]},
        "valueQuantity": {"value": 72, "unit": "beats/minute"}
    }
    requests.post(f"{server.base_url}/Observation", json=observation)

    # Search each type separately
    patients = requests.get(f"{server.base_url}/Patient").json()
    observations = requests.get(f"{server.base_url}/Observation").json()

    assert patients["total"] == 1
    assert observations["total"] == 1
```

### Direct Server Usage (No HTTP)

```python
def test_direct_server_usage(mock_fhir_server):
    server = mock_fhir_server

    patient_data = {
        "resourceType": "Patient",
        "name": [{"family": "Trombone", "given": ["Rusty"]}]
    }

    # Use server methods directly
    result = server.create_resource(patient_data)
    patient_id = result["created_resource"]["id"]

    # Read back directly
    retrieved = server.read_resource("Patient", patient_id)
    assert retrieved["name"][0]["family"] == "DirectAccess"

    # Search directly
    search_result = server.search_resources("Patient", {})
    assert search_result["total"] == 1
```
## How to use


```python
def test_ehr_patient_sync(fhir_server_with_requests_mock):
    """Test syncing patients from external EHR system"""
    server = fhir_server_with_requests_mock

    # Simulate EHR patient data
    ehr_patients = [
        {
            "resourceType": "Patient",
            "identifier": [{"system": "http://hospital.co.uk/crn", "value": f"EHR{i:03d}"}],
            "name": [{"family": f"Patient{i}", "given": ["Test"]}]
        }
        for i in range(1, 6)  # 5 patients
    ]

    # Sync patients using conditional creates
    for patient in ehr_patients:
        identifier = patient["identifier"][0]
        response = requests.post(
            f"{server.base_url}/Patient",
            json=patient,
            headers={"If-None-Exist": f"identifier={identifier['system']}|{identifier['value']}"}
        )
        assert response.status_code == 201  # All should be new

    # Verify all patients were created
    all_patients = requests.get(f"{server.base_url}/Patient").json()
    assert all_patients["total"] == 5
```

### Clinical Decision Support Testing

```python
def test_clinical_decision_support(fhir_server_with_requests_mock):
    """Test clinical decision support rules"""
    server = fhir_server_with_requests_mock

    # Create patient with diabetes
    patient = {
        "resourceType": "Patient",
        "identifier": [{"system": "http://hospital.co.uk/crn", "value": "CDS001"}],
        "name": [{"family": "Poopy", "given": ["Patient"]}]
    }
    create_response = requests.post(f"{server.base_url}/Patient", json=patient)
    patient_id = create_response.json()["created_resource"]["id"]

    # Add high glucose observation
    observation = {
        "resourceType": "Observation",
        "status": "final",
        "subject": {"reference": f"Patient/{patient_id}"},
        "code": {"coding": [{"system": "http://loinc.org", "code": "15074-8", "display": "Glucose"}]},
        "valueQuantity": {"value": 250, "unit": "mg/dL"}  # High glucose
    }
    requests.post(f"{server.base_url}/Observation", json=observation)

    # Your clinical decision support logic would fetch patient and observations
    # and determine if alerts should fire

    # Verify data is available for CDS processing
    patient_response = requests.get(f"{server.base_url}/Patient/{patient_id}")
    observations_response = requests.get(f"{server.base_url}/Observation")

    assert patient_response.status_code == 200
    assert observations_response.json()["total"] == 1
```

## Configuration

### Custom Base URL

```python
# Default: http://localhost:8080/fhir
server = MockFHIRServer(base_url="https://my-fhir-server.example.com/fhir/R4")
```

### Server Reset

```python
def test_isolated_tests(mock_fhir_server):
    # Server automatically resets between tests
    # Or manually reset:
    mock_fhir_server.reset()
```
