"""
Thread-local tenant context manager for multi-tenant Flask application.

This module provides thread-safe storage for the current tenant throughout
the request lifecycle. Each thread (request) has its own isolated tenant context.

Key Features:
- Thread-local storage using threading.local()
- Context manager support: with tenant_context(tenant):
- Decorator support: @require_tenant
- Type-safe tenant access with validation
- Automatic cleanup on request completion

Architecture:
    Thread 1 (Request A) → Tenant X in context
    Thread 2 (Request B) → Tenant Y in context
    Thread 3 (Request C) → Tenant Z in context
    (Completely isolated - no cross-contamination)

Usage:
    # Set tenant for current request
    set_current_tenant(tenant)

    # Get tenant anywhere in request handling
    tenant = get_current_tenant()

    # Use as context manager
    with tenant_context(tenant):
        # All code here has tenant set
        do_something()

    # Use as decorator
    @require_tenant()
    def my_handler():
        tenant = get_current_tenant()
        # tenant is guaranteed to be set
"""

import functools
import logging
import threading
from contextlib import contextmanager
from typing import Optional, Callable, Any
from uuid import UUID

from src.middleware.exceptions import TenantContextError

logger = logging.getLogger(__name__)


# Thread-local storage for tenant context
# Each thread (HTTP request) gets its own isolated storage
_thread_local = threading.local()


def set_current_tenant(tenant: Any) -> None:
    """
    Set the current tenant for this request/thread.

    This should be called by the Flask middleware at the start of each request
    after successfully loading the tenant from the database.

    Args:
        tenant: Tenant model instance (must have 'id' and 'slack_team_id' attributes)

    Raises:
        ValueError: If tenant is None or invalid

    Example:
        tenant = load_tenant_by_slack_id("T0123456789", db)
        set_current_tenant(tenant)
    """
    if tenant is None:
        raise ValueError("Cannot set None as current tenant")

    # Validate that it's a proper Tenant object
    if not hasattr(tenant, 'id') or not hasattr(tenant, 'slack_team_id'):
        raise ValueError(
            "Invalid tenant object: must have 'id' and 'slack_team_id' attributes"
        )

    _thread_local.tenant = tenant

    # Add tenant info to logger context for structured logging
    logger.debug(
        f"Tenant context set: {tenant.slack_team_id} (id={tenant.id})",
        extra={
            'tenant_id': str(tenant.id),
            'slack_team_id': tenant.slack_team_id
        }
    )


def get_current_tenant() -> Any:
    """
    Get the current tenant for this request/thread.

    Returns:
        Tenant model instance

    Raises:
        TenantContextError: If no tenant is set in the current context

    Example:
        tenant = get_current_tenant()
        print(f"Current workspace: {tenant.slack_team_name}")
    """
    tenant = getattr(_thread_local, 'tenant', None)

    if tenant is None:
        raise TenantContextError(
            "No tenant context is currently set. "
            "This function must be called within a request that has been "
            "processed by the TenantMiddleware."
        )

    return tenant


def get_current_tenant_id() -> UUID:
    """
    Get the current tenant's UUID.

    Convenience method that extracts just the ID from the current tenant.
    Useful when you only need the ID for database queries.

    Returns:
        UUID of the current tenant

    Raises:
        TenantContextError: If no tenant is set in the current context

    Example:
        tenant_id = get_current_tenant_id()
        query = db.query(MeetingSession).filter(
            MeetingSession.tenant_id == tenant_id
        )
    """
    tenant = get_current_tenant()
    return tenant.id


def get_current_tenant_safe() -> Optional[Any]:
    """
    Get the current tenant without raising an exception if none is set.

    Returns:
        Tenant model instance or None if no tenant is set

    Example:
        tenant = get_current_tenant_safe()
        if tenant:
            print(f"Tenant: {tenant.slack_team_name}")
        else:
            print("No tenant context")
    """
    return getattr(_thread_local, 'tenant', None)


def clear_tenant_context() -> None:
    """
    Clear the tenant context for the current thread.

    This should be called by the Flask middleware in the after_request handler
    to ensure clean state between requests (especially important for thread pooling).

    Example:
        # In Flask after_request handler
        @app.after_request
        def cleanup(response):
            clear_tenant_context()
            return response
    """
    if hasattr(_thread_local, 'tenant'):
        tenant = _thread_local.tenant
        logger.debug(
            f"Tenant context cleared: {tenant.slack_team_id}",
            extra={
                'tenant_id': str(tenant.id),
                'slack_team_id': tenant.slack_team_id
            }
        )
        delattr(_thread_local, 'tenant')


@contextmanager
def tenant_context(tenant: Any):
    """
    Context manager for temporarily setting a tenant context.

    Useful for background jobs, testing, or nested operations that need
    to temporarily switch tenant context.

    Args:
        tenant: Tenant model instance

    Yields:
        The tenant instance

    Example:
        # In a background job
        tenant = load_tenant_by_slack_id("T0123456789", db)
        with tenant_context(tenant):
            # All database queries here are scoped to this tenant
            process_tenant_data()
        # Context automatically cleared when exiting
    """
    old_tenant = getattr(_thread_local, 'tenant', None)

    try:
        set_current_tenant(tenant)
        yield tenant
    finally:
        # Restore previous tenant context (or clear if there wasn't one)
        if old_tenant is not None:
            set_current_tenant(old_tenant)
        else:
            clear_tenant_context()


def require_tenant() -> Callable:
    """
    Decorator that ensures a tenant is set before executing the function.

    Raises TenantContextError if no tenant is set, providing a clear
    error message about the missing context.

    Returns:
        Decorator function

    Example:
        @require_tenant()
        def process_meeting(meeting_id: str):
            tenant = get_current_tenant()
            # tenant is guaranteed to be set here
            ...

    Flask route example:
        @app.route('/api/meetings')
        @require_tenant()
        def list_meetings():
            tenant = get_current_tenant()
            return jsonify({'meetings': get_meetings_for_tenant(tenant.id)})
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Check if tenant context is set
            try:
                get_current_tenant()
            except TenantContextError as e:
                logger.error(
                    f"Function {func.__name__} requires tenant context but none is set",
                    extra={'function': func.__name__}
                )
                raise

            # Execute the function
            return func(*args, **kwargs)

        return wrapper

    return decorator


def get_tenant_attribute(attribute_name: str, default: Any = None) -> Any:
    """
    Safely get an attribute from the current tenant.

    Args:
        attribute_name: Name of the attribute to retrieve
        default: Default value if attribute doesn't exist or no tenant set

    Returns:
        Attribute value or default

    Example:
        plan_tier = get_tenant_attribute('plan_tier', 'free')
        timezone = get_tenant_attribute('timezone', 'UTC')
    """
    try:
        tenant = get_current_tenant()
        return getattr(tenant, attribute_name, default)
    except TenantContextError:
        return default


def add_tenant_to_log_context(record: logging.LogRecord) -> logging.LogRecord:
    """
    Add tenant information to log records for structured logging.

    This can be used with a custom logging filter to automatically include
    tenant context in all log messages.

    Args:
        record: Log record to enhance

    Returns:
        Enhanced log record

    Example:
        # In logging configuration
        class TenantContextFilter(logging.Filter):
            def filter(self, record):
                add_tenant_to_log_context(record)
                return True

        handler.addFilter(TenantContextFilter())
    """
    tenant = get_current_tenant_safe()

    if tenant:
        record.tenant_id = str(tenant.id)
        record.slack_team_id = tenant.slack_team_id
        record.tenant_name = getattr(tenant, 'slack_team_name', 'Unknown')
    else:
        record.tenant_id = None
        record.slack_team_id = None
        record.tenant_name = None

    return record


# Optional: Custom logging filter that can be added to handlers
class TenantContextFilter(logging.Filter):
    """
    Logging filter that adds tenant context to all log records.

    Usage:
        import logging
        from middleware.tenant_context import TenantContextFilter

        handler = logging.StreamHandler()
        handler.addFilter(TenantContextFilter())
        logger.addHandler(handler)

        # Now all logs will include tenant_id and slack_team_id
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Add tenant context to log record."""
        add_tenant_to_log_context(record)
        return True
