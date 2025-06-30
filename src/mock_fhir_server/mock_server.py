"""
Mock FHIR Server for pytest testing

This module provides a mock FHIR server that can be used in pytest fixtures
to simulate FHIR operations including CREATE, READ, and SEARCH operations.
Designed specifically for use with fhir-resources library.
"""

import json
import uuid
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union
import pytest
import requests_mock
from urllib.parse import parse_qs, urlparse

from fhir_core.fhirabstractmodel import FHIRAbstractModel
from fhir.resources import get_fhir_model_class


class MockFHIRResource:
    """Represents a FHIR resource with metadata"""

    def __init__(self, resource_data: Union[Dict[str, Any], FHIRAbstractModel]):
        # Handle fhir-resources model objects
        if isinstance(resource_data, FHIRAbstractModel):
            self.resource_data = resource_data.model_dump()
            self._fhir_model = resource_data
        else:
            # Handle dictionary input
            self.resource_data = resource_data.copy() if isinstance(resource_data, dict) else resource_data
            self._fhir_model = None

        self.resource_type = self.resource_data.get('resourceType')
        self.id = self.resource_data.get('id')
        self.identifier = self.resource_data.get('identifier', [])
        self.created_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        self.version_id = '1'

        # Ensure the resource has an ID
        if not self.id:
            self.id = str(uuid.uuid4())
            self.resource_data['id'] = self.id
            if self._fhir_model and hasattr(self._fhir_model, 'id'):
                self._fhir_model.id = self.id

        # Add FHIR metadata
        meta = {
            'versionId': self.version_id,
            'lastUpdated': self.created_at
        }
        self.resource_data['meta'] = meta

    def as_fhir_model(self):
        """Return the resource as a fhir-resources model object"""
        if self._fhir_model:
            return self._fhir_model

        # Create fhir-resources model from data
        model_class = get_fhir_model_class(self.resource_type)
        return model_class(**self.resource_data)

    def as_dict(self) -> Dict[str, Any]:
        """Return the resource as a dictionary"""
        return self.resource_data


class MockFHIRServer:
    """Mock FHIR server that handles basic FHIR operations"""

    def __init__(self, base_url: str = "http://localhost:8080/fhir"):
        self.base_url = base_url.rstrip('/')
        self.resources: Dict[str, Dict[str, MockFHIRResource]] = {}
        self.requests_mock = None

    def reset(self):
        """Clear all stored resources"""
        self.resources.clear()

    def _get_resource_store(self, resource_type: str) -> Dict[str, MockFHIRResource]:
        """Get or create resource store for a given resource type"""
        if resource_type not in self.resources:
            self.resources[resource_type] = {}
        return self.resources[resource_type]

    def _find_by_identifier(self, resource_type: str, identifier_system: Optional[str],
                           identifier_value: str) -> Optional[MockFHIRResource]:
        """Find a resource by identifier"""
        store = self._get_resource_store(resource_type)

        for resource in store.values():
            for ident in resource.identifier:
                if isinstance(ident, dict):
                    # Check if identifier matches
                    ident_value = ident.get('value')
                    ident_system = ident.get('system')

                    if ident_value == identifier_value:
                        if identifier_system is None or ident_system == identifier_system:
                            return resource
        return None

    def create_resource(self, resource_data: Union[Dict[str, Any], FHIRAbstractModel]) -> Dict[str, Any]:
        """Create a new FHIR resource"""
        resource = MockFHIRResource(resource_data)
        store = self._get_resource_store(resource.resource_type)
        store[resource.id] = resource

        return {
            "resourceType": "OperationOutcome",
            "issue": [{
                "severity": "information",
                "code": "informational",
                "diagnostics": f"Resource {resource.resource_type}/{resource.id} created successfully"
            }],
            "location": f"{self.base_url}/{resource.resource_type}/{resource.id}",
            "created_resource": resource.as_dict(),
            "created": True
        }

    def update_resource(self, resource_type: str, resource_id: str,
                       resource_data: Union[Dict[str, Any], FHIRAbstractModel]) -> Dict[str, Any]:
        """Update an existing FHIR resource"""
        # Ensure the resource data has the correct ID
        if isinstance(resource_data, dict):
            resource_data = resource_data.copy()
            resource_data['id'] = resource_id
        else:
            # fhir-resources model
            resource_data.id = resource_id

        resource = MockFHIRResource(resource_data)
        store = self._get_resource_store(resource_type)

        # Check if resource exists
        exists = resource_id in store
        store[resource_id] = resource

        return {
            "resourceType": "OperationOutcome",
            "issue": [{
                "severity": "information",
                "code": "informational",
                "diagnostics": f"Resource {resource_type}/{resource_id} {'updated' if exists else 'created'} successfully"
            }],
            "location": f"{self.base_url}/{resource_type}/{resource_id}",
            "created_resource": resource.as_dict(),
            "created": not exists
        }

    def conditional_create(self, resource_data: Union[Dict[str, Any], FHIRAbstractModel],
                          if_none_exist: str) -> Dict[str, Any]:
        """Create resource only if none exist matching the search criteria"""
        # Extract resource type
        if isinstance(resource_data, dict):
            resource_type = resource_data.get('resourceType')
        else:
            resource_type = resource_data.resourceType

        # Parse the if-none-exist search parameters
        search_params = self._parse_search_string(if_none_exist)

        # Check if any resources match the search criteria
        existing_resources = self._search_by_params(resource_type, search_params)

        if existing_resources:
            # Resource already exists, return 200 with existing resource
            existing = existing_resources[0]
            return {
                "resourceType": "OperationOutcome",
                "issue": [{
                    "severity": "information",
                    "code": "informational",
                    "diagnostics": f"Resource already exists, not created"
                }],
                "location": f"{self.base_url}/{resource_type}/{existing.id}",
                "created_resource": existing.as_dict(),
                "created": False
            }
        else:
            # No existing resource, create new one
            return self.create_resource(resource_data)

    def conditional_update(self, resource_type: str, resource_data: Union[Dict[str, Any], FHIRAbstractModel],
                          search_criteria: str) -> Dict[str, Any]:
        """Update resource(s) matching search criteria"""
        print(f"DEBUG: conditional_update called with search_criteria: {search_criteria}")
        search_params = self._parse_search_string(search_criteria)
        print(f"DEBUG: parsed search_params: {search_params}")
        existing_resources = self._search_by_params(resource_type, search_params)
        print(f"DEBUG: found {len(existing_resources)} existing resources")

        if not existing_resources:
            # No match found, create new resource
            print("DEBUG: No existing resources found, creating new")
            result = self.create_resource(resource_data)
            result['created'] = True
            return result
        elif len(existing_resources) == 1:
            # Single match, update it
            existing = existing_resources[0]
            print(f"DEBUG: Found 1 existing resource with ID: {existing.id}, updating it")
            result = self.update_resource(resource_type, existing.id, resource_data)
            result['created'] = False  # This was an update, not a create
            print(f"DEBUG: Update result created flag: {result.get('created')}")
            return result
        else:
            # Multiple matches - this should be an error in FHIR
            print(f"DEBUG: Multiple matches found: {len(existing_resources)}")
            return {
                "resourceType": "OperationOutcome",
                "issue": [{
                    "severity": "error",
                    "code": "multiple-matches",
                    "diagnostics": f"Multiple resources match the search criteria: {len(existing_resources)} found"
                }]
            }

    def _parse_search_string(self, search_string: str) -> Dict[str, List[str]]:
        """Parse a search string like 'identifier=system|value&name=Smith' into parameters"""
        params = {}
        if not search_string:
            return params

        for param_pair in search_string.split('&'):
            if '=' in param_pair:
                key, value = param_pair.split('=', 1)
                if key not in params:
                    params[key] = []
                params[key].append(value)
        return params

    def _search_by_params(self, resource_type: str, params: Dict[str, List[str]]) -> List[MockFHIRResource]:
        """Search for resources matching the given parameters"""
        store = self._get_resource_store(resource_type)
        matching_resources = []

        if not params:
            # No search parameters, return all
            return list(store.values())

        for resource in store.values():
            if self._resource_matches_params(resource, params):
                matching_resources.append(resource)

        return matching_resources

    def _resource_matches_params(self, resource: MockFHIRResource, params: Dict[str, List[str]]) -> bool:
        """Check if a resource matches the search parameters"""
        for param_name, param_values in params.items():
            if param_name == 'identifier':
                # Handle identifier search
                if not self._matches_identifier_search(resource, param_values):
                    return False
            # For any other search parameters, just return False (not supported)
            else:
                return False

        return True

    def _matches_identifier_search(self, resource: MockFHIRResource, identifier_values: List[str]) -> bool:
        """Check if resource matches identifier search"""
        for identifier_param in identifier_values:
            # Parse identifier parameter (system|value or just value)
            if '|' in identifier_param:
                system, value = identifier_param.split('|', 1)
            else:
                system, value = None, identifier_param

            for ident in resource.identifier:
                if isinstance(ident, dict):
                    ident_value = ident.get('value')
                    ident_system = ident.get('system')

                    if ident_value == value:
                        if system is None or ident_system == system:
                            return True
        return False

    def process_bundle(self, bundle_data: Union[Dict[str, Any], FHIRAbstractModel]) -> Dict[str, Any]:
        """Process a FHIR Bundle with transaction/batch operations"""
        if isinstance(bundle_data, dict):
            bundle_dict = bundle_data
        else:
            bundle_dict = bundle_data.model_dump()

        bundle_type = bundle_dict.get('type', 'collection')
        entries = bundle_dict.get('entry', [])

        response_entries = []

        for entry in entries:
            request_info = entry.get('request', {})
            resource = entry.get('resource', {})

            method = request_info.get('method', 'GET').upper()
            url = request_info.get('url', '')
            if_none_exist = request_info.get('ifNoneExist')

            try:
                if method == 'POST':
                    if if_none_exist:
                        # Conditional create
                        result = self.conditional_create(resource, if_none_exist)
                        status = "201 Created" if result.get('created', True) else "200 OK"
                    else:
                        # Regular create
                        result = self.create_resource(resource)
                        status = "201 Created"

                    response_entries.append({
                        "response": {
                            "status": status,
                            "location": result.get('location'),
                            "outcome": result
                        }
                    })

                elif method == 'PUT':
                    # Parse URL to get resource type and ID or search criteria
                    url_parts = url.strip('/').split('/')
                    if len(url_parts) >= 2:
                        resource_type = url_parts[0]
                        if '?' in url_parts[1]:
                            # Conditional update
                            search_criteria = url_parts[1].split('?', 1)[1]
                            result = self.conditional_update(resource_type, resource, search_criteria)
                        else:
                            # Regular update
                            resource_id = url_parts[1]
                            result = self.update_resource(resource_type, resource_id, resource)

                        status = "201 Created" if result.get('created', False) else "200 OK"
                        response_entries.append({
                            "response": {
                                "status": status,
                                "location": result.get('location'),
                                "outcome": result
                            }
                        })
                    else:
                        response_entries.append({
                            "response": {
                                "status": "400 Bad Request",
                                "outcome": {
                                    "resourceType": "OperationOutcome",
                                    "issue": [{
                                        "severity": "error",
                                        "code": "invalid",
                                        "diagnostics": f"Invalid URL format: {url}"
                                    }]
                                }
                            }
                        })

                elif method == 'GET':
                    # Handle search within bundle
                    url_parts = url.strip('/').split('/')
                    if len(url_parts) >= 1:
                        if '?' in url_parts[0]:
                            resource_type, query = url_parts[0].split('?', 1)
                            search_params = self._parse_search_string(query)
                            results = self._search_by_params(resource_type, search_params)

                            response_entries.append({
                                "response": {
                                    "status": "200 OK"
                                },
                                "resource": {
                                    "resourceType": "Bundle",
                                    "type": "searchset",
                                    "total": len(results),
                                    "entry": [{"resource": r.as_dict()} for r in results]
                                }
                            })
                        else:
                            response_entries.append({
                                "response": {
                                    "status": "400 Bad Request",
                                    "outcome": {
                                        "resourceType": "OperationOutcome",
                                        "issue": [{
                                            "severity": "error",
                                            "code": "not-supported",
                                            "diagnostics": "GET operations in bundles require search parameters"
                                        }]
                                    }
                                }
                            })
                else:
                    # Unsupported method
                    response_entries.append({
                        "response": {
                            "status": "404 Not Found",
                            "outcome": {
                                "resourceType": "OperationOutcome",
                                "issue": [{
                                    "severity": "error",
                                    "code": "not-supported",
                                    "diagnostics": f"Method {method} not supported"
                                }]
                            }
                        }
                    })

            except Exception as e:
                response_entries.append({
                    "response": {
                        "status": "500 Internal Server Error",
                        "outcome": {
                            "resourceType": "OperationOutcome",
                            "issue": [{
                                "severity": "error",
                                "code": "exception",
                                "diagnostics": f"Error processing entry: {str(e)}"
                            }]
                        }
                    }
                })

        return {
            "resourceType": "Bundle",
            "type": f"{bundle_type}-response",
            "entry": response_entries
        }

    def read_resource(self, resource_type: str, resource_id: str,
                     return_fhir_model: bool = False) -> Optional[Union[Dict[str, Any], FHIRAbstractModel]]:
        """Read a resource by ID"""
        store = self._get_resource_store(resource_type)
        resource = store.get(resource_id)

        if not resource:
            return None

        if return_fhir_model:
            return resource.as_fhir_model()
        else:
            return resource.as_dict()

    def search_resources(self, resource_type: str, params: Dict[str, List[str]],
                        return_fhir_models: bool = False) -> Dict[str, Any]:
        """Search resources with basic parameter support"""
        store = self._get_resource_store(resource_type)
        matching_resources = []

        # Handle identifier search
        if 'identifier' in params:
            identifier_param = params['identifier'][0]

            # Parse identifier parameter (system|value or just value)
            if '|' in identifier_param:
                system, value = identifier_param.split('|', 1)
            else:
                system, value = None, identifier_param

            resource = self._find_by_identifier(resource_type, system, value)
            if resource:
                if return_fhir_models:
                    matching_resources.append(resource.as_fhir_model().model_dump())
                else:
                    matching_resources.append(resource.as_dict())
        else:
            # Return all resources if no specific search parameters
            for resource in store.values():
                if return_fhir_models:
                    matching_resources.append(resource.as_fhir_model().model_dump())
                else:
                    matching_resources.append(resource.as_dict())

        # Create FHIR Bundle response
        return {
            "resourceType": "Bundle",
            "type": "searchset",
            "total": len(matching_resources),
            "entry": [
                {
                    "resource": resource,
                    "fullUrl": f"{self.base_url}/{resource['resourceType']}/{resource['id']}"
                }
                for resource in matching_resources
            ]
        }

    def _handle_request(self, request, context):
        """Handle HTTP requests to the mock server"""
        method = request.method
        url = request.url

        parsed_url = urlparse(url)
        path_parts = [p for p in parsed_url.path.split('/') if p]

        # Remove 'fhir' from path if present
        if path_parts and path_parts[0] == 'fhir':
            path_parts = path_parts[1:]

        try:
            if method == 'POST' and len(path_parts) == 1:
                # Create resource: POST /ResourceType
                resource_type = path_parts[0]

                # Get JSON data from request
                if hasattr(request, 'json') and callable(request.json):
                    resource_data = request.json()
                elif hasattr(request, 'json') and request.json:
                    resource_data = request.json
                elif hasattr(request, 'body') and request.body:
                    resource_data = json.loads(request.body)
                else:
                    resource_data = {}

                # Check for conditional create (If-None-Exist header)
                if_none_exist = request.headers.get('If-None-Exist')
                if if_none_exist:
                    result = self.conditional_create(resource_data, if_none_exist)
                    status_code = 201 if result.get('created', True) else 200
                else:
                    result = self.create_resource(resource_data)
                    status_code = 201

                context.status_code = status_code
                context.headers['Content-Type'] = 'application/fhir+json'
                return result

            elif method == 'POST' and len(path_parts) == 0:
                # Bundle processing: POST /
                if hasattr(request, 'json') and callable(request.json):
                    bundle_data = request.json()
                elif hasattr(request, 'json') and request.json:
                    bundle_data = request.json
                elif hasattr(request, 'body') and request.body:
                    bundle_data = json.loads(request.body)
                else:
                    bundle_data = {}

                result = self.process_bundle(bundle_data)
                context.status_code = 200
                context.headers['Content-Type'] = 'application/fhir+json'
                return result

            elif method == 'PUT' and len(path_parts) >= 1:
                # Update resource: PUT /ResourceType/id or PUT /ResourceType?search
                resource_type = path_parts[0]

                # Get JSON data from request
                if hasattr(request, 'json') and callable(request.json):
                    resource_data = request.json()
                elif hasattr(request, 'json') and request.json:
                    resource_data = request.json
                elif hasattr(request, 'body') and request.body:
                    resource_data = json.loads(request.body)
                else:
                    resource_data = {}

                if len(path_parts) == 2:
                    # Regular update: PUT /ResourceType/id
                    resource_id = path_parts[1]
                    result = self.update_resource(resource_type, resource_id, resource_data)
                    status_code = 201 if result.get('created', False) else 200
                elif parsed_url.query:
                    # Conditional update: PUT /ResourceType?search
                    result = self.conditional_update(resource_type, resource_data, parsed_url.query)
                    # Check if this was actually a create or update
                    if result.get('resourceType') == 'OperationOutcome' and result.get('created') is not None:
                        status_code = 201 if result.get('created', False) else 200
                    else:
                        # Error case
                        status_code = 400
                else:
                    context.status_code = 400
                    error = {
                        "resourceType": "OperationOutcome",
                        "issue": [{
                            "severity": "error",
                            "code": "invalid",
                            "diagnostics": "PUT requests must include resource ID or search parameters"
                        }]
                    }
                    context.headers['Content-Type'] = 'application/fhir+json'
                    return error

                context.status_code = status_code
                context.headers['Content-Type'] = 'application/fhir+json'
                return result

            elif method == 'GET' and len(path_parts) == 2:
                # Read resource: GET /ResourceType/id
                resource_type, resource_id = path_parts
                result = self.read_resource(resource_type, resource_id, return_fhir_model=False)

                if result:
                    context.status_code = 200
                    context.headers['Content-Type'] = 'application/fhir+json'
                    return result
                else:
                    context.status_code = 404
                    error = {
                        "resourceType": "OperationOutcome",
                        "issue": [{
                            "severity": "error",
                            "code": "not-found",
                            "diagnostics": f"Resource {resource_type}/{resource_id} not found"
                        }]
                    }
                    context.headers['Content-Type'] = 'application/fhir+json'
                    return error

            elif method == 'GET' and len(path_parts) == 1:
                # Search resources: GET /ResourceType?params
                resource_type = path_parts[0]
                query_params = parse_qs(parsed_url.query)
                result = self.search_resources(resource_type, query_params, return_fhir_models=False)

                context.status_code = 200
                context.headers['Content-Type'] = 'application/fhir+json'
                return result

        except Exception as e:
            # Return server error
            import traceback
            print(f"Exception in _handle_request: {e}")
            traceback.print_exc()

            error = {
                "resourceType": "OperationOutcome",
                "issue": [{
                    "severity": "error",
                    "code": "exception",
                    "diagnostics": f"Server error: {str(e)}"
                }]
            }
            context.status_code = 500
            context.headers['Content-Type'] = 'application/fhir+json'
            return error

        # Default 404 response
        error = {
            "resourceType": "OperationOutcome",
            "issue": [{
                "severity": "error",
                "code": "not-found",
                "diagnostics": "Endpoint not found"
            }]
        }
        context.status_code = 404
        context.headers['Content-Type'] = 'application/fhir+json'
        return error

    def start_mock(self, requests_mocker):
        """Start the mock server using requests-mock"""
        self.requests_mock = requests_mocker

        # Register handlers for different HTTP methods and patterns
        base_pattern = re.escape(self.base_url)
        requests_mocker.register_uri(
            requests_mock.ANY,
            re.compile(f"^{base_pattern}/.*"),
            json=self._handle_request
        )

    def stop_mock(self):
        """Stop the mock server"""
        if self.requests_mock:
            self.requests_mock.stop()
            self.requests_mock = None


# Pytest fixtures
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