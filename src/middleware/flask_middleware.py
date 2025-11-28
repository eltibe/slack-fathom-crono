"""
Flask middleware for tenant context management.

This module provides Flask integration for the tenant middleware system.
It registers before_request and after_request handlers to manage tenant
context throughout the request lifecycle.

Flow:
    1. Request arrives → before_request handler
    2. Extract team_id from Slack payload
    3. Verify Slack signature (security)
    4. Load tenant from cache/database
    5. Set tenant in thread-local context
    6. Request handler executes (with tenant context available)
    7. Response generated
    8. after_request handler clears context
    9. Response sent

Whitelisted Routes:
    - /health (health checks)
    - /metrics (monitoring)
    - /static/* (static assets)
    - /favicon.ico

Error Responses:
    - 403: Invalid signature, tenant not found, subscription suspended
    - 400: Invalid Slack request format
    - 500: Internal error loading tenant
"""

import logging
from typing import List, Optional, Callable, Set
from flask import Flask, request, jsonify, g
from werkzeug.exceptions import HTTPException

from src.database import get_session
from src.middleware.tenant_context import (
    set_current_tenant,
    clear_tenant_context,
    get_current_tenant_safe
)
from src.middleware.slack_parser import (
    extract_tenant_id_from_request,
    verify_slack_signature,
    log_request_info
)
from src.middleware.tenant_loader import load_tenant_by_slack_id
from src.middleware.exceptions import (
    TenantNotFoundError,
    TenantSuspendedError,
    InvalidSlackRequestError,
    TenantContextError
)

logger = logging.getLogger(__name__)


class TenantMiddleware:
    """
    Flask middleware for multi-tenant request handling.

    This class registers Flask before_request and after_request handlers
    to manage tenant context automatically for all requests.

    Usage:
        app = Flask(__name__)
        middleware = TenantMiddleware(app)
        middleware.register()

        # Or use init_app pattern:
        middleware = TenantMiddleware()
        middleware.init_app(app)
    """

    def __init__(
        self,
        app: Flask = None,
        whitelist_routes: List[str] = None,
        verify_signatures: bool = True,
        enable_logging: bool = True
    ):
        """
        Initialize tenant middleware.

        Args:
            app: Flask application instance (optional)
            whitelist_routes: Routes that don't require tenant context
            verify_signatures: Whether to verify Slack signatures (default: True)
            enable_logging: Whether to log request info (default: True)
        """
        self.app = app
        self.verify_signatures = verify_signatures
        self.enable_logging = enable_logging

        # Default whitelisted routes (don't require tenant)
        self.whitelist_routes: Set[str] = {
            '/health',
            '/metrics',
            '/favicon.ico',
            '/robots.txt',
            '/_health',
            '/_status'
        }

        # Whitelist patterns (prefix matching)
        self.whitelist_patterns: List[str] = [
            '/static/',
            '/assets/',
            '/public/'
        ]

        # Add custom whitelisted routes
        if whitelist_routes:
            self.whitelist_routes.update(whitelist_routes)

        # Register with app if provided
        if app:
            self.init_app(app)

    def init_app(self, app: Flask) -> None:
        """
        Initialize middleware with Flask app.

        Args:
            app: Flask application instance
        """
        self.app = app
        self.register()

    def register(self) -> None:
        """Register before_request and after_request handlers."""
        if not self.app:
            raise RuntimeError("Flask app not initialized. Call init_app() first.")

        self.app.before_request(self.process_request)
        self.app.after_request(self.cleanup_request)
        self.app.errorhandler(Exception)(self.handle_error)

        logger.info("TenantMiddleware registered with Flask app")

    def is_whitelisted(self, path: str) -> bool:
        """
        Check if a route is whitelisted (doesn't require tenant).

        Args:
            path: Request path

        Returns:
            True if whitelisted, False otherwise
        """
        # Check exact matches
        if path in self.whitelist_routes:
            return True

        # Check prefix patterns
        for pattern in self.whitelist_patterns:
            if path.startswith(pattern):
                return True

        return False

    def process_request(self) -> Optional[tuple]:
        """
        Before request handler: Extract tenant and set context.

        Returns:
            None to continue processing, or tuple (response, status_code) to abort

        This is called automatically by Flask before each request.
        """
        try:
            # Check if route is whitelisted
            if self.is_whitelisted(request.path):
                logger.debug(f"Whitelisted route: {request.path}")
                return None

            # Log request info (if enabled)
            if self.enable_logging:
                log_request_info(request)

            # Verify Slack signature (security check)
            if self.verify_signatures:
                if not verify_slack_signature(request):
                    logger.warning(
                        f"Invalid Slack signature: {request.path}",
                        extra={'path': request.path, 'ip': request.remote_addr}
                    )
                    return jsonify({
                        'error': 'Invalid request signature',
                        'code': 'INVALID_SIGNATURE'
                    }), 403

            # Extract tenant ID from request
            team_id = extract_tenant_id_from_request(request)
            if not team_id:
                logger.warning(
                    f"No team_id in request: {request.path}",
                    extra={'path': request.path}
                )
                return jsonify({
                    'error': 'Cannot determine Slack workspace',
                    'code': 'MISSING_TEAM_ID'
                }), 400

            # Load tenant from database (with caching)
            db_session = get_session()
            try:
                tenant = load_tenant_by_slack_id(
                    slack_team_id=team_id,
                    db_session=db_session,
                    use_cache=True,
                    check_subscription=True
                )

                # Set tenant in thread-local context
                set_current_tenant(tenant)

                # Also attach to Flask's g object for convenience
                g.tenant = tenant
                g.tenant_id = tenant.id
                g.slack_team_id = team_id
                g.db_session = db_session  # Store for cleanup

                logger.info(
                    f"Tenant context set for request: {tenant.slack_team_name}",
                    extra={
                        'tenant_id': str(tenant.id),
                        'slack_team_id': team_id,
                        'path': request.path
                    }
                )

                return None  # Continue processing

            except TenantNotFoundError as e:
                db_session.close()
                logger.warning(
                    f"Tenant not found: {team_id}",
                    extra={'slack_team_id': team_id, 'path': request.path}
                )
                return jsonify({
                    'error': 'Workspace not installed',
                    'code': 'TENANT_NOT_FOUND',
                    'message': 'This workspace has not installed the app yet.',
                    'slack_team_id': team_id
                }), 403

            except TenantSuspendedError as e:
                db_session.close()
                logger.warning(
                    f"Tenant suspended: {team_id} ({e.subscription_status})",
                    extra={
                        'slack_team_id': team_id,
                        'subscription_status': e.subscription_status,
                        'path': request.path
                    }
                )
                return jsonify({
                    'error': 'Subscription suspended',
                    'code': 'TENANT_SUSPENDED',
                    'message': 'Your subscription is currently suspended. Please contact support.',
                    'subscription_status': e.subscription_status
                }), 403

        except Exception as e:
            logger.error(
                f"Error in tenant middleware: {e}",
                exc_info=True,
                extra={'path': request.path}
            )
            return jsonify({
                'error': 'Internal server error',
                'code': 'MIDDLEWARE_ERROR'
            }), 500

    def cleanup_request(self, response):
        """
        After request handler: Clean up tenant context and database session.

        Args:
            response: Flask response object

        Returns:
            Response object (unmodified)

        This is called automatically by Flask after each request.
        """
        try:
            # Clear tenant context
            tenant = get_current_tenant_safe()
            if tenant:
                logger.debug(
                    f"Clearing tenant context: {tenant.slack_team_id}",
                    extra={'tenant_id': str(tenant.id)}
                )
                clear_tenant_context()

            # Close database session if stored in g
            if hasattr(g, 'db_session'):
                try:
                    g.db_session.close()
                except Exception as e:
                    logger.error(f"Error closing database session: {e}")

            # Clean up g object
            for attr in ['tenant', 'tenant_id', 'slack_team_id', 'db_session']:
                if hasattr(g, attr):
                    delattr(g, attr)

        except Exception as e:
            # Don't let cleanup errors affect the response
            logger.error(f"Error in cleanup handler: {e}", exc_info=True)

        return response

    def handle_error(self, error: Exception):
        """
        Global error handler for tenant-related exceptions.

        Args:
            error: Exception that occurred

        Returns:
            JSON error response
        """
        # Re-raise HTTP exceptions (Flask will handle them)
        if isinstance(error, HTTPException):
            return error

        # Handle our custom exceptions
        if isinstance(error, TenantNotFoundError):
            return jsonify({
                'error': 'Workspace not installed',
                'code': error.error_code,
                'slack_team_id': error.slack_team_id
            }), error.http_status

        if isinstance(error, TenantSuspendedError):
            return jsonify({
                'error': 'Subscription suspended',
                'code': error.error_code,
                'subscription_status': error.subscription_status
            }), error.http_status

        if isinstance(error, InvalidSlackRequestError):
            return jsonify({
                'error': error.message,
                'code': error.error_code,
                'details': error.details
            }), error.http_status

        if isinstance(error, TenantContextError):
            return jsonify({
                'error': 'Tenant context not available',
                'code': 'TENANT_CONTEXT_ERROR'
            }), 500

        # Log unexpected errors
        logger.error(f"Unhandled error: {error}", exc_info=True)

        # Don't expose internal errors in production
        return jsonify({
            'error': 'Internal server error',
            'code': 'INTERNAL_ERROR'
        }), 500

    def add_whitelist_route(self, route: str) -> None:
        """
        Add a route to the whitelist.

        Args:
            route: Route path to whitelist
        """
        self.whitelist_routes.add(route)
        logger.debug(f"Added whitelist route: {route}")

    def add_whitelist_pattern(self, pattern: str) -> None:
        """
        Add a route pattern to the whitelist.

        Args:
            pattern: Route prefix pattern (e.g., '/api/public/')
        """
        self.whitelist_patterns.append(pattern)
        logger.debug(f"Added whitelist pattern: {pattern}")

    def remove_whitelist_route(self, route: str) -> None:
        """
        Remove a route from the whitelist.

        Args:
            route: Route path to remove
        """
        self.whitelist_routes.discard(route)
        logger.debug(f"Removed whitelist route: {route}")


def get_current_tenant_from_g():
    """
    Get current tenant from Flask's g object.

    Convenience function for accessing tenant in Flask routes.

    Returns:
        Tenant instance or None

    Example:
        @app.route('/api/meetings')
        def list_meetings():
            tenant = get_current_tenant_from_g()
            if not tenant:
                return jsonify({'error': 'Unauthorized'}), 401
            ...
    """
    return getattr(g, 'tenant', None)


def get_current_db_session():
    """
    Get current database session from Flask's g object.

    Returns:
        Database session or None

    Example:
        @app.route('/api/meetings')
        def list_meetings():
            db = get_current_db_session()
            meetings = scoped_query(MeetingSession, db).all()
            ...
    """
    return getattr(g, 'db_session', None)


# Decorator for routes that require tenant
def require_tenant_route(func: Callable) -> Callable:
    """
    Decorator to ensure tenant is set for a route.

    This is redundant if TenantMiddleware is registered (it sets tenant
    for all routes), but can be used for explicit documentation.

    Example:
        @app.route('/api/meetings')
        @require_tenant_route
        def list_meetings():
            tenant = get_current_tenant_from_g()
            ...
    """
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        tenant = get_current_tenant_from_g()
        if not tenant:
            return jsonify({
                'error': 'Tenant context required',
                'code': 'TENANT_REQUIRED'
            }), 403
        return func(*args, **kwargs)

    return wrapper
