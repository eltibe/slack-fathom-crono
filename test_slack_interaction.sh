#!/bin/bash
# Test Slack interaction endpoint with realistic payload

echo "Testing Slack external_select suggestion..."
echo ""

PAYLOAD='{
  "type": "block_suggestion",
  "action_id": "crono_account_select",
  "block_id": "crono_account_block",
  "value": "test",
  "user": {
    "id": "U03CDJEJ3QB",
    "username": "lorenzo",
    "name": "lorenzo"
  },
  "team": {
    "id": "T_LOCAL",
    "domain": "test"
  },
  "container": {
    "type": "view",
    "view_id": "V123"
  },
  "api_app_id": "A123",
  "token": "test_token"
}'

echo "Sending request to ngrok URL..."
RESPONSE=$(curl -s -X POST "https://ciderlike-sleetier-maureen.ngrok-free.dev/slack/interactions" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "X-Slack-Request-Timestamp: $(date +%s)" \
  -H "X-Slack-Signature: v0=test_signature" \
  --data-urlencode "payload=$PAYLOAD")

echo "Response:"
echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
echo ""
echo "✅ If you see options above, the server is working correctly"
echo "❌ If you see an error, check the configuration"
