"""
Basic FHIR operations tests - focusing on core CREATE, READ, UPDATE, SEARCH functionality
"""

import pytest
import requests
import sys
import os

# Add the parent directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestBasicCRUDOperations:
    """Test basic Create, Read, Update, Delete operations"""

    def test_create_patient(self, fhir_server_with_requests_mock):
        """Test creating a basic patient resource"""
        server = fhir_server_with_requests_mock

        patient_data = {
            "resourceType": "Patient",
            "name": [{"family": "Smith", "given": ["John"]}],
            "gender": "male",
            "birthDate": "1980-01-01",
        }

        response = requests.post(f"{server.base_url}/Patient", json=patient_data)

        assert response.status_code == 201
        result = response.json()
        assert result["resourceType"] == "OperationOutcome"
        assert "created_resource" in result

        created_patient = result["created_resource"]
        assert created_patient["resourceType"] == "Patient"
        assert created_patient["name"][0]["family"] == "Smith"
        assert "id" in created_patient
        assert "meta" in created_patient

    def test_read_patient_by_id(self, fhir_server_with_requests_mock):
        """Test reading a patient by ID"""
        server = fhir_server_with_requests_mock

        # Create a patient first
        patient_data = {
            "resourceType": "Patient",
            "name": [{"family": "Doe", "given": ["Jane"]}],
            "gender": "female",
        }

        create_response = requests.post(f"{server.base_url}/Patient", json=patient_data)
        patient_id = create_response.json()["created_resource"]["id"]

        # Read the patient back
        read_response = requests.get(f"{server.base_url}/Patient/{patient_id}")

        assert read_response.status_code == 200
        patient = read_response.json()
        assert patient["resourceType"] == "Patient"
        assert patient["id"] == patient_id
        assert patient["name"][0]["family"] == "Doe"
        assert patient["gender"] == "female"

    def test_read_nonexistent_patient(self, fhir_server_with_requests_mock):
        """Test reading a patient that doesn't exist"""
        server = fhir_server_with_requests_mock

        response = requests.get(f"{server.base_url}/Patient/nonexistent-id")

        assert response.status_code == 404
        error = response.json()
        assert error["resourceType"] == "OperationOutcome"
        assert error["issue"][0]["severity"] == "error"
        assert "not found" in error["issue"][0]["diagnostics"].lower()

    def test_update_patient(self, fhir_server_with_requests_mock):
        """Test updating an existing patient"""
        server = fhir_server_with_requests_mock

        # Create initial patient
        initial_patient = {
            "resourceType": "Patient",
            "name": [{"family": "Johnson", "given": ["Bob"]}],
            "gender": "male",
        }

        create_response = requests.post(
            f"{server.base_url}/Patient", json=initial_patient
        )
        patient_id = create_response.json()["created_resource"]["id"]

        # Update the patient
        updated_patient = {
            "resourceType": "Patient",
            "name": [{"family": "Johnson", "given": ["Robert"]}],  # Changed name
            "gender": "male",
            "birthDate": "1975-06-15",  # Added birth date
        }

        update_response = requests.put(
            f"{server.base_url}/Patient/{patient_id}", json=updated_patient
        )

        assert update_response.status_code == 200  # Updated existing
        result = update_response.json()
        assert result["created_resource"]["name"][0]["given"] == ["Robert"]
        assert result["created_resource"]["birthDate"] == "1975-06-15"

        # Verify the update by reading back
        read_response = requests.get(f"{server.base_url}/Patient/{patient_id}")
        patient = read_response.json()
        assert patient["name"][0]["given"] == ["Robert"]
        assert patient["birthDate"] == "1975-06-15"


class TestPatientIdentifiers:
    """Test patient operations with identifiers"""

    def test_create_patient_with_identifier(self, fhir_server_with_requests_mock):
        """Test creating a patient with an identifier"""
        server = fhir_server_with_requests_mock

        patient_data = {
            "resourceType": "Patient",
            "identifier": [{"system": "http://hospital.org/mrn", "value": "MRN12345"}],
            "name": [{"family": "Williams", "given": ["Sarah"]}],
        }

        response = requests.post(f"{server.base_url}/Patient", json=patient_data)

        assert response.status_code == 201
        created_patient = response.json()["created_resource"]
        assert created_patient["identifier"][0]["system"] == "http://hospital.org/mrn"
        assert created_patient["identifier"][0]["value"] == "MRN12345"

    def test_search_patient_by_identifier(self, fhir_server_with_requests_mock):
        """Test searching for a patient by identifier"""
        server = fhir_server_with_requests_mock

        # Create patients with different identifiers
        patients = [
            {
                "resourceType": "Patient",
                "identifier": [
                    {"system": "http://hospital.org/mrn", "value": "MRN001"}
                ],
                "name": [{"family": "Alpha", "given": ["Patient"]}],
            },
            {
                "resourceType": "Patient",
                "identifier": [
                    {"system": "http://hospital.org/mrn", "value": "MRN002"}
                ],
                "name": [{"family": "Beta", "given": ["Patient"]}],
            },
            {
                "resourceType": "Patient",
                "identifier": [{"system": "http://other.org/id", "value": "OTHER001"}],
                "name": [{"family": "Gamma", "given": ["Patient"]}],
            },
        ]

        for patient in patients:
            requests.post(f"{server.base_url}/Patient", json=patient)

        # Search by specific identifier (system + value)
        response = requests.get(
            f"{server.base_url}/Patient?identifier=http://hospital.org/mrn|MRN001"
        )

        assert response.status_code == 200
        bundle = response.json()
        assert bundle["resourceType"] == "Bundle"
        assert bundle["total"] == 1
        assert bundle["entry"][0]["resource"]["name"][0]["family"] == "Alpha"

    def test_search_patient_by_identifier_value_only(
        self, fhir_server_with_requests_mock
    ):
        """Test searching by identifier value without system"""
        server = fhir_server_with_requests_mock

        # Create patient
        patient_data = {
            "resourceType": "Patient",
            "identifier": [{"system": "http://example.org/mrn", "value": "UNIQUE123"}],
            "name": [{"family": "Unique", "given": ["Patient"]}],
        }

        requests.post(f"{server.base_url}/Patient", json=patient_data)

        # Search by value only
        response = requests.get(f"{server.base_url}/Patient?identifier=UNIQUE123")

        assert response.status_code == 200
        bundle = response.json()
        assert bundle["total"] == 1
        assert bundle["entry"][0]["resource"]["name"][0]["family"] == "Unique"


class TestConditionalOperations:
    """Test conditional create and update operations"""

    def test_conditional_create_new_patient(self, fhir_server_with_requests_mock):
        """Test conditional create when patient doesn't exist"""
        server = fhir_server_with_requests_mock

        patient_data = {
            "resourceType": "Patient",
            "identifier": [{"system": "http://hospital.org/mrn", "value": "NEW123"}],
            "name": [{"family": "New", "given": ["Patient"]}],
        }

        response = requests.post(
            f"{server.base_url}/Patient",
            json=patient_data,
            headers={"If-None-Exist": "identifier=http://hospital.org/mrn|NEW123"},
        )

        assert response.status_code == 201  # Created new
        result = response.json()
        assert result["created_resource"]["name"][0]["family"] == "New"

    def test_conditional_create_existing_patient(self, fhir_server_with_requests_mock):
        """Test conditional create when patient already exists"""
        server = fhir_server_with_requests_mock

        # Create initial patient
        initial_patient = {
            "resourceType": "Patient",
            "identifier": [{"system": "http://hospital.org/mrn", "value": "EXISTS123"}],
            "name": [{"family": "Existing", "given": ["Patient"]}],
        }

        create_response = requests.post(
            f"{server.base_url}/Patient", json=initial_patient
        )
        original_id = create_response.json()["created_resource"]["id"]

        # Try to create again with conditional create
        duplicate_patient = {
            "resourceType": "Patient",
            "identifier": [{"system": "http://hospital.org/mrn", "value": "EXISTS123"}],
            "name": [{"family": "Should", "given": ["NotCreate"]}],  # Different name
        }

        response = requests.post(
            f"{server.base_url}/Patient",
            json=duplicate_patient,
            headers={"If-None-Exist": "identifier=http://hospital.org/mrn|EXISTS123"},
        )

        assert response.status_code == 200  # Found existing, not created
        result = response.json()
        assert result["created_resource"]["id"] == original_id  # Same patient
        assert (
            result["created_resource"]["name"][0]["family"] == "Existing"
        )  # Original name

    def test_conditional_update_existing_patient(self, fhir_server_with_requests_mock):
        """Test conditional update when patient exists"""
        server = fhir_server_with_requests_mock

        # Create initial patient
        initial_patient = {
            "resourceType": "Patient",
            "identifier": [{"system": "http://hospital.org/mrn", "value": "UPDATE123"}],
            "name": [{"family": "Before", "given": ["Update"]}],
        }

        create_response = requests.post(
            f"{server.base_url}/Patient", json=initial_patient
        )
        original_id = create_response.json()["created_resource"]["id"]

        # Update via conditional update
        updated_patient = {
            "resourceType": "Patient",
            "identifier": [{"system": "http://hospital.org/mrn", "value": "UPDATE123"}],
            "name": [{"family": "After", "given": ["Update"]}],
            "gender": "unknown",
        }

        response = requests.put(
            f"{server.base_url}/Patient?identifier=http://hospital.org/mrn|UPDATE123",
            json=updated_patient,
        )

        assert response.status_code == 200  # Updated existing
        result = response.json()
        assert result["created_resource"]["id"] == original_id  # Same ID
        assert result["created_resource"]["name"][0]["family"] == "After"
        assert result["created_resource"]["gender"] == "unknown"

    def test_conditional_update_nonexistent_patient(
        self, fhir_server_with_requests_mock
    ):
        """Test conditional update when patient doesn't exist"""
        server = fhir_server_with_requests_mock

        new_patient = {
            "resourceType": "Patient",
            "identifier": [
                {"system": "http://hospital.org/mrn", "value": "NEWUPDATE123"}
            ],
            "name": [{"family": "Created", "given": ["ByUpdate"]}],
        }

        response = requests.put(
            f"{server.base_url}/Patient?identifier=http://hospital.org/mrn|NEWUPDATE123",
            json=new_patient,
        )

        assert response.status_code == 201  # Created new
        result = response.json()
        assert result["created_resource"]["name"][0]["family"] == "Created"


class TestMultipleResourceTypes:
    """Test operations with different FHIR resource types"""

    def test_create_observation(self, fhir_server_with_requests_mock):
        """Test creating an Observation resource"""
        server = fhir_server_with_requests_mock

        observation_data = {
            "resourceType": "Observation",
            "status": "final",
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": "8867-4",
                        "display": "Heart rate",
                    }
                ]
            },
            "valueQuantity": {
                "value": 72,
                "unit": "beats/minute",
                "system": "http://unitsofmeasure.org",
                "code": "/min",
            },
        }

        response = requests.post(
            f"{server.base_url}/Observation", json=observation_data
        )

        assert response.status_code == 201
        created_obs = response.json()["created_resource"]
        assert created_obs["resourceType"] == "Observation"
        assert created_obs["status"] == "final"
        assert created_obs["valueQuantity"]["value"] == 72

    def test_create_practitioner(self, fhir_server_with_requests_mock):
        """Test creating a Practitioner resource"""
        server = fhir_server_with_requests_mock

        practitioner_data = {
            "resourceType": "Practitioner",
            "identifier": [
                {"system": "http://hospital.org/practitioners", "value": "PRAC001"}
            ],
            "name": [{"family": "House", "given": ["Gregory"], "prefix": ["Dr."]}],
            "qualification": [
                {
                    "code": {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/v2-0360",
                                "code": "MD",
                                "display": "Doctor of Medicine",
                            }
                        ]
                    }
                }
            ],
        }

        response = requests.post(
            f"{server.base_url}/Practitioner", json=practitioner_data
        )

        assert response.status_code == 201
        created_prac = response.json()["created_resource"]
        assert created_prac["resourceType"] == "Practitioner"
        assert created_prac["name"][0]["family"] == "House"
        assert created_prac["identifier"][0]["value"] == "PRAC001"


class TestSearchOperations:
    """Test various search operations"""

    def test_search_all_patients(self, fhir_server_with_requests_mock):
        """Test searching for all patients (no parameters)"""
        server = fhir_server_with_requests_mock

        # Create multiple patients
        patients = [
            {"resourceType": "Patient", "name": [{"family": "Patient1"}]},
            {"resourceType": "Patient", "name": [{"family": "Patient2"}]},
            {"resourceType": "Patient", "name": [{"family": "Patient3"}]},
        ]

        for patient in patients:
            requests.post(f"{server.base_url}/Patient", json=patient)

        # Search all patients
        response = requests.get(f"{server.base_url}/Patient")

        assert response.status_code == 200
        bundle = response.json()
        assert bundle["resourceType"] == "Bundle"
        assert bundle["type"] == "searchset"
        assert bundle["total"] == 3
        assert len(bundle["entry"]) == 3

    def test_search_empty_results(self, fhir_server_with_requests_mock):
        """Test search that returns no results"""
        server = fhir_server_with_requests_mock

        response = requests.get(f"{server.base_url}/Patient?identifier=nonexistent")

        assert response.status_code == 200
        bundle = response.json()
        assert bundle["total"] == 0
        assert len(bundle["entry"]) == 0

    def test_mixed_resource_types(self, fhir_server_with_requests_mock):
        """Test that searches are scoped to resource type"""
        server = fhir_server_with_requests_mock

        # Create patients and observations
        patient_data = {"resourceType": "Patient", "name": [{"family": "TestPatient"}]}
        obs_data = {"resourceType": "Observation", "status": "final"}

        requests.post(f"{server.base_url}/Patient", json=patient_data)
        requests.post(f"{server.base_url}/Observation", json=obs_data)

        # Search patients should only return patients
        patient_response = requests.get(f"{server.base_url}/Patient")
        patient_bundle = patient_response.json()
        assert patient_bundle["total"] == 1
        assert patient_bundle["entry"][0]["resource"]["resourceType"] == "Patient"

        # Search observations should only return observations
        obs_response = requests.get(f"{server.base_url}/Observation")
        obs_bundle = obs_response.json()
        assert obs_bundle["total"] == 1
        assert obs_bundle["entry"][0]["resource"]["resourceType"] == "Observation"


class TestFhirResourcesIntegration:
    """Test integration with fhir-resources library"""

    @pytest.mark.fhir_resources
    def test_create_with_fhir_resources_model(self, fhir_server_with_requests_mock):
        """Test creating resources using fhir-resources models"""
        pytest.importorskip("fhir.resources")
        from fhir.resources.patient import Patient
        from fhir.resources.humanname import HumanName
        from fhir.resources.identifier import Identifier

        server = fhir_server_with_requests_mock

        # Create patient using fhir-resources models
        patient = Patient(
            identifier=[Identifier(system="http://example.org/mrn", value="FHIR123")],
            name=[HumanName(family="Model", given=["FHIR"])],
        )

        response = requests.post(
            f"{server.base_url}/Patient", json=patient.model_dump()
        )

        assert response.status_code == 201
        created_patient = response.json()["created_resource"]
        assert created_patient["name"][0]["family"] == "Model"
        assert created_patient["identifier"][0]["value"] == "FHIR123"

        # Parse the response back into a model to verify structure
        retrieved_patient = Patient(**created_patient)
        assert retrieved_patient.name[0].family == "Model"
        assert retrieved_patient.identifier[0].value == "FHIR123"

    @pytest.mark.fhir_resources
    def test_direct_model_storage(self, mock_fhir_server):
        """Test storing fhir-resources models directly in server"""
        pytest.importorskip("fhir.resources")
        from fhir.resources.patient import Patient
        from fhir.resources.humanname import HumanName

        server = mock_fhir_server

        patient = Patient(name=[HumanName(family="Direct", given=["Storage"])])

        # Store directly without HTTP
        result = server.create_resource(patient)
        patient_id = result["created_resource"]["id"]

        # Read back as dict
        retrieved_dict = server.read_resource("Patient", patient_id)
        assert retrieved_dict["name"][0]["family"] == "Direct"

        # Read back as fhir-resources model
        retrieved_model = server.read_resource(
            "Patient", patient_id, return_fhir_model=True
        )
        assert isinstance(retrieved_model, Patient)
        assert retrieved_model.name[0].family == "Direct"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
