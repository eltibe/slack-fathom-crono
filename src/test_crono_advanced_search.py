#!/usr/bin/env python3
"""Test Crono POST search with different payload formats"""
import requests
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('CRONO_API_KEY')
public_key = os.getenv('CRONO_PUBLIC_KEY')
base_url = 'https://ext.crono.one/api/v1'

headers = {
    "X-Api-Key": public_key,
    "X-Api-Secret": api_key,
    "Content-Type": "application/json",
    "Accept": "application/json"
}

# Different search terms to try
search_terms = [
    "NeuronUP",
    "neuronup",
    "Neuron",
    "neuronup.com",
    "www.neuronup.com",
]

# Different payload structures to try
def test_search(search_term):
    print(f"\n{'='*60}")
    print(f"🔍 Testing search for: '{search_term}'")
    print(f"{'='*60}")

    payloads_to_try = [
        {"search": search_term},
        {"search": search_term, "limit": 100},
        {"search": search_term, "limit": 200},
        {"query": search_term},
        {"name": search_term},
        {"filter": {"name": search_term}},
        {"searchText": search_term},
    ]

    for i, payload in enumerate(payloads_to_try):
        print(f"\n📋 Test {i+1}: Payload = {payload}")

        try:
            response = requests.post(
                f"{base_url}/Accounts/search",
                headers=headers,
                json=payload,
                timeout=15
            )

            if response.status_code == 200:
                data = response.json()
                accounts = data.get('data', [])

                if isinstance(accounts, list) and len(accounts) > 0:
                    print(f"   ✅ Found {len(accounts)} account(s)")

                    # Check if any match our search
                    for acc in accounts:
                        name = acc.get('name', '').lower()
                        website = acc.get('website', '').lower()

                        if 'neuron' in name or 'neuron' in website:
                            print(f"\n   🎯 POTENTIAL MATCH!")
                            print(f"      Name: {acc.get('name')}")
                            print(f"      Website: {acc.get('website')}")
                            print(f"      ObjectId: {acc.get('objectId')}")
                            return acc.get('objectId')  # Return if found
                else:
                    print(f"   No accounts found")
            elif response.status_code == 400:
                error = response.json()
                print(f"   ❌ Bad request: {error}")
            else:
                print(f"   Status {response.status_code}: {response.text[:200]}")

        except Exception as e:
            print(f"   Error: {e}")

    return None

# Try all search terms
found_id = None
for term in search_terms:
    result = test_search(term)
    if result:
        found_id = result
        print(f"\n{'='*60}")
        print(f"✅ SUCCESS! Found NeuronUP with ObjectId: {found_id}")
        print(f"{'='*60}")
        break

if not found_id:
    print(f"\n{'='*60}")
    print("❌ NeuronUP not found with any search method")
    print(f"{'='*60}")
