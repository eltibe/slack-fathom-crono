"""
Tenant context middleware package for multi-tenant Flask application.

This package provides comprehensive tenant isolation middleware to ensure
all database operations are properly scoped to the correct Slack workspace (tenant).

Components:
- tenant_context: Thread-local context manager for storing current tenant
- slack_parser: Extract tenant information from Slack webhook requests
- tenant_loader: Load tenant from database with caching support
- flask_middleware: Flask integration (before_request/after_request)
- query_helpers: Tenant-scoped database query utilities
- exceptions: Custom exception classes for tenant operations

Usage:
    from middleware import TenantMiddleware
    from flask import Flask

    app = Flask(__name__)
    middleware = TenantMiddleware(app)
    middleware.register()

Architecture:
    1. Slack sends webhook → Flask receives request
    2. Flask before_request → Extract team_id from Slack payload
    3. Load tenant from cache/DB → Set thread-local context
    4. Request handler executes → All queries use tenant context
    5. Flask after_request → Clear tenant context (cleanup)
"""

from src.middleware.exceptions import (
    TenantContextError,
    TenantNotFoundError,
    TenantSuspendedError,
    InvalidSlackRequestError,
)
from src.middleware.tenant_context import (
    set_current_tenant,
    get_current_tenant,
    get_current_tenant_id,
    clear_tenant_context,
    require_tenant,
    tenant_context,
)
from src.middleware.slack_parser import (
    extract_tenant_id_from_request,
    verify_slack_signature,
)
from src.middleware.tenant_loader import (
    load_tenant_by_slack_id,
    get_or_create_tenant,
    clear_tenant_cache,
)
from src.middleware.flask_middleware import TenantMiddleware
from src.middleware.query_helpers import (
    scoped_query,
    create_scoped,
    verify_tenant_access,
)

__all__ = [
    # Exceptions
    "TenantContextError",
    "TenantNotFoundError",
    "TenantSuspendedError",
    "InvalidSlackRequestError",
    # Context management
    "set_current_tenant",
    "get_current_tenant",
    "get_current_tenant_id",
    "clear_tenant_context",
    "require_tenant",
    "tenant_context",
    # Slack parsing
    "extract_tenant_id_from_request",
    "verify_slack_signature",
    # Tenant loading
    "load_tenant_by_slack_id",
    "get_or_create_tenant",
    "clear_tenant_cache",
    # Flask middleware
    "TenantMiddleware",
    # Query helpers
    "scoped_query",
    "create_scoped",
    "verify_tenant_access",
]

__version__ = "1.0.0"
