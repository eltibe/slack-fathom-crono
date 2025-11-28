#!/usr/bin/env python3
"""Test Crono POST /api/v1/Accounts/search endpoint"""
import requests
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('CRONO_API_KEY')
public_key = os.getenv('CRONO_PUBLIC_KEY')
# Note: The docs show /api/v1 not just /v1
base_url = 'https://ext.crono.one/api/v1'

headers = {
    "X-Api-Key": public_key,
    "X-Api-Secret": api_key,
    "Content-Type": "application/json",
    "Accept": "application/json"
}

print("🔍 Testing POST /api/v1/Accounts/search endpoint")

# Test 1: Search for NeuronUP by name
print("\n📋 Test 1: Searching for 'NeuronUP'...")
payload = {
    "search": "NeuronUP"
}

try:
    response = requests.post(
        f"{base_url}/Accounts/search",
        headers=headers,
        json=payload,
        timeout=15
    )

    print(f"   Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"   Response keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")

        # Extract accounts
        accounts = data.get('data', data.get('accounts', data if isinstance(data, list) else []))

        if isinstance(accounts, list):
            print(f"   ✅ Found {len(accounts)} account(s)")

            for acc in accounts:
                name = acc.get('name', 'Unknown')
                website = acc.get('website', 'No website')
                object_id = acc.get('objectId')

                print(f"\n   📌 Account: {name}")
                print(f"      Website: {website}")
                print(f"      ObjectId: {object_id}")

                if 'neuronup' in name.lower():
                    print(f"\n   🎯 FOUND NEURONUP!")
                    print(f"      ✅ ObjectId: {object_id}")
        else:
            print(f"   Response: {data}")
    else:
        print(f"   Error: {response.text[:300]}")

except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

# Test 2: Search for neuronup.com domain
print("\n\n📋 Test 2: Searching for 'neuronup.com'...")
payload2 = {
    "search": "neuronup.com"
}

try:
    response = requests.post(
        f"{base_url}/Accounts/search",
        headers=headers,
        json=payload2,
        timeout=15
    )

    print(f"   Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        accounts = data.get('data', data.get('accounts', data if isinstance(data, list) else []))

        if isinstance(accounts, list):
            print(f"   ✅ Found {len(accounts)} account(s)")

            for acc in accounts:
                name = acc.get('name', 'Unknown')
                website = acc.get('website', 'No website')
                object_id = acc.get('objectId')

                print(f"\n   📌 Account: {name}")
                print(f"      Website: {website}")
                print(f"      ObjectId: {object_id}")
    else:
        print(f"   Error: {response.text[:300]}")

except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n✅ Test complete")
