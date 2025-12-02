#!/bin/bash
# Start Slack Webhook Server
# This script ensures proper PYTHONPATH and working directory

cd "$(dirname "$0")"
export PYTHONPATH="$(pwd):${PYTHONPATH}"

echo "Starting Slack webhook server..."
echo "PYTHONPATH: $PYTHONPATH"
echo "Working directory: $(pwd)"
echo ""

python3 -m src.slack_webhook_handler --port 3000 "$@"
