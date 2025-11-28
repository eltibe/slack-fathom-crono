#!/usr/bin/env python3
from modules.crono_client import CronoClient
from dotenv import load_dotenv

load_dotenv()

try:
    print("🔍 Testing Crono account search by name...")
    crono = CronoClient()

    # Try searching by company name
    print("\n📋 Searching for 'NeuronUP' by name...")
    accounts = crono.search_accounts(query="NeuronUP", limit=10)

    print(f"   Found {len(accounts)} account(s)")

    if accounts:
        for acc in accounts:
            print(f"\n   ✅ Account: {acc.get('name')}")
            print(f"      Website: {acc.get('website', 'No website')}")
            print(f"      ObjectId: {acc.get('objectId')}")
    else:
        print("\n   ❌ No accounts found with name 'NeuronUP'")

        # Try partial match
        print("\n📋 Trying search for 'Neuron'...")
        accounts = crono.search_accounts(query="Neuron", limit=10)
        print(f"   Found {len(accounts)} account(s)")
        for acc in accounts:
            print(f"      - {acc.get('name')}")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
