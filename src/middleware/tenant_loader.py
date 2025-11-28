"""
Tenant loader with database queries and Redis caching.

This module handles loading tenants from the database with optional Redis caching
for performance. It provides graceful degradation if Redis is unavailable.

Features:
- Load tenant by Slack team ID
- Auto-provisioning for new installations
- Redis caching with 5-minute TTL
- Audit logging for tenant access
- Soft-delete filtering
- Subscription status validation

Architecture:
    1. Check Redis cache (if enabled)
    2. If cache miss, query database
    3. Cache result in Redis (if enabled)
    4. Log audit event
    5. Return tenant

Performance:
    - Cache hit: ~1-2ms
    - Cache miss + DB query: ~50-100ms
    - Without Redis: ~50-100ms (direct DB query)
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from src.models.tenant import Tenant
from src.models.audit_log import AuditLog
from src.middleware.exceptions import (
    TenantNotFoundError,
    TenantSuspendedError,
    TenantCacheError
)

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Redis configuration
REDIS_ENABLED = os.getenv('REDIS_ENABLED', 'false').lower() == 'true'
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
TENANT_CACHE_TTL = int(os.getenv('TENANT_CACHE_TTL', '300'))  # 5 minutes

# Lazy import Redis to make it optional
_redis_client = None


def _get_redis_client():
    """
    Get or create Redis client (lazy initialization).

    Returns:
        Redis client or None if disabled/unavailable
    """
    global _redis_client

    if not REDIS_ENABLED:
        return None

    if _redis_client is not None:
        return _redis_client

    try:
        import redis
        _redis_client = redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_timeout=2,
            socket_connect_timeout=2,
            retry_on_timeout=False
        )
        # Test connection
        _redis_client.ping()
        logger.info(f"Redis connection established: {REDIS_URL}")
        return _redis_client

    except ImportError:
        logger.warning("Redis package not installed, caching disabled")
        return None
    except Exception as e:
        logger.warning(f"Redis connection failed, caching disabled: {e}")
        return None


def _get_cache_key(slack_team_id: str) -> str:
    """Generate Redis cache key for a tenant."""
    return f"tenant:slack_id:{slack_team_id}"


def _serialize_tenant(tenant: Tenant) -> str:
    """
    Serialize tenant to JSON for caching.

    Args:
        tenant: Tenant instance

    Returns:
        JSON string
    """
    return json.dumps({
        'id': str(tenant.id),
        'slack_team_id': tenant.slack_team_id,
        'slack_team_name': tenant.slack_team_name,
        'slack_team_domain': tenant.slack_team_domain,
        'plan_tier': tenant.plan_tier,
        'subscription_status': tenant.subscription_status,
        'default_crm_provider': tenant.default_crm_provider,
        'timezone': tenant.timezone,
        'locale': tenant.locale,
        'created_at': tenant.created_at.isoformat() if tenant.created_at else None,
        'updated_at': tenant.updated_at.isoformat() if tenant.updated_at else None,
    })


def _get_tenant_from_cache(slack_team_id: str) -> Optional[Dict[str, Any]]:
    """
    Get tenant data from Redis cache.

    Args:
        slack_team_id: Slack team ID

    Returns:
        Tenant data dict or None if not cached/unavailable
    """
    redis = _get_redis_client()
    if not redis:
        return None

    try:
        cache_key = _get_cache_key(slack_team_id)
        cached_data = redis.get(cache_key)

        if cached_data:
            logger.debug(f"Tenant cache HIT: {slack_team_id}")
            return json.loads(cached_data)

        logger.debug(f"Tenant cache MISS: {slack_team_id}")
        return None

    except Exception as e:
        logger.warning(f"Error reading from cache: {e}")
        return None


def _set_tenant_in_cache(slack_team_id: str, tenant: Tenant) -> None:
    """
    Store tenant data in Redis cache.

    Args:
        slack_team_id: Slack team ID
        tenant: Tenant instance
    """
    redis = _get_redis_client()
    if not redis:
        return

    try:
        cache_key = _get_cache_key(slack_team_id)
        serialized = _serialize_tenant(tenant)
        redis.setex(cache_key, TENANT_CACHE_TTL, serialized)
        logger.debug(f"Tenant cached: {slack_team_id} (TTL={TENANT_CACHE_TTL}s)")

    except Exception as e:
        logger.warning(f"Error writing to cache: {e}")


def clear_tenant_cache(slack_team_id: str = None) -> bool:
    """
    Clear tenant cache for a specific tenant or all tenants.

    Args:
        slack_team_id: Slack team ID to clear, or None to clear all

    Returns:
        True if successful, False otherwise

    Example:
        # Clear specific tenant
        clear_tenant_cache("T0123456789")

        # Clear all tenant cache
        clear_tenant_cache()
    """
    redis = _get_redis_client()
    if not redis:
        return False

    try:
        if slack_team_id:
            # Clear specific tenant
            cache_key = _get_cache_key(slack_team_id)
            redis.delete(cache_key)
            logger.info(f"Cleared cache for tenant: {slack_team_id}")
        else:
            # Clear all tenant cache
            pattern = _get_cache_key('*')
            keys = redis.keys(pattern)
            if keys:
                redis.delete(*keys)
                logger.info(f"Cleared cache for {len(keys)} tenants")

        return True

    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        return False


def load_tenant_by_slack_id(
    slack_team_id: str,
    db_session: Session,
    use_cache: bool = True,
    check_subscription: bool = True
) -> Tenant:
    """
    Load tenant by Slack team ID with caching support.

    Args:
        slack_team_id: Slack team ID (e.g., "T0123456789")
        db_session: SQLAlchemy database session
        use_cache: Whether to use Redis cache (default: True)
        check_subscription: Whether to check subscription status (default: True)

    Returns:
        Tenant instance

    Raises:
        TenantNotFoundError: If tenant doesn't exist
        TenantSuspendedError: If tenant subscription is suspended

    Example:
        with get_db() as db:
            tenant = load_tenant_by_slack_id("T0123456789", db)
            print(f"Loaded: {tenant.slack_team_name}")
    """
    # Try cache first (if enabled)
    if use_cache and REDIS_ENABLED:
        cached_data = _get_tenant_from_cache(slack_team_id)
        if cached_data:
            # Reconstruct tenant object from cache
            # Note: This is a simplified version - in production you might want to
            # refresh the full object from DB periodically
            tenant = db_session.query(Tenant).filter(
                Tenant.id == cached_data['id']
            ).first()

            if tenant:
                logger.debug(f"Tenant loaded from cache: {slack_team_id}")
                _log_tenant_access(tenant, db_session, source='cache')
                _check_tenant_subscription(tenant, check_subscription)
                return tenant

    # Cache miss or disabled - query database
    logger.debug(f"Loading tenant from database: {slack_team_id}")

    tenant = Tenant.get_by_slack_team_id(
        session=db_session,
        slack_team_id=slack_team_id,
        include_deleted=False
    )

    if not tenant:
        logger.warning(f"Tenant not found: {slack_team_id}")
        raise TenantNotFoundError(slack_team_id)

    logger.info(
        f"Tenant loaded from DB: {tenant.slack_team_name} ({slack_team_id})",
        extra={
            'tenant_id': str(tenant.id),
            'slack_team_id': slack_team_id,
            'plan_tier': tenant.plan_tier
        }
    )

    # Cache the result (if enabled)
    if use_cache and REDIS_ENABLED:
        _set_tenant_in_cache(slack_team_id, tenant)

    # Log access for audit trail
    _log_tenant_access(tenant, db_session, source='database')

    # Check subscription status
    _check_tenant_subscription(tenant, check_subscription)

    return tenant


def get_or_create_tenant(
    slack_team_id: str,
    team_name: str,
    db_session: Session,
    team_domain: str = None,
    installed_by_user_id: str = None
) -> Tenant:
    """
    Get existing tenant or create new one (auto-provisioning).

    This is used during Slack app installation to automatically provision
    new tenants when they install the app.

    Args:
        slack_team_id: Slack team ID
        team_name: Workspace display name
        db_session: Database session
        team_domain: Workspace domain (optional)
        installed_by_user_id: Slack user ID who installed (optional)

    Returns:
        Tenant instance (existing or newly created)

    Example:
        # During OAuth callback
        tenant = get_or_create_tenant(
            slack_team_id="T0123456789",
            team_name="Acme Corp",
            team_domain="acme-corp",
            installed_by_user_id="U9876543210",
            db_session=db
        )
    """
    # Try to get existing tenant
    try:
        tenant = load_tenant_by_slack_id(
            slack_team_id,
            db_session,
            use_cache=False,  # Don't use cache for create operations
            check_subscription=False  # Don't check during provisioning
        )
        logger.info(f"Existing tenant found: {tenant.slack_team_name}")
        return tenant

    except TenantNotFoundError:
        # Create new tenant
        logger.info(f"Creating new tenant: {team_name} ({slack_team_id})")

        # Calculate trial end date (14 days from now)
        trial_ends_at = datetime.utcnow() + timedelta(days=14)

        tenant = Tenant(
            slack_team_id=slack_team_id,
            slack_team_name=team_name,
            slack_team_domain=team_domain,
            plan_tier='free',
            subscription_status='trial',
            trial_ends_at=trial_ends_at,
            installed_at=datetime.utcnow(),
            installed_by_user_id=installed_by_user_id,
            timezone='UTC',
            locale='en'
        )

        db_session.add(tenant)
        db_session.flush()  # Get ID without committing

        logger.info(
            f"Tenant created: {tenant.slack_team_name} (id={tenant.id})",
            extra={
                'tenant_id': str(tenant.id),
                'slack_team_id': slack_team_id,
                'plan_tier': tenant.plan_tier,
                'subscription_status': tenant.subscription_status
            }
        )

        # Log audit event
        _log_tenant_access(tenant, db_session, source='provisioning', event_type='tenant.created')

        # Commit is handled by caller or context manager

        return tenant


def _check_tenant_subscription(tenant: Tenant, check_enabled: bool) -> None:
    """
    Check if tenant subscription is active.

    Args:
        tenant: Tenant instance
        check_enabled: Whether to perform the check

    Raises:
        TenantSuspendedError: If subscription is not active
    """
    if not check_enabled:
        return

    # Check if subscription is active or in trial
    if not tenant.is_active:
        logger.warning(
            f"Tenant subscription suspended: {tenant.slack_team_id} "
            f"(status={tenant.subscription_status})"
        )
        raise TenantSuspendedError(
            tenant.slack_team_id,
            tenant.subscription_status
        )

    # Check if trial has expired
    if tenant.is_trial and tenant.trial_expired:
        logger.warning(
            f"Tenant trial expired: {tenant.slack_team_id} "
            f"(expired_at={tenant.trial_ends_at})"
        )
        raise TenantSuspendedError(
            tenant.slack_team_id,
            'trial_expired',
            f"Trial period expired on {tenant.trial_ends_at}"
        )


def _log_tenant_access(
    tenant: Tenant,
    db_session: Session,
    source: str = 'unknown',
    event_type: str = 'tenant.accessed'
) -> None:
    """
    Log tenant access to audit log.

    Args:
        tenant: Tenant instance
        db_session: Database session
        source: Source of access ('cache', 'database', 'provisioning')
        event_type: Type of audit event
    """
    try:
        audit_log = AuditLog(
            tenant_id=tenant.id,
            event_type=event_type,
            user_id=None,  # System-level event
            resource_type='tenant',
            resource_id=str(tenant.id),
            action='read',
            metadata={
                'source': source,
                'slack_team_id': tenant.slack_team_id,
                'subscription_status': tenant.subscription_status,
                'plan_tier': tenant.plan_tier
            },
            ip_address=None,
            user_agent=None
        )

        db_session.add(audit_log)
        # Don't commit here - let the caller manage transactions

    except Exception as e:
        # Don't fail the request if audit logging fails
        logger.error(f"Error logging tenant access: {e}", exc_info=True)


def refresh_tenant(tenant: Tenant, db_session: Session) -> Tenant:
    """
    Refresh tenant from database and update cache.

    Useful after updating tenant data to ensure cache is current.

    Args:
        tenant: Tenant instance to refresh
        db_session: Database session

    Returns:
        Refreshed tenant instance

    Example:
        tenant.plan_tier = 'pro'
        db_session.commit()
        tenant = refresh_tenant(tenant, db_session)
    """
    db_session.refresh(tenant)

    # Update cache
    if REDIS_ENABLED:
        _set_tenant_in_cache(tenant.slack_team_id, tenant)
        logger.debug(f"Tenant refreshed and cache updated: {tenant.slack_team_id}")

    return tenant


def preload_tenants(db_session: Session, limit: int = 100) -> int:
    """
    Preload active tenants into cache (warm-up).

    Useful for application startup to reduce initial cache misses.

    Args:
        db_session: Database session
        limit: Maximum number of tenants to preload

    Returns:
        Number of tenants preloaded

    Example:
        # At application startup
        with get_db() as db:
            count = preload_tenants(db, limit=500)
            logger.info(f"Preloaded {count} tenants into cache")
    """
    if not REDIS_ENABLED:
        logger.info("Redis disabled, skipping tenant preload")
        return 0

    try:
        tenants = Tenant.get_active_tenants(db_session, limit=limit)
        count = 0

        for tenant in tenants:
            _set_tenant_in_cache(tenant.slack_team_id, tenant)
            count += 1

        logger.info(f"Preloaded {count} tenants into cache")
        return count

    except Exception as e:
        logger.error(f"Error preloading tenants: {e}", exc_info=True)
        return 0
