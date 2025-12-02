#!/bin/bash
# Test API settings endpoint

echo "Testing /api/settings endpoint..."
echo ""

USER_SLACK_ID="U03CDJEJ3QB"

echo "Request:"
echo "  curl http://localhost:3000/api/settings -H 'X-User-Slack-ID: $USER_SLACK_ID'"
echo ""

echo "Response:"
curl -s http://localhost:3000/api/settings \
  -H "X-User-Slack-ID: $USER_SLACK_ID" \
  -H "Content-Type: application/json" | python3 -m json.tool

echo ""
echo "Done."
