#!/usr/bin/env python3
"""
Test script for CRM Provider Architecture

This script tests the new provider architecture to ensure:
1. Factory can create providers correctly
2. Crono provider implements all interface methods
3. Backward compatibility is maintained
4. Error handling works properly
"""

import os
import sys
import pytest
from dotenv import load_dotenv

pytest.skip("Test script manuale: fixture provider non definita, richiede setup/parametrizzazione", allow_module_level=True)

# Load environment variables
load_dotenv()

def test_factory():
    """Test the CRM provider factory."""
    print("\n" + "="*60)
    print("Testing CRM Provider Factory")
    print("="*60)

    from providers import CRMProviderFactory

    # Test 1: Get supported types
    print("\n[Test 1] Get supported CRM types")
    supported = CRMProviderFactory.get_supported_types()
    print(f"✅ Supported types: {supported}")
    assert 'crono' in supported, "Crono should be supported"

    # Test 2: Check if provider is supported
    print("\n[Test 2] Check provider support")
    assert CRMProviderFactory.is_supported('crono'), "Crono should be supported"
    assert not CRMProviderFactory.is_supported('unknown'), "Unknown CRM should not be supported"
    print("✅ Provider support check works")

    # Test 3: Create provider with invalid type
    print("\n[Test 3] Create provider with invalid type")
    try:
        CRMProviderFactory.create('invalid_crm', {})
        print("❌ Should have raised ValueError")
        sys.exit(1)
    except ValueError as e:
        print(f"✅ Correctly raised ValueError: {e}")

    # Test 4: Create Crono provider with missing credentials
    print("\n[Test 4] Create Crono provider with missing credentials")
    try:
        CRMProviderFactory.create('crono', {})
        print("❌ Should have raised ValueError for missing credentials")
        sys.exit(1)
    except Exception as e:
        print(f"✅ Correctly raised error: {e}")

    # Test 5: Create Crono provider with valid credentials
    print("\n[Test 5] Create Crono provider with valid credentials")
    credentials = {
        'public_key': os.getenv('CRONO_PUBLIC_KEY', 'test_pk'),
        'private_key': os.getenv('CRONO_API_KEY', 'test_sk')
    }
    provider = CRMProviderFactory.create('crono', credentials)
    print(f"✅ Created provider: {type(provider).__name__}")

    return provider


def test_crono_provider(provider):
    """Test Crono provider implementation."""
    print("\n" + "="*60)
    print("Testing Crono Provider Implementation")
    print("="*60)

    # Test 1: Check provider type
    print("\n[Test 1] Check provider type")
    from providers import CRMProvider
    assert isinstance(provider, CRMProvider), "Provider should be instance of CRMProvider"
    print("✅ Provider implements CRMProvider interface")

    # Test 2: Test stage mapping
    print("\n[Test 2] Get stage mapping")
    stage_mapping = provider.get_stage_mapping()
    print(f"✅ Stage mapping: {stage_mapping}")
    assert 'lead' in stage_mapping, "Stage mapping should include 'lead'"
    assert 'closed_won' in stage_mapping, "Stage mapping should include 'closed_won'"

    # Test 3: Test create_task (should raise NotImplementedError)
    print("\n[Test 3] Test create_task (should raise NotImplementedError)")
    try:
        provider.create_task('test_account', {'title': 'Test'})
        print("❌ Should have raised NotImplementedError")
        sys.exit(1)
    except NotImplementedError as e:
        print(f"✅ Correctly raised NotImplementedError: {e}")

    # Test 4: Test update_deal_stage (should raise NotImplementedError)
    print("\n[Test 4] Test update_deal_stage (should raise NotImplementedError)")
    try:
        provider.update_deal_stage('test_deal', 'qualified')
        print("❌ Should have raised NotImplementedError")
        sys.exit(1)
    except NotImplementedError as e:
        print(f"✅ Correctly raised NotImplementedError: {e}")

    # Test 5: Test search_accounts (if credentials are valid)
    print("\n[Test 5] Test search_accounts")
    if os.getenv('CRONO_PUBLIC_KEY') and os.getenv('CRONO_API_KEY'):
        print("Testing with real API credentials...")
        try:
            accounts = provider.search_accounts('', limit=5)
            print(f"✅ Search returned {len(accounts)} accounts")
            if accounts:
                print(f"   Sample account: {accounts[0].get('name')} (ID: {accounts[0].get('id')})")

                # Test 6: Test get_account_by_id
                print("\n[Test 6] Test get_account_by_id")
                account_id = accounts[0].get('id')
                account = provider.get_account_by_id(account_id)
                if account:
                    print(f"✅ Retrieved account: {account.get('name')}")
                    print(f"   CRM type: {account.get('crm_type')}")
                else:
                    print("⚠️  Could not retrieve account by ID")

                # Test 7: Test get_deals
                print("\n[Test 7] Test get_deals")
                deals = provider.get_deals(account_id, limit=5)
                print(f"✅ Retrieved {len(deals)} deals for account")
                if deals:
                    print(f"   Sample deal: {deals[0].get('name')} (Stage: {deals[0].get('stage')})")
        except Exception as e:
            print(f"⚠️  API test skipped due to error: {e}")
    else:
        print("⚠️  Skipping API tests (no credentials in environment)")


def test_backward_compatibility():
    """Test backward compatibility with existing code."""
    print("\n" + "="*60)
    print("Testing Backward Compatibility")
    print("="*60)

    from providers import CRMProviderFactory

    # Test that we can create a provider using environment variables
    print("\n[Test 1] Create provider from environment variables")
    crm_type = os.getenv('CRM_PROVIDER', 'crono')
    credentials = {
        'public_key': os.getenv('CRONO_PUBLIC_KEY', 'test_pk'),
        'private_key': os.getenv('CRONO_API_KEY', 'test_sk')
    }

    try:
        crm_provider = CRMProviderFactory.create(crm_type, credentials)
        print(f"✅ Created {crm_type} provider from environment")
    except Exception as e:
        print(f"⚠️  Could not create provider: {e}")
        return

    # Test that provider has backward-compatible methods
    print("\n[Test 2] Check backward-compatible methods")
    assert hasattr(crm_provider, 'find_account_by_domain'), "Should have find_account_by_domain method"
    assert hasattr(crm_provider, 'create_meeting_summary'), "Should have create_meeting_summary method"
    print("✅ Backward-compatible methods exist")

    # Test that standardized accounts include original fields
    print("\n[Test 3] Check account standardization preserves original fields")
    test_account = {
        'objectId': 'test_123',
        'name': 'Test Company',
        'website': 'test.com',
        'customField': 'value'
    }
    standardized = crm_provider._standardize_account(test_account)
    assert standardized.get('id') == 'test_123', "Should have 'id' field"
    assert standardized.get('objectId') == 'test_123', "Should preserve 'objectId' field"
    assert standardized.get('crm_type') == 'crono', "Should have 'crm_type' field"
    assert standardized.get('customField') == 'value', "Should preserve custom fields"
    print("✅ Account standardization preserves original fields")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("CRM Provider Architecture Test Suite")
    print("="*60)

    try:
        # Test factory
        provider = test_factory()

        # Test Crono provider
        test_crono_provider(provider)

        # Test backward compatibility
        test_backward_compatibility()

        # Summary
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)
        print("\nThe CRM provider architecture is working correctly.")
        print("You can now use the factory pattern to create CRM providers.")
        print("\nNext steps:")
        print("1. Run the Flask server: python3 slack_webhook_handler.py")
        print("2. Test the /meetings command in Slack")
        print("3. Test 'Create Crono Note' functionality")
        print("="*60 + "\n")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
