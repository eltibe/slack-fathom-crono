#!/usr/bin/env python3
"""Test searching Crono contacts/people by email"""
import requests
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('CRONO_API_KEY')
public_key = os.getenv('CRONO_PUBLIC_KEY')
base_url = 'https://ext.crono.one/v1'

headers = {
    "X-Api-Key": public_key,
    "X-Api-Secret": api_key,
    "Content-Type": "application/json",
    "Accept": "application/json"
}

test_email = "lorena@neuronup.com"

print(f"🔍 Searching for contact with email: {test_email}")

# Try different endpoint names
endpoints_to_try = [
    "/Contacts",
    "/People",
    "/Persons",
    "/Leads",
    f"/Accounts?search={test_email}",
]

for endpoint in endpoints_to_try:
    print(f"\n📡 Trying: GET {base_url}{endpoint}")
    try:
        response = requests.get(
            f"{base_url}{endpoint}",
            headers=headers,
            params={"limit": 200} if "search" not in endpoint else {},
            timeout=10
        )

        print(f"   Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()

            # Try to extract items
            items = None
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get('data', data.get('items', data.get('contacts', data.get('people', []))))

            if items and isinstance(items, list):
                print(f"   ✅ Found {len(items)} item(s)")

                # Search for our email in the results
                for item in items:
                    # Check various possible email fields
                    emails_to_check = [
                        item.get('email', ''),
                        item.get('Email', ''),
                        item.get('emailAddress', ''),
                    ]

                    for email in emails_to_check:
                        if email and test_email.lower() in email.lower():
                            print(f"\n   🎯 POTENTIAL MATCH FOUND!")
                            print(f"      Item: {item}")
                            break

                # Show first item as example
                if len(items) > 0:
                    print(f"\n   Example first item keys: {list(items[0].keys())[:10]}")
            else:
                print(f"   Response structure: {list(data.keys()) if isinstance(data, dict) else 'list'}")

        elif response.status_code == 404:
            print(f"   ❌ Endpoint not found")
        else:
            print(f"   Response: {response.text[:200]}")

    except Exception as e:
        print(f"   Error: {e}")

print("\n✅ Test complete")
