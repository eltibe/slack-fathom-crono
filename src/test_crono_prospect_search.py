#!/usr/bin/env python3
"""Test searching Crono prospects by email to find account"""
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

# Email from the meeting (Lorena Ruiz from NeuronUP)
test_email = "lorena@neuronup.com"

print(f"🔍 Searching for prospect with email: {test_email}")

# Try different endpoints
endpoints_to_try = [
    f"/Prospects?email={test_email}",
    f"/Prospects?search={test_email}",
    "/Prospects",
]

for endpoint in endpoints_to_try:
    print(f"\n📡 Trying: GET {base_url}{endpoint}")
    try:
        response = requests.get(
            f"{base_url}{endpoint}",
            headers=headers,
            timeout=10
        )

        print(f"   Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()

            # Handle different response formats
            if isinstance(data, list):
                prospects = data
            else:
                prospects = data.get('data', data.get('prospects', []))

            print(f"   Found {len(prospects) if isinstance(prospects, list) else 'unknown'} prospect(s)")

            if isinstance(prospects, list) and len(prospects) > 0:
                print("\n   First few prospects:")
                for i, prospect in enumerate(prospects[:3]):
                    email = prospect.get('email', prospect.get('Email', 'No email'))
                    name = prospect.get('name', prospect.get('Name', 'Unknown'))
                    account_id = prospect.get('accountId', prospect.get('AccountId'))
                    print(f"   {i+1}. {name} - {email}")
                    print(f"      Account ID: {account_id}")

                    # Check if this is our target email
                    if email.lower() == test_email.lower():
                        print(f"\n✅ FOUND! This is our target prospect!")
                        print(f"   Account ID: {account_id}")
                        break
            break
        else:
            print(f"   Response: {response.text[:200]}")

    except Exception as e:
        print(f"   Error: {e}")

print("\n✅ Test complete")
