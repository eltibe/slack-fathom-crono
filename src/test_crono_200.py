#!/usr/bin/env python3
from modules.crono_client import CronoClient
from dotenv import load_dotenv

load_dotenv()

try:
    print("🔍 Testing Crono account search for neuronup.com with limit=200...")
    crono = CronoClient()

    # Test 1: Search all accounts with limit 200
    print("\n📋 Fetching all accounts (limit 200)...")
    all_accounts = crono.search_accounts(limit=200)
    print(f"   Found {len(all_accounts)} accounts total")

    # Check if neuronup.com is in the list
    found = False
    for acc in all_accounts:
        website = acc.get('website', '') or acc.get('Website', '')
        name = acc.get('name', 'Unknown')
        if 'neuronup' in str(website).lower() or 'neuronup' in str(name).lower():
            print(f"\n✅ Found NeuronUP account!")
            print(f"   Name: {name}")
            print(f"   Website: {website}")
            print(f"   ObjectId: {acc.get('objectId')}")
            found = True
            break

    if not found:
        print("\n❌ No account with 'neuronup' found in first 200 accounts")

    # Test 2: Try find_account_by_domain
    print("\n🔍 Testing find_account_by_domain('neuronup.com')...")
    account = crono.find_account_by_domain('neuronup.com')

    if account:
        print(f"✅ Account found!")
        print(f"   Name: {account.get('name')}")
        print(f"   Website: {account.get('website')}")
        print(f"   ObjectId: {account.get('objectId')}")
    else:
        print("❌ Account not found by domain")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
