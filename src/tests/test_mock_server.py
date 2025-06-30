"""
Tests for advanced FHIR operations: conditional creates, updates, and bundle processing
"""

import pytest
import requests
import sys
import os

# Add the parent directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestConditionalOperations:
    """Test conditional FHIR operations"""

    def test_conditional_create_with_if_none_exist(self, fhir_server_with_requests_mock):
        """Test conditional create using If-None-Exist header"""
        server = fhir_server_with_requests_mock

        patient_data = {
            "resourceType": "Patient",
            "identifier": [{
                "system": "http://example.org/mrn",
                "value": "12345"
            }],
            "name": [{"family": "Smith", "given": ["John"]}]
        }

        # First create should succeed
        response = requests.post(
            f"{server.base_url}/Patient",
            json=patient_data,
            headers={'If-None-Exist': 'identifier=http://example.org/mrn|12345'}
        )
        assert response.status_code == 201
        first_result = response.json()

        # Second create with same identifier should return existing
        response = requests.post(
            f"{server.base_url}/Patient",
            json=patient_data,
            headers={'If-None-Exist': 'identifier=http://example.org/mrn|12345'}
        )
        assert response.status_code == 200  # Not created, existing returned
        second_result = response.json()

        # Should reference the same resource
        assert first_result['created_resource']['id'] == second_result['created_resource']['id']

    def test_conditional_update(self, fhir_server_with_requests_mock):
        """Test conditional update operations"""
        server = fhir_server_with_requests_mock

        # Create initial patient
        initial_patient = {
            "resourceType": "Patient",
            "identifier": [{
                "system": "http://example.org/mrn",
                "value": "12345"
            }],
            "name": [{"family": "Smith", "given": ["John"]}]
        }

        response = requests.post(f"{server.base_url}/Patient", json=initial_patient)
        assert response.status_code == 201
        print(f"Initial create: {response.status_code}")

        # Update using conditional PUT
        updated_patient = {
            "resourceType": "Patient",
            "identifier": [{
                "system": "http://example.org/mrn",
                "value": "12345"
            }],
            "name": [{"family": "Smith", "given": ["John", "Michael"]}],
            "gender": "male"
        }

        response = requests.put(
            f"{server.base_url}/Patient?identifier=http://example.org/mrn|12345",
            json=updated_patient
        )
        print(f"Update response: {response.status_code}")
        print(f"Update result: {response.json()}")
        assert response.status_code == 200  # Updated existing

        # Verify the update
        result = response.json()
        patient_id = result['created_resource']['id']

        get_response = requests.get(f"{server.base_url}/Patient/{patient_id}")
        assert get_response.status_code == 200
        patient = get_response.json()
        assert patient['name'][0]['given'] == ["John", "Michael"]
        assert patient['gender'] == "male"

    def test_regular_update(self, fhir_server_with_requests_mock):
        """Test regular PUT update with resource ID"""
        server = fhir_server_with_requests_mock

        # Create patient
        patient_data = {
            "resourceType": "Patient",
            "name": [{"family": "Doe", "given": ["Jane"]}]
        }

        response = requests.post(f"{server.base_url}/Patient", json=patient_data)
        assert response.status_code == 201
        patient_id = response.json()['created_resource']['id']

        # Update with PUT
        updated_data = {
            "resourceType": "Patient",
            "name": [{"family": "Doe", "given": ["Jane", "Marie"]}],
            "gender": "female"
        }

        response = requests.put(f"{server.base_url}/Patient/{patient_id}", json=updated_data)
        assert response.status_code == 200

        # Verify update
        get_response = requests.get(f"{server.base_url}/Patient/{patient_id}")
        patient = get_response.json()
        assert patient['name'][0]['given'] == ["Jane", "Marie"]
        assert patient['gender'] == "female"


class TestBundleOperations:
    """Test FHIR Bundle processing"""

    def test_transaction_bundle_with_creates(self, fhir_server_with_requests_mock):
        """Test processing a transaction bundle with POST operations"""
        server = fhir_server_with_requests_mock

        bundle = {
            "resourceType": "Bundle",
            "type": "transaction",
            "entry": [
                {
                    "request": {
                        "method": "POST",
                        "url": "Patient"
                    },
                    "resource": {
                        "resourceType": "Patient",
                        "name": [{"family": "Smith", "given": ["John"]}]
                    }
                },
                {
                    "request": {
                        "method": "POST",
                        "url": "Patient"
                    },
                    "resource": {
                        "resourceType": "Patient",
                        "name": [{"family": "Doe", "given": ["Jane"]}]
                    }
                }
            ]
        }

        response = requests.post(f"{server.base_url}/", json=bundle)
        assert response.status_code == 200

        result = response.json()
        assert result['resourceType'] == 'Bundle'
        assert result['type'] == 'transaction-response'
        assert len(result['entry']) == 2

        # Check both entries were created successfully
        for entry in result['entry']:
            assert entry['response']['status'] == '201 Created'
            assert 'location' in entry['response']

    def test_bundle_with_conditional_creates(self, fhir_server_with_requests_mock):
        """Test bundle with conditional creates using ifNoneExist"""
        server = fhir_server_with_requests_mock

        bundle = {
            "resourceType": "Bundle",
            "type": "transaction",
            "entry": [
                {
                    "request": {
                        "method": "POST",
                        "url": "Patient",
                        "ifNoneExist": "identifier=http://example.org/mrn|12345"
                    },
                    "resource": {
                        "resourceType": "Patient",
                        "identifier": [{
                            "system": "http://example.org/mrn",
                            "value": "12345"
                        }],
                        "name": [{"family": "Smith", "given": ["John"]}]
                    }
                },
                {
                    "request": {
                        "method": "POST",
                        "url": "Patient",
                        "ifNoneExist": "identifier=http://example.org/mrn|12345"
                    },
                    "resource": {
                        "resourceType": "Patient",
                        "identifier": [{
                            "system": "http://example.org/mrn",
                            "value": "12345"
                        }],
                        "name": [{"family": "Smith", "given": ["John", "Michael"]}]
                    }
                }
            ]
        }

        response = requests.post(f"{server.base_url}/", json=bundle)
        assert response.status_code == 200

        result = response.json()
        assert len(result['entry']) == 2

        # First should be created, second should return existing
        assert result['entry'][0]['response']['status'] == '201 Created'
        assert result['entry'][1]['response']['status'] == '200 OK'

    def test_bundle_with_updates(self, fhir_server_with_requests_mock):
        """Test bundle with PUT operations"""
        server = fhir_server_with_requests_mock

        # First create a patient to update later
        patient = {
            "resourceType": "Patient",
            "identifier": [{
                "system": "http://example.org/mrn",
                "value": "54321"
            }],
            "name": [{"family": "Brown", "given": ["Bob"]}]
        }

        create_response = requests.post(f"{server.base_url}/Patient", json=patient)
        patient_id = create_response.json()['created_resource']['id']

        # Now create a bundle that updates this patient
        bundle = {
            "resourceType": "Bundle",
            "type": "transaction",
            "entry": [
                {
                    "request": {
                        "method": "PUT",
                        "url": f"Patient/{patient_id}"
                    },
                    "resource": {
                        "resourceType": "Patient",
                        "identifier": [{
                            "system": "http://example.org/mrn",
                            "value": "54321"
                        }],
                        "name": [{"family": "Brown", "given": ["Robert"]}],
                        "gender": "male"
                    }
                },
                {
                    "request": {
                        "method": "PUT",
                        "url": "Patient?identifier=http://example.org/mrn|99999"
                    },
                    "resource": {
                        "resourceType": "Patient",
                        "identifier": [{
                            "system": "http://example.org/mrn",
                            "value": "99999"
                        }],
                        "name": [{"family": "Wilson", "given": ["William"]}]
                    }
                }
            ]
        }

        response = requests.post(f"{server.base_url}/", json=bundle)
        assert response.status_code == 200

        result = response.json()
        assert len(result['entry']) == 2

        # First should be an update (200), second should be a create (201)
        assert result['entry'][0]['response']['status'] == '200 OK'
        assert result['entry'][1]['response']['status'] == '201 Created'

        # Verify the update worked
        get_response = requests.get(f"{server.base_url}/Patient/{patient_id}")
        updated_patient = get_response.json()
        assert updated_patient['name'][0]['given'] == ["Robert"]
        assert updated_patient['gender'] == "male"

    def test_bundle_with_mixed_operations(self, fhir_server_with_requests_mock):
        """Test bundle with mix of different operations"""
        server = fhir_server_with_requests_mock

        # Create some initial data
        initial_patient = {
            "resourceType": "Patient",
            "identifier": [{"system": "http://example.org/mrn", "value": "11111"}],
            "name": [{"family": "Initial", "given": ["Patient"]}]
        }
        requests.post(f"{server.base_url}/Patient", json=initial_patient)

        # Complex bundle with multiple operation types
        bundle = {
            "resourceType": "Bundle",
            "type": "transaction",
            "entry": [
                # Conditional create - should find existing
                {
                    "request": {
                        "method": "POST",
                        "url": "Patient",
                        "ifNoneExist": "identifier=http://example.org/mrn|11111"
                    },
                    "resource": {
                        "resourceType": "Patient",
                        "identifier": [{"system": "http://example.org/mrn", "value": "11111"}],
                        "name": [{"family": "Should", "given": ["NotCreate"]}]
                    }
                },
                # Regular create - should create new
                {
                    "request": {
                        "method": "POST",
                        "url": "Patient"
                    },
                    "resource": {
                        "resourceType": "Patient",
                        "name": [{"family": "New", "given": ["Patient"]}]
                    }
                },
                # Conditional update - should update existing
                {
                    "request": {
                        "method": "PUT",
                        "url": "Patient?identifier=http://example.org/mrn|11111"
                    },
                    "resource": {
                        "resourceType": "Patient",
                        "identifier": [{"system": "http://example.org/mrn", "value": "11111"}],
                        "name": [{"family": "Updated", "given": ["Patient"]}],
                        "gender": "unknown"
                    }
                }
            ]
        }

        response = requests.post(f"{server.base_url}/", json=bundle)
        assert response.status_code == 200

        result = response.json()
        assert len(result['entry']) == 3

        # Conditional create should return existing (200)
        assert result['entry'][0]['response']['status'] == '200 OK'
        # Regular create should create new (201)
        assert result['entry'][1]['response']['status'] == '201 Created'
        # Conditional update should update existing (200)
        assert result['entry'][2]['response']['status'] == '200 OK'


class TestAdvancedSearching:
    """Test advanced search capabilities"""

    def test_search_with_multiple_identifiers(self, fhir_server_with_requests_mock):
        """Test searching with multiple identifier systems"""
        server = fhir_server_with_requests_mock

        # Create patients with different identifier systems
        patients = [
            {
                "resourceType": "Patient",
                "identifier": [
                    {"system": "http://example.org/mrn", "value": "MRN123"},
                    {"system": "http://example.org/ssn", "value": "SSN456"}
                ],
                "name": [{"family": "MultiID", "given": ["Patient1"]}]
            },
            {
                "resourceType": "Patient",
                "identifier": [
                    {"system": "http://example.org/mrn", "value": "MRN789"}
                ],
                "name": [{"family": "SingleID", "given": ["Patient2"]}]
            }
        ]

        for patient in patients:
            requests.post(f"{server.base_url}/Patient", json=patient)

        # Search by MRN system
        response = requests.get(f"{server.base_url}/Patient?identifier=http://example.org/mrn|MRN123")
        assert response.status_code == 200
        bundle = response.json()
        assert bundle['total'] == 1
        assert bundle['entry'][0]['resource']['name'][0]['given'] == ["Patient1"]

        # Search by SSN system
        response = requests.get(f"{server.base_url}/Patient?identifier=http://example.org/ssn|SSN456")
        assert response.status_code == 200
        bundle = response.json()
        assert bundle['total'] == 1
        assert bundle['entry'][0]['resource']['name'][0]['given'] == ["Patient1"]


class TestErrorHandling:
    """Test error handling in advanced operations"""

    def test_conditional_update_multiple_matches(self, mock_fhir_server):
        """Test conditional update when multiple resources match"""
        server = mock_fhir_server

        # Create two patients with same family name
        patients = [
            {
                "resourceType": "Patient",
                "name": [{"family": "Duplicate", "given": ["First"]}]
            },
            {
                "resourceType": "Patient",
                "name": [{"family": "Duplicate", "given": ["Second"]}]
            }
        ]

        for patient in patients:
            server.create_resource(patient)

        # Try conditional update - should fail with multiple matches
        update_data = {
            "resourceType": "Patient",
            "name": [{"family": "Duplicate", "given": ["Updated"]}]
        }

        result = server.conditional_update("Patient", update_data, "name=Duplicate")
        assert result['resourceType'] == 'OperationOutcome'
        assert result['issue'][0]['code'] == 'multiple-matches'

    def test_bundle_with_invalid_operations(self, fhir_server_with_requests_mock):
        """Test bundle with invalid operations"""
        server = fhir_server_with_requests_mock

        bundle = {
            "resourceType": "Bundle",
            "type": "transaction",
            "entry": [
                {
                    "request": {
                        "method": "PUT",
                        "url": "InvalidURL"  # Missing resource type/ID
                    },
                    "resource": {
                        "resourceType": "Patient",
                        "name": [{"family": "Test"}]
                    }
                },
                {
                    "request": {
                        "method": "DELETE",  # Unsupported method
                        "url": "Patient/123"
                    },
                    "resource": {
                        "resourceType": "Patient",
                        "name": [{"family": "ToDelete"}]
                    }
                }
            ]
        }

        response = requests.post(f"{server.base_url}/", json=bundle)
        assert response.status_code == 200

        result = response.json()
        assert len(result['entry']) == 2

        # First should be 400 Bad Request (invalid URL)
        assert '400' in result['entry'][0]['response']['status']
        # Second should be 404 Not Found (unsupported method)
        assert '404' in result['entry'][1]['response']['status']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])