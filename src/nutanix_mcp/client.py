"""Nutanix Prism Central API client with v4/v3 version routing."""

import asyncio
import re
from typing import Any, Optional

import httpx

from nutanix_mcp.config import Settings
from nutanix_mcp.sdk_client import NutanixSDKClient


class NutanixAPIError(Exception):
    """Base exception for Nutanix API errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        details: Optional[str] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class AuthenticationError(NutanixAPIError):
    """Authentication failed."""

    pass


class NotFoundError(NutanixAPIError):
    """Resource not found."""

    pass


class ValidationError(NutanixAPIError):
    """Request validation failed."""

    pass


class NutanixClient:
    """Async HTTP client for Nutanix Prism Central.

    Prefers v4 API endpoints, falls back to v3/v2 when needed.
    v4 uses OData-style query params ($filter, $orderby, $top, $skip).
    v3 uses POST-based list with body filters.
    """

    V4_VERSION = "v4.0"
    V3_VERSION = "v3"
    V2_VERSION = "v2.0"

    # Retry settings for rate-limited (429) responses
    MAX_RETRIES = 3
    RETRY_BACKOFF_BASE = 2.0  # seconds; exponential: 2, 4, 8

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: Optional[httpx.AsyncClient] = None
        self._pe_clients: dict[str, httpx.AsyncClient] = {}
        self.sdk = NutanixSDKClient(settings)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.settings.base_url,
                headers={
                    **self.settings.get_auth_header(),
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                verify=self.settings.verify_ssl,
                timeout=httpx.Timeout(self.settings.timeout),
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
        for pe_client in self._pe_clients.values():
            if not pe_client.is_closed:
                await pe_client.aclose()
        self._pe_clients.clear()

    # ─── v4 API methods ───────────────────────────────────────────────────

    async def _v4_request(
        self,
        method: str,
        namespace: str,
        path: str,
        params: Optional[dict[str, str]] = None,
        body: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> httpx.Response:
        """Send a v4 API request with connection error mapping and 429 retry."""
        client = await self._get_client()
        url = f"/{namespace}/{self.V4_VERSION}/{path}"

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = await client.request(method, url, params=params, json=body, headers=headers)
            except httpx.ConnectError as e:
                raise NutanixAPIError(
                    f"Connection failed to {self.settings.host}:{self.settings.port}",
                    details=str(e),
                )
            except httpx.TimeoutException as e:
                raise NutanixAPIError(
                    f"Request timed out after {self.settings.timeout}s",
                    details=str(e),
                )

            if response.status_code == 429 and attempt < self.MAX_RETRIES:
                wait = self.RETRY_BACKOFF_BASE * (2**attempt)
                await asyncio.sleep(wait)
                continue

            if response.status_code >= 400:
                self._handle_error(response)

            return response

        # Retries exhausted on 429
        self._handle_error(response)
        raise NutanixAPIError("Rate limited: retries exhausted", status_code=429)  # unreachable

    async def v4_get(
        self,
        namespace: str,
        path: str,
        params: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """GET request against v4 API.

        Args:
            namespace: API namespace (e.g., 'vmm', 'clustermgmt', 'prism')
            path: Resource path (e.g., 'ahv/config/vms')
            params: Optional OData query parameters
        """
        response = await self._v4_request("GET", namespace, path, params=params)
        return response.json()

    async def v4_get_with_etag(
        self,
        namespace: str,
        path: str,
        params: Optional[dict[str, str]] = None,
    ) -> tuple[dict[str, Any], Optional[str]]:
        """GET request against v4 API, returning (body, ETag header).

        The ETag must be echoed back as If-Match on subsequent mutating
        requests — Nutanix v4 rejects PUT/DELETE without it (HTTP 428).
        """
        response = await self._v4_request("GET", namespace, path, params=params)
        return response.json(), response.headers.get("ETag")

    async def v4_put(
        self,
        namespace: str,
        path: str,
        body: dict[str, Any],
        headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """PUT request against v4 API (used for updates with ETag)."""
        response = await self._v4_request("PUT", namespace, path, body=body, headers=headers)
        return response.json()

    async def v4_post(
        self,
        namespace: str,
        path: str,
        body: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """POST request against v4 API (used for $actions endpoints)."""
        response = await self._v4_request("POST", namespace, path, body=body, headers=headers)
        return response.json()

    # Maximum allowed length for OData filter/orderby expressions
    MAX_FILTER_LENGTH = 500

    # Characters that should never appear in OData filter expressions
    _FILTER_DENY_PATTERN = re.compile(r"[;{}<>\\]|--|\*/|/\*")

    def _validate_odata_param(self, value: str, param_name: str) -> None:
        """Validate an OData query parameter for injection patterns.

        Raises ValidationError if the value contains suspicious characters
        or exceeds the maximum allowed length.
        """
        if len(value) > self.MAX_FILTER_LENGTH:
            raise ValidationError(
                f"OData {param_name} exceeds maximum length ({self.MAX_FILTER_LENGTH} chars)",
                status_code=None,
            )
        if self._FILTER_DENY_PATTERN.search(value):
            raise ValidationError(
                f"OData {param_name} contains disallowed characters",
                status_code=None,
            )

    async def v4_list(
        self,
        namespace: str,
        path: str,
        filter: Optional[str] = None,
        orderby: Optional[str] = None,
        top: Optional[int] = None,
        skip: Optional[int] = None,
        select: Optional[str] = None,
    ) -> dict[str, Any]:
        """List resources using v4 API with OData query parameters.

        Args:
            namespace: API namespace (e.g., 'vmm', 'clustermgmt')
            path: Resource path
            filter: OData $filter expression
            orderby: OData $orderby expression
            top: Maximum number of results
            skip: Number of results to skip
            select: Fields to include in response
        """
        params: dict[str, str] = {}
        if filter:
            self._validate_odata_param(filter, "$filter")
            params["$filter"] = filter
        if orderby:
            self._validate_odata_param(orderby, "$orderby")
            params["$orderby"] = orderby
        if top is not None:
            params["$top"] = str(top)
        if skip is not None:
            params["$skip"] = str(skip)
        if select:
            self._validate_odata_param(select, "$select")
            params["$select"] = select

        return await self.v4_get(namespace, path, params=params)

    # ─── v3 API methods (fallback) ────────────────────────────────────────

    async def v3_list(
        self,
        resource: str,
        kind: str,
        filter: Optional[str] = None,
        length: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List entities using v3 API (POST /api/nutanix/v3/{resource}/list).

        Used as fallback when v4 doesn't support a resource.
        """
        client = await self._get_client()
        url = f"/nutanix/{self.V3_VERSION}/{resource}/list"

        body: dict[str, Any] = {
            "kind": kind,
            "length": length,
            "offset": offset,
        }
        if filter:
            body["filter"] = filter

        try:
            response = await client.post(url, json=body)
        except httpx.ConnectError as e:
            raise NutanixAPIError(
                f"Connection failed to {self.settings.host}:{self.settings.port}",
                details=str(e),
            )
        except httpx.TimeoutException as e:
            raise NutanixAPIError(
                f"Request timed out after {self.settings.timeout}s",
                details=str(e),
            )

        if response.status_code >= 400:
            self._handle_error(response)

        return response.json()

    async def v3_get(
        self,
        resource: str,
        uuid: str,
    ) -> dict[str, Any]:
        """Get a single entity by UUID using v3 API."""
        client = await self._get_client()
        url = f"/nutanix/{self.V3_VERSION}/{resource}/{uuid}"

        try:
            response = await client.get(url)
        except httpx.ConnectError as e:
            raise NutanixAPIError(
                f"Connection failed to {self.settings.host}:{self.settings.port}",
                details=str(e),
            )
        except httpx.TimeoutException as e:
            raise NutanixAPIError(
                f"Request timed out after {self.settings.timeout}s",
                details=str(e),
            )

        if response.status_code >= 400:
            self._handle_error(response)

        return response.json()

    # ─── Prism Element v2 API methods ─────────────────────────────────────

    def _validate_pe_host(self, pe_host: str) -> None:
        """Validate that pe_host is allowed before sending credentials."""
        # Basic format validation: must look like an IP or hostname
        if not re.match(r"^[a-zA-Z0-9._-]+$", pe_host):
            raise ValidationError(
                "Invalid PE host format: contains disallowed characters",
                status_code=None,
            )

        # Check against allowlist
        if not self.settings.is_pe_host_allowed(pe_host):
            raise ValidationError(
                "PE host not in allowlist. Add it to NUTANIX_ALLOWED_PE_HOSTS.",
                status_code=None,
            )

    async def _get_pe_client(self, pe_host: str) -> httpx.AsyncClient:
        """Get or create an HTTP client for a Prism Element node."""
        self._validate_pe_host(pe_host)

        if pe_host not in self._pe_clients or self._pe_clients[pe_host].is_closed:
            self._pe_clients[pe_host] = httpx.AsyncClient(
                base_url=f"https://{pe_host}:{self.settings.port}/api/nutanix/{self.V2_VERSION}",
                headers={
                    **self.settings.get_pe_auth_header(),
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                verify=self.settings.verify_ssl,
                timeout=httpx.Timeout(self.settings.timeout),
            )
        return self._pe_clients[pe_host]

    async def pe_v1_get(
        self,
        pe_host: str,
        path: str,
        params: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """GET request against a Prism Element v1 API.

        Args:
            pe_host: Prism Element CVM IP or hostname
            path: Resource path (e.g., 'authconfig', 'license')
        """
        self._validate_pe_host(pe_host)
        client = await self._get_client_for_pe_v1(pe_host)

        try:
            response = await client.get(f"/{path}", params=params)
        except httpx.ConnectError as e:
            raise NutanixAPIError(
                f"Connection failed to PE host {pe_host}",
                details=str(e),
            )
        except httpx.TimeoutException as e:
            raise NutanixAPIError(
                f"Request to PE {pe_host} timed out after {self.settings.timeout}s",
                details=str(e),
            )

        if response.status_code >= 400:
            self._handle_error(response)

        return response.json()

    async def _get_client_for_pe_v1(self, pe_host: str) -> httpx.AsyncClient:
        """Get or create an HTTP client for Prism Element v1 API."""
        cache_key = f"{pe_host}_v1"
        if cache_key not in self._pe_clients or self._pe_clients[cache_key].is_closed:
            self._pe_clients[cache_key] = httpx.AsyncClient(
                base_url=f"https://{pe_host}:{self.settings.port}/api/nutanix/v1",
                headers={
                    **self.settings.get_pe_auth_header(),
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                verify=self.settings.verify_ssl,
                timeout=httpx.Timeout(self.settings.timeout),
            )
        return self._pe_clients[cache_key]

    async def pe_get(
        self,
        pe_host: str,
        path: str,
        params: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """GET request against a Prism Element v2 API.

        Args:
            pe_host: Prism Element CVM IP or hostname
            path: Resource path (e.g., 'vms', 'hosts', 'cluster')
        """
        client = await self._get_pe_client(pe_host)

        try:
            response = await client.get(f"/{path}", params=params)
        except httpx.ConnectError as e:
            raise NutanixAPIError(
                f"Connection failed to PE host {pe_host}",
                details=str(e),
            )
        except httpx.TimeoutException as e:
            raise NutanixAPIError(
                f"Request to PE {pe_host} timed out after {self.settings.timeout}s",
                details=str(e),
            )

        if response.status_code >= 400:
            self._handle_error(response)

        return response.json()

    async def pe_list(
        self,
        pe_host: str,
        resource: str,
        count: Optional[int] = None,
        filter_criteria: Optional[str] = None,
    ) -> dict[str, Any]:
        """List resources from a Prism Element node using v2 API.

        Args:
            pe_host: Prism Element CVM IP or hostname
            resource: Resource type (e.g., 'vms', 'hosts', 'disks', 'containers')
            count: Max results to return
            filter_criteria: Filter string for the query
        """
        params: dict[str, str] = {}
        if count is not None:
            params["count"] = str(count)
        if filter_criteria:
            params["filter_criteria"] = filter_criteria

        return await self.pe_get(pe_host, resource, params=params)

    async def pe_v3_groups(
        self,
        pe_host: str,
        entity_type: str,
        count: int = 500,
    ) -> dict[str, Any]:
        """Query a Prism Element's v3 groups API for an entity type.

        Some Prism Element configuration lives only behind this endpoint — it is
        how the Prism UI itself fetches those entities — with no v1 or v2 route.
        Attributes are deliberately not requested: the API does not validate
        attribute names, so asking for a guessed set silently yields nothing.
        """
        self._validate_pe_host(pe_host)
        client = await self._get_client_for_pe_v3(pe_host)

        body = {"entity_type": entity_type, "group_member_count": count}
        try:
            response = await client.post("/groups", json=body)
        except httpx.ConnectError as e:
            raise NutanixAPIError(f"Connection failed to PE host {pe_host}", details=str(e))
        except httpx.TimeoutException as e:
            raise NutanixAPIError(
                f"Request to PE {pe_host} timed out after {self.settings.timeout}s",
                details=str(e),
            )

        if response.status_code >= 400:
            self._handle_error(response)

        return response.json()

    async def _get_client_for_pe_v3(self, pe_host: str) -> httpx.AsyncClient:
        """Get or create an HTTP client for Prism Element v3 API."""
        cache_key = f"{pe_host}_v3"
        if cache_key not in self._pe_clients or self._pe_clients[cache_key].is_closed:
            self._pe_clients[cache_key] = httpx.AsyncClient(
                base_url=f"https://{pe_host}:{self.settings.port}/api/nutanix/{self.V3_VERSION}",
                headers={
                    **self.settings.get_auth_header(),
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                verify=self.settings.verify_ssl,
                timeout=httpx.Timeout(self.settings.timeout),
            )
        return self._pe_clients[cache_key]

    # ─── Error handling ───────────────────────────────────────────────────

    def _handle_error(self, response: httpx.Response) -> None:
        """Raise appropriate exception based on HTTP status.

        Provides sanitized error messages without leaking internal details.
        """
        status = response.status_code
        try:
            error_data = response.json()
            # Only extract high-level message, not full response body
            message = error_data.get("message", "")
            if not message:
                message = error_data.get("error", f"HTTP {status}")
            # Truncate overly long messages that might contain stack traces
            if len(message) > 200:
                message = message[:200] + "..."
            details = None
        except Exception:
            message = f"HTTP {status}"
            details = None

        if status in (401, 403):
            raise AuthenticationError(
                f"Authentication failed (HTTP {status})",
                status_code=status,
                details=None,
            )
        elif status == 404:
            raise NotFoundError(
                "Resource not found",
                status_code=status,
                details=None,
            )
        elif status in (400, 422):
            raise ValidationError(
                f"Request validation error: {message}",
                status_code=status,
                details=None,
            )
        else:
            raise NutanixAPIError(
                f"API request failed (HTTP {status})",
                status_code=status,
                details=details,
            )
