"""
Mock FHIR Server for pytest testing

This module provides a mock FHIR server that can be used in pytest fixtures
to simulate FHIR operations including CREATE, READ, and SEARCH operations.
Designed specifically for use with fhir-resources library.
"""

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from urllib.parse import parse_qs, unquote, urlparse

import requests_mock
from fhir.resources import get_fhir_model_class
from fhir_core.fhirabstractmodel import FHIRAbstractModel


class MockFHIRResource:
    """Represents a FHIR resource with metadata"""

    def __init__(
        self, resource_data: Union[Dict[str, Any], FHIRAbstractModel]
    ) -> None:  # Handle fhir-resources model objects
        if isinstance(resource_data, FHIRAbstractModel):
            self.resource_data = resource_data.model_dump()
            self._fhir_model = resource_data
        else:
            # Handle dictionary input
            self.resource_data = (
                resource_data.copy()
                if isinstance(resource_data, dict)
                else resource_data
            )
            self._fhir_model = None

        self.resource_type = self.resource_data.get("resourceType")
        self.id = self.resource_data.get("id")
        self.identifier = self.resource_data.get("identifier", [])
        self.created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.version_id = "1"

        # Ensure the resource has an ID
        if not self.id:
            self.id = str(uuid.uuid4())
            self.resource_data["id"] = self.id
            if self._fhir_model and hasattr(self._fhir_model, "id"):
                self._fhir_model.id = self.id

        # Add FHIR metadata
        meta = {"versionId": self.version_id, "lastUpdated": self.created_at}
        self.resource_data["meta"] = meta

    def as_fhir_model(self) -> FHIRAbstractModel:
        """Return the resource as a fhir-resources model object"""
        if self._fhir_model:
            return self._fhir_model

        # Create fhir-resources model from data
        model_class = get_fhir_model_class(self.resource_type)
        return model_class(**self.resource_data)

    def as_dict(self) -> Dict[str, Any]:
        """Return the resource as a dictionary"""
        return self.resource_data  # type: ignore


class MockFHIRServer:
    """Mock FHIR server that handles basic FHIR operations"""

    def __init__(self, base_url: str = "http://localhost:8080/fhir") -> None:
        self.base_url = base_url.rstrip("/")
        self.resources: Dict[str, Dict[str, MockFHIRResource]] = {}
        self.requests_mock = None

    def reset(self) -> None:
        """Clear all stored resources"""
        self.resources.clear()

    def _get_resource_store(self, resource_type: str) -> Dict[str, MockFHIRResource]:
        """Get or create resource store for a given resource type"""
        if resource_type not in self.resources:
            self.resources[resource_type] = {}
        return self.resources[resource_type]

    @staticmethod
    def _parse_search_string(search_string: str) -> Dict[str, List[str]]:
        """Parse a search string like 'identifier=system|value&name=Smith' into
        parameters"""
        params: Dict[str, List[str]] = {}
        if not search_string:
            return params

        # URL decode the search string first
        search_string = unquote(search_string)

        for param_pair in search_string.split("&"):
            if "=" in param_pair:
                key, value = param_pair.split("=", 1)
                if key not in params:
                    params[key] = []
                params[key].append(value)
        return params

    def _search_by_params(
        self, resource_type: str, params: Dict[str, List[str]]
    ) -> List[MockFHIRResource]:
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

    def _resource_matches_params(
        self, resource: MockFHIRResource, params: Dict[str, List[str]]
    ) -> bool:
        """Check if a resource matches the search parameters"""
        for param_name, param_values in params.items():
            if param_name == "identifier":
                # Handle identifier search
                if not self._matches_identifier_search(resource, param_values):
                    return False
            # For any other search parameters, just return False (not supported)
            else:
                return False

        return True

    @staticmethod
    def _matches_identifier_search(
        resource: MockFHIRResource, identifier_values: List[str]
    ) -> bool:
        """Check if resource matches identifier search"""
        for identifier_param in identifier_values:
            # Parse identifier parameter (system|value or just value)
            if "|" in identifier_param:
                system, value = identifier_param.split("|", 1)
            else:
                system, value = None, identifier_param

            for ident in resource.identifier:
                if isinstance(ident, dict):
                    ident_value = ident.get("value")
                    ident_system = ident.get("system")

                    if ident_value == value:
                        if system is None or ident_system == system:
                            return True
        return False

    def create_resource(
        self, resource_data: Union[Dict[str, Any], FHIRAbstractModel]
    ) -> Dict[str, Any]:
        """Create a new FHIR resource"""
        resource = MockFHIRResource(resource_data)
        store = self._get_resource_store(resource.resource_type)
        store[resource.id] = resource

        return {
            "resourceType": "OperationOutcome",
            "issue": [
                {
                    "severity": "information",
                    "code": "informational",
                    "diagnostics": (
                        f"Resource {resource.resource_type}/{resource.id} ",
                        "created successfully",
                    ),
                }
            ],
            "location": f"{self.base_url}/{resource.resource_type}/{resource.id}",
            "created_resource": resource.as_dict(),
            "created": True,
        }

    def update_resource(
        self,
        resource_type: str,
        resource_id: str,
        resource_data: Union[Dict[str, Any], FHIRAbstractModel],
    ) -> Dict[str, Any]:
        """Update an existing FHIR resource"""
        # Ensure the resource data has the correct ID
        if isinstance(resource_data, dict):
            resource_data = resource_data.copy()
            resource_data["id"] = resource_id
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
            "issue": [
                {
                    "severity": "information",
                    "code": "informational",
                    "diagnostics": (
                        f"Resource {resource_type}/{resource_id}",
                        f"{'updated' if exists else 'created'} successfully",
                    ),
                }
            ],
            "location": f"{self.base_url}/{resource_type}/{resource_id}",
            "created_resource": resource.as_dict(),
            "created": not exists,
        }

    def conditional_create(
        self,
        resource_data: Union[Dict[str, Any], FHIRAbstractModel],
        if_none_exist: str,
    ) -> Dict[str, Any]:
        """Create resource only if none exist matching the search criteria"""
        # Extract resource type
        if isinstance(resource_data, dict):
            resource_type: str = resource_data.get("resourceType")  # type: ignore
        else:
            resource_type: str = resource_data.resourceType  # type: ignore

        # Parse the if-none-exist search parameters
        search_params = self._parse_search_string(if_none_exist)

        # Check if any resources match the search criteria
        existing_resources = self._search_by_params(resource_type, search_params)

        if existing_resources:
            # Resource already exists, return 200 with existing resource
            existing = existing_resources[0]
            return {
                "resourceType": "OperationOutcome",
                "issue": [
                    {
                        "severity": "information",
                        "code": "informational",
                        "diagnostics": "Resource already exists, not created",
                    }
                ],
                "location": f"{self.base_url}/{resource_type}/{existing.id}",
                "created_resource": existing.as_dict(),
                "created": False,
            }
        else:
            # No existing resource, create new one
            return self.create_resource(resource_data)

    def conditional_update(
        self,
        resource_type: str,
        resource_data: Union[Dict[str, Any], FHIRAbstractModel],
        search_criteria: str,
    ) -> Dict[str, Any]:
        """Update resource(s) matching search criteria"""
        search_params = self._parse_search_string(search_criteria)
        existing_resources = self._search_by_params(resource_type, search_params)

        if not existing_resources:
            # No match found, create new resource
            result = self.create_resource(resource_data)
            result["created"] = True
            return result
        elif len(existing_resources) == 1:
            # Single match, update it
            existing = existing_resources[0]
            result = self.update_resource(resource_type, existing.id, resource_data)
            result["created"] = False  # This was an update, not a create
            return result
        else:
            # Multiple matches - this should be an error in FHIR
            return {
                "resourceType": "OperationOutcome",
                "issue": [
                    {
                        "severity": "error",
                        "code": "multiple-matches",
                        "diagnostics": (
                            "Multiple resources match the search criteria:",
                            f"{len(existing_resources)} found",
                        ),
                    }
                ],
            }

    def read_resource(
        self, resource_type: str, resource_id: str, return_fhir_model: bool = False
    ) -> Optional[Union[Dict[str, Any], FHIRAbstractModel]]:
        """Read a resource by ID"""
        store = self._get_resource_store(resource_type)
        resource = store.get(resource_id)

        if not resource:
            return None

        if return_fhir_model:
            return resource.as_fhir_model()
        else:
            return resource.as_dict()

    def search_resources(
        self,
        resource_type: str,
        params: Dict[str, List[str]],
        return_fhir_models: bool = False,
    ) -> Dict[str, Any]:
        """Search resources with basic parameter support"""
        store = self._get_resource_store(resource_type)

        if not params:
            # No search parameters, return all resources
            matching_resources = list(store.values())
        else:
            # Use the internal search method
            matching_resources = self._search_by_params(resource_type, params)

        # Convert to appropriate format
        result_resources = []
        for resource in matching_resources:
            if return_fhir_models:
                try:
                    result_resources.append(resource.as_fhir_model().model_dump())
                except (ImportError, ValueError):
                    result_resources.append(resource.as_dict())
            else:
                result_resources.append(resource.as_dict())

        # Create FHIR Bundle response
        return {
            "resourceType": "Bundle",
            "type": "searchset",
            "total": len(result_resources),
            "entry": [
                {
                    "resource": resource,
                    "fullUrl": (
                        f"{self.base_url}/{resource['resourceType']}",
                        f"/{resource['id']}",
                    ),
                }
                for resource in result_resources
            ],
        }

    def process_bundle(
        self, bundle_data: Union[Dict[str, Any], FHIRAbstractModel]
    ) -> Dict[str, Any]:
        """Process a FHIR Bundle with transaction/batch operations"""
        if isinstance(bundle_data, dict):
            bundle_dict = bundle_data
        else:
            bundle_dict = bundle_data.model_dump()

        bundle_type = bundle_dict.get("type", "collection")
        entries = bundle_dict.get("entry", [])

        response_entries = []

        for entry in entries:
            request_info = entry.get("request", {})
            resource = entry.get("resource", {})

            method = request_info.get("method", "GET").upper()
            url = request_info.get("url", "")
            if_none_exist = request_info.get("ifNoneExist")

            try:
                if method == "POST":
                    if if_none_exist:
                        # Conditional create
                        result = self.conditional_create(resource, if_none_exist)
                        status = (
                            "201 Created" if result.get("created", True) else "200 OK"
                        )
                    else:
                        # Regular create
                        result = self.create_resource(resource)
                        status = "201 Created"

                    response_entries.append(
                        {
                            "response": {
                                "status": status,
                                "location": result.get("location"),
                                "outcome": result,
                            }
                        }
                    )

                elif method == "PUT":
                    # Parse URL to get resource type and ID or search criteria
                    url_parts = url.strip("/").split("/")
                    if len(url_parts) >= 1:
                        resource_type = url_parts[0]
                        if "?" in url:
                            # Conditional update - extract search criteria
                            search_criteria = url.split("?", 1)[1]
                            result = self.conditional_update(
                                resource_type, resource, search_criteria
                            )
                        elif len(url_parts) >= 2:
                            # Regular update
                            resource_id = url_parts[1]
                            result = self.update_resource(
                                resource_type, resource_id, resource
                            )
                        else:
                            # Invalid URL format
                            response_entries.append(
                                {
                                    "response": {
                                        "status": "400 Bad Request",
                                        "outcome": {
                                            "resourceType": "OperationOutcome",
                                            "issue": [
                                                {
                                                    "severity": "error",
                                                    "code": "invalid",
                                                    "diagnostics": (
                                                        "Invalid URL ",
                                                        f"format: {url}",
                                                    ),
                                                }
                                            ],
                                        },
                                    }
                                }
                            )
                            continue

                        status = (
                            "201 Created" if result.get("created", False) else "200 OK"
                        )
                        response_entries.append(
                            {
                                "response": {
                                    "status": status,
                                    "location": result.get("location"),
                                    "outcome": result,
                                }
                            }
                        )
                    else:
                        # Invalid URL format - no resource type
                        response_entries.append(
                            {
                                "response": {
                                    "status": "400 Bad Request",
                                    "outcome": {
                                        "resourceType": "OperationOutcome",
                                        "issue": [
                                            {
                                                "severity": "error",
                                                "code": "invalid",
                                                "diagnostics": (
                                                    "Invalid URL format:",
                                                    f"{url}",
                                                ),
                                            }
                                        ],
                                    },
                                }
                            }
                        )

                else:
                    # Unsupported method
                    response_entries.append(
                        {
                            "response": {
                                "status": "404 Not Found",
                                "outcome": {
                                    "resourceType": "OperationOutcome",
                                    "issue": [
                                        {
                                            "severity": "error",
                                            "code": "not-supported",
                                            "diagnostics": (
                                                f"Method {method} not ",
                                                "supported",
                                            ),
                                        }
                                    ],
                                },
                            }
                        }
                    )

            except Exception as e:
                response_entries.append(
                    {
                        "response": {
                            "status": "500 Internal Server Error",
                            "outcome": {
                                "resourceType": "OperationOutcome",
                                "issue": [
                                    {
                                        "severity": "error",
                                        "code": "exception",
                                        "diagnostics": (
                                            "Error processing entry:",
                                            f"{str(e)}",
                                        ),
                                    }
                                ],
                            },
                        }
                    }
                )

        return {
            "resourceType": "Bundle",
            "type": f"{bundle_type}-response",
            "entry": response_entries,
        }

    def _handle_request(self, request, context):  # type: ignore
        """Handle HTTP requests to the mock server"""
        method = request.method
        url = request.url

        parsed_url = urlparse(url)
        path_parts = [p for p in parsed_url.path.split("/") if p]

        # Remove 'fhir' from path if present
        if path_parts and path_parts[0] == "fhir":
            path_parts = path_parts[1:]

        try:
            if method == "POST" and len(path_parts) == 1:
                # Create resource: POST /ResourceType
                resource_type = path_parts[0]

                # Get JSON data from request
                if hasattr(request, "json") and callable(request.json):
                    resource_data = request.json()
                elif hasattr(request, "json") and request.json:
                    resource_data = request.json
                elif hasattr(request, "body") and request.body:
                    resource_data = json.loads(request.body)
                else:
                    resource_data = {}

                # Check for conditional create (If-None-Exist header)
                if_none_exist = request.headers.get("If-None-Exist")
                if if_none_exist:
                    result = self.conditional_create(resource_data, if_none_exist)
                    status_code = 201 if result.get("created", True) else 200
                else:
                    result = self.create_resource(resource_data)
                    status_code = 201

                context.status_code = status_code
                context.headers["Content-Type"] = "application/fhir+json"
                return result

            elif method == "POST" and len(path_parts) == 0:
                # Bundle processing: POST /
                if hasattr(request, "json") and callable(request.json):
                    bundle_data = request.json()
                elif hasattr(request, "json") and request.json:
                    bundle_data = request.json
                elif hasattr(request, "body") and request.body:
                    bundle_data = json.loads(request.body)
                else:
                    bundle_data = {}

                result = self.process_bundle(bundle_data)
                context.status_code = 200
                context.headers["Content-Type"] = "application/fhir+json"
                return result

            elif method == "PUT" and len(path_parts) >= 1:
                # Update resource: PUT /ResourceType/id or PUT /ResourceType?search
                resource_type = path_parts[0]

                # Get JSON data from request
                if hasattr(request, "json") and callable(request.json):
                    resource_data = request.json()
                elif hasattr(request, "json") and request.json:
                    resource_data = request.json
                elif hasattr(request, "body") and request.body:
                    resource_data = json.loads(request.body)
                else:
                    resource_data = {}

                if len(path_parts) == 2:
                    # Regular update: PUT /ResourceType/id
                    resource_id = path_parts[1]
                    result = self.update_resource(
                        resource_type, resource_id, resource_data
                    )
                    status_code = 201 if result.get("created", False) else 200
                elif parsed_url.query:
                    # Conditional update: PUT /ResourceType?search
                    result = self.conditional_update(
                        resource_type, resource_data, parsed_url.query
                    )
                    status_code = 201 if result.get("created", False) else 200
                else:
                    context.status_code = 400
                    error = {
                        "resourceType": "OperationOutcome",
                        "issue": [
                            {
                                "severity": "error",
                                "code": "invalid",
                                "diagnostics": (
                                    "PUT requests must include resource ID",
                                    "or search parameters",
                                ),
                            }
                        ],
                    }
                    context.headers["Content-Type"] = "application/fhir+json"
                    return error

                context.status_code = status_code
                context.headers["Content-Type"] = "application/fhir+json"
                return result

            elif method == "GET" and len(path_parts) == 2:
                # Read resource: GET /ResourceType/id
                resource_type, resource_id = path_parts
                result = self.read_resource(  # type: ignore
                    resource_type, resource_id, return_fhir_model=False
                )

                if result:
                    context.status_code = 200
                    context.headers["Content-Type"] = "application/fhir+json"
                    return result
                else:
                    context.status_code = 404
                    error = {
                        "resourceType": "OperationOutcome",
                        "issue": [
                            {
                                "severity": "error",
                                "code": "not-found",
                                "diagnostics": (
                                    f"Resource {resource_type}/",
                                    f"{resource_id} not found",
                                ),
                            }
                        ],
                    }
                    context.headers["Content-Type"] = "application/fhir+json"
                    return error

            elif method == "GET" and len(path_parts) == 1:
                # Search resources: GET /ResourceType?params
                resource_type = path_parts[0]
                query_params = parse_qs(parsed_url.query)
                result = self.search_resources(
                    resource_type, query_params, return_fhir_models=False
                )

                context.status_code = 200
                context.headers["Content-Type"] = "application/fhir+json"
                return result

        except Exception as e:
            # Return server error
            import traceback

            print(f"Exception in _handle_request: {e}")
            traceback.print_exc()

            error = {
                "resourceType": "OperationOutcome",
                "issue": [
                    {
                        "severity": "error",
                        "code": "exception",
                        "diagnostics": f"Server error: {str(e)}",
                    }
                ],
            }
            context.status_code = 500
            context.headers["Content-Type"] = "application/fhir+json"
            return error

        # Default 404 response
        error = {
            "resourceType": "OperationOutcome",
            "issue": [
                {
                    "severity": "error",
                    "code": "not-found",
                    "diagnostics": "Endpoint not found",
                }
            ],
        }
        context.status_code = 404
        context.headers["Content-Type"] = "application/fhir+json"
        return error

    def start_mock(self, requests_mocker) -> None:  # type: ignore
        """Start the mock server using requests-mock"""
        self.requests_mock = requests_mocker

        # Register handlers for different HTTP methods and patterns
        base_pattern = re.escape(self.base_url)
        requests_mocker.register_uri(
            requests_mock.ANY,
            re.compile(f"^{base_pattern}/.*"),
            json=self._handle_request,
        )

    def stop_mock(self) -> None:
        """Stop the mock server"""
        if self.requests_mock:
            self.requests_mock.stop()  # type: ignore
            self.requests_mock = None
