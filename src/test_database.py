#!/usr/bin/env python3
"""
Comprehensive database test script for Slack Fathom Crono multi-tenant architecture.

Tests:
- Database connection
- Table creation
- CRUD operations on all models
- Relationships between models
- Tenant isolation
- Soft delete functionality
- Query methods
"""

import sys
from datetime import datetime, timedelta
from uuid import uuid4
from decimal import Decimal

from sqlalchemy import inspect

# Import database and models
from database import engine, get_db, check_connection, get_database_info
from models import (
    Base, Tenant, User, CRMConnection, MeetingSession,
    AccountMapping, AuditLog, APIRateLimit
)


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_test(test_name: str):
    """Print test name."""
    print(f"\n{Colors.BLUE}► Testing: {test_name}{Colors.RESET}")


def print_success(message: str):
    """Print success message."""
    print(f"  {Colors.GREEN}✓ {message}{Colors.RESET}")


def print_error(message: str):
    """Print error message."""
    print(f"  {Colors.RED}✗ {message}{Colors.RESET}")


def print_info(message: str):
    """Print info message."""
    print(f"  {Colors.YELLOW}ℹ {message}{Colors.RESET}")


def test_database_connection():
    """Test database connection."""
    print_test("Database Connection")

    # Print database info
    info = get_database_info()
    print_info(f"Database URL: {info['url']}")
    print_info(f"Pool size: {info['pool_size']}")

    # Check connection
    if check_connection():
        print_success("Database connection successful")
        return True
    else:
        print_error("Database connection failed")
        return False


def test_table_creation():
    """Test table creation."""
    print_test("Table Creation")

    try:
        # Create all tables
        Base.metadata.create_all(bind=engine)
        print_success("All tables created successfully")

        # Verify tables exist
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        expected_tables = [
            'tenants', 'users', 'crm_connections', 'meeting_sessions',
            'account_mappings', 'audit_logs', 'api_rate_limits'
        ]

        for table in expected_tables:
            if table in tables:
                print_success(f"Table '{table}' exists")
            else:
                print_error(f"Table '{table}' missing")
                return False

        return True

    except Exception as e:
        print_error(f"Table creation failed: {e}")
        return False


def test_tenant_crud():
    """Test Tenant model CRUD operations."""
    print_test("Tenant Model CRUD")

    try:
        with get_db() as db:
            # CREATE
            tenant = Tenant(
                slack_team_id="T0123456789",
                slack_team_name="Test Workspace",
                slack_team_domain="test.slack.com",
                plan_tier="pro",
                subscription_status="active",
                timezone="Europe/Rome",
                locale="it"
            )
            db.add(tenant)
            db.flush()
            tenant_id = tenant.id
            print_success(f"Created tenant: {tenant_id}")

            # READ
            found_tenant = Tenant.get_by_id(db, tenant_id)
            assert found_tenant is not None
            assert found_tenant.slack_team_id == "T0123456789"
            print_success(f"Read tenant: {found_tenant.slack_team_name}")

            # UPDATE
            found_tenant.plan_tier = "enterprise"
            db.flush()
            updated_tenant = Tenant.get_by_id(db, tenant_id)
            assert updated_tenant.plan_tier == "enterprise"
            print_success("Updated tenant plan tier")

            # Test query methods
            tenant_by_slack_id = Tenant.get_by_slack_team_id(db, "T0123456789")
            assert tenant_by_slack_id is not None
            print_success("Query by Slack team ID works")

            # SOFT DELETE
            found_tenant.soft_delete()
            db.flush()
            deleted_tenant = Tenant.get_by_id(db, tenant_id, include_deleted=True)
            assert deleted_tenant.is_deleted
            print_success("Soft delete works")

            # Verify not returned in normal queries
            normal_query = Tenant.get_by_id(db, tenant_id)
            assert normal_query is None
            print_success("Soft-deleted tenant excluded from normal queries")

            db.rollback()  # Rollback for clean slate

        return True

    except Exception as e:
        print_error(f"Tenant CRUD failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_relationships():
    """Test relationships between models."""
    print_test("Model Relationships")

    try:
        with get_db() as db:
            # Create tenant
            tenant = Tenant(
                slack_team_id="T_REL_TEST",
                slack_team_name="Relationship Test Workspace",
                plan_tier="pro"
            )
            db.add(tenant)
            db.flush()

            # Create user
            user = User(
                tenant_id=tenant.id,
                slack_user_id="U_TEST_001",
                slack_email="test@example.com",
                slack_real_name="Test User",
                role="admin"
            )
            db.add(user)
            db.flush()
            print_success(f"Created user: {user.slack_email}")

            # Verify tenant → user relationship
            assert len(tenant.users) == 1
            assert tenant.users[0].id == user.id
            print_success("Tenant → Users relationship works")

            # Create CRM connection
            crm_conn = CRMConnection(
                tenant_id=tenant.id,
                provider_type="hubspot",
                connection_name="Test HubSpot",
                credentials_secret_id="arn:aws:secretsmanager:test",
                connected_by_user_id=user.id,
                is_default=True
            )
            db.add(crm_conn)
            db.flush()
            print_success(f"Created CRM connection: {crm_conn.provider_type}")

            # Verify tenant → crm_connections relationship
            assert len(tenant.crm_connections) == 1
            print_success("Tenant → CRM Connections relationship works")

            # Verify user → crm_connections relationship
            assert len(user.created_crm_connections) == 1
            print_success("User → Created CRM Connections relationship works")

            # Create meeting session
            meeting = MeetingSession(
                tenant_id=tenant.id,
                user_id=user.id,
                crm_connection_id=crm_conn.id,
                fathom_recording_id="fathom_test_001",
                fathom_meeting_title="Test Meeting",
                processing_status="completed"
            )
            db.add(meeting)
            db.flush()
            print_success(f"Created meeting: {meeting.fathom_meeting_title}")

            # Verify relationships
            assert len(user.meeting_sessions) == 1
            assert len(tenant.meeting_sessions) == 1
            print_success("Meeting Session relationships work")

            # Create account mapping
            mapping = AccountMapping(
                tenant_id=tenant.id,
                crm_connection_id=crm_conn.id,
                email_domain="example.com",
                crm_account_id="acc_123",
                crm_account_name="Example Corp",
                mapping_source="manual",
                verified=True,
                created_by_user_id=user.id
            )
            db.add(mapping)
            db.flush()
            print_success(f"Created account mapping: {mapping.email_domain}")

            # Create audit log
            audit = AuditLog.log_event(
                session=db,
                tenant_id=tenant.id,
                user_id=user.id,
                event_type="test.event",
                event_category="integration",
                action_description="Test event",
                status="success"
            )
            print_success(f"Created audit log: {audit.event_type}")

            # Create rate limit
            rate_limit = APIRateLimit.get_or_create(
                session=db,
                tenant_id=tenant.id,
                resource_type="meetings_processed",
                limit_period="daily",
                limit_value=100
            )
            print_success(f"Created rate limit: {rate_limit.resource_type}")

            db.rollback()  # Rollback for clean slate

        return True

    except Exception as e:
        print_error(f"Relationship test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tenant_isolation():
    """Test tenant isolation (queries filtered by tenant_id)."""
    print_test("Tenant Isolation")

    try:
        with get_db() as db:
            # Create two tenants
            tenant1 = Tenant(
                slack_team_id="T_ISO_001",
                slack_team_name="Tenant 1",
                plan_tier="pro"
            )
            tenant2 = Tenant(
                slack_team_id="T_ISO_002",
                slack_team_name="Tenant 2",
                plan_tier="pro"
            )
            db.add_all([tenant1, tenant2])
            db.flush()

            # Create users for each tenant
            user1 = User(
                tenant_id=tenant1.id,
                slack_user_id="U_ISO_001",
                slack_email="user1@tenant1.com"
            )
            user2 = User(
                tenant_id=tenant2.id,
                slack_user_id="U_ISO_002",
                slack_email="user2@tenant2.com"
            )
            db.add_all([user1, user2])
            db.flush()

            # Verify tenant1 only sees its users
            tenant1_users = User.get_tenant_users(db, tenant1.id)
            assert len(tenant1_users) == 1
            assert tenant1_users[0].slack_email == "user1@tenant1.com"
            print_success("Tenant 1 sees only its own users")

            # Verify tenant2 only sees its users
            tenant2_users = User.get_tenant_users(db, tenant2.id)
            assert len(tenant2_users) == 1
            assert tenant2_users[0].slack_email == "user2@tenant2.com"
            print_success("Tenant 2 sees only its own users")

            # Test cross-tenant query should return nothing
            cross_tenant_query = User.get_by_slack_user_id(
                db, tenant1.id, "U_ISO_002"  # tenant1 looking for tenant2's user
            )
            assert cross_tenant_query is None
            print_success("Cross-tenant queries properly isolated")

            db.rollback()

        return True

    except Exception as e:
        print_error(f"Tenant isolation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_query_methods():
    """Test various query methods on models."""
    print_test("Query Methods")

    try:
        with get_db() as db:
            # Create test data
            tenant = Tenant(
                slack_team_id="T_QUERY_TEST",
                slack_team_name="Query Test Workspace",
                plan_tier="enterprise"
            )
            db.add(tenant)
            db.flush()

            # Create multiple users
            for i in range(5):
                user = User(
                    tenant_id=tenant.id,
                    slack_user_id=f"U_QUERY_{i:03d}",
                    slack_email=f"user{i}@test.com",
                    role="admin" if i == 0 else "member"
                )
                db.add(user)
            db.flush()

            # Test get_all
            all_users = User.get_tenant_users(db, tenant.id)
            assert len(all_users) == 5
            print_success(f"get_tenant_users returned {len(all_users)} users")

            # Test get_admins
            admins = User.get_admins(db, tenant.id)
            assert len(admins) == 1
            print_success(f"get_admins returned {len(admins)} admin")

            # Test count
            user_count = db.query(User).filter(
                User.tenant_id == tenant.id
            ).count()
            assert user_count == 5
            print_success(f"Count returned {user_count} users")

            db.rollback()

        return True

    except Exception as e:
        print_error(f"Query methods test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_rate_limiting():
    """Test rate limiting functionality."""
    print_test("Rate Limiting")

    try:
        with get_db() as db:
            # Create tenant
            tenant = Tenant(
                slack_team_id="T_RATE_TEST",
                slack_team_name="Rate Limit Test",
                plan_tier="pro"
            )
            db.add(tenant)
            db.flush()

            # Test rate limit creation
            is_allowed, rate_limit = APIRateLimit.check_limit(
                db, tenant.id, "meetings_processed", "daily", 10
            )
            assert is_allowed is True
            assert rate_limit.remaining == 10
            print_success("Rate limit created successfully")

            # Test incrementing
            for i in range(8):
                success, rate_limit = APIRateLimit.increment_usage(
                    db, tenant.id, "meetings_processed", "daily", 10
                )
                assert success is True

            assert rate_limit.current_count == 8
            assert rate_limit.remaining == 2
            print_success(f"Incremented to {rate_limit.current_count}/10")

            # Test hitting the limit
            APIRateLimit.increment_usage(db, tenant.id, "meetings_processed", "daily", 10)
            APIRateLimit.increment_usage(db, tenant.id, "meetings_processed", "daily", 10)

            # Should be at limit now
            is_allowed, rate_limit = APIRateLimit.check_limit(
                db, tenant.id, "meetings_processed", "daily", 10
            )
            assert rate_limit.is_exceeded
            print_success("Rate limit exceeded correctly detected")

            # Test trying to increment when exceeded
            success, rate_limit = APIRateLimit.increment_usage(
                db, tenant.id, "meetings_processed", "daily", 10
            )
            assert success is False
            print_success("Increment blocked when limit exceeded")

            db.rollback()

        return True

    except Exception as e:
        print_error(f"Rate limiting test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_audit_logging():
    """Test audit logging functionality."""
    print_test("Audit Logging")

    try:
        with get_db() as db:
            # Create tenant and user
            tenant = Tenant(
                slack_team_id="T_AUDIT_TEST",
                slack_team_name="Audit Test",
                plan_tier="pro"
            )
            db.add(tenant)
            db.flush()

            user = User(
                tenant_id=tenant.id,
                slack_user_id="U_AUDIT_001",
                slack_email="audit@test.com"
            )
            db.add(user)
            db.flush()

            # Create various audit logs
            events = [
                ("user.login", "authentication", "success"),
                ("crm.note.created", "integration", "success"),
                ("setting.changed", "configuration", "success"),
                ("crm.api.failed", "integration", "failure"),
            ]

            for event_type, category, status in events:
                AuditLog.log_event(
                    session=db,
                    tenant_id=tenant.id,
                    user_id=user.id,
                    event_type=event_type,
                    event_category=category,
                    action_description=f"Test {event_type}",
                    status=status
                )
            db.flush()
            print_success(f"Created {len(events)} audit log entries")

            # Test querying logs
            tenant_logs = AuditLog.get_tenant_logs(db, tenant.id, days=1)
            assert len(tenant_logs) == 4
            print_success(f"Retrieved {len(tenant_logs)} tenant logs")

            # Test filtering by category
            integration_logs = AuditLog.get_tenant_logs(
                db, tenant.id, event_category="integration", days=1
            )
            assert len(integration_logs) == 2
            print_success(f"Filtered logs by category: {len(integration_logs)}")

            # Test failure logs
            failures = AuditLog.get_recent_failures(db, tenant.id, hours=1)
            assert len(failures) == 1
            print_success(f"Retrieved failure logs: {len(failures)}")

            # Test immutability (should raise error)
            try:
                tenant_logs[0].soft_delete()
                print_error("Audit logs should be immutable!")
                return False
            except NotImplementedError:
                print_success("Audit logs are immutable (cannot be deleted)")

            db.rollback()

        return True

    except Exception as e:
        print_error(f"Audit logging test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all database tests."""
    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}Slack Fathom Crono - Database Test Suite{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*70}{Colors.RESET}")

    tests = [
        ("Database Connection", test_database_connection),
        ("Table Creation", test_table_creation),
        ("Tenant CRUD", test_tenant_crud),
        ("Model Relationships", test_relationships),
        ("Tenant Isolation", test_tenant_isolation),
        ("Query Methods", test_query_methods),
        ("Rate Limiting", test_rate_limiting),
        ("Audit Logging", test_audit_logging),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print_error(f"Test '{test_name}' crashed: {e}")
            results.append((test_name, False))

    # Print summary
    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}Test Summary{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*70}{Colors.RESET}")

    passed = sum(1 for _, result in results if result)
    failed = len(results) - passed

    for test_name, result in results:
        status = f"{Colors.GREEN}PASS{Colors.RESET}" if result else f"{Colors.RED}FAIL{Colors.RESET}"
        print(f"  {status} - {test_name}")

    print(f"\n{Colors.BOLD}Total: {len(results)} | Passed: {Colors.GREEN}{passed}{Colors.RESET} | Failed: {Colors.RED}{failed}{Colors.RESET}{Colors.BOLD}{Colors.RESET}")

    if failed == 0:
        print(f"\n{Colors.GREEN}{Colors.BOLD}✓ All tests passed!{Colors.RESET}")
        return 0
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}✗ Some tests failed!{Colors.RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
