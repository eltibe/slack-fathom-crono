#!/usr/bin/env python3
"""
Slack Webhook Handler for Meeting Follow-up Tool

Handles interactive Slack messages and user responses for
executing meeting follow-up actions (Gmail, Calendar, Crono).
"""

import os
import json
import hmac
import hashlib
import time
from typing import Dict, List, Optional
from flask import Flask, request, jsonify
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
from dotenv import load_dotenv

from modules.slack_client import SlackClient
from modules.slack_slash_commands import SlackSlashCommandHandler
from modules.gmail_draft_creator import GmailDraftCreator
from modules.calendar_event_creator import CalendarEventCreator
from modules.fathom_client import FathomClient
from modules.claude_email_generator import ClaudeEmailGenerator
from modules.meeting_summary_generator import MeetingSummaryGenerator
from modules.sales_summary_generator import SalesSummaryGenerator
from modules.date_extractor import DateExtractor
from providers.factory import CRMProviderFactory

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Initialize Slack clients
slack_client = SlackClient()
slack_web_client = WebClient(token=os.getenv('SLACK_BOT_TOKEN'))
slash_command_handler = SlackSlashCommandHandler()

# Signature verifier for security
signature_verifier = SignatureVerifier(os.getenv('SLACK_SIGNING_SECRET'))

# In-memory state storage (in production, use Redis or database)
# Format: {thread_ts: {channel, selected_actions, meeting_data, awaiting_confirmation}}
conversation_state = {}


@app.route('/slack/events', methods=['POST'])
def slack_events():
    """Handle Slack events (messages, reactions, etc.)."""

    # Verify the request is from Slack
    if not verify_slack_request(request):
        return jsonify({'error': 'Invalid signature'}), 403

    data = request.json

    # Handle URL verification challenge
    if data.get('type') == 'url_verification':
        return jsonify({'challenge': data['challenge']})

    # Handle event callbacks
    if data.get('type') == 'event_callback':
        event = data.get('event', {})

        # Handle message events (for confirmation flow)
        if event.get('type') == 'message' and not event.get('bot_id'):
            handle_user_message(event)

    return jsonify({'status': 'ok'})


@app.route('/slack/commands', methods=['POST'])
def slack_commands():
    """Handle Slack slash commands."""

    # Verify the request is from Slack
    # TEMPORARY: Log but don't block for debugging
    if not verify_slack_request(request):
        print("⚠️  Signature verification failed (allowing for debug)")
        # return jsonify({'error': 'Invalid signature'}), 403

    # Parse command data
    command = request.form.get('command')
    user_id = request.form.get('user_id')
    channel_id = request.form.get('channel_id')
    response_url = request.form.get('response_url')

    import sys
    sys.stderr.write(f"📥 Received command: {command}\n")
    sys.stderr.write(f"   User: {user_id}\n")
    sys.stderr.write(f"   Channel: {channel_id}\n")
    sys.stderr.flush()

    if command == '/followup' or command == '/meetings':
        sys.stderr.write(f"✅ Handling {command} command\n")
        sys.stderr.flush()

        # Respond immediately to avoid timeout
        import threading
        def process_in_background():
            try:
                sys.stderr.write("🔄 Starting background processing...\n")
                sys.stderr.flush()

                response = slash_command_handler.handle_followup_command(
                    user_id=user_id,
                    channel_id=channel_id,
                    response_url=response_url
                )

                sys.stderr.write(f"📤 Got response, sending to {response_url[:50]}...\n")
                sys.stderr.write(f"   Response has {len(response.get('blocks', []))} blocks\n")

                # Debug: print full response
                import json
                sys.stderr.write(f"   Full response JSON:\n{json.dumps(response, indent=2)}\n")
                sys.stderr.flush()

                # Send response to response_url (delayed response)
                import requests
                resp = requests.post(response_url, json=response, timeout=5)
                sys.stderr.write(f"✅ Sent delayed response (status: {resp.status_code})\n")

                if resp.status_code != 200:
                    sys.stderr.write(f"❌ Slack error response: {resp.text[:200]}\n")

                sys.stderr.flush()
            except Exception as e:
                sys.stderr.write(f"❌ Error in background processing: {e}\n")
                sys.stderr.flush()
                import traceback
                traceback.print_exc(file=sys.stderr)

        # Start background processing
        thread = threading.Thread(target=process_in_background)
        thread.start()

        # Return immediate acknowledgment
        return jsonify({
            "response_type": "ephemeral",
            "text": "⏳ Loading today's meetings..."
        })

    print(f"⚠️  Unknown command: {command}")
    return jsonify({
        'response_type': 'ephemeral',
        'text': f'Unknown command: {command}'
    })


@app.route('/slack/interactions', methods=['POST'])
def slack_interactions():
    """Handle Slack interactive components (buttons, checkboxes, etc.)."""

    # Verify the request is from Slack
    if not verify_slack_request(request):
        return jsonify({'error': 'Invalid signature'}), 403

    # Parse the payload
    payload = json.loads(request.form.get('payload'))

    interaction_type = payload.get('type')

    if interaction_type == 'block_actions':
        actions = payload.get('actions', [])

        for action in actions:
            action_id = action.get('action_id')

            if action_id == 'execute_button':
                handle_execute_button(payload)
            elif action_id == 'cancel_button':
                handle_cancel_button(payload)
            elif action_id == 'select_meeting':
                # Just acknowledge - selection is stored in state
                pass
            elif action_id == 'process_meeting_button':
                return handle_process_meeting_button(payload)
            elif action_id == 'create_gmail_draft':
                return handle_create_gmail_draft(payload)
            elif action_id == 'create_calendar_event':
                return handle_create_calendar_event(payload)
            elif action_id == 'create_crono_note':
                return handle_create_crono_note(payload)
            elif action_id == 'view_crono_deals':
                return handle_view_crono_deals(payload)

    return jsonify({'status': 'ok'})


def verify_slack_request(request) -> bool:
    """Verify that the request is from Slack using signature verification."""
    try:
        return signature_verifier.is_valid(
            body=request.get_data().decode('utf-8'),
            timestamp=request.headers.get('X-Slack-Request-Timestamp'),
            signature=request.headers.get('X-Slack-Signature')
        )
    except Exception as e:
        print(f"Signature verification failed: {e}")
        return False


def handle_execute_button(payload: Dict):
    """Handle when user clicks 'Execute Selected Actions' button."""

    user = payload['user']
    channel = payload['container']['channel_id']
    message_ts = payload['container']['message_ts']

    # Get selected checkboxes
    selected_actions = []
    for action in payload.get('actions', []):
        if action.get('action_id') == 'actions_checkbox':
            # This is a bit complex - we need to look at the previous action in the state
            # For now, we'll look at the block_actions to find the checkboxes
            pass

    # Find the checkbox action in the state
    state_values = payload.get('state', {}).get('values', {})

    for block_id, block_values in state_values.items():
        if block_id == 'action_selection':
            checkbox_values = block_values.get('actions_checkbox', {})
            selected_options = checkbox_values.get('selected_options', [])
            selected_actions = [opt['value'] for opt in selected_options]

    if not selected_actions:
        # Send error message
        slack_web_client.chat_postMessage(
            channel=channel,
            thread_ts=message_ts,
            text="⚠️ No actions selected. Please select at least one action."
        )
        return

    # Store conversation state
    conversation_state[message_ts] = {
        'channel': channel,
        'selected_actions': selected_actions,
        'user_id': user['id'],
        'awaiting_confirmation': True,
        'meeting_data': payload.get('message', {}).get('metadata', {}).get('event_payload', {})
    }

    # Send confirmation request
    slack_client.send_confirmation_request(
        channel=channel,
        thread_ts=message_ts,
        selected_actions=selected_actions
    )


def handle_cancel_button(payload: Dict):
    """Handle when user clicks 'Cancel' button."""

    channel = payload['container']['channel_id']
    message_ts = payload['container']['message_ts']

    # Clean up state
    if message_ts in conversation_state:
        del conversation_state[message_ts]

    # Send cancellation message
    slack_client.send_cancellation_message(
        channel=channel,
        thread_ts=message_ts
    )


def handle_process_meeting_button(payload: Dict):
    """Handle when user clicks 'Generate Follow-up' button after selecting a meeting."""

    user = payload['user']
    channel = payload['container']['channel_id']
    response_url = payload.get('response_url')

    # Get selected meeting from radio buttons
    state_values = payload.get('state', {}).get('values', {})
    selected_recording_id = None

    for block_id, block_values in state_values.items():
        if block_id == 'meeting_selection':
            radio_values = block_values.get('select_meeting', {})
            selected_option = radio_values.get('selected_option')
            if selected_option:
                selected_recording_id = selected_option['value']

    if not selected_recording_id:
        # Return error response immediately
        return jsonify({
            "response_type": "ephemeral",
            "replace_original": False,
            "text": "⚠️ Please select a meeting first."
        })

    # Process the meeting in background
    import threading
    thread = threading.Thread(
        target=process_selected_meeting,
        args=(selected_recording_id, channel, user['id'], response_url)
    )
    thread.start()

    # Return immediate acknowledgment
    return jsonify({
        "response_type": "ephemeral",
        "replace_original": True,
        "text": "⏳ Processing meeting... This may take 30-60 seconds."
    })


def process_selected_meeting(recording_id: str, channel: str, user_id: str, response_url: str = None):
    """
    Process a selected meeting (run in background thread).

    Args:
        recording_id: Fathom recording ID
        channel: Slack channel to send results to
        user_id: Slack user ID who requested
        response_url: Slack response URL for updates
    """
    import sys
    import requests

    try:
        sys.stderr.write(f"🔄 Processing meeting {recording_id}...\n")
        sys.stderr.flush()

        # Fetch meeting data
        fathom = FathomClient()
        meeting_data = fathom.get_specific_meeting_with_transcript(int(recording_id))

        if not meeting_data:
            sys.stderr.write(f"❌ Meeting {recording_id} not found\n")
            sys.stderr.flush()

            if response_url:
                requests.post(response_url, json={
                    "response_type": "ephemeral",
                    "replace_original": True,
                    "text": "❌ Could not fetch meeting data."
                }, timeout=5)
            return

        meeting_title = meeting_data.get('meeting_title') or meeting_data.get('title', 'Untitled Meeting')
        # Allow None to enable AI auto-detection of language from transcript
        meeting_language = meeting_data.get('transcript_language')
        transcript = fathom.format_transcript_for_ai(meeting_data)

        # Extract external emails
        external_emails = []
        calendar_invitees = meeting_data.get('calendar_invitees', [])
        external_emails = [
            invitee['email']
            for invitee in calendar_invitees
            if invitee.get('is_external', False)
        ]

        # Generate email with Claude
        claude_gen = ClaudeEmailGenerator()
        final_email = claude_gen.generate_followup_email(
            transcript=transcript,
            context=None,
            tone='professional',
            meeting_language=meeting_language
        )

        # Generate meeting summary
        summary_gen = MeetingSummaryGenerator()
        meeting_summary = summary_gen.generate_calendar_summary(
            transcript,
            meeting_title,
            meeting_language
        )

        # Extract sales insights
        # Always generate CRM notes in English for consistency
        sales_gen = SalesSummaryGenerator()
        sales_data = sales_gen.extract_sales_data(
            transcript=transcript,
            meeting_title=meeting_title,
            meeting_language='en'  # Force English for CRM notes
        )

        # Get meeting URL
        meeting_url = f"https://app.fathom.video/meetings/{recording_id}"

        sys.stderr.write(f"✅ Successfully processed meeting: {meeting_title}\n")
        sys.stderr.flush()

        # Store processed data in conversation state for button handlers
        conversation_state[recording_id] = {
            'meeting_title': meeting_title,
            'final_email': final_email,
            'meeting_summary': meeting_summary,
            'sales_data': sales_data,
            'external_emails': external_emails,
            'meeting_url': meeting_url,
            'meeting_data': meeting_data,
            'transcript': transcript,  # Needed for date extraction in calendar events
            'channel': channel,
            'user_id': user_id
        }

        # Send interactive message with actions via response_url
        if response_url:
            # Truncate smartly with ellipsis
            def smart_truncate(text, max_len=2000):
                if len(text) <= max_len:
                    return text
                return text[:max_len-3] + "..."

            # Convert HTML to plain text
            def html_to_text(html_text):
                import re
                # Remove HTML tags
                text = re.sub(r'<br\s*/?>', '\n', html_text)
                text = re.sub(r'<p>', '\n', text)
                text = re.sub(r'</p>', '\n', text)
                text = re.sub(r'<li>', '\n• ', text)
                text = re.sub(r'</li>', '', text)
                text = re.sub(r'<ul>', '\n', text)
                text = re.sub(r'</ul>', '\n', text)
                text = re.sub(r'<b>(.*?)</b>', r'*\1*', text)
                text = re.sub(r'<strong>(.*?)</strong>', r'*\1*', text)
                text = re.sub(r'<i>(.*?)</i>', r'_\1_', text)
                text = re.sub(r'<em>(.*?)</em>', r'_\1_', text)
                # Remove any remaining HTML tags
                text = re.sub(r'<[^>]+>', '', text)
                # Clean up multiple newlines
                text = re.sub(r'\n{3,}', '\n\n', text)
                return text.strip()

            # Format sales data nicely
            def format_sales_data(data):
                if not isinstance(data, dict):
                    return str(data)

                formatted = ""
                field_names = {
                    'tech_stack': '🔧 Tech Stack',
                    'pain_points': '⚠️ Pain Points',
                    'impact': '💥 Business Impact',
                    'next_steps': '🎯 Next Steps',
                    'roadblocks': '🚧 Roadblocks'
                }

                for key, value in data.items():
                    field_name = field_names.get(key, key.replace('_', ' ').title())
                    formatted += f"\n*{field_name}:*\n{value}\n"

                return formatted.strip()

            # Build the message blocks
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": meeting_title
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Meeting Summary:*\n{smart_truncate(html_to_text(meeting_summary), 1500)}"
                    }
                },
                {
                    "type": "divider"
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Follow-up Email:*\n{smart_truncate(html_to_text(final_email), 1500)}"
                    }
                },
                {
                    "type": "divider"
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*💼 Sales Insights:*\n{smart_truncate(format_sales_data(sales_data), 2000)}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"<{meeting_url}|View Recording in Fathom>"
                    }
                },
                {
                    "type": "divider"
                },
                {
                    "type": "actions",
                    "block_id": "followup_actions",
                    "elements": [
                        {
                            "type": "button",
                            "action_id": "create_gmail_draft",
                            "text": {
                                "type": "plain_text",
                                "text": "📧 Create Gmail Draft"
                            },
                            "style": "primary",
                            "value": str(recording_id)
                        },
                        {
                            "type": "button",
                            "action_id": "create_calendar_event",
                            "text": {
                                "type": "plain_text",
                                "text": "📅 Create Calendar Event"
                            },
                            "value": str(recording_id)
                        },
                        {
                            "type": "button",
                            "action_id": "create_crono_note",
                            "text": {
                                "type": "plain_text",
                                "text": "📝 Create Crono Note"
                            },
                            "value": str(recording_id)
                        },
                        {
                            "type": "button",
                            "action_id": "view_crono_deals",
                            "text": {
                                "type": "plain_text",
                                "text": "💰 View Crono Deals"
                            },
                            "value": str(recording_id)
                        }
                    ]
                }
            ]

            requests.post(response_url, json={
                "response_type": "ephemeral",
                "replace_original": True,
                "text": f"✅ Processed: {meeting_title}",
                "blocks": blocks
            }, timeout=5)

    except Exception as e:
        sys.stderr.write(f"❌ Error processing meeting: {str(e)}\n")
        sys.stderr.flush()
        import traceback
        traceback.print_exc(file=sys.stderr)

        if response_url:
            requests.post(response_url, json={
                "response_type": "ephemeral",
                "replace_original": True,
                "text": f"❌ Error processing meeting: {str(e)}"
            }, timeout=5)


def handle_create_gmail_draft(payload: Dict):
    """Handle when user clicks 'Create Gmail Draft' button."""
    import sys
    import requests

    try:
        # Get recording_id from button value
        recording_id = payload['actions'][0]['value']
        response_url = payload.get('response_url')

        sys.stderr.write(f"📧 Creating Gmail draft for recording {recording_id}...\n")
        sys.stderr.flush()

        # Retrieve stored meeting data
        if recording_id not in conversation_state:
            sys.stderr.write(f"❌ No data found for recording {recording_id}\n")
            sys.stderr.flush()
            return jsonify({
                "response_type": "ephemeral",
                "replace_original": False,
                "text": "❌ Meeting data not found. Please try processing the meeting again."
            })

        state = conversation_state[recording_id]
        email_text = state['final_email']
        recipients = state['external_emails']

        if not recipients:
            return jsonify({
                "response_type": "ephemeral",
                "replace_original": False,
                "text": "⚠️ No external attendees found. Cannot create draft without recipients."
            })

        # Process in background (Gmail API can be slow)
        import threading

        def create_draft_in_background():
            try:
                sys.stderr.write(f"🔄 Creating Gmail draft in background...\n")
                sys.stderr.flush()

                gmail = GmailDraftCreator()
                draft_id = gmail.create_draft_from_generated_email(
                    email_text=email_text,
                    to=recipients
                )

                if draft_id:
                    sys.stderr.write(f"✅ Gmail draft created: {draft_id}\n")
                    sys.stderr.flush()

                    if response_url:
                        requests.post(response_url, json={
                            "response_type": "ephemeral",
                            "replace_original": False,
                            "text": f"✅ Gmail draft created successfully!\n\nRecipients: {', '.join(recipients)}\n\nCheck your Gmail drafts folder."
                        }, timeout=5)
                else:
                    if response_url:
                        requests.post(response_url, json={
                            "response_type": "ephemeral",
                            "replace_original": False,
                            "text": "❌ Failed to create Gmail draft. Check logs for details."
                        }, timeout=5)

            except Exception as e:
                sys.stderr.write(f"❌ Error creating Gmail draft: {e}\n")
                sys.stderr.flush()
                import traceback
                traceback.print_exc(file=sys.stderr)

                if response_url:
                    requests.post(response_url, json={
                        "response_type": "ephemeral",
                        "replace_original": False,
                        "text": f"❌ Error creating Gmail draft: {str(e)}"
                    }, timeout=5)

        thread = threading.Thread(target=create_draft_in_background)
        thread.start()

        # Return immediate acknowledgment
        return jsonify({
            "response_type": "ephemeral",
            "replace_original": False,
            "text": "⏳ Creating Gmail draft... This may take a few seconds."
        })

    except Exception as e:
        sys.stderr.write(f"❌ Error in handle_create_gmail_draft: {e}\n")
        sys.stderr.flush()
        import traceback
        traceback.print_exc(file=sys.stderr)

        return jsonify({
            "response_type": "ephemeral",
            "replace_original": False,
            "text": f"❌ Error: {str(e)}"
        })


def handle_create_calendar_event(payload: Dict):
    """Handle when user clicks 'Create Calendar Event' button."""
    import sys
    import requests
    from datetime import datetime, timedelta
    import pytz

    try:
        # Get recording_id from button value
        recording_id = payload['actions'][0]['value']
        response_url = payload.get('response_url')

        sys.stderr.write(f"📅 Creating calendar event for recording {recording_id}...\n")
        sys.stderr.flush()

        # Retrieve stored meeting data
        if recording_id not in conversation_state:
            sys.stderr.write(f"❌ No data found for recording {recording_id}\n")
            sys.stderr.flush()
            return jsonify({
                "response_type": "ephemeral",
                "replace_original": False,
                "text": "❌ Meeting data not found. Please try processing the meeting again."
            })

        state = conversation_state[recording_id]
        meeting_title = state['meeting_title']
        meeting_summary = state['meeting_summary']
        recipients = state['external_emails']

        # Process in background (Calendar API can be slow)
        import threading

        def create_event_in_background():
            try:
                sys.stderr.write(f"🔄 Creating calendar event in background...\n")
                sys.stderr.flush()

                # Extract date from transcript using AI (instead of hardcoding)
                transcript = state.get('transcript')
                meeting_data = state.get('meeting_data', {})

                # Get original meeting start time from Fathom data
                # Fathom provides start_date in ISO 8601 format (e.g., "2024-05-20T14:00:00.000Z")
                original_meeting_iso = meeting_data.get('start_date') or meeting_data.get('recording_start_time')

                if original_meeting_iso:
                    # Parse ISO format, handling 'Z' suffix for UTC
                    original_dt = datetime.fromisoformat(original_meeting_iso.replace('Z', '+00:00'))
                else:
                    # Fallback if no start date available
                    original_dt = datetime.now(pytz.utc)

                # Use AI to extract follow-up date from transcript
                date_extractor = DateExtractor()
                extracted_date_str, followup_discussed = date_extractor.extract_followup_date(
                    transcript=transcript,
                    meeting_date=original_meeting_iso or str(original_dt)
                )

                # Parse extracted date or default to 1 week from original meeting time
                calendar = CalendarEventCreator()
                followup_datetime = calendar.parse_followup_date(extracted_date_str, original_dt)

                # Create the calendar event with the correctly extracted date
                event_id = calendar.create_followup_meeting(
                    title=f"Follow-up: {meeting_title}",
                    start_datetime=followup_datetime,
                    duration_minutes=30,
                    attendees=recipients,
                    description=meeting_summary
                )

                if event_id:
                    sys.stderr.write(f"✅ Calendar event created: {event_id}\n")
                    sys.stderr.flush()

                    if response_url:
                        followup_date_str = followup_datetime.strftime('%B %d, %Y at %H:%M %Z')

                        # Add info about whether date was extracted or defaulted
                        date_source = ""
                        if extracted_date_str:
                            date_source = f"\n📌 Date extracted from transcript: '{extracted_date_str}'"
                        else:
                            date_source = "\n📌 No specific date mentioned, scheduled for same time next week"

                        requests.post(response_url, json={
                            "response_type": "ephemeral",
                            "replace_original": False,
                            "text": f"✅ Calendar event created successfully!\n\nTitle: Follow-up: {meeting_title}\nDate: {followup_date_str}\nDuration: 30 minutes{date_source}\n\nCheck your Google Calendar."
                        }, timeout=5)
                else:
                    if response_url:
                        requests.post(response_url, json={
                            "response_type": "ephemeral",
                            "replace_original": False,
                            "text": "❌ Failed to create calendar event. Check logs for details."
                        }, timeout=5)

            except Exception as e:
                sys.stderr.write(f"❌ Error creating calendar event: {e}\n")
                sys.stderr.flush()
                import traceback
                traceback.print_exc(file=sys.stderr)

                if response_url:
                    requests.post(response_url, json={
                        "response_type": "ephemeral",
                        "replace_original": False,
                        "text": f"❌ Error creating calendar event: {str(e)}"
                    }, timeout=5)

        thread = threading.Thread(target=create_event_in_background)
        thread.start()

        # Return immediate acknowledgment
        return jsonify({
            "response_type": "ephemeral",
            "replace_original": False,
            "text": "⏳ Creating calendar event... This may take a few seconds."
        })

    except Exception as e:
        sys.stderr.write(f"❌ Error in handle_create_calendar_event: {e}\n")
        sys.stderr.flush()
        import traceback
        traceback.print_exc(file=sys.stderr)

        return jsonify({
            "response_type": "ephemeral",
            "replace_original": False,
            "text": f"❌ Error: {str(e)}"
        })


def handle_create_crono_note(payload: Dict):
    """Handle when user clicks 'Create Crono Note' button."""
    import sys
    import requests

    try:
        # Get recording_id from button value
        recording_id = payload['actions'][0]['value']
        response_url = payload.get('response_url')

        sys.stderr.write(f"📝 Creating Crono note for recording {recording_id}...\n")
        sys.stderr.flush()

        # Retrieve stored meeting data
        if recording_id not in conversation_state:
            sys.stderr.write(f"❌ No data found for recording {recording_id}\n")
            sys.stderr.flush()
            return jsonify({
                "response_type": "ephemeral",
                "replace_original": False,
                "text": "❌ Meeting data not found. Please try processing the meeting again."
            })

        state = conversation_state[recording_id]
        meeting_title = state['meeting_title']
        sales_data = state['sales_data']
        meeting_url = state['meeting_url']
        external_emails = state['external_emails']

        if not external_emails:
            return jsonify({
                "response_type": "ephemeral",
                "replace_original": False,
                "text": "⚠️ No external attendees found. Cannot determine which Crono account to add note to."
            })

        # Process in background (Crono API can be slow)
        import threading

        def create_note_in_background():
            try:
                sys.stderr.write(f"🔄 Creating Crono note in background...\n")
                sys.stderr.flush()

                # TODO: Get tenant's CRM type and credentials from database
                # For now, use Crono with env variables (backward compatible)
                crm_type = os.getenv('CRM_PROVIDER', 'crono')
                credentials = {
                    'public_key': os.getenv('CRONO_PUBLIC_KEY'),
                    'private_key': os.getenv('CRONO_API_KEY')
                }
                crm_provider = CRMProviderFactory.create(crm_type, credentials)

                # Find account by domain
                email_domain = external_emails[0].split('@')[-1]
                company_name_raw = email_domain.split('.')[0] # Pass raw name, let find_account_by_domain handle variations

                account = crm_provider.find_account_by_domain(
                    email_domain=email_domain,
                    company_name=company_name_raw
                )

                if not account:
                    sys.stderr.write(f"⚠️  No Crono account found for domain {email_domain}\n")
                    sys.stderr.flush()

                    if response_url:
                        requests.post(response_url, json={
                            "response_type": "ephemeral",
                            "replace_original": False,
                            "text": f"⚠️ No Crono account found for domain '{email_domain}'.\n\nPlease create the account in Crono first, then try again."
                        }, timeout=5)
                    return

                account_id = account.get('objectId') or account.get('id')
                account_name = account.get('name', 'Unknown')

                sys.stderr.write(f"✅ Found Crono account: {account_name} ({account_id})\n")
                sys.stderr.flush()

                # Build Crono URL
                crono_url = f"https://app.crono.one/accounts/{account_id}"

                # Create meeting summary note
                note_id = crm_provider.create_meeting_summary(
                    account_id=account_id,
                    meeting_title=meeting_title,
                    summary_data=sales_data,
                    meeting_url=meeting_url
                )

                if note_id:
                    sys.stderr.write(f"✅ Crono note created: {note_id}\n")
                    sys.stderr.flush()

                    success_text = f"✅ Crono note created successfully!\n\nAccount: {account_name}\nMeeting: {meeting_title}"
                    if response_url:
                        requests.post(response_url, json={
                            "response_type": "ephemeral",
                            "replace_original": False,
                            "text": success_text,
                            "blocks": [
                                {
                                    "type": "section",
                                    "text": {
                                        "type": "mrkdwn",
                                        "text": success_text
                                    }
                                },
                                {
                                    "type": "actions",
                                    "elements": [
                                        {
                                            "type": "button",
                                            "text": {
                                                "type": "plain_text",
                                                "text": "🔗 Open in Crono CRM"
                                            },
                                            "url": crono_url,
                                            "style": "primary"
                                        }
                                    ]
                                }
                            ]
                        }, timeout=5)
                else:
                    warning_text = f"⚠️ Note created but Crono API may not support direct note creation.\n\nAccount: {account_name}\n\nThe meeting data has been processed - you may need to add it manually to Crono."
                    if response_url:
                        requests.post(response_url, json={
                            "response_type": "ephemeral",
                            "replace_original": False,
                            "text": warning_text,
                            "blocks": [
                                {
                                    "type": "section",
                                    "text": {
                                        "type": "mrkdwn",
                                        "text": warning_text
                                    }
                                },
                                {
                                    "type": "actions",
                                    "elements": [
                                        {
                                            "type": "button",
                                            "text": {
                                                "type": "plain_text",
                                                "text": "🔗 Open in Crono CRM"
                                            },
                                            "url": crono_url,
                                            "style": "primary"
                                        }
                                    ]
                                }
                            ]
                        }, timeout=5)

            except Exception as e:
                sys.stderr.write(f"❌ Error creating Crono note: {e}\n")
                sys.stderr.flush()
                import traceback
                traceback.print_exc(file=sys.stderr)

                if response_url:
                    requests.post(response_url, json={
                        "response_type": "ephemeral",
                        "replace_original": False,
                        "text": f"❌ Error creating Crono note: {str(e)}"
                    }, timeout=5)

        thread = threading.Thread(target=create_note_in_background)
        thread.start()

        # Return immediate acknowledgment
        return jsonify({
            "response_type": "ephemeral",
            "replace_original": False,
            "text": "⏳ Creating Crono note... This may take a few seconds."
        })

    except Exception as e:
        sys.stderr.write(f"❌ Error in handle_create_crono_note: {e}\n")
        sys.stderr.flush()
        import traceback
        traceback.print_exc(file=sys.stderr)

        return jsonify({
            "response_type": "ephemeral",
            "replace_original": False,
            "text": f"❌ Error: {str(e)}"
        })


def handle_view_crono_deals(payload: Dict):
    """Handle when user clicks 'View Crono Deals' button."""
    import sys
    import requests

    try:
        # Get recording_id from button value
        recording_id = payload['actions'][0]['value']
        response_url = payload.get('response_url')

        sys.stderr.write(f"💰 Viewing Crono deals for recording {recording_id}...\n")
        sys.stderr.flush()

        # Retrieve stored meeting data
        if recording_id not in conversation_state:
            sys.stderr.write(f"❌ No data found for recording {recording_id}\n")
            sys.stderr.flush()
            return jsonify({
                "response_type": "ephemeral",
                "replace_original": False,
                "text": "❌ Meeting data not found. Please try processing the meeting again."
            })

        state = conversation_state[recording_id]
        external_emails = state['external_emails']

        if not external_emails:
            return jsonify({
                "response_type": "ephemeral",
                "replace_original": False,
                "text": "⚠️ No external attendees found. Cannot determine Crono account for deals."
            })

        # Process in background
        import threading

        def view_deals_in_background():
            try:
                sys.stderr.write(f"🔄 Fetching Crono deals in background...\n")
                sys.stderr.flush()

                # TODO: Get tenant's CRM type and credentials from database
                # For now, use Crono with env variables (backward compatible)
                crm_type = os.getenv('CRM_PROVIDER', 'crono')
                credentials = {
                    'public_key': os.getenv('CRONO_PUBLIC_KEY'),
                    'private_key': os.getenv('CRONO_API_KEY')
                }
                crm_provider = CRMProviderFactory.create(crm_type, credentials)

                # Find account by domain
                email_domain = external_emails[0].split('@')[-1]
                company_name_raw = email_domain.split('.')[0] # Pass raw name, let find_account_by_domain handle variations

                account = crm_provider.find_account_by_domain(
                    email_domain=email_domain,
                    company_name=company_name_raw
                )

                if not account:
                    sys.stderr.write(f"⚠️  No Crono account found for domain {email_domain}\n")
                    sys.stderr.flush()

                    if response_url:
                        requests.post(response_url, json={
                            "response_type": "ephemeral",
                            "replace_original": False,
                            "text": f"⚠️ No Crono account found for domain '{email_domain}'.\n\nCannot retrieve deals without a linked Crono account."
                        }, timeout=5)
                    return

                account_id = account.get('objectId') or account.get('id')
                account_name = account.get('name', 'Unknown')

                sys.stderr.write(f"✅ Found Crono account: {account_name} ({account_id})\n")
                sys.stderr.flush()

                # Build Crono URL
                crono_url = f"https://app.crono.one/accounts/{account_id}"

                # Get deals for the account
                deals = crm_provider.get_deals(account_id, limit=100)

                if deals:
                    sys.stderr.write(f"✅ Found {len(deals)} deals for account {account_id}\n")
                    sys.stderr.flush()

                    # Format deals for Slack display
                    deals_text = f"💰 *Crono Deals for {account_name}:*\n\n"
                    for deal in deals:
                        deal_name = deal.get('name', 'N/A')
                        deal_stage = deal.get('stage', 'N/A')
                        deal_amount = deal.get('amount', 'N/A')
                        deal_id = deal.get('objectId', 'N/A')
                        deals_text += f"• *{deal_name}* (ID: {deal_id})\n"
                        deals_text += f"  Stage: {deal_stage}\n"
                        deals_text += f"  Amount: {deal_amount}\n\n"
                    deals_text += "\n_Only showing first 100 deals._" # Limit set in get_deals_for_account

                    if response_url:
                        requests.post(response_url, json={
                            "response_type": "ephemeral",
                            "replace_original": False,
                            "text": deals_text,
                            "blocks": [
                                {
                                    "type": "section",
                                    "text": {
                                        "type": "mrkdwn",
                                        "text": deals_text
                                    }
                                },
                                {
                                    "type": "actions",
                                    "elements": [
                                        {
                                            "type": "button",
                                            "text": {
                                                "type": "plain_text",
                                                "text": "🔗 Open in Crono CRM"
                                            },
                                            "url": crono_url,
                                            "style": "primary"
                                        }
                                    ]
                                }
                            ]
                        }, timeout=5)
                else:
                    sys.stderr.write(f"⚠️ No deals found for account {account_id}\n")
                    sys.stderr.flush()
                    no_deals_text = f"⚠️ No Crono deals found for account '{account_name}'."
                    if response_url:
                        requests.post(response_url, json={
                            "response_type": "ephemeral",
                            "replace_original": False,
                            "text": no_deals_text,
                            "blocks": [
                                {
                                    "type": "section",
                                    "text": {
                                        "type": "mrkdwn",
                                        "text": no_deals_text
                                    }
                                },
                                {
                                    "type": "actions",
                                    "elements": [
                                        {
                                            "type": "button",
                                            "text": {
                                                "type": "plain_text",
                                                "text": "🔗 Open in Crono CRM"
                                            },
                                            "url": crono_url,
                                            "style": "primary"
                                        }
                                    ]
                                }
                            ]
                        }, timeout=5)

            except Exception as e:
                sys.stderr.write(f"❌ Error fetching Crono deals: {e}\n")
                sys.stderr.flush()
                import traceback
                traceback.print_exc(file=sys.stderr)

                if response_url:
                    requests.post(response_url, json={
                        "response_type": "ephemeral",
                        "replace_original": False,
                        "text": f"❌ Error fetching Crono deals: {str(e)}"
                    }, timeout=5)

        thread = threading.Thread(target=view_deals_in_background)
        thread.start()

        # Return immediate acknowledgment
        return jsonify({
            "response_type": "ephemeral",
            "replace_original": False,
            "text": "⏳ Fetching Crono deals... This may take a few seconds."
        })

    except Exception as e:
        sys.stderr.write(f"❌ Error in handle_view_crono_deals: {e}\n")
        sys.stderr.flush()
        import traceback
        traceback.print_exc(file=sys.stderr)

        return jsonify({
            "response_type": "ephemeral",
            "replace_original": False,
            "text": f"❌ Error: {str(e)}"
        })


def handle_user_message(event: Dict):
    """Handle user messages (for confirmation flow)."""

    text = event.get('text', '').lower().strip()
    channel = event.get('channel')
    thread_ts = event.get('thread_ts')

    # Only process messages in threads we're tracking
    if not thread_ts or thread_ts not in conversation_state:
        return

    state = conversation_state[thread_ts]

    # Check if we're awaiting confirmation
    if not state.get('awaiting_confirmation'):
        return

    # Check for affirmative or negative response
    if text in ['sì', 'si', 'yes', 'y', 'ok', 'vai', 'procedi']:
        # Execute actions
        state['awaiting_confirmation'] = False
        execute_selected_actions(thread_ts, state)

    elif text in ['no', 'n', 'cancel', 'annulla', 'stop']:
        # Cancel
        state['awaiting_confirmation'] = False
        slack_client.send_cancellation_message(
            channel=channel,
            thread_ts=thread_ts
        )
        # Clean up state
        del conversation_state[thread_ts]


def execute_selected_actions(thread_ts: str, state: Dict):
    """Execute the selected actions and send results."""

    channel = state['channel']
    selected_actions = state['selected_actions']
    meeting_data = state.get('meeting_data', {})

    results = {}
    details = {}

    # Execute Gmail Draft
    if 'gmail_draft' in selected_actions:
        try:
            gmail = GmailDraftCreator()
            draft_id = gmail.create_draft_from_generated_email(
                email_text=meeting_data.get('proposed_email', ''),
                to=meeting_data.get('external_emails', [])
            )
            results['gmail_draft'] = draft_id is not None
            if draft_id:
                details['gmail_draft'] = f"Draft ID: {draft_id}"
        except Exception as e:
            results['gmail_draft'] = False
            details['gmail_draft'] = f"Error: {str(e)}"

    # Execute Calendar Event
    if 'calendar_event' in selected_actions:
        try:
            calendar = CalendarEventCreator()
            event_id = calendar.create_followup_meeting(
                title=meeting_data.get('meeting_title', 'Follow-up Meeting'),
                start_datetime=meeting_data.get('followup_datetime'),
                duration_minutes=30,
                attendees=meeting_data.get('external_emails', []),
                description=meeting_data.get('meeting_summary', '')
            )
            results['calendar_event'] = event_id is not None
            if event_id:
                details['calendar_event'] = "View in Google Calendar"
        except Exception as e:
            results['calendar_event'] = False
            details['calendar_event'] = f"Error: {str(e)}"

    # Execute Crono Note
    if 'crono_note' in selected_actions:
        try:
            # TODO: Get tenant's CRM type and credentials from database
            # For now, use Crono with env variables (backward compatible)
            crm_type = os.getenv('CRM_PROVIDER', 'crono')
            credentials = {
                'public_key': os.getenv('CRONO_PUBLIC_KEY'),
                'private_key': os.getenv('CRONO_API_KEY')
            }
            crm_provider = CRMProviderFactory.create(crm_type, credentials)

            # Find account
            external_emails = meeting_data.get('external_emails', [])
            account = None
            account_id = None

            if external_emails:
                email_domain = external_emails[0].split('@')[-1]
                company_name_guess = email_domain.split('.')[0].capitalize()
                account = crm_provider.find_account_by_domain(
                    email_domain=email_domain,
                    company_name=company_name_guess
                )

            if account:
                account_id = account.get('objectId') or account.get('id')

            if account_id:
                note_id = crm_provider.create_meeting_summary(
                    account_id=account_id,
                    meeting_title=meeting_data.get('meeting_title', ''),
                    summary_data=meeting_data.get('sales_insights', {}),
                    meeting_url=meeting_data.get('meeting_url')
                )
                results['crono_note'] = note_id is not None
                if note_id:
                    details['crono_note'] = f"Note ID: {note_id}"
            else:
                results['crono_note'] = False
                details['crono_note'] = "Company not found in Crono"

        except Exception as e:
            results['crono_note'] = False
            details['crono_note'] = f"Error: {str(e)}"

    # Send results
    slack_client.send_execution_result(
        channel=channel,
        thread_ts=thread_ts,
        results=results,
        details=details
    )

    # Clean up state
    if thread_ts in conversation_state:
        del conversation_state[thread_ts]


def start_webhook_server(port: int = 3000, debug: bool = False):
    """
    Start the Flask webhook server.

    Args:
        port: Port to run the server on (default: 3000)
        debug: Enable debug mode (default: False)
    """
    print(f"🚀 Starting Slack webhook handler on port {port}...")
    print(f"📡 Webhook URLs:")
    print(f"   Events: http://localhost:{port}/slack/events")
    print(f"   Interactions: http://localhost:{port}/slack/interactions")
    print(f"\n⚠️  Make sure to expose this with ngrok for Slack to reach it:")
    print(f"   ngrok http {port}")
    print(f"\nPress Ctrl+C to stop\n")

    app.run(host='0.0.0.0', port=port, debug=debug)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Start Slack webhook handler')
    parser.add_argument('--port', type=int, default=3000, help='Port to run on (default: 3000)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')

    args = parser.parse_args()

    start_webhook_server(port=args.port, debug=args.debug)
