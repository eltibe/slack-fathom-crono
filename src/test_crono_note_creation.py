#!/usr/bin/env python3
"""
Test script to verify Crono note creation with real AccountId.
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_note_creation():
    """Test creating a note on a real Crono account using direct API call."""

    # Get credentials
    public_key = os.getenv('CRONO_PUBLIC_KEY')
    private_key = os.getenv('CRONO_API_KEY')

    if not public_key or not private_key:
        print("❌ Missing CRONO_PUBLIC_KEY or CRONO_API_KEY in .env")
        return False

    print("=" * 60)
    print("🧪 Testing Crono Note Creation")
    print("=" * 60)

    # Real AccountId from user
    account_id = "25995825_6149990627"
    base_url = "https://ext.crono.one/api/v1"  # Correct API base URL

    print(f"\n📋 Test Parameters:")
    print(f"   AccountId: {account_id}")
    print(f"   API Base URL: {base_url}")
    print(f"   Public Key: {public_key[:20]}...")

    # Test content - formatted exactly like in crono_provider.py
    meeting_title = "Test Meeting - Customer Discovery Call"
    content = f"""🎯 Meeting Summary: {meeting_title}

💻 Tech Stack
Python, React, PostgreSQL

⚠️ Pain Points
Manual data entry taking too much time

📊 Impact of Pain
Team spending 10 hours/week on repetitive tasks

✅ Next Steps
Schedule demo for next week

🚧 Roadblocks
Budget approval needed from CFO

🎥 View Full Meeting Recording: https://app.fathom.video/share/test-meeting-123"""

    print(f"\n🎯 Creating test note...")
    print(f"   Title: {meeting_title}")
    print(f"   Content length: {len(content)} chars")

    # Prepare payload - Data wrapper required by Crono API
    payload = {
        "Data": {
            "AccountId": account_id,
            "description": content
        }
    }

    # Prepare headers - FIXED: must match crono_provider.py line 42-47
    headers = {
        "x-api-key": public_key,
        "x-api-secret": private_key,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    print(f"\n📤 Sending POST request to: {base_url}/Notes")
    print(f"   Payload keys: {list(payload.keys())}")
    print(f"   Headers: {list(headers.keys())}")

    try:
        response = requests.post(
            f"{base_url}/Notes",
            headers=headers,
            json=payload,
            timeout=10
        )

        print(f"\n📥 Response Status: {response.status_code}")
        print(f"   Response Headers: {dict(response.headers)}")

        if response.status_code in [200, 201]:
            result = response.json()
            print(f"\n📋 Response Body:")
            print(json.dumps(result, indent=2))

            if result.get('isSuccess'):
                print(f"\n✅ SUCCESS! Note created!")
                print(f"   View in Crono: https://app.crono.one/accounts/{account_id}")
                return True
            else:
                errors = result.get('errors', [])
                print(f"\n❌ FAILED: isSuccess=false")
                print(f"   Errors: {errors}")
                return False
        else:
            print(f"\n❌ HTTP Error: {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            return False

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_note_creation()
    sys.exit(0 if success else 1)
