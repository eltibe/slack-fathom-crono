"""
Database models package for Slack Fathom Crono multi-tenant application.

This package contains all SQLAlchemy ORM models for the application:
- Tenant: Slack workspaces (root of tenant hierarchy)
- User: Slack users within workspaces
- CRMConnection: CRM provider integrations
- MeetingSession: Meeting processing history
- AccountMapping: Domain to CRM account mappings
- AuditLog: Security and compliance audit trail
- APIRateLimit: Rate limiting tracking

All models use UUID primary keys, automatic timestamps, and support soft deletes.
"""

from src.models.base import Base, BaseModel
from src.models.tenant import Tenant
from src.models.user import User
from src.models.crm_connection import CRMConnection
from src.models.meeting_session import MeetingSession
from src.models.account_mapping import AccountMapping
from src.models.audit_log import AuditLog
from src.models.api_rate_limit import APIRateLimit
from src.models.user_settings import UserSettings
from src.models.conversation_state import ConversationState

# Export all models for convenience
__all__ = [
    "Base",
    "BaseModel",
    "Tenant",
    "User",
    "CRMConnection",
    "MeetingSession",
    "AccountMapping",
    "AuditLog",
    "APIRateLimit",
    "UserSettings",
    "ConversationState",
]


def create_all(engine):
    """
    Create all database tables.

    WARNING: This should only be used for testing/development.
    Use Alembic migrations for production.

    Args:
        engine: SQLAlchemy engine instance

    Example:
        from sqlalchemy import create_engine
        from src.models import create_all

        engine = create_engine("postgresql://...")
        create_all(engine)
    """
    Base.metadata.create_all(bind=engine)
    print("✓ All database tables created successfully")


def drop_all(engine):
    """
    Drop all database tables.

    WARNING: This is destructive and should only be used in testing.

    Args:
        engine: SQLAlchemy engine instance

    Example:
        from sqlalchemy import create_engine
        from src.models import drop_all

        engine = create_engine("postgresql://...")
        drop_all(engine)
    """
    Base.metadata.drop_all(bind=engine)
    print("✓ All database tables dropped")


def get_model_by_name(model_name: str):
    """
    Get a model class by its name.

    Args:
        model_name: Name of the model (e.g., 'Tenant', 'User')

    Returns:
        Model class or None if not found

    Example:
        Tenant = get_model_by_name('Tenant')
        tenants = session.query(Tenant).all()
    """
    models = {
        "Tenant": Tenant,
        "User": User,
        "CRMConnection": CRMConnection,
        "MeetingSession": MeetingSession,
        "AccountMapping": AccountMapping,
        "AuditLog": AuditLog,
        "APIRateLimit": APIRateLimit,
        "UserSettings": UserSettings,
        "ConversationState": ConversationState,
    }
    return models.get(model_name)


def list_all_models():
    """
    Get a list of all model classes.

    Returns:
        List of model classes

    Example:
        models = list_all_models()
        for model in models:
            print(f"Model: {model.__name__}, Table: {model.__tablename__}")
    """
    return [
        Tenant,
        User,
        CRMConnection,
        MeetingSession,
        AccountMapping,
        AuditLog,
        APIRateLimit,
        UserSettings,
        ConversationState,
    ]


def get_model_info():
    """
    Get information about all models.

    Returns:
        Dictionary with model information

    Example:
        info = get_model_info()
        for model_name, details in info.items():
            print(f"{model_name}: {details['table_name']}")
    """
    models = list_all_models()
    info = {}

    for model in models:
        info[model.__name__] = {
            "table_name": model.__tablename__,
            "columns": [col.name for col in model.__table__.columns],
            "primary_key": [col.name for col in model.__table__.primary_key.columns],
        }

    return info


# Module-level metadata
__version__ = "1.0.0"
__author__ = "Slack Fathom Crono Team"
