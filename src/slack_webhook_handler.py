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
import sys
import ssl
from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, render_template
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.signature import SignatureVerifier
from dotenv import load_dotenv

from src.modules.slack_client import SlackClient
from src.modules.slack_slash_commands import SlackSlashCommandHandler
from src.modules.gmail_draft_creator import GmailDraftCreator
from src.modules.calendar_event_creator import CalendarEventCreator
from src.modules.fathom_client import FathomClient
from src.modules.claude_email_generator import ClaudeEmailGenerator
from src.modules.meeting_summary_generator import MeetingSummaryGenerator
from src.modules.sales_summary_generator import SalesSummaryGenerator
from src.modules.date_extractor import DateExtractor
from src.providers.factory import CRMProviderFactory
from src.providers.crono_provider import CronoProvider
from src.database import get_db
from src.models import User
from src.models.tenant import Tenant
from src.models.user_settings import UserSettings

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Create SSL context that doesn't verify certificates (for local development)
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Initialize Slack clients
slack_client = SlackClient()
slack_web_client = WebClient(token=os.getenv('SLACK_BOT_TOKEN'), ssl=ssl_context)

# Signature verifier for security
signature_verifier = SignatureVerifier(os.getenv('SLACK_SIGNING_SECRET'))

# In-memory state storage (in production, use Redis or database)
# Format: {thread_ts: {channel, selected_actions, meeting_data, awaiting_confirmation}}
conversation_state = {}

# Global cache for storing selected account IDs by view_id
# Format: {view_id: account_id}
selected_accounts_cache: Dict[str, str] = {}


def get_user_crm_credentials(db, slack_user_id: str, team_id: str) -> Optional[Dict]:
    """Get CRM credentials for a Slack user."""
    try:
        # First find the tenant by slack_team_id to get the UUID
        tenant = db.query(Tenant).filter(Tenant.slack_team_id == team_id).first()
        if not tenant:
            sys.stderr.write(f"Tenant not found for team_id: {team_id}\n")
            return None

        # Then find the user with the tenant UUID
        user = db.query(User).filter(
            User.slack_user_id == slack_user_id,
            User.tenant_id == tenant.id
        ).first()

        if not user:
            sys.stderr.write(f"User not found: slack_user_id={slack_user_id}, tenant_id={tenant.id}\n")
            return None

        if not user.settings:
            sys.stderr.write(f"User settings not found for user_id={user.id}\n")
            return None

        return {
            'api_url': 'https://ext.crono.one/api/v1',
            'public_key': user.settings.crono_public_key,
            'private_key': user.settings.crono_private_key
        }
    except Exception as e:
        sys.stderr.write(f"Error getting CRM credentials: {e}\n")
        return None


def get_user_fathom_key(db, slack_user_id: str, team_id: str) -> Optional[str]:
    """Get Fathom API key for a Slack user."""
    try:
        # First find the tenant by slack_team_id to get the UUID
        tenant = db.query(Tenant).filter(Tenant.slack_team_id == team_id).first()
        if not tenant:
            sys.stderr.write(f"Tenant not found for team_id: {team_id}\n")
            return None

        # Then find the user with the tenant UUID
        user = db.query(User).filter(
            User.slack_user_id == slack_user_id,
            User.tenant_id == tenant.id
        ).first()

        if not user:
            sys.stderr.write(f"User not found: slack_user_id={slack_user_id}, tenant_id={tenant.id}\n")
            return None

        if not user.settings:
            sys.stderr.write(f"User settings not found for user_id={user.id}\n")
            return None

        return user.settings.fathom_api_key
    except Exception as e:
        sys.stderr.write(f"Error getting Fathom API key: {e}\n")
        return None


def get_user_api_keys(db, slack_user_id: str, team_id: str) -> Optional[Dict]:
    """Get all API keys for a Slack user."""
    try:
        # First find the tenant by slack_team_id to get the UUID
        tenant = db.query(Tenant).filter(Tenant.slack_team_id == team_id).first()
        if not tenant:
            return None

        # Then find the user with the tenant UUID
        user = db.query(User).filter(
            User.slack_user_id == slack_user_id,
            User.tenant_id == tenant.id
        ).first()

        if not user:
            return None

        if not user.settings:
            return None

        return {
            'crono_api_key': user.settings.crono_api_key,
            'crono_public_key': user.settings.crono_public_key,
            'crono_private_key': user.settings.crono_private_key,
            'fathom_api_key': user.settings.fathom_api_key
        }
    except Exception as e:
        sys.stderr.write(f"Error getting API keys: {e}\n")
        return None


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

        try:
            # Get user's Fathom API key from database
            team_id = request.form.get('team_id')
            trigger_id = request.form.get('trigger_id')

            with get_db() as db:
                fathom_api_key = get_user_fathom_key(db, user_id, team_id)

            # Create handler with user's Fathom key
            user_slash_command_handler = SlackSlashCommandHandler(fathom_api_key=fathom_api_key)

            # Open modal immediately (no background thread needed)
            user_slash_command_handler.handle_followup_command(
                user_id=user_id,
                channel_id=channel_id,
                trigger_id=trigger_id,
                slack_web_client=slack_web_client
            )

            # Return empty 200 OK (modal already opened)
            return '', 200

        except Exception as e:
            sys.stderr.write(f"❌ Error handling /followup: {e}\n")
            import traceback
            traceback.print_exc(file=sys.stderr)
            return jsonify({
                "response_type": "ephemeral",
                "text": f"❌ Error: {str(e)}"
            })

    elif command == '/crono-add-task':
        sys.stderr.write(f"📥 Received command: {command} from user {user_id}\\n")
        sys.stderr.flush()

        try:
            team_id = request.form.get('team_id')
            trigger_id = request.form.get('trigger_id')

            # Get today's date as initial date
            today = datetime.now().strftime("%Y-%m-%d")

            # Open modal for task creation
            slack_web_client.views_open(
                trigger_id=trigger_id,
                view={
                    "type": "modal",
                    "callback_id": "crono_task_modal",
                    "title": {"type": "plain_text", "text": "Create CRM Task"},
                    "submit": {"type": "plain_text", "text": "Create"},
                    "close": {"type": "plain_text", "text": "Cancel"},
                    "private_metadata": json.dumps({"channel_id": channel_id, "user_id": user_id, "team_id": team_id}),
                    "blocks": [
                        {
                            "type": "input",
                            "block_id": "crono_prospect_block",
                            "label": {"type": "plain_text", "text": "Contact"},
                            "element": {
                                "type": "external_select",
                                "action_id": "crono_prospect_select",
                                "placeholder": {"type": "plain_text", "text": "Search for a contact..."},
                                "min_query_length": 2
                            }
                        },
                        {
                            "type": "input",
                            "block_id": "crono_subject_block",
                            "label": {"type": "plain_text", "text": "Subject"},
                            "element": {
                                "type": "plain_text_input",
                                "action_id": "crono_task_subject",
                                "placeholder": {"type": "plain_text", "text": "Call notes, meeting summary, etc."}
                            }
                        },
                        {
                            "type": "input",
                            "block_id": "crono_date_block",
                            "label": {"type": "plain_text", "text": "Day"},
                            "element": {
                                "type": "datepicker",
                                "action_id": "crono_task_date",
                                "initial_date": today,
                                "placeholder": {"type": "plain_text", "text": "Select day"}
                            }
                        },
                        {
                            "type": "input",
                            "block_id": "crono_type_block",
                            "label": {"type": "plain_text", "text": "Task type"},
                            "element": {
                                "type": "static_select",
                                "action_id": "crono_task_type",
                                "initial_option": {
                                    "text": {"type": "plain_text", "text": "Call"},
                                    "value": "call"
                                },
                                "options": [
                                    {"text": {"type": "plain_text", "text": "Email"}, "value": "email"},
                                    {"text": {"type": "plain_text", "text": "Call"}, "value": "call"},
                                    {"text": {"type": "plain_text", "text": "LinkedIn Message"}, "value": "linkedin"},
                                    {"text": {"type": "plain_text", "text": "InMail"}, "value": "inmail"}
                                ]
                            }
                        },
                        {
                            "type": "input",
                            "block_id": "crono_description_block",
                            "optional": True,
                            "label": {"type": "plain_text", "text": "Description (optional)"},
                            "element": {
                                "type": "plain_text_input",
                                "action_id": "crono_task_description",
                                "multiline": True,
                                "placeholder": {"type": "plain_text", "text": "Call details"}
                            }
                        }
                    ]
                }
            )
            return '', 200
        except SlackApiError as e:
            sys.stderr.write(f"❌ Slack API error opening modal: {e.response}\\n")
            return jsonify({
                "response_type": "ephemeral",
                "text": f"❌ Could not open modal: {e.response.get('error', 'Slack error')}"
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
            elif action_id == 'load_previous_meetings':
                return handle_load_previous_meetings(payload)
            elif action_id == 'create_gmail_draft_from_modal':
                return handle_create_gmail_draft_from_modal(payload)
            elif action_id == 'create_calendar_event_from_modal':
                return handle_create_calendar_event_from_modal(payload)
            elif action_id == 'push_note_to_crono_from_modal':
                return handle_push_note_to_crono_from_modal(payload)
            elif action_id == 'view_crono_deals_from_modal':
                return handle_view_crono_deals_from_modal(payload)
            elif action_id == 'create_crono_task_from_modal':
                return handle_create_crono_task_from_modal(payload)
            elif action_id == 'open_followup_edit_modal':
                return handle_open_followup_edit_modal(payload)

    elif interaction_type == 'block_suggestion':
        return handle_block_suggestion(payload)

    elif interaction_type == 'view_submission':
        callback_id = payload.get('view', {}).get('callback_id')
        if callback_id == 'crono_task_modal':
            return handle_crono_task_submission(payload)
        elif callback_id == 'followup_meeting_select_modal':
            return handle_followup_meeting_submission(payload)

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


def handle_load_previous_meetings(payload: Dict):
    """Handle when user clicks 'Load Previous Meetings' button in modal."""
    import sys

    try:
        view_id = payload.get('view', {}).get('id')
        user_id = payload.get('user', {}).get('id')
        team_id = payload.get('team', {}).get('id')

        sys.stderr.write(f"⏮️ Loading previous meetings for user {user_id}...\n")
        sys.stderr.flush()

        # Get user's Fathom API key
        with get_db() as db:
            fathom_api_key = get_user_fathom_key(db, user_id, team_id)

        # Create handler with user's Fathom key
        slash_handler = SlackSlashCommandHandler(fathom_api_key=fathom_api_key)

        # Get yesterday's meetings
        meetings = slash_handler._get_yesterdays_meetings()

        if not meetings:
            # Try last week if yesterday is empty
            from datetime import timedelta
            last_week_date = datetime.now(timezone.utc).date() - timedelta(days=7)
            meetings = slash_handler._get_meetings_by_date(last_week_date)
            day_label = "Last Week"
        else:
            day_label = "Yesterday"

        if not meetings:
            # No meetings found
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "📭 No meetings found in the last week."
                    }
                }
            ]
        else:
            # Build new blocks with previous meetings (no load more button)
            blocks = slash_handler._build_meeting_selection_modal_blocks(
                meetings,
                day_label=day_label,
                show_load_more=False
            )

        # Update the modal view
        slack_web_client.views_update(
            view_id=view_id,
            view={
                "type": "modal",
                "callback_id": "followup_meeting_select_modal",
                "title": {"type": "plain_text", "text": "Meeting Follow-up"},
                "submit": {"type": "plain_text", "text": "Next"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "blocks": blocks,
                "private_metadata": payload.get('view', {}).get('private_metadata', '{}')
            }
        )

        return jsonify({'status': 'ok'})

    except Exception as e:
        sys.stderr.write(f"❌ Error in handle_load_previous_meetings: {e}\n")
        sys.stderr.flush()
        import traceback
        traceback.print_exc(file=sys.stderr)

        return jsonify({
            "response_action": "errors",
            "errors": {
                "load_previous_meetings_block": f"Error loading meetings: {str(e)}"
            }
        })


def handle_open_followup_edit_modal(payload: Dict):
    """Handle when user clicks 'View & Edit' button to open modal with editable fields."""
    import sys

    try:
        # Extract recording_id from button value
        recording_id = payload['actions'][0]['value']
        trigger_id = payload.get('trigger_id')

        sys.stderr.write(f"📝 Opening follow-up edit modal for recording {recording_id}...\n")
        sys.stderr.flush()

        # Retrieve stored meeting data from conversation state
        if recording_id not in conversation_state:
            sys.stderr.write(f"❌ No data found for recording {recording_id}\n")
            sys.stderr.flush()
            return jsonify({
                'status': 'error',
                'text': '❌ Meeting data not found. Please try processing the meeting again.'
            })

        # Get data from conversation state
        state = conversation_state[recording_id]
        meeting_title = state.get('meeting_title', 'Meeting')
        meeting_summary = state.get('meeting_summary', '')
        final_email = state.get('final_email', '')
        crm_note = state.get('crm_note', '')
        external_attendees_str = state.get('external_attendees_str', 'N/A')
        user_id = state.get('user_id')
        team_id = state.get('team_id')

        sys.stderr.write(f"✅ Retrieved state for {meeting_title}\n")
        sys.stderr.flush()

        # Truncate initial values to Slack's 3000 character limit for text inputs
        def truncate_text(text, max_len=3000):
            if not text:
                return ""
            if len(text) <= max_len:
                return text
            return text[:max_len]

        # Prepare private metadata
        private_metadata = {
            "recording_id": recording_id,
            "user_id": user_id,
            "team_id": team_id
        }

        # Open modal with editable fields
        slack_web_client.views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "callback_id": "followup_edit_modal",
                "title": {"type": "plain_text", "text": "Edit Follow-up"},
                "submit": {"type": "plain_text", "text": "Done"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "private_metadata": json.dumps(private_metadata),
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": meeting_title[:150]  # Slack header text limit
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*External Attendees:* {external_attendees_str}"
                        }
                    },
                    {
                        "type": "divider"
                    },
                    {
                        "type": "input",
                        "block_id": "summary_block",
                        "optional": True,
                        "label": {"type": "plain_text", "text": "Meeting Summary"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "summary_input",
                            "multiline": True,
                            "initial_value": truncate_text(meeting_summary),
                            "placeholder": {"type": "plain_text", "text": "Edit meeting summary..."}
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "email_block",
                        "optional": True,
                        "label": {"type": "plain_text", "text": "Follow-up Email"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "email_input",
                            "multiline": True,
                            "initial_value": truncate_text(final_email),
                            "placeholder": {"type": "plain_text", "text": "Edit follow-up email..."}
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "crm_note_block",
                        "optional": True,
                        "label": {"type": "plain_text", "text": "CRM Note"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "crm_note_input",
                            "multiline": True,
                            "initial_value": truncate_text(crm_note),
                            "placeholder": {"type": "plain_text", "text": "Edit CRM note..."}
                        }
                    },
                    {
                        "type": "divider"
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Actions:* Click any button below to execute that action"
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "action_id": "create_gmail_draft_from_modal",
                                "text": {
                                    "type": "plain_text",
                                    "text": "📧 Gmail Draft"
                                },
                                "style": "primary",
                                "value": recording_id
                            },
                            {
                                "type": "button",
                                "action_id": "create_calendar_event_from_modal",
                                "text": {
                                    "type": "plain_text",
                                    "text": "📅 Calendar Event"
                                },
                                "value": recording_id
                            },
                            {
                                "type": "button",
                                "action_id": "push_note_to_crono_from_modal",
                                "text": {
                                    "type": "plain_text",
                                    "text": "📝 Crono Note"
                                },
                                "value": recording_id
                            }
                        ]
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "action_id": "view_crono_deals_from_modal",
                                "text": {
                                    "type": "plain_text",
                                    "text": "👁️ View Deals"
                                },
                                "value": recording_id
                            },
                            {
                                "type": "button",
                                "action_id": "create_crono_task_from_modal",
                                "text": {
                                    "type": "plain_text",
                                    "text": "✅ Create Task"
                                },
                                "value": recording_id
                            }
                        ]
                    }
                ]
            }
        )

        sys.stderr.write(f"✅ Modal opened successfully\n")
        sys.stderr.flush()

        return jsonify({'status': 'ok'})

    except Exception as e:
        sys.stderr.write(f"❌ Error in handle_open_followup_edit_modal: {e}\n")
        sys.stderr.flush()
        import traceback
        traceback.print_exc(file=sys.stderr)

        return jsonify({
            'status': 'error',
            'text': f'❌ Error opening modal: {str(e)}'
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


def handle_create_gmail_draft_from_modal(payload: Dict):
    """
    Handle Gmail draft creation from modal button.
    Uses data from conversation_state (already generated).
    """
    # NOTE: This function reuses the existing handle_create_gmail_draft logic
    # The data is already in conversation_state from handle_followup_meeting_submission
    return handle_create_gmail_draft(payload)


def handle_create_calendar_event_from_modal(payload: Dict):
    """
    Handle calendar event creation from modal button.
    Uses data from conversation_state (already generated).
    """
    # NOTE: This function reuses the existing handle_create_calendar_event logic
    return handle_create_calendar_event(payload)


def handle_push_note_to_crono_from_modal(payload: Dict):
    """
    Handle Crono note creation from modal button.
    Uses data from conversation_state (already generated).
    """
    # NOTE: This function reuses the existing handle_create_crono_note logic
    return handle_create_crono_note(payload)


def handle_view_crono_deals_from_modal(payload: Dict):
    """
    Handle viewing Crono deals from modal button.
    Uses data from conversation_state (already generated).
    """
    # NOTE: This function reuses the existing handle_view_crono_deals logic
    return handle_view_crono_deals(payload)


def handle_create_crono_task_from_modal(payload: Dict):
    """
    Handle creating Crono task from modal button.
    Opens a new modal for task creation using the external_select for contact search.
    """
    import sys

    try:
        # Get recording_id from button value (if available)
        recording_id = payload.get('actions', [{}])[0].get('value')
        user_id = payload.get('user', {}).get('id')
        team_id = payload.get('team', {}).get('id')
        trigger_id = payload.get('trigger_id')

        sys.stderr.write(f"✅ Opening task creation modal for recording {recording_id}...\n")
        sys.stderr.flush()

        # Get meeting data from conversation_state if available
        meeting_title = "Follow-up Task"
        if recording_id and recording_id in conversation_state:
            state = conversation_state[recording_id]
            meeting_title = state.get('meeting_title', 'Follow-up Task')

        # Get today's date as initial date
        today = datetime.now().strftime("%Y-%m-%d")

        # Open the same task creation modal as /crono-add-task command
        slack_web_client.views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "callback_id": "crono_task_modal",
                "title": {"type": "plain_text", "text": "Create CRM Task"},
                "submit": {"type": "plain_text", "text": "Create"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "private_metadata": json.dumps({
                    "user_id": user_id,
                    "team_id": team_id,
                    "recording_id": recording_id
                }),
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "crono_prospect_block",
                        "label": {"type": "plain_text", "text": "Contact"},
                        "element": {
                            "type": "external_select",
                            "action_id": "crono_prospect_select",
                            "placeholder": {"type": "plain_text", "text": "Search for a contact..."},
                            "min_query_length": 2
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "crono_subject_block",
                        "label": {"type": "plain_text", "text": "Subject"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "crono_task_subject",
                            "initial_value": f"Follow-up: {meeting_title}",
                            "placeholder": {"type": "plain_text", "text": "Task subject"}
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "crono_date_block",
                        "label": {"type": "plain_text", "text": "Day"},
                        "element": {
                            "type": "datepicker",
                            "action_id": "crono_task_date",
                            "initial_date": today,
                            "placeholder": {"type": "plain_text", "text": "Select day"}
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "crono_type_block",
                        "label": {"type": "plain_text", "text": "Task type"},
                        "element": {
                            "type": "static_select",
                            "action_id": "crono_task_type",
                            "initial_option": {
                                "text": {"type": "plain_text", "text": "Call"},
                                "value": "call"
                            },
                            "options": [
                                {"text": {"type": "plain_text", "text": "Email"}, "value": "email"},
                                {"text": {"type": "plain_text", "text": "Call"}, "value": "call"},
                                {"text": {"type": "plain_text", "text": "LinkedIn Message"}, "value": "linkedin"},
                                {"text": {"type": "plain_text", "text": "InMail"}, "value": "inmail"}
                            ]
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "crono_description_block",
                        "optional": True,
                        "label": {"type": "plain_text", "text": "Description (optional)"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "crono_task_description",
                            "multiline": True,
                            "placeholder": {"type": "plain_text", "text": "Task details"}
                        }
                    }
                ]
            }
        )

        return jsonify({'status': 'ok'})

    except SlackApiError as e:
        sys.stderr.write(f"❌ Slack API error opening task modal: {e.response}\n")
        sys.stderr.flush()
        return jsonify({
            "response_type": "ephemeral",
            "text": f"❌ Could not open task modal: {e.response.get('error', 'Slack error')}"
        })
    except Exception as e:
        sys.stderr.write(f"❌ Error in handle_create_crono_task_from_modal: {e}\n")
        sys.stderr.flush()
        import traceback
        traceback.print_exc(file=sys.stderr)

        return jsonify({
            "response_type": "ephemeral",
            "text": f"❌ Error: {str(e)}"
        })


def handle_block_suggestion(payload: dict):
    """Handler for external select suggestions (e.g., prospect search)."""
    action_id = payload.get('action_id')
    user_id = payload.get('user', {}).get('id')
    team_id = payload.get('team', {}).get('id')

    if action_id == 'crono_prospect_select':
        query = payload.get('value', '')
        sys.stderr.write(f"🔍 [crono_prospect_select] query='{query}'\\n")
        options: List[Dict] = []

        try:
            with get_db() as db:
                credentials = get_user_crm_credentials(db, user_id, team_id)
                if credentials:
                    crm_provider = CronoProvider(credentials=credentials)
                    prospects = crm_provider.search_prospects(query=query, account_id=None, limit=200)
                    sys.stderr.write(f"  - 📞 Found {len(prospects)} prospects\\n")

                    if len(prospects) == 0:
                        options.append({
                            "text": {"type": "plain_text", "text": "No contacts found. Try a different search."},
                            "value": "no_prospects"
                        })
                    else:
                        # Slack has a limit of ~100 options for external_select
                        max_options = 100
                        if len(prospects) > max_options:
                            sys.stderr.write(f"  - Too many results ({len(prospects)}), limiting to {max_options}\\n")

                        for i, p in enumerate(prospects):
                            if i >= max_options:
                                break

                            # Display format: "Name (Account) - email"
                            display_name = p.get('name', 'No Name')
                            account_name = p.get('accountName', '')
                            if account_name and account_name != 'Unknown Account':
                                display_name += f" ({account_name})"
                            if p.get('email'):
                                display_name += f" - {p.get('email')}"

                            # Use compact format: prospect_id|account_id (max 75 chars)
                            value_str = f"{p.get('id', '')}|{p.get('accountId', '')}"
                            options.append({
                                "text": {"type": "plain_text", "text": display_name[:75]},
                                "value": value_str[:75]  # Slack limit
                            })

                        sys.stderr.write(f"  - Returning {len(options)} options\\n")
                        sys.stderr.write(f"  - Response JSON (first 500 chars): {json.dumps({'options': options}, ensure_ascii=False)[:500]}\\n")
        except Exception as e:
            sys.stderr.write(f"🔥🔥🔥 EXCEPTION in crono_prospect_select: {e}\\n")
            import traceback
            traceback.print_exc(file=sys.stderr)

        sys.stderr.flush()
        return jsonify({"options": options})

    return jsonify({"options": []})


def handle_followup_meeting_submission(payload: dict):
    """
    Handle submission of the first modal (meeting selection).
    Opens a second modal with editable AI-generated content.
    """
    import sys
    import threading
    import requests

    view = payload.get('view', {})
    user = payload.get('user', {})
    user_id = user.get('id')
    team_id = payload.get('team', {}).get('id')

    # Extract selected meeting ID from modal
    state = view.get('state', {}).get('values', {})
    meeting_block = state.get('meeting_selection_block', {})
    meeting_select = meeting_block.get('selected_meeting_id', {})
    selected_option = meeting_select.get('selected_option', {})
    selected_recording_id = selected_option.get('value')

    if not selected_recording_id:
        return jsonify({
            "response_action": "errors",
            "errors": {
                "meeting_selection_block": "Please select a meeting"
            }
        })

    sys.stderr.write(f"📝 Processing meeting {selected_recording_id} for followup modal...\n")
    sys.stderr.flush()

    # Get channel_id from original modal metadata
    original_metadata = json.loads(view.get('private_metadata', '{}'))
    metadata_channel = original_metadata.get('channel_id')

    # Send "Processing..." message BEFORE starting background thread
    # For DMs, open a conversation first to get the proper channel ID
    if metadata_channel and metadata_channel.startswith('D'):
        # Open/ensure DM conversation exists
        dm_response = slack_web_client.conversations_open(users=user_id)
        channel_id = dm_response['channel']['id']
        sys.stderr.write(f"DEBUG: Opened DM conversation: {channel_id}\n")
        sys.stderr.flush()
    else:
        channel_id = metadata_channel or user_id

    # Step 1: Send immediate "Processing..." message
    processing_msg = slack_web_client.chat_postMessage(
        channel=channel_id,
        text=f"⏳ Generating follow-up content... (30-60s)",
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"⏳ *Generating follow-up content...*\n\nThis may take 30-60 seconds. You'll be notified when ready."
                }
            }
        ]
    )

    processing_ts = processing_msg['ts']
    sys.stderr.write(f"✅ Sent processing message (ts: {processing_ts})\n")
    sys.stderr.flush()

    # Process AI generation in background thread
    def process_and_update_message():
        """Background thread to generate AI content and update message."""
        try:
            # Get user's Fathom API key
            with get_db() as db:
                fathom_api_key = get_user_fathom_key(db, user_id, team_id)

            # Fetch meeting data
            fathom = FathomClient(api_key=fathom_api_key)
            meeting_data = fathom.get_specific_meeting_with_transcript(int(selected_recording_id))

            if not meeting_data:
                sys.stderr.write(f"❌ Meeting {selected_recording_id} not found\n")
                sys.stderr.flush()
                return

            meeting_title = meeting_data.get('meeting_title') or meeting_data.get('title', 'Untitled Meeting')
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
            external_attendees_str = ', '.join(external_emails) if external_emails else 'N/A'

            sys.stderr.write(f"🤖 Generating AI content for: {meeting_title}\n")
            sys.stderr.flush()

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

            # Extract sales insights (in English for CRM)
            sales_gen = SalesSummaryGenerator()
            sales_data = sales_gen.extract_sales_data(
                transcript=transcript,
                meeting_title=meeting_title,
                meeting_language='en'
            )

            # Format sales data as plain text for CRM note
            def format_sales_data_plain(data):
                if not isinstance(data, dict):
                    return str(data)

                formatted = ""
                field_names = {
                    'tech_stack': 'Tech Stack',
                    'pain_points': 'Pain Points',
                    'impact': 'Business Impact',
                    'next_steps': 'Next Steps',
                    'roadblocks': 'Roadblocks'
                }

                for key, value in data.items():
                    field_name = field_names.get(key, key.replace('_', ' ').title())
                    formatted += f"{field_name}:\n{value}\n\n"

                return formatted.strip()

            crm_note_content = format_sales_data_plain(sales_data)

            sys.stderr.write(f"✅ AI content generated successfully\n")
            sys.stderr.flush()

            # Convert HTML to plain text for modal display
            def html_to_text(html_text):
                import re
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
                text = re.sub(r'<[^>]+>', '', text)
                text = re.sub(r'\n{3,}', '\n\n', text)
                return text.strip()

            # Prepare private metadata for second modal
            private_metadata = {
                "recording_id": selected_recording_id,
                "meeting_title": meeting_title,
                "external_attendees": external_attendees_str,
                "user_id": user_id,
                "team_id": team_id
            }

            # Build second modal with editable content
            second_modal = {
                "type": "modal",
                "callback_id": "followup_edit_modal",
                "title": {"type": "plain_text", "text": "Edit Follow-up"},
                "close": {"type": "plain_text", "text": "Close"},
                "private_metadata": json.dumps(private_metadata),
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": meeting_title[:150]
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*External Attendees:* {external_attendees_str}"
                        }
                    },
                    {
                        "type": "divider"
                    },
                    {
                        "type": "input",
                        "block_id": "summary_block",
                        "label": {"type": "plain_text", "text": "Meeting Summary"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "summary_input",
                            "multiline": True,
                            "initial_value": html_to_text(meeting_summary)[:3000],
                            "placeholder": {"type": "plain_text", "text": "Edit meeting summary..."}
                        },
                        "optional": True
                    },
                    {
                        "type": "input",
                        "block_id": "email_block",
                        "label": {"type": "plain_text", "text": "Follow-up Email"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "email_input",
                            "multiline": True,
                            "initial_value": html_to_text(final_email)[:3000],
                            "placeholder": {"type": "plain_text", "text": "Edit follow-up email..."}
                        },
                        "optional": True
                    },
                    {
                        "type": "input",
                        "block_id": "crm_note_block",
                        "label": {"type": "plain_text", "text": "CRM Note (Sales Insights)"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "crm_note_input",
                            "multiline": True,
                            "initial_value": crm_note_content[:3000],
                            "placeholder": {"type": "plain_text", "text": "Edit CRM note..."}
                        },
                        "optional": True
                    },
                    {
                        "type": "divider"
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Actions:* Click any button below to execute that action with the edited content above."
                        }
                    },
                    {
                        "type": "actions",
                        "block_id": "modal_actions",
                        "elements": [
                            {
                                "type": "button",
                                "action_id": "create_gmail_draft_from_modal",
                                "text": {"type": "plain_text", "text": "📧 Gmail Draft"},
                                "style": "primary"
                            },
                            {
                                "type": "button",
                                "action_id": "create_calendar_event_from_modal",
                                "text": {"type": "plain_text", "text": "📅 Calendar Event"}
                            },
                            {
                                "type": "button",
                                "action_id": "push_note_to_crono_from_modal",
                                "text": {"type": "plain_text", "text": "📝 Crono Note"}
                            }
                        ]
                    },
                    {
                        "type": "actions",
                        "block_id": "modal_actions_2",
                        "elements": [
                            {
                                "type": "button",
                                "action_id": "view_crono_deals_from_modal",
                                "text": {"type": "plain_text", "text": "👁️ View Deals"}
                            },
                            {
                                "type": "button",
                                "action_id": "create_crono_task_from_modal",
                                "text": {"type": "plain_text", "text": "✅ Create Task"}
                            }
                        ]
                    }
                ]
            }

            # Store data in conversation_state for modal handler
            conversation_state[selected_recording_id] = {
                'meeting_title': meeting_title,
                'meeting_summary': html_to_text(meeting_summary),
                'final_email': html_to_text(final_email),
                'crm_note': crm_note_content,
                'external_emails': external_emails,
                'external_attendees_str': external_attendees_str,
                'user_id': user_id,
                'team_id': team_id,
                'meeting_data': meeting_data,
                'transcript': transcript
            }

            sys.stderr.write(f"✅ Content generated, updating message with 'View & Edit' button\n")
            sys.stderr.flush()

            # Step 3: Update the "Processing..." message with "Ready" + "View & Edit" button
            slack_web_client.chat_update(
                channel=channel_id,
                ts=processing_ts,
                text=f"✅ Follow-up ready for '{meeting_title}'",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"✅ *Follow-up ready for:*\n*{meeting_title}*"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"📊 Generated:\n• Meeting Summary\n• Follow-up Email\n• CRM Note\n\n_Click below to view and edit the content._"
                        }
                    },
                    {
                        "type": "divider"
                    },
                    {
                        "type": "actions",
                        "block_id": "followup_view_edit_actions",
                        "elements": [
                            {
                                "type": "button",
                                "action_id": "open_followup_edit_modal",
                                "text": {"type": "plain_text", "text": "📝 View & Edit"},
                                "style": "primary",
                                "value": selected_recording_id
                            }
                        ]
                    }
                ]
            )

            sys.stderr.write(f"✅ Message updated with 'View & Edit' button\n")
            sys.stderr.flush()

        except Exception as e:
            sys.stderr.write(f"❌ Error in process_and_update_message: {e}\n")
            sys.stderr.flush()
            import traceback
            traceback.print_exc(file=sys.stderr)

            # Update message with error
            try:
                slack_web_client.chat_update(
                    channel=channel_id,
                    ts=processing_ts,
                    text=f"❌ Error generating follow-up",
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"❌ *Error generating follow-up*\n\n{str(e)}"
                            }
                        }
                    ]
                )
            except:
                pass

    # Start background thread
    thread = threading.Thread(target=process_and_update_message)
    thread.start()

    # Return immediate acknowledgment (closes first modal)
    return jsonify({"response_action": "clear"})


def handle_crono_task_submission(payload: dict):
    """Handle submission of Crono task creation modal."""
    view = payload.get('view', {})
    user = payload.get('user', {})
    user_id = user.get('id')

    # Extract values from modal
    state = view.get('state', {}).get('values', {})

    # Get prospect (format: prospect_id|account_id)
    prospect_state = state.get('crono_prospect_block', {}).get('crono_prospect_select', {})
    selected_option = prospect_state.get('selected_option', {})
    prospect_value = selected_option.get('value', '')

    # Parse prospect_id and account_id
    if '|' in prospect_value:
        prospect_id, account_id = prospect_value.split('|', 1)
    else:
        return jsonify({
            "response_action": "errors",
            "errors": {
                "crono_prospect_block": "Please select a contact"
            }
        })

    # Get other fields
    subject_state = state.get('crono_subject_block', {}).get('crono_task_subject', {})
    subject = subject_state.get('value', 'Task')

    date_state = state.get('crono_date_block', {}).get('crono_task_date', {})
    selected_date = date_state.get('selected_date')  # Format: YYYY-MM-DD

    type_state = state.get('crono_type_block', {}).get('crono_task_type', {})
    selected_option_type = type_state.get('selected_option', {})
    selected_type = selected_option_type.get('value', 'call')

    description_state = state.get('crono_description_block', {}).get('crono_task_description', {})
    description = description_state.get('value', '')

    # Convert date to datetime (set time to 9 AM)
    if selected_date:
        due_date = datetime.strptime(selected_date, "%Y-%m-%d").replace(hour=9, minute=0, second=0)
    else:
        due_date = datetime.now().replace(hour=9, minute=0, second=0)

    try:
        private_meta = view.get('private_metadata') or '{}'
        metadata = json.loads(private_meta)
        team_id = metadata.get('team_id')

        with get_db() as db:
            credentials = get_user_crm_credentials(db, user_id, team_id)
            if not credentials:
                return jsonify({
                    "response_action": "errors",
                    "errors": {
                        "crono_prospect_block": "CRM credentials not found"
                    }
                })

            crm_provider = CronoProvider(credentials=credentials)

            # Get account name for notification
            account_name = selected_option.get('text', {}).get('text', 'Unknown')

            # Create task in Crono
            result = crm_provider.create_task(
                account_id=account_id,
                subject=subject,
                description=description,
                due_date=due_date,
                task_type=selected_type,
                prospect_id=prospect_id
            )
            private_meta = view.get('private_metadata') or '{}'
            channel_id = json.loads(private_meta).get("channel_id")

            # Try to send confirmation message (non-blocking)
            if channel_id and user_id:
                try:
                    slack_web_client.chat_postEphemeral(
                        channel=channel_id,
                        user=user_id,
                        text=f"✅ Task '{subject}' created for {account_name}."
                    )
                except Exception as notify_error:
                    # Log but don't fail - task was already created successfully
                    sys.stderr.write(f"⚠️  Could not send confirmation message: {notify_error}\n")

            return jsonify({"response_action": "clear"})
    except Exception as e:
        sys.stderr.write(f"🔥🔥🔥 Error in task creation view_submission: {e}\\n")
        return jsonify({
            "response_action": "errors",
            "errors": {
                "crono_prospect_block": f"Error: {str(e)}"
            }
        })


# ============================================================================
# SETTINGS API ROUTES
# ============================================================================

@app.route('/settings', methods=['GET'])
def settings_page():
    """Serve the settings HTML page."""
    return render_template('settings.html')


@app.route('/api/settings', methods=['GET'])
def get_user_settings_api():
    """
    Get user settings from database.

    Expected header: X-User-Slack-ID
    Returns: JSON with user settings (keys masked)
    """
    slack_user_id = request.headers.get('X-User-Slack-ID')

    if not slack_user_id:
        return jsonify({"error": "X-User-Slack-ID header required"}), 400

    try:
        with get_db() as db:
            # Find tenant
            tenant = db.query(Tenant).filter(Tenant.slack_team_id == 'T02R43CJEMA').first()
            if not tenant:
                return jsonify({"error": "Tenant not found"}), 404

            # Find or create user
            user = db.query(User).filter(
                User.slack_user_id == slack_user_id,
                User.tenant_id == tenant.id
            ).first()

            if not user:
                # Create new user on first access
                user = User(
                    tenant_id=tenant.id,
                    slack_user_id=slack_user_id,
                    is_active=True
                )
                db.add(user)
                db.commit()
                db.refresh(user)

            # Find or create settings
            if not user.settings:
                settings = UserSettings(
                    tenant_id=tenant.id,
                    user_id=user.id
                )
                db.add(settings)
                db.commit()
                db.refresh(settings)
            else:
                settings = user.settings

            # Return settings (mask sensitive keys)
            response = {}
            if settings.crono_public_key:
                response['crono_public_key'] = '**masked**'
            if settings.crono_private_key:
                response['crono_private_key'] = '**masked**'
            if settings.fathom_api_key:
                response['fathom_api_key'] = '**masked**'
            if settings.piper_api_key:
                response['piper_api_key'] = '**masked**'
            if settings.gmail_token:
                response['gmail_token'] = '**masked**'
            if settings.calendar_token:
                response['calendar_token'] = '**masked**'
            if settings.email_tone:
                response['email_tone'] = settings.email_tone

            return jsonify(response), 200

    except Exception as e:
        sys.stderr.write(f"Error in get_user_settings: {e}\n")
        return jsonify({"error": str(e)}), 500


@app.route('/api/settings', methods=['POST'])
def save_user_settings_api():
    """
    Save user settings to database.

    Expected header: X-User-Slack-ID
    Expected body: JSON with settings to update
    Returns: Success message
    """
    slack_user_id = request.headers.get('X-User-Slack-ID')

    if not slack_user_id:
        return jsonify({"error": "X-User-Slack-ID header required"}), 400

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    try:
        with get_db() as db:
            # Find tenant
            tenant = db.query(Tenant).filter(Tenant.slack_team_id == 'T02R43CJEMA').first()
            if not tenant:
                return jsonify({"error": "Tenant not found"}), 404

            # Find or create user
            user = db.query(User).filter(
                User.slack_user_id == slack_user_id,
                User.tenant_id == tenant.id
            ).first()

            if not user:
                # Create new user
                user = User(
                    tenant_id=tenant.id,
                    slack_user_id=slack_user_id,
                    is_active=True
                )
                db.add(user)
                db.commit()
                db.refresh(user)

            # Find or create settings
            if not user.settings:
                settings = UserSettings(
                    tenant_id=tenant.id,
                    user_id=user.id
                )
                db.add(settings)
                db.commit()
                db.refresh(settings)
            else:
                settings = user.settings

            # Update only provided fields
            if 'crono_public_key' in data and data['crono_public_key']:
                settings.crono_public_key = data['crono_public_key']
            if 'crono_private_key' in data and data['crono_private_key']:
                settings.crono_private_key = data['crono_private_key']
            if 'fathom_api_key' in data and data['fathom_api_key']:
                settings.fathom_api_key = data['fathom_api_key']
            if 'piper_api_key' in data and data['piper_api_key']:
                settings.piper_api_key = data['piper_api_key']
            if 'gmail_token' in data and data['gmail_token']:
                settings.gmail_token = data['gmail_token']
            if 'calendar_token' in data and data['calendar_token']:
                settings.calendar_token = data['calendar_token']
            if 'email_tone' in data:
                settings.email_tone = data['email_tone']

            db.commit()

            return jsonify({"message": "Settings saved successfully"}), 200

    except Exception as e:
        sys.stderr.write(f"Error in save_user_settings: {e}\n")
        return jsonify({"error": str(e)}), 500


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for monitoring.
    Returns 200 if the server is running.
    """
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "slack-fathom-crono"
    }), 200


@app.route('/', methods=['GET'])
def root():
    """Root endpoint - redirects to health check."""
    return jsonify({
        "message": "Slack Fathom Crono Integration API",
        "health": "/health",
        "version": "1.0.0"
    }), 200


# ============================================================================
# SERVER STARTUP
# ============================================================================

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
