#!/usr/bin/env python3
"""Test script to find InsightRevenue account in Crono"""
import requests
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('CRONO_API_KEY')
public_key = os.getenv('CRONO_PUBLIC_KEY')

headers = {
    "X-Api-Key": public_key,
    "X-Api-Secret": api_key,
    "Content-Type": "application/json",
    "Accept": "application/json"
}

print("=" * 70)
print("🔍 Searching for InsightRevenue account in Crono")
print("=" * 70)

# Different search terms to try
search_terms = [
    "InsightRevenue",
    "Insight Revenue",
    "insightrevenue",
    "insight revenue",
    "Insight",
    "Revenue",
]

def search_by_name(term):
    """POST search by name"""
    try:
        api_url = "https://ext.crono.one/api/v1"
        payload = {"name": term}

        response = requests.post(
            f"{api_url}/Accounts/search",
            headers=headers,
            json=payload,
            timeout=15
        )

        if response.status_code == 200:
            data = response.json()
            accounts = data.get('data', [])
            return accounts
        return []
    except Exception as e:
        print(f"   Error: {e}")
        return []

def search_by_query(term):
    """GET search by query"""
    try:
        base_url = "https://ext.crono.one/v1"
        params = {"search": term, "limit": 50}

        response = requests.get(
            f"{base_url}/Accounts",
            headers=headers,
            params=params,
            timeout=15
        )

        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                return data
            return data.get('data', data.get('accounts', []))
        return []
    except Exception as e:
        print(f"   Error: {e}")
        return []

# Try POST search with each term
print("\n📋 Strategy 1: POST /api/v1/Accounts/search")
print("-" * 70)
found_accounts = []
for term in search_terms:
    print(f"\n🔍 Trying: '{term}'")
    accounts = search_by_name(term)
    if accounts:
        print(f"   ✅ Found {len(accounts)} account(s)")
        for acc in accounts:
            name = acc.get('name', 'N/A')
            website = acc.get('website', 'N/A')
            obj_id = acc.get('objectId', 'N/A')

            # Check if it matches insightrevenue
            if 'insight' in name.lower() or 'insightrevenue.com' in website.lower():
                print(f"\n   🎯 MATCH FOUND!")
                print(f"      Name: {name}")
                print(f"      Website: {website}")
                print(f"      ObjectId: {obj_id}")
                found_accounts.append({'name': name, 'website': website, 'objectId': obj_id})
    else:
        print(f"   No results")

# Try GET search
print("\n\n📋 Strategy 2: GET /v1/Accounts with search query")
print("-" * 70)
for term in search_terms:
    print(f"\n🔍 Trying: '{term}'")
    accounts = search_by_query(term)
    if accounts:
        print(f"   ✅ Found {len(accounts)} account(s)")
        for acc in accounts:
            name = acc.get('name', 'N/A')
            website = acc.get('website', 'N/A')
            obj_id = acc.get('objectId', 'N/A')

            # Check if it matches insightrevenue
            if 'insight' in name.lower() or 'insightrevenue.com' in website.lower():
                print(f"\n   🎯 MATCH FOUND!")
                print(f"      Name: {name}")
                print(f"      Website: {website}")
                print(f"      ObjectId: {obj_id}")
                if not any(fa['objectId'] == obj_id for fa in found_accounts):
                    found_accounts.append({'name': name, 'website': website, 'objectId': obj_id})
    else:
        print(f"   No results")

# Search all accounts and filter by website
print("\n\n📋 Strategy 3: GET all accounts (limit 200) and filter by website")
print("-" * 70)
try:
    base_url = "https://ext.crono.one/v1"
    response = requests.get(
        f"{base_url}/Accounts",
        headers=headers,
        params={"limit": 200},
        timeout=15
    )

    if response.status_code == 200:
        data = response.json()
        if isinstance(data, list):
            accounts = data
        else:
            accounts = data.get('data', data.get('accounts', []))

        print(f"   Fetched {len(accounts)} accounts, filtering by website...")

        for acc in accounts:
            website = acc.get('website', '') or ''
            name = acc.get('name', 'N/A')
            obj_id = acc.get('objectId', 'N/A')

            # Normalize website
            website_clean = website.lower().replace('http://', '').replace('https://', '').replace('www.', '').strip('/')

            if 'insightrevenue.com' in website_clean or 'insight' in name.lower():
                print(f"\n   🎯 POTENTIAL MATCH!")
                print(f"      Name: {name}")
                print(f"      Website: {website}")
                print(f"      ObjectId: {obj_id}")
                if not any(fa['objectId'] == obj_id for fa in found_accounts):
                    found_accounts.append({'name': name, 'website': website, 'objectId': obj_id})
except Exception as e:
    print(f"   Error: {e}")

# Summary
print("\n" + "=" * 70)
if found_accounts:
    print(f"✅ FOUND {len(found_accounts)} MATCHING ACCOUNT(S):")
    print("=" * 70)
    for acc in found_accounts:
        print(f"\nName: {acc['name']}")
        print(f"Website: {acc['website']}")
        print(f"ObjectId: {acc['objectId']}")
        print(f"\n💾 To add to account_mappings.json:")
        print(f'   "insightrevenue.com": "{acc["objectId"]}"')
else:
    print("❌ NO MATCHING ACCOUNTS FOUND")
    print("=" * 70)
    print("\nThe account might be:")
    print("  1. Beyond the 200 account limit")
    print("  2. Named differently than expected")
    print("  3. Website field formatted differently")
    print("\nTry searching manually in Crono for 'InsightRevenue' or 'Insight Revenue'")
print("=" * 70)
