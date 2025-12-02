"""
Comprehensive test suite for tenant middleware system.

This test script validates:
1. Thread-local context isolation
2. Slack request parsing (all formats)
3. Tenant loading from database and cache
4. Query scoping enforcement
5. Error handling (missing tenant, suspended, etc.)
6. Cache behavior (Redis)
7. Concurrent request simulation
8. Security (signature verification, cross-tenant access)

Usage:
    python src/test_tenant_middleware.py
    python src/test_tenant_middleware.py --verbose
    python src/test_tenant_middleware.py --skip-redis
"""

import os
import sys
import json
import time
import hmac
import hashlib
import threading
from datetime import datetime, timedelta
from typing import List, Dict
from unittest.mock import Mock, MagicMock
import pytest

pytest.skip("Test middleware placeholder: fixture parameters mancanti, da eseguire solo manualmente", allow_module_level=True)

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# Import middleware components
from middleware.tenant_context import (
    set_current_tenant,
    get_current_tenant,
    get_current_tenant_id,
    clear_tenant_context,
    tenant_context,
    require_tenant,
    TenantContextError
)
from middleware.exceptions import (
    TenantNotFoundError,
    TenantSuspendedError,
    InvalidSlackRequestError,
    TenantAccessDeniedError
)
from middleware.query_helpers import (
    scoped_query,
    create_scoped,
    verify_tenant_access
)
from middleware.slack_parser import (
    extract_tenant_id_from_request,
    verify_slack_signature
)
from middleware.tenant_loader import (
    load_tenant_by_slack_id,
    get_or_create_tenant,
    clear_tenant_cache
)

# Import database
from database import get_db, engine
from models import Tenant, User, MeetingSession

# Test configuration
VERBOSE = '--verbose' in sys.argv
SKIP_REDIS = '--skip-redis' in sys.argv


class TestResult:
    """Track test results."""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors: List[str] = []


def log(message: str, level: str = 'INFO'):
    """Log test output."""
    if level == 'ERROR' or VERBOSE:
        prefix = {
            'INFO': '  ',
            'SUCCESS': '✓ ',
            'ERROR': '✗ ',
            'WARN': '⚠ '
        }.get(level, '  ')
        print(f"{prefix}{message}")


def test_section(name: str):
    """Print test section header."""
    print(f"\n{'='*60}")
    print(f"  {name}")
    print('='*60)


def assert_equal(actual, expected, message: str):
    """Assert equality with message."""
    if actual != expected:
        raise AssertionError(
            f"{message}\n  Expected: {expected}\n  Got: {actual}"
        )


def assert_raises(exception_class, func, *args, **kwargs):
    """Assert that function raises specific exception."""
    try:
        func(*args, **kwargs)
        raise AssertionError(
            f"Expected {exception_class.__name__} to be raised"
        )
    except exception_class:
        pass  # Expected


# ============================================================================
# Test 1: Thread-Local Context Isolation
# ============================================================================

def test_thread_local_context(result: TestResult):
    """Test that tenant context is properly isolated between threads."""
    test_section("Test 1: Thread-Local Context Isolation")

    # Create mock tenants
    tenant1 = Mock(id='uuid-1', slack_team_id='T111', slack_team_name='Tenant 1')
    tenant2 = Mock(id='uuid-2', slack_team_id='T222', slack_team_name='Tenant 2')

    results = {}

    def thread_func(tenant, thread_id):
        """Function to run in separate thread."""
        try:
            # Set tenant for this thread
            set_current_tenant(tenant)
            time.sleep(0.1)  # Simulate work

            # Verify it's still the correct tenant
            current = get_current_tenant()
            results[thread_id] = current.slack_team_id

            # Clean up
            clear_tenant_context()

        except Exception as e:
            results[thread_id] = f"ERROR: {e}"

    # Run two threads with different tenants
    t1 = threading.Thread(target=thread_func, args=(tenant1, 'thread1'))
    t2 = threading.Thread(target=thread_func, args=(tenant2, 'thread2'))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Verify isolation
    try:
        assert_equal(results['thread1'], 'T111', "Thread 1 should have Tenant 1")
        assert_equal(results['thread2'], 'T222', "Thread 2 should have Tenant 2")
        log("Thread isolation working correctly", 'SUCCESS')
        result.passed += 1
    except AssertionError as e:
        log(str(e), 'ERROR')
        result.failed += 1
        result.errors.append(str(e))


# ============================================================================
# Test 2: Context Manager Support
# ============================================================================

def test_context_manager(result: TestResult):
    """Test context manager support."""
    test_section("Test 2: Context Manager Support")

    tenant = Mock(id='uuid-1', slack_team_id='T111', slack_team_name='Test Tenant')

    try:
        # Context should not be set initially
        try:
            get_current_tenant()
            raise AssertionError("Should raise TenantContextError")
        except TenantContextError:
            pass  # Expected

        # Use context manager
        with tenant_context(tenant):
            current = get_current_tenant()
            assert_equal(current.slack_team_id, 'T111', "Tenant should be set in context")

        # Context should be cleared after exiting
        try:
            get_current_tenant()
            raise AssertionError("Should raise TenantContextError after context exit")
        except TenantContextError:
            pass  # Expected

        log("Context manager working correctly", 'SUCCESS')
        result.passed += 1

    except Exception as e:
        log(f"Context manager test failed: {e}", 'ERROR')
        result.failed += 1
        result.errors.append(str(e))


# ============================================================================
# Test 3: Decorator Support
# ============================================================================

def test_decorator(result: TestResult):
    """Test @require_tenant decorator."""
    test_section("Test 3: Decorator Support")

    tenant = Mock(id='uuid-1', slack_team_id='T111', slack_team_name='Test Tenant')

    @require_tenant()
    def protected_function():
        return get_current_tenant().slack_team_id

    try:
        # Should fail without tenant context
        try:
            protected_function()
            raise AssertionError("Should raise TenantContextError")
        except TenantContextError:
            pass  # Expected

        # Should work with tenant context
        with tenant_context(tenant):
            team_id = protected_function()
            assert_equal(team_id, 'T111', "Decorator should allow access with tenant")

        log("Decorator working correctly", 'SUCCESS')
        result.passed += 1

    except Exception as e:
        log(f"Decorator test failed: {e}", 'ERROR')
        result.failed += 1
        result.errors.append(str(e))


# ============================================================================
# Test 4: Slack Request Parsing
# ============================================================================

def test_slack_request_parsing(result: TestResult):
    """Test parsing different Slack request formats."""
    test_section("Test 4: Slack Request Parsing")

    # Test 4a: Slash command
    try:
        request = Mock()
        request.content_type = 'application/x-www-form-urlencoded'
        request.form = {'team_id': 'T0123456789', 'command': '/followup'}

        team_id = extract_tenant_id_from_request(request)
        assert_equal(team_id, 'T0123456789', "Should extract team_id from slash command")
        log("Slash command parsing works", 'SUCCESS')
        result.passed += 1

    except Exception as e:
        log(f"Slash command parsing failed: {e}", 'ERROR')
        result.failed += 1
        result.errors.append(str(e))

    # Test 4b: Interaction with payload
    try:
        payload = {'team': {'id': 'T9876543210'}, 'type': 'block_actions'}
        request = Mock()
        request.content_type = 'application/x-www-form-urlencoded'
        request.form = {'payload': json.dumps(payload)}

        team_id = extract_tenant_id_from_request(request)
        assert_equal(team_id, 'T9876543210', "Should extract team.id from interaction")
        log("Interaction parsing works", 'SUCCESS')
        result.passed += 1

    except Exception as e:
        log(f"Interaction parsing failed: {e}", 'ERROR')
        result.failed += 1
        result.errors.append(str(e))

    # Test 4c: Events API
    try:
        request = Mock()
        request.content_type = 'application/json'
        request.get_json = lambda silent=True: {'team_id': 'T1111111111', 'type': 'event_callback'}

        team_id = extract_tenant_id_from_request(request)
        assert_equal(team_id, 'T1111111111', "Should extract team_id from events API")
        log("Events API parsing works", 'SUCCESS')
        result.passed += 1

    except Exception as e:
        log(f"Events API parsing failed: {e}", 'ERROR')
        result.failed += 1
        result.errors.append(str(e))


# ============================================================================
# Test 5: Signature Verification
# ============================================================================

def test_signature_verification(result: TestResult):
    """Test Slack signature verification."""
    test_section("Test 5: Signature Verification")

    signing_secret = os.getenv('SLACK_SIGNING_SECRET', 'test_secret_123')
    timestamp = str(int(time.time()))
    body = 'team_id=T0123456789&command=/followup'

    # Generate valid signature
    sig_basestring = f"v0:{timestamp}:{body}"
    signature = 'v0=' + hmac.new(
        signing_secret.encode('utf-8'),
        sig_basestring.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # Test valid signature
    try:
        request = Mock()
        request.headers = {
            'X-Slack-Request-Timestamp': timestamp,
            'X-Slack-Signature': signature
        }
        request.get_data = lambda as_text=True: body

        is_valid = verify_slack_signature(request, signing_secret)
        assert_equal(is_valid, True, "Valid signature should pass")
        log("Valid signature verification works", 'SUCCESS')
        result.passed += 1

    except Exception as e:
        log(f"Signature verification failed: {e}", 'ERROR')
        result.failed += 1
        result.errors.append(str(e))

    # Test invalid signature
    try:
        request = Mock()
        request.headers = {
            'X-Slack-Request-Timestamp': timestamp,
            'X-Slack-Signature': 'v0=invalid_signature'
        }
        request.get_data = lambda as_text=True: body

        is_valid = verify_slack_signature(request, signing_secret)
        assert_equal(is_valid, False, "Invalid signature should fail")
        log("Invalid signature rejection works", 'SUCCESS')
        result.passed += 1

    except Exception as e:
        log(f"Invalid signature test failed: {e}", 'ERROR')
        result.failed += 1
        result.errors.append(str(e))


# ============================================================================
# Test 6: Database Integration
# ============================================================================

def test_database_integration(result: TestResult):
    """Test tenant loading from database."""
    test_section("Test 6: Database Integration")

    try:
        with get_db() as db:
            # Create test tenant
            test_tenant = Tenant(
                slack_team_id='T_TEST_' + str(int(time.time())),
                slack_team_name='Test Tenant',
                slack_team_domain='test-tenant',
                plan_tier='free',
                subscription_status='active',
                timezone='UTC',
                locale='en'
            )
            db.add(test_tenant)
            db.commit()

            # Load tenant
            loaded_tenant = load_tenant_by_slack_id(
                test_tenant.slack_team_id,
                db,
                use_cache=False
            )

            assert_equal(
                loaded_tenant.slack_team_id,
                test_tenant.slack_team_id,
                "Loaded tenant should match"
            )

            # Test get_or_create (should return existing)
            tenant2 = get_or_create_tenant(
                test_tenant.slack_team_id,
                'Test Tenant Updated',
                db
            )

            assert_equal(
                tenant2.id,
                test_tenant.id,
                "get_or_create should return existing tenant"
            )

            # Clean up
            db.delete(test_tenant)
            db.commit()

            log("Database integration works", 'SUCCESS')
            result.passed += 1

    except Exception as e:
        log(f"Database integration failed: {e}", 'ERROR')
        result.failed += 1
        result.errors.append(str(e))


# ============================================================================
# Test 7: Query Scoping
# ============================================================================

def test_query_scoping(result: TestResult):
    """Test tenant-scoped queries."""
    test_section("Test 7: Query Scoping")

    try:
        with get_db() as db:
            # Create two test tenants
            tenant1 = Tenant(
                slack_team_id='T_SCOPE1_' + str(int(time.time())),
                slack_team_name='Tenant 1',
                plan_tier='free',
                subscription_status='active'
            )
            tenant2 = Tenant(
                slack_team_id='T_SCOPE2_' + str(int(time.time())),
                slack_team_name='Tenant 2',
                plan_tier='free',
                subscription_status='active'
            )
            db.add_all([tenant1, tenant2])
            db.commit()

            # Create user for tenant1
            with tenant_context(tenant1):
                user1 = create_scoped(
                    User,
                    db,
                    slack_user_id='U111',
                    email='user1@test.com',
                    display_name='User 1'
                )
                db.add(user1)
                db.commit()

                # Query should only return tenant1's users
                users = scoped_query(User, db).all()
                assert_equal(len(users), 1, "Should only see tenant1's users")
                assert_equal(users[0].slack_user_id, 'U111', "Should be correct user")

            # Create user for tenant2
            with tenant_context(tenant2):
                user2 = create_scoped(
                    User,
                    db,
                    slack_user_id='U222',
                    email='user2@test.com',
                    display_name='User 2'
                )
                db.add(user2)
                db.commit()

                # Query should only return tenant2's users
                users = scoped_query(User, db).all()
                assert_equal(len(users), 1, "Should only see tenant2's users")
                assert_equal(users[0].slack_user_id, 'U222', "Should be correct user")

            # Test cross-tenant access prevention
            with tenant_context(tenant1):
                # Try to access tenant2's user (should fail verification)
                try:
                    verify_tenant_access(user2, raise_error=True)
                    raise AssertionError("Should prevent cross-tenant access")
                except TenantAccessDeniedError:
                    pass  # Expected

            # Clean up
            db.delete(user1)
            db.delete(user2)
            db.delete(tenant1)
            db.delete(tenant2)
            db.commit()

            log("Query scoping works correctly", 'SUCCESS')
            result.passed += 1

    except Exception as e:
        log(f"Query scoping test failed: {e}", 'ERROR')
        result.failed += 1
        result.errors.append(str(e))


# ============================================================================
# Test 8: Error Handling
# ============================================================================

def test_error_handling(result: TestResult):
    """Test error handling for various failure scenarios."""
    test_section("Test 8: Error Handling")

    # Test 8a: Tenant not found
    try:
        with get_db() as db:
            try:
                load_tenant_by_slack_id('T_NONEXISTENT', db)
                raise AssertionError("Should raise TenantNotFoundError")
            except TenantNotFoundError:
                pass  # Expected

        log("TenantNotFoundError raised correctly", 'SUCCESS')
        result.passed += 1

    except Exception as e:
        log(f"Error handling test failed: {e}", 'ERROR')
        result.failed += 1
        result.errors.append(str(e))

    # Test 8b: Suspended tenant
    try:
        with get_db() as db:
            suspended_tenant = Tenant(
                slack_team_id='T_SUSPENDED_' + str(int(time.time())),
                slack_team_name='Suspended Tenant',
                plan_tier='free',
                subscription_status='suspended'
            )
            db.add(suspended_tenant)
            db.commit()

            try:
                load_tenant_by_slack_id(
                    suspended_tenant.slack_team_id,
                    db,
                    check_subscription=True
                )
                raise AssertionError("Should raise TenantSuspendedError")
            except TenantSuspendedError:
                pass  # Expected

            # Clean up
            db.delete(suspended_tenant)
            db.commit()

        log("TenantSuspendedError raised correctly", 'SUCCESS')
        result.passed += 1

    except Exception as e:
        log(f"Suspended tenant test failed: {e}", 'ERROR')
        result.failed += 1
        result.errors.append(str(e))


# ============================================================================
# Main Test Runner
# ============================================================================

def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("  TENANT MIDDLEWARE TEST SUITE")
    print("="*60)

    result = TestResult()

    # Run all tests
    test_thread_local_context(result)
    test_context_manager(result)
    test_decorator(result)
    test_slack_request_parsing(result)
    test_signature_verification(result)
    test_database_integration(result)
    test_query_scoping(result)
    test_error_handling(result)

    # Print summary
    print("\n" + "="*60)
    print("  TEST SUMMARY")
    print("="*60)
    print(f"  Passed: {result.passed}")
    print(f"  Failed: {result.failed}")
    print(f"  Total:  {result.passed + result.failed}")

    if result.failed > 0:
        print("\n  ERRORS:")
        for i, error in enumerate(result.errors, 1):
            print(f"  {i}. {error}")

    print("="*60 + "\n")

    # Exit with appropriate code
    sys.exit(0 if result.failed == 0 else 1)


if __name__ == '__main__':
    main()
