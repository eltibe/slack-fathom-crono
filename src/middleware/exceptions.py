"""
Custom exception classes for tenant middleware operations.

These exceptions provide specific error handling for multi-tenant operations,
making it easier to diagnose issues and return appropriate HTTP responses.
"""


class TenantContextError(Exception):
    """
    Raised when attempting to access tenant context but none is set.

    This typically indicates a programming error where a function requiring
    tenant context is called outside of a request that has been processed
    by the tenant middleware.

    Example:
        try:
            tenant = get_current_tenant()
        except TenantContextError:
            # Handle missing tenant context
            pass
    """

    def __init__(self, message: str = "No tenant context is currently set"):
        super().__init__(message)
        self.message = message
        self.http_status = 500  # Internal Server Error


class TenantNotFoundError(Exception):
    """
    Raised when a tenant cannot be found in the database.

    This typically indicates that the Slack workspace has not yet installed
    the app, or the tenant record has been deleted.

    Example:
        try:
            tenant = load_tenant_by_slack_id("T0123456789", db)
        except TenantNotFoundError:
            # Return 403 or redirect to installation page
            pass
    """

    def __init__(
        self,
        slack_team_id: str,
        message: str = None
    ):
        self.slack_team_id = slack_team_id
        self.message = message or f"Tenant not found for Slack team {slack_team_id}"
        super().__init__(self.message)
        self.http_status = 403  # Forbidden
        self.error_code = "TENANT_NOT_FOUND"


class TenantSuspendedError(Exception):
    """
    Raised when a tenant's subscription is suspended.

    This indicates that the tenant exists but their subscription is not active
    (e.g., payment failed, account suspended by admin, etc.).

    Example:
        try:
            tenant = load_tenant_by_slack_id("T0123456789", db)
            if not tenant.is_active:
                raise TenantSuspendedError(tenant.slack_team_id)
        except TenantSuspendedError:
            # Return 403 with subscription error message
            pass
    """

    def __init__(
        self,
        slack_team_id: str,
        subscription_status: str = None,
        message: str = None
    ):
        self.slack_team_id = slack_team_id
        self.subscription_status = subscription_status
        self.message = message or (
            f"Tenant {slack_team_id} subscription is suspended "
            f"(status: {subscription_status})"
        )
        super().__init__(self.message)
        self.http_status = 403  # Forbidden
        self.error_code = "TENANT_SUSPENDED"


class InvalidSlackRequestError(Exception):
    """
    Raised when a Slack request cannot be parsed or verified.

    This typically indicates:
    - Invalid signature (security issue)
    - Malformed payload
    - Missing required fields (team_id)
    - Unknown request type

    Example:
        try:
            team_id = extract_tenant_id_from_request(request)
            if not team_id:
                raise InvalidSlackRequestError("Missing team_id in request")
        except InvalidSlackRequestError:
            # Return 400 or 403
            pass
    """

    def __init__(
        self,
        message: str = "Invalid or malformed Slack request",
        details: str = None
    ):
        self.message = message
        self.details = details
        full_message = message
        if details:
            full_message = f"{message}: {details}"
        super().__init__(full_message)
        self.http_status = 400  # Bad Request
        self.error_code = "INVALID_SLACK_REQUEST"


class TenantAccessDeniedError(Exception):
    """
    Raised when attempting to access a resource that belongs to a different tenant.

    This is a security error indicating that cross-tenant data access was attempted,
    which should never happen in a properly isolated multi-tenant system.

    Example:
        try:
            verify_tenant_access(meeting_session, raise_error=True)
        except TenantAccessDeniedError:
            # Log security incident and return 403
            pass
    """

    def __init__(
        self,
        resource_type: str,
        resource_id: str = None,
        expected_tenant_id: str = None,
        actual_tenant_id: str = None
    ):
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.expected_tenant_id = expected_tenant_id
        self.actual_tenant_id = actual_tenant_id

        message = f"Access denied: {resource_type}"
        if resource_id:
            message += f" {resource_id}"
        if expected_tenant_id and actual_tenant_id:
            message += (
                f" belongs to tenant {actual_tenant_id}, "
                f"but current tenant is {expected_tenant_id}"
            )

        super().__init__(message)
        self.http_status = 403  # Forbidden
        self.error_code = "TENANT_ACCESS_DENIED"


class TenantCacheError(Exception):
    """
    Raised when there's an error with the tenant cache (Redis).

    This is typically a warning-level error that should fall back to database
    queries. The application should continue to function without Redis.

    Example:
        try:
            cached_tenant = get_tenant_from_cache(team_id)
        except TenantCacheError as e:
            logger.warning(f"Cache error, falling back to DB: {e}")
            tenant = load_tenant_from_db(team_id)
    """

    def __init__(self, message: str = "Error accessing tenant cache", details: str = None):
        self.message = message
        self.details = details
        full_message = message
        if details:
            full_message = f"{message}: {details}"
        super().__init__(full_message)
        # This is not an HTTP error - it's internal only
        self.http_status = None
