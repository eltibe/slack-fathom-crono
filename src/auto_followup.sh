#!/bin/bash
# Auto Follow-up Script
# This script automatically generates follow-up emails after Fathom meetings

# Configuration
SCRIPT_DIR="/Users/lorenzo/cazzeggio"
LOG_FILE="$SCRIPT_DIR/auto_followup.log"
LAST_MEETING_FILE="$SCRIPT_DIR/.last_meeting_id"

# Function to log messages
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# Change to script directory
cd "$SCRIPT_DIR" || exit 1

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

log_message "Starting auto follow-up check..."

# Run the script with Claude model (silent mode - no interaction needed)
python3 meeting_followup.py --model claude >> "$LOG_FILE" 2>&1

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    log_message "✅ Follow-up email drafted successfully"
else
    log_message "❌ Follow-up script failed with exit code $EXIT_CODE"
fi

log_message "Auto follow-up check completed"
