"""
Tenant-scoped database query helpers.

This module provides helper functions to ensure all database queries are
automatically filtered by tenant_id, preventing cross-tenant data leaks.

Key Functions:
- scoped_query(): Returns a query pre-filtered by current tenant
- create_scoped(): Create a new record with tenant_id auto-populated
- verify_tenant_access(): Verify a resource belongs to current tenant

Security:
These helpers are critical for maintaining tenant isolation. Always use
scoped_query() instead of direct db.query() to prevent accidentally
accessing another tenant's data.

Example - BAD (security risk):
    meetings = db.query(MeetingSession).all()  # Returns ALL tenants' data!

Example - GOOD (tenant-scoped):
    meetings = scoped_query(MeetingSession, db).all()  # Only current tenant
"""

import logging
from typing import Type, TypeVar, Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session, Query

from src.middleware.tenant_context import get_current_tenant, get_current_tenant_id
from src.middleware.exceptions import (
    TenantContextError,
    TenantAccessDeniedError
)

logger = logging.getLogger(__name__)

# Type variable for generic model classes
T = TypeVar('T')


def scoped_query(model_class: Type[T], db_session: Session) -> Query:
    """
    Create a query pre-filtered by the current tenant.

    This is the primary function for tenant-scoped database queries.
    It automatically adds a WHERE clause filtering by tenant_id.

    Args:
        model_class: SQLAlchemy model class to query
        db_session: Database session

    Returns:
        Query object filtered by current tenant_id

    Raises:
        TenantContextError: If no tenant is set in context
        AttributeError: If model doesn't have tenant_id column

    Example:
        # Instead of: meetings = db.query(MeetingSession).all()
        meetings = scoped_query(MeetingSession, db).all()

        # With additional filters:
        recent_meetings = (
            scoped_query(MeetingSession, db)
            .filter(MeetingSession.created_at > last_week)
            .order_by(MeetingSession.created_at.desc())
            .limit(10)
            .all()
        )
    """
    try:
        tenant_id = get_current_tenant_id()
    except TenantContextError as e:
        logger.error(
            f"Attempted scoped query without tenant context: {model_class.__name__}",
            extra={'model': model_class.__name__}
        )
        raise

    # Verify model has tenant_id column
    if not hasattr(model_class, 'tenant_id'):
        raise AttributeError(
            f"Model {model_class.__name__} does not have a tenant_id column. "
            f"Cannot perform tenant-scoped query."
        )

    # Create query filtered by tenant_id
    query = db_session.query(model_class).filter(
        model_class.tenant_id == tenant_id
    )

    # Also filter out soft-deleted records (if model supports it)
    if hasattr(model_class, 'deleted_at'):
        query = query.filter(model_class.deleted_at.is_(None))

    logger.debug(
        f"Created scoped query for {model_class.__name__}",
        extra={
            'model': model_class.__name__,
            'tenant_id': str(tenant_id)
        }
    )

    return query


def create_scoped(
    model_class: Type[T],
    db_session: Session,
    **kwargs
) -> T:
    """
    Create a new model instance with tenant_id automatically set.

    This ensures that all new records are automatically associated with
    the current tenant, preventing accidentally creating records without
    tenant association.

    Args:
        model_class: SQLAlchemy model class to instantiate
        db_session: Database session
        **kwargs: Model attributes

    Returns:
        New model instance (not yet committed)

    Raises:
        TenantContextError: If no tenant is set in context
        AttributeError: If model doesn't have tenant_id column

    Example:
        # Instead of: meeting = MeetingSession(user_id=123, ...)
        meeting = create_scoped(
            MeetingSession,
            db,
            user_id=user_id,
            fathom_recording_id=recording_id,
            meeting_title="Client Call"
        )
        db.add(meeting)
        db.commit()
    """
    try:
        tenant_id = get_current_tenant_id()
    except TenantContextError as e:
        logger.error(
            f"Attempted to create record without tenant context: {model_class.__name__}",
            extra={'model': model_class.__name__}
        )
        raise

    # Verify model has tenant_id column
    if not hasattr(model_class, 'tenant_id'):
        raise AttributeError(
            f"Model {model_class.__name__} does not have a tenant_id column. "
            f"Cannot create tenant-scoped record."
        )

    # Prevent manual override of tenant_id (security)
    if 'tenant_id' in kwargs:
        provided_tenant_id = kwargs['tenant_id']
        if provided_tenant_id != tenant_id:
            logger.error(
                f"Attempted to create record with different tenant_id: "
                f"current={tenant_id}, provided={provided_tenant_id}",
                extra={
                    'model': model_class.__name__,
                    'current_tenant_id': str(tenant_id),
                    'provided_tenant_id': str(provided_tenant_id)
                }
            )
            raise TenantAccessDeniedError(
                resource_type=model_class.__name__,
                expected_tenant_id=str(tenant_id),
                actual_tenant_id=str(provided_tenant_id)
            )

    # Set tenant_id
    kwargs['tenant_id'] = tenant_id

    # Create instance
    instance = model_class(**kwargs)

    logger.debug(
        f"Created scoped instance: {model_class.__name__}",
        extra={
            'model': model_class.__name__,
            'tenant_id': str(tenant_id)
        }
    )

    return instance


def verify_tenant_access(
    resource: Any,
    raise_error: bool = True
) -> bool:
    """
    Verify that a resource belongs to the current tenant.

    This is a security check to ensure that a loaded resource actually
    belongs to the current tenant. Use this when loading resources by ID
    from user input to prevent tenant data leaks.

    Args:
        resource: Model instance to verify
        raise_error: Whether to raise exception on mismatch (default: True)

    Returns:
        True if resource belongs to current tenant, False otherwise

    Raises:
        TenantContextError: If no tenant is set in context
        TenantAccessDeniedError: If resource belongs to different tenant (when raise_error=True)

    Example:
        # User provides meeting_id in request
        meeting = db.query(MeetingSession).filter_by(id=meeting_id).first()

        # Verify it belongs to their tenant before using it
        if not verify_tenant_access(meeting, raise_error=False):
            return jsonify({'error': 'Access denied'}), 403

        # Or let it raise exception:
        verify_tenant_access(meeting)  # Raises TenantAccessDeniedError if mismatch
    """
    try:
        tenant_id = get_current_tenant_id()
    except TenantContextError as e:
        logger.error(
            "Attempted to verify tenant access without tenant context",
            extra={'resource_type': type(resource).__name__}
        )
        if raise_error:
            raise
        return False

    # Check if resource has tenant_id
    if not hasattr(resource, 'tenant_id'):
        logger.warning(
            f"Resource {type(resource).__name__} does not have tenant_id column",
            extra={'resource_type': type(resource).__name__}
        )
        return True  # Can't verify, assume OK

    # Check if tenant_id matches
    resource_tenant_id = resource.tenant_id
    if resource_tenant_id != tenant_id:
        logger.error(
            f"Tenant access violation: resource belongs to different tenant",
            extra={
                'resource_type': type(resource).__name__,
                'resource_id': str(getattr(resource, 'id', None)),
                'current_tenant_id': str(tenant_id),
                'resource_tenant_id': str(resource_tenant_id)
            }
        )

        if raise_error:
            raise TenantAccessDeniedError(
                resource_type=type(resource).__name__,
                resource_id=str(getattr(resource, 'id', None)),
                expected_tenant_id=str(tenant_id),
                actual_tenant_id=str(resource_tenant_id)
            )

        return False

    return True


def get_scoped_by_id(
    model_class: Type[T],
    db_session: Session,
    resource_id: Any,
    verify_access: bool = True
) -> Optional[T]:
    """
    Get a resource by ID with automatic tenant verification.

    Combines query + tenant verification in one call for convenience.

    Args:
        model_class: SQLAlchemy model class
        db_session: Database session
        resource_id: ID of resource to fetch
        verify_access: Whether to verify tenant access (default: True)

    Returns:
        Model instance or None if not found

    Raises:
        TenantContextError: If no tenant is set
        TenantAccessDeniedError: If resource belongs to different tenant

    Example:
        # Get meeting by ID with tenant verification
        meeting = get_scoped_by_id(MeetingSession, db, meeting_id)
        if not meeting:
            return jsonify({'error': 'Not found'}), 404
    """
    resource = scoped_query(model_class, db_session).filter(
        model_class.id == resource_id
    ).first()

    if resource and verify_access:
        verify_tenant_access(resource, raise_error=True)

    return resource


def bulk_verify_tenant_access(
    resources: list,
    raise_error: bool = True
) -> bool:
    """
    Verify that multiple resources belong to the current tenant.

    Args:
        resources: List of model instances to verify
        raise_error: Whether to raise exception on mismatch

    Returns:
        True if all resources belong to current tenant, False otherwise

    Raises:
        TenantAccessDeniedError: If any resource belongs to different tenant

    Example:
        meetings = db.query(MeetingSession).filter(
            MeetingSession.id.in_(meeting_ids)
        ).all()

        # Verify all belong to current tenant
        if not bulk_verify_tenant_access(meetings):
            return jsonify({'error': 'Access denied'}), 403
    """
    for resource in resources:
        if not verify_tenant_access(resource, raise_error=raise_error):
            return False

    return True


def count_scoped(model_class: Type[T], db_session: Session) -> int:
    """
    Count records for current tenant.

    Args:
        model_class: SQLAlchemy model class
        db_session: Database session

    Returns:
        Count of records belonging to current tenant

    Example:
        meeting_count = count_scoped(MeetingSession, db)
        print(f"Total meetings: {meeting_count}")
    """
    return scoped_query(model_class, db_session).count()


def delete_scoped(
    resource: T,
    db_session: Session,
    soft_delete: bool = True
) -> None:
    """
    Delete a resource with tenant verification.

    Args:
        resource: Model instance to delete
        db_session: Database session
        soft_delete: Use soft delete if model supports it (default: True)

    Raises:
        TenantAccessDeniedError: If resource belongs to different tenant

    Example:
        meeting = get_scoped_by_id(MeetingSession, db, meeting_id)
        delete_scoped(meeting, db)
        db.commit()
    """
    # Verify tenant access before deleting
    verify_tenant_access(resource, raise_error=True)

    # Perform soft delete if supported
    if soft_delete and hasattr(resource, 'deleted_at'):
        from datetime import datetime
        resource.deleted_at = datetime.utcnow()
        logger.info(
            f"Soft deleted {type(resource).__name__} {getattr(resource, 'id', None)}",
            extra={
                'resource_type': type(resource).__name__,
                'resource_id': str(getattr(resource, 'id', None)),
                'tenant_id': str(resource.tenant_id)
            }
        )
    else:
        # Hard delete
        db_session.delete(resource)
        logger.warning(
            f"Hard deleted {type(resource).__name__} {getattr(resource, 'id', None)}",
            extra={
                'resource_type': type(resource).__name__,
                'resource_id': str(getattr(resource, 'id', None)),
                'tenant_id': str(resource.tenant_id)
            }
        )


def update_scoped(
    resource: T,
    db_session: Session,
    **kwargs
) -> T:
    """
    Update a resource with tenant verification.

    Args:
        resource: Model instance to update
        db_session: Database session
        **kwargs: Attributes to update

    Returns:
        Updated resource

    Raises:
        TenantAccessDeniedError: If resource belongs to different tenant

    Example:
        meeting = get_scoped_by_id(MeetingSession, db, meeting_id)
        update_scoped(meeting, db, status='completed', notes='Great call!')
        db.commit()
    """
    # Verify tenant access before updating
    verify_tenant_access(resource, raise_error=True)

    # Prevent changing tenant_id (security)
    if 'tenant_id' in kwargs:
        logger.error(
            "Attempted to change tenant_id via update_scoped",
            extra={
                'resource_type': type(resource).__name__,
                'resource_id': str(getattr(resource, 'id', None))
            }
        )
        raise ValueError("Cannot change tenant_id of existing resource")

    # Update attributes
    for key, value in kwargs.items():
        if hasattr(resource, key):
            setattr(resource, key, value)

    logger.debug(
        f"Updated {type(resource).__name__} {getattr(resource, 'id', None)}",
        extra={
            'resource_type': type(resource).__name__,
            'resource_id': str(getattr(resource, 'id', None)),
            'updated_fields': list(kwargs.keys())
        }
    )

    return resource
