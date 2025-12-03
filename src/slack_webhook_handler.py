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
import logging
import base64
from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, render_template, redirect, url_for
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.signature import SignatureVerifier
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleRequest

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
from src.models.conversation_state import ConversationState

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Global error handler
@app.errorhandler(Exception)
def handle_exception(error):
    """
    Global error handler for all unhandled exceptions.
    Logs the error and returns a generic error response.
    """
    logger.error(f"Unhandled exception: {error}", exc_info=True)
    return jsonify({
        "error": "Internal server error",
        "message": str(error)
    }), 500

# Create SSL context that doesn't verify certificates (for local development)
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Initialize Slack clients
slack_client = SlackClient()
slack_web_client = WebClient(token=os.getenv('SLACK_BOT_TOKEN'), ssl=ssl_context)

# Signature verifier for security
signature_verifier = SignatureVerifier(os.getenv('SLACK_SIGNING_SECRET'))

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
GOOGLE_SCOPES = [
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/calendar'
]

# ASSUMPTION: Using environment variable for redirect URI to support both local and production
# In production, this should be set to https://your-domain.com/oauth/google/callback
GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:5000/oauth/google/callback')

def create_google_oauth_flow():
    """
    Create a Google OAuth flow instance.

    Returns:
        Flow: Configured OAuth flow object
    """
    # ASSUMPTION: Creating client config from environment variables since we don't have credentials.json
    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [GOOGLE_REDIRECT_URI]
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=GOOGLE_SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI
    )

    return flow

# Database-backed conversation state functions
def get_conversation_state(db, state_key: str) -> Optional[Dict]:
    """Get conversation state from database"""
    try:
        state = db.query(ConversationState).filter(
            ConversationState.state_key == state_key
        ).first()

        if state:
            logger.info(f"✅ Found conversation state for key: {state_key}")
            return state.state_data
        else:
            logger.warning(f"❌ No data found for recording {state_key}")
            return None
    except Exception as e:
        logger.error(f"Error getting conversation state: {e}")
        return None


def set_conversation_state(db, state_key: str, state_data: Dict) -> bool:
    """Set conversation state in database"""
    try:
        # Check if state already exists
        state = db.query(ConversationState).filter(
            ConversationState.state_key == state_key
        ).first()

        if state:
            # Update existing state
            state.state_data = state_data
            state.updated_at = datetime.utcnow()
        else:
            # Create new state
            state = ConversationState(
                state_key=state_key,
                state_data=state_data,
                expires_at=datetime.utcnow() + timedelta(hours=24)
            )
            db.add(state)

        db.commit()
        logger.info(f"✅ Saved conversation state for key: {state_key}")
        return True
    except Exception as e:
        logger.error(f"Error setting conversation state: {e}")
        db.rollback()
        return False


def delete_conversation_state(db, state_key: str) -> bool:
    """Delete conversation state from database"""
    try:
        state = db.query(ConversationState).filter(
            ConversationState.state_key == state_key
        ).first()

        if state:
            db.delete(state)
            db.commit()
            logger.info(f"✅ Deleted conversation state for key: {state_key}")
            return True
        return False
    except Exception as e:
        logger.error(f"Error deleting conversation state: {e}")
        db.rollback()
        return False


# Global cache for storing selected account IDs by view_id
# Format: {view_id: account_id}
selected_accounts_cache: Dict[str, str] = {}


def get_user_crm_credentials(db, slack_user_id: str, team_id: str) -> Optional[Dict]:
    """Get CRM credentials for a Slack user."""
    try:
        # First find the tenant by slack_team_id to get the UUID
        tenant = db.query(Tenant).filter(Tenant.slack_team_id == team_id).first()
        if not tenant:
            logger.error(f"Tenant not found for team_id: {team_id}")
            return None

        # Then find the user with the tenant UUID
        user = db.query(User).filter(
            User.slack_user_id == slack_user_id,
            User.tenant_id == tenant.id
        ).first()

        if not user:
            logger.error(f"User not found: slack_user_id={slack_user_id}, tenant_id={tenant.id}")
            return None

        if not user.settings:
            logger.error(f"User settings not found for user_id={user.id}")
            return None

        return {
            'api_url': 'https://ext.crono.one/api/v1',
            'public_key': user.settings.crono_public_key,
            'private_key': user.settings.crono_private_key
        }
    except Exception as e:
        logger.error(f"Error getting CRM credentials: {e}")
        return None


def get_user_fathom_key(db, slack_user_id: str, team_id: str) -> Optional[str]:
    """Get Fathom API key for a Slack user."""
    try:
        # First find the tenant by slack_team_id to get the UUID
        tenant = db.query(Tenant).filter(Tenant.slack_team_id == team_id).first()
        if not tenant:
            logger.error(f"Tenant not found for team_id: {team_id}")
            return None

        # Then find the user with the tenant UUID
        user = db.query(User).filter(
            User.slack_user_id == slack_user_id,
            User.tenant_id == tenant.id
        ).first()

        if not user:
            logger.error(f"User not found: slack_user_id={slack_user_id}, tenant_id={tenant.id}")
            return None

        if not user.settings:
            logger.error(f"User settings not found for user_id={user.id}")
            return None

        return user.settings.fathom_api_key
    except Exception as e:
        logger.error(f"Error getting Fathom API key: {e}")
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
        logger.error(f"Error getting API keys: {e}")
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
        logger.warning("⚠️  Signature verification failed (allowing for debug)")
        # return jsonify({'error': 'Invalid signature'}), 403

    # Parse command data
    command = request.form.get('command')
    user_id = request.form.get('user_id')
    channel_id = request.form.get('channel_id')
    response_url = request.form.get('response_url')

    import sys
    logger.info(f"📥 Received command: {command}")
    logger.info(f"   User: {user_id}")
    logger.info(f"   Channel: {channel_id}")

    if command == '/followup' or command == '/meetings':
        logger.info(f"✅ Handling {command} command")

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
            logger.error(f"❌ Error handling /followup: {e}")
            import traceback
            traceback.print_exc(file=sys.stderr)
            return jsonify({
                "response_type": "ephemeral",
                "text": f"❌ Error: {str(e)}"
            })

    elif command == '/crono-add-task':
        logger.info(f"📥 Received command: {command} from user {user_id}\\n")

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
            logger.error(f"❌ Slack API error opening modal: {e.response}\\n")
            return jsonify({
                "response_type": "ephemeral",
                "text": f"❌ Could not open modal: {e.response.get('error', 'Slack error')}"
            })

    logger.warning(f"⚠️  Unknown command: {command}")
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

    # Get database session
    with get_db() as db:
        interaction_type = payload.get('type')

        if interaction_type == 'block_actions':
            actions = payload.get('actions', [])

            for action in actions:
                action_id = action.get('action_id')

                if action_id == 'execute_button':
                    handle_execute_button(db, payload)
                elif action_id == 'cancel_button':
                    handle_cancel_button(db, payload)
                elif action_id == 'select_meeting':
                    # Just acknowledge - selection is stored in state
                    pass
                elif action_id == 'process_meeting_button':
                    return handle_process_meeting_button(db, payload)
                elif action_id == 'create_gmail_draft':
                    return handle_create_gmail_draft(db, payload)
                elif action_id == 'create_calendar_event':
                    return handle_create_calendar_event(db, payload)
                elif action_id == 'create_crono_note':
                    return handle_create_crono_note(db, payload)
                elif action_id == 'view_crono_deals':
                    return handle_view_crono_deals(db, payload)
                elif action_id == 'load_previous_meetings':
                    return handle_load_previous_meetings(db, payload)
                elif action_id == 'create_gmail_draft_from_modal':
                    return handle_create_gmail_draft_from_modal(db, payload)
                elif action_id == 'create_calendar_event_from_modal':
                    return handle_create_calendar_event_from_modal(db, payload)
                elif action_id == 'push_note_to_crono_from_modal':
                    return handle_push_note_to_crono_from_modal(db, payload)
                elif action_id == 'view_crono_deals_from_modal':
                    return handle_view_crono_deals_from_modal(db, payload)
                elif action_id == 'create_crono_task_from_modal':
                    return handle_create_crono_task_from_modal(db, payload)
                elif action_id == 'open_followup_edit_modal':
                    return handle_open_followup_edit_modal(db, payload)

        elif interaction_type == 'block_suggestion':
            return handle_block_suggestion(db, payload)

        elif interaction_type == 'view_submission':
            callback_id = payload.get('view', {}).get('callback_id')
            if callback_id == 'crono_task_modal':
                return handle_crono_task_submission(db, payload)
            elif callback_id == 'followup_meeting_select_modal':
                return handle_followup_meeting_submission(db, payload)

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
        logger.error(f"Signature verification failed: {e}")
        return False


def handle_execute_button(db, payload: Dict):
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
    set_conversation_state(db, message_ts, {
        'channel': channel,
        'selected_actions': selected_actions,
        'user_id': user['id'],
        'awaiting_confirmation': True,
        'meeting_data': payload.get('message', {}).get('metadata', {}).get('event_payload', {})
    })

    # Send confirmation request
    slack_client.send_confirmation_request(
        channel=channel,
        thread_ts=message_ts,
        selected_actions=selected_actions
    )


def handle_cancel_button(db, payload: Dict):
    """Handle when user clicks 'Cancel' button."""

    channel = payload['container']['channel_id']
    message_ts = payload['container']['message_ts']

    # Clean up state
    if get_conversation_state(db, message_ts):
        delete_conversation_state(db, message_ts)

    # Send cancellation message
    slack_client.send_cancellation_message(
        channel=channel,
        thread_ts=message_ts
    )


def handle_process_meeting_button(db, payload: Dict):
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
        args=(selected_recording_id, channel, user['id'], response_url, db)
    )
    thread.start()

    # Return immediate acknowledgment
    return jsonify({
        "response_type": "ephemeral",
        "replace_original": True,
        "text": "⏳ Processing meeting... This may take 30-60 seconds."
    })


def process_selected_meeting(recording_id: str, channel: str, user_id: str, response_url: str = None, db = None):
    """
    Process a selected meeting (run in background thread).

    Args:
        recording_id: Fathom recording ID
        channel: Slack channel to send results to
        user_id: Slack user ID who requested
        response_url: Slack response URL for updates
        db: Database session (optional, will create new one if None)
    """
    import sys
    import requests

    # ASSUMPTION: Create new db session if not provided (for background threads)
    if db is None:
        db = next(get_db())

    try:
        logger.info(f"🔄 Processing meeting {recording_id}...")

        # Fetch meeting data
        fathom = FathomClient()
        meeting_data = fathom.get_specific_meeting_with_transcript(int(recording_id))

        if not meeting_data:
            logger.error(f"❌ Meeting {recording_id} not found")

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

        logger.info(f"✅ Successfully processed meeting: {meeting_title}")

        # Store processed data in database for button handlers
        set_conversation_state(db, recording_id, {
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
        })

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
        logger.error(f"❌ Error processing meeting: {str(e)}")
        import traceback
        traceback.print_exc(file=sys.stderr)

        if response_url:
            requests.post(response_url, json={
                "response_type": "ephemeral",
                "replace_original": True,
                "text": f"❌ Error processing meeting: {str(e)}"
            }, timeout=5)


def handle_create_gmail_draft(db, payload: Dict):
    """Handle when user clicks 'Create Gmail Draft' button."""
    import sys
    import requests

    try:
        # Get recording_id from button value
        recording_id = payload['actions'][0]['value']
        response_url = payload.get('response_url')
        slack_user_id = payload['user']['id']
        team_id = payload['team']['id']

        # Check if this action is from within a modal
        is_modal_action = 'view' in payload
        view_id = payload.get('view', {}).get('id') if is_modal_action else None

        logger.info(f"📧 Creating Gmail draft for recording {recording_id}... (modal={is_modal_action})")

        # Retrieve stored meeting data
        if not get_conversation_state(db, recording_id):
            logger.error(f"❌ No data found for recording {recording_id}")

            if is_modal_action:
                slack_client.client.views_update(
                    view_id=view_id,
                    view={
                        "type": "modal",
                        "title": {"type": "plain_text", "text": "Error"},
                        "close": {"type": "plain_text", "text": "Close"},
                        "blocks": [{
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "❌ *Error*\n\nMeeting data not found. Please try processing the meeting again."
                            }
                        }]
                    }
                )
                return jsonify({})
            else:
                return jsonify({
                    "response_type": "ephemeral",
                    "replace_original": False,
                    "text": "❌ Meeting data not found. Please try processing the meeting again."
                })

        state = get_conversation_state(db, recording_id)
        email_text = state['final_email']
        recipients = state['external_emails']

        if not recipients:
            error_msg = "⚠️ No external attendees found. Cannot create draft without recipients."

            if is_modal_action:
                slack_client.client.views_update(
                    view_id=view_id,
                    view={
                        "type": "modal",
                        "title": {"type": "plain_text", "text": "Warning"},
                        "close": {"type": "plain_text", "text": "Close"},
                        "blocks": [{
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"⚠️ *Warning*\n\n{error_msg}"
                            }
                        }]
                    }
                )
                return jsonify({})
            else:
                return jsonify({
                    "response_type": "ephemeral",
                    "replace_original": False,
                    "text": error_msg
                })

        # Get user and check Gmail token
        tenant = db.query(Tenant).filter(Tenant.slack_team_id == team_id).first()
        if not tenant:
            error_msg = "❌ Tenant not found"

            if is_modal_action:
                slack_client.client.views_update(
                    view_id=view_id,
                    view={
                        "type": "modal",
                        "title": {"type": "plain_text", "text": "Error"},
                        "close": {"type": "plain_text", "text": "Close"},
                        "blocks": [{
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": error_msg}
                        }]
                    }
                )
                return jsonify({})
            else:
                return jsonify({"response_type": "ephemeral", "text": error_msg})

        user = db.query(User).filter(
            User.slack_user_id == slack_user_id,
            User.tenant_id == tenant.id
        ).first()

        if not user or not user.settings or not user.settings.gmail_token:
            error_msg = "❌ Please connect your Google account first at https://slack-fathom-crono.onrender.com/settings"

            if is_modal_action:
                slack_client.client.views_update(
                    view_id=view_id,
                    view={
                        "type": "modal",
                        "title": {"type": "plain_text", "text": "Error"},
                        "close": {"type": "plain_text", "text": "Close"},
                        "blocks": [{
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": error_msg}
                        }]
                    }
                )
                return jsonify({})
            else:
                return jsonify({"response_type": "ephemeral", "text": error_msg})

        # If from modal, create draft synchronously and update modal
        if is_modal_action:
            try:
                # Define callback to save refreshed tokens
                def save_gmail_token(new_token_json):
                    user.settings.gmail_token = new_token_json
                    db.commit()
                    logger.info(f"Refreshed Gmail token for user {slack_user_id}")

                gmail = GmailDraftCreator(
                    token_json=user.settings.gmail_token,
                    token_save_callback=save_gmail_token
                )
                draft_id = gmail.create_draft_from_generated_email(
                    email_text=email_text,
                    to=recipients
                )

                if draft_id:
                    # Update modal with success banner, preserving all fields and buttons
                    current_view = payload.get('view', {})
                    success_message = f"Gmail Draft Created! Recipients: {', '.join(recipients)}"
                    updated_view = update_modal_with_success(
                        view=current_view,
                        completed_action_id='create_gmail_draft_from_modal',
                        success_message=success_message,
                        action_link="https://mail.google.com/mail/u/0/#drafts"
                    )
                    slack_client.client.views_update(view_id=view_id, view=updated_view)
                    return jsonify({})
                else:
                    raise Exception("Failed to create Gmail draft")

            except Exception as e:
                logger.error(f"❌ Error creating Gmail draft: {e}")
                slack_client.client.views_update(
                    view_id=view_id,
                    view={
                        "type": "modal",
                        "title": {"type": "plain_text", "text": "Error"},
                        "close": {"type": "plain_text", "text": "Close"},
                        "blocks": [{
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"❌ *Error Creating Draft*\n\n{str(e)}"
                            }
                        }]
                    }
                )
                return jsonify({})

        # Process in background (Gmail API can be slow)
        import threading

        def create_draft_in_background():
            try:
                logger.info(f"🔄 Creating Gmail draft in background...")

                # Define callback to save refreshed tokens
                def save_gmail_token(new_token_json):
                    user.settings.gmail_token = new_token_json
                    db.commit()
                    logger.info(f"Refreshed Gmail token for user {slack_user_id}")

                gmail = GmailDraftCreator(
                    token_json=user.settings.gmail_token,
                    token_save_callback=save_gmail_token
                )
                draft_id = gmail.create_draft_from_generated_email(
                    email_text=email_text,
                    to=recipients
                )

                if draft_id:
                    logger.info(f"✅ Gmail draft created: {draft_id}")

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
                logger.error(f"❌ Error creating Gmail draft: {e}")
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
        logger.error(f"❌ Error in handle_create_gmail_draft: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)

        return jsonify({
            "response_type": "ephemeral",
            "replace_original": False,
            "text": f"❌ Error: {str(e)}"
        })


def handle_create_calendar_event(db, payload: Dict):
    """Handle when user clicks 'Create Calendar Event' button."""
    import sys
    import requests
    from datetime import datetime, timedelta
    import pytz

    try:
        # Get recording_id from button value
        recording_id = payload['actions'][0]['value']
        response_url = payload.get('response_url')

        logger.info(f"📅 Creating calendar event for recording {recording_id}...")

        # Retrieve stored meeting data
        if not get_conversation_state(db, recording_id):
            logger.error(f"❌ No data found for recording {recording_id}")
            return jsonify({
                "response_type": "ephemeral",
                "replace_original": False,
                "text": "❌ Meeting data not found. Please try processing the meeting again."
            })

        state = get_conversation_state(db, recording_id)
        meeting_title = state['meeting_title']
        meeting_summary = state['meeting_summary']
        recipients = state['external_emails']

        # Process in background (Calendar API can be slow)
        import threading

        def create_event_in_background():
            try:
                logger.info(f"🔄 Creating calendar event in background...")

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
                    logger.info(f"✅ Calendar event created: {event_id}")

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
                logger.error(f"❌ Error creating calendar event: {e}")
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
        logger.error(f"❌ Error in handle_create_calendar_event: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)

        return jsonify({
            "response_type": "ephemeral",
            "replace_original": False,
            "text": f"❌ Error: {str(e)}"
        })


def update_modal_with_success(view: Dict, completed_action_id: str, success_message: str, action_link: str = None) -> Dict:
    """
    Update an existing modal view to show success message and mark action as completed.

    This preserves all existing blocks and input values, just adds a success banner
    and updates the clicked button to show it's completed.

    Args:
        view: The current view dict from payload['view']
        completed_action_id: The action_id of the button that was clicked
        success_message: Success message to show in banner (without emoji, will add ✅)
        action_link: Optional link to the created resource

    Returns:
        Updated view dict (cleaned for views.update API)
    """
    import copy

    # Deep copy to avoid modifying original
    blocks = copy.deepcopy(view.get('blocks', []))

    # Create success banner
    success_block = {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"✅ {success_message}"
        }
    }

    # Add link as accessory button if provided
    if action_link:
        success_block["accessory"] = {
            "type": "button",
            "text": {"type": "plain_text", "text": "View"},
            "url": action_link
        }

    # Find the right position to insert success banner
    # Insert after header if exists, otherwise at the top
    insert_position = 0
    if blocks and blocks[0].get('type') == 'header':
        insert_position = 1

    # Remove any existing success banners first (to avoid duplicates)
    blocks = [b for b in blocks if not (b.get('type') == 'section' and '✅' in b.get('text', {}).get('text', ''))]

    # Insert success banner
    blocks.insert(insert_position, success_block)

    # Find and update the completed button in action blocks
    for block in blocks:
        if block.get('type') == 'actions':
            elements = block.get('elements', [])
            for element in elements:
                if element.get('action_id') == completed_action_id:
                    # Mark button as completed
                    original_text = element['text']['text']
                    # Remove emoji if present and add checkmark
                    clean_text = original_text.replace('📧', '').replace('📅', '').replace('📝', '').replace('✅', '').replace('👁️', '').strip()
                    element['text']['text'] = f"✅ {clean_text}"
                    # Change action_id to prevent re-triggering
                    element['action_id'] = f"{completed_action_id}_completed"
                    # Keep the style if it exists
                    if 'style' not in element:
                        element['style'] = 'primary'

    # Return only the fields that views.update accepts
    # Exclude: id, team_id, state, hash, previous_view_id, root_view_id, app_id, app_installed_team_id, bot_id
    return {
        "type": view.get("type", "modal"),
        "title": view.get("title"),
        "submit": view.get("submit"),
        "close": view.get("close"),
        "blocks": blocks,
        "private_metadata": view.get("private_metadata"),
        "callback_id": view.get("callback_id"),
        "clear_on_close": view.get("clear_on_close"),
        "notify_on_close": view.get("notify_on_close"),
        "external_id": view.get("external_id")
    }


def handle_create_crono_note(db, payload: Dict):
    """Handle when user clicks 'Create Crono Note' button."""
    import sys
    import requests

    try:
        # Get recording_id from button value
        recording_id = payload['actions'][0]['value']
        response_url = payload.get('response_url')

        # Check if this action is from within a modal
        is_modal_action = 'view' in payload
        view_id = payload.get('view', {}).get('id') if is_modal_action else None

        logger.info(f"📝 Creating Crono note for recording {recording_id}... (modal={is_modal_action})")

        # Retrieve stored meeting data
        if not get_conversation_state(db, recording_id):
            logger.error(f"❌ No data found for recording {recording_id}")

            if is_modal_action:
                # Update modal with error
                slack_client.client.views_update(
                    view_id=view_id,
                    view={
                        "type": "modal",
                        "title": {"type": "plain_text", "text": "Error"},
                        "close": {"type": "plain_text", "text": "Close"},
                        "blocks": [
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": "❌ *Error*\n\nMeeting data not found. Please try processing the meeting again."
                                }
                            }
                        ]
                    }
                )
                return jsonify({})
            else:
                return jsonify({
                    "response_type": "ephemeral",
                    "replace_original": False,
                    "text": "❌ Meeting data not found. Please try processing the meeting again."
                })

        state = get_conversation_state(db, recording_id)
        meeting_title = state['meeting_title']
        sales_data = state.get('sales_data', {})  # Use empty dict if not present
        meeting_url = state.get('meeting_url', '')  # Use empty string if not present
        external_emails = state['external_emails']

        if not external_emails:
            error_msg = "⚠️ No external attendees found. Cannot determine which Crono account to add note to."

            if is_modal_action:
                slack_client.client.views_update(
                    view_id=view_id,
                    view={
                        "type": "modal",
                        "title": {"type": "plain_text", "text": "Warning"},
                        "close": {"type": "plain_text", "text": "Close"},
                        "blocks": [
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"⚠️ *Warning*\n\n{error_msg}"
                                }
                            }
                        ]
                    }
                )
                return jsonify({})
            else:
                return jsonify({
                    "response_type": "ephemeral",
                    "replace_original": False,
                    "text": error_msg
                })

        # If from modal, create note synchronously and update modal
        if is_modal_action:
            try:
                # Create note synchronously
                crm_type = os.getenv('CRM_PROVIDER', 'crono')
                credentials = {
                    'public_key': os.getenv('CRONO_PUBLIC_KEY'),
                    'private_key': os.getenv('CRONO_API_KEY')
                }
                crm_provider = CRMProviderFactory.create(crm_type, credentials)

                # Find account
                email_domain = external_emails[0].split('@')[-1]
                company_name_raw = email_domain.split('.')[0]

                account = crm_provider.find_account_by_domain(
                    email_domain=email_domain,
                    company_name=company_name_raw
                )

                if not account:
                    slack_client.client.views_update(
                        view_id=view_id,
                        view={
                            "type": "modal",
                            "title": {"type": "plain_text", "text": "Not Found"},
                            "close": {"type": "plain_text", "text": "Close"},
                            "blocks": [
                                {
                                    "type": "section",
                                    "text": {
                                        "type": "mrkdwn",
                                        "text": f"⚠️ *Account Not Found*\n\nNo Crono account found for domain '{email_domain}'.\n\nPlease create the account in Crono first, then try again."
                                    }
                                }
                            ]
                        }
                    )
                    return jsonify({})

                account_id = account.get('objectId') or account.get('id')
                account_name = account.get('name', 'Unknown')
                crono_url = f"https://app.crono.one/accounts/{account_id}"

                # Create note
                note_id = crm_provider.create_meeting_summary(
                    account_id=account_id,
                    meeting_title=meeting_title,
                    summary_data=sales_data,
                    meeting_url=meeting_url
                )

                if note_id:
                    # Update modal with success banner, preserving all fields and buttons
                    current_view = payload.get('view', {})
                    success_message = f"Crono Note Created! Account: {account_name}"
                    updated_view = update_modal_with_success(
                        view=current_view,
                        completed_action_id='push_note_to_crono_from_modal',
                        success_message=success_message,
                        action_link=crono_url
                    )
                    slack_client.client.views_update(view_id=view_id, view=updated_view)
                    return jsonify({})
                else:
                    raise Exception("Failed to create note")

            except Exception as e:
                logger.error(f"❌ Error creating Crono note: {e}")
                slack_client.client.views_update(
                    view_id=view_id,
                    view={
                        "type": "modal",
                        "title": {"type": "plain_text", "text": "Error"},
                        "close": {"type": "plain_text", "text": "Close"},
                        "blocks": [
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"❌ *Error Creating Note*\n\n{str(e)}"
                                }
                            }
                        ]
                    }
                )
                return jsonify({})

        # If not from modal, process in background (Crono API can be slow)
        import threading

        def create_note_in_background():
            try:
                logger.info(f"🔄 Creating Crono note in background...")

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
                    logger.warning(f"⚠️  No Crono account found for domain {email_domain}")

                    if response_url:
                        requests.post(response_url, json={
                            "response_type": "ephemeral",
                            "replace_original": False,
                            "text": f"⚠️ No Crono account found for domain '{email_domain}'.\n\nPlease create the account in Crono first, then try again."
                        }, timeout=5)
                    return

                account_id = account.get('objectId') or account.get('id')
                account_name = account.get('name', 'Unknown')

                logger.info(f"✅ Found Crono account: {account_name} ({account_id})")

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
                    logger.info(f"✅ Crono note created: {note_id}")

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
                logger.error(f"❌ Error creating Crono note: {e}")
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
        logger.error(f"❌ Error in handle_create_crono_note: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)

        return jsonify({
            "response_type": "ephemeral",
            "replace_original": False,
            "text": f"❌ Error: {str(e)}"
        })


def handle_load_previous_meetings(db, payload: Dict):
    """Handle when user clicks 'Load Previous Meetings' button in modal."""
    import sys

    try:
        view_id = payload.get('view', {}).get('id')
        user_id = payload.get('user', {}).get('id')
        team_id = payload.get('team', {}).get('id')

        logger.info(f"⏮️ Loading previous meetings for user {user_id}...")

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
        logger.error(f"❌ Error in handle_load_previous_meetings: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)

        return jsonify({
            "response_action": "errors",
            "errors": {
                "load_previous_meetings_block": f"Error loading meetings: {str(e)}"
            }
        })


def handle_open_followup_edit_modal(db, payload: Dict):
    """Handle when user clicks 'View & Edit' button to open modal with editable fields."""
    import sys

    try:
        # Extract recording_id from button value
        recording_id = payload['actions'][0]['value']
        trigger_id = payload.get('trigger_id')

        logger.info(f"📝 Opening follow-up edit modal for recording {recording_id}...")

        # Retrieve stored meeting data from conversation state
        if not get_conversation_state(db, recording_id):
            logger.error(f"❌ No data found for recording {recording_id}")
            return jsonify({
                'status': 'error',
                'text': '❌ Meeting data not found. Please try processing the meeting again.'
            })

        # Get data from conversation state
        state = get_conversation_state(db, recording_id)
        meeting_title = state.get('meeting_title', 'Meeting')
        meeting_summary = state.get('meeting_summary', '')
        final_email = state.get('final_email', '')
        crm_note = state.get('crm_note', '')
        external_attendees_str = state.get('external_attendees_str', 'N/A')
        user_id = state.get('user_id')
        team_id = state.get('team_id')

        logger.info(f"✅ Retrieved state for {meeting_title}")

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

        logger.info(f"✅ Modal opened successfully")

        return jsonify({'status': 'ok'})

    except Exception as e:
        logger.error(f"❌ Error in handle_open_followup_edit_modal: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)

        return jsonify({
            'status': 'error',
            'text': f'❌ Error opening modal: {str(e)}'
        })


def handle_view_crono_deals(db, payload: Dict):
    """Handle when user clicks 'View Crono Deals' button."""
    import sys
    import requests

    try:
        # Get recording_id from button value
        recording_id = payload['actions'][0]['value']
        response_url = payload.get('response_url')

        logger.info(f"💰 Viewing Crono deals for recording {recording_id}...")

        # Retrieve stored meeting data
        if not get_conversation_state(db, recording_id):
            logger.error(f"❌ No data found for recording {recording_id}")
            return jsonify({
                "response_type": "ephemeral",
                "replace_original": False,
                "text": "❌ Meeting data not found. Please try processing the meeting again."
            })

        state = get_conversation_state(db, recording_id)
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
                logger.info(f"🔄 Fetching Crono deals in background...")

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
                    logger.warning(f"⚠️  No Crono account found for domain {email_domain}")

                    if response_url:
                        requests.post(response_url, json={
                            "response_type": "ephemeral",
                            "replace_original": False,
                            "text": f"⚠️ No Crono account found for domain '{email_domain}'.\n\nCannot retrieve deals without a linked Crono account."
                        }, timeout=5)
                    return

                account_id = account.get('objectId') or account.get('id')
                account_name = account.get('name', 'Unknown')

                logger.info(f"✅ Found Crono account: {account_name} ({account_id})")

                # Build Crono URL
                crono_url = f"https://app.crono.one/accounts/{account_id}"

                # Get deals for the account
                deals = crm_provider.get_deals(account_id, limit=100)

                if deals:
                    logger.info(f"✅ Found {len(deals)} deals for account {account_id}")

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
                    logger.warning(f"⚠️ No deals found for account {account_id}")
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
                logger.error(f"❌ Error fetching Crono deals: {e}")
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
        logger.error(f"❌ Error in handle_view_crono_deals: {e}")
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
    if not thread_ts or not get_conversation_state(db, thread_ts):
        return

    state = get_conversation_state(db, thread_ts)

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
        delete_conversation_state(db, thread_ts)


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
    if get_conversation_state(db, thread_ts):
        delete_conversation_state(db, thread_ts)


def handle_create_gmail_draft_from_modal(db, payload: Dict):
    """
    Handle Gmail draft creation from modal button.
    Uses data from database (already generated).
    """
    # NOTE: This function reuses the existing handle_create_gmail_draft logic
    # The data is already in database from handle_followup_meeting_submission
    return handle_create_gmail_draft(db, payload)


def handle_create_calendar_event_from_modal(db, payload: Dict):
    """
    Handle calendar event creation from modal button.
    Uses data from database (already generated).
    """
    # NOTE: This function reuses the existing handle_create_calendar_event logic
    return handle_create_calendar_event(db, payload)


def handle_push_note_to_crono_from_modal(db, payload: Dict):
    """
    Handle Crono note creation from modal button.
    Uses data from database (already generated).
    """
    # NOTE: This function reuses the existing handle_create_crono_note logic
    return handle_create_crono_note(db, payload)


def handle_view_crono_deals_from_modal(db, payload: Dict):
    """
    Handle viewing Crono deals from modal button.
    Uses data from database (already generated).
    """
    # NOTE: This function reuses the existing handle_view_crono_deals logic
    return handle_view_crono_deals(db, payload)


def handle_create_crono_task_from_modal(db, payload: Dict):
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

        logger.info(f"✅ Opening task creation modal for recording {recording_id}...")

        # Get meeting data from database if available
        meeting_title = "Follow-up Task"
        if recording_id and get_conversation_state(db, recording_id):
            state = get_conversation_state(db, recording_id)
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
        logger.error(f"❌ Slack API error opening task modal: {e.response}")
        return jsonify({
            "response_type": "ephemeral",
            "text": f"❌ Could not open task modal: {e.response.get('error', 'Slack error')}"
        })
    except Exception as e:
        logger.error(f"❌ Error in handle_create_crono_task_from_modal: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)

        return jsonify({
            "response_type": "ephemeral",
            "text": f"❌ Error: {str(e)}"
        })


def handle_block_suggestion(db, payload: dict):
    """Handler for external select suggestions (e.g., prospect search)."""
    action_id = payload.get('action_id')
    user_id = payload.get('user', {}).get('id')
    team_id = payload.get('team', {}).get('id')

    if action_id == 'crono_prospect_select':
        query = payload.get('value', '')
        logger.debug(f"🔍 [crono_prospect_select] query='{query}'\\n")
        options: List[Dict] = []

        try:
            with get_db() as db:
                credentials = get_user_crm_credentials(db, user_id, team_id)
                if credentials:
                    crm_provider = CronoProvider(credentials=credentials)
                    prospects = crm_provider.search_prospects(query=query, account_id=None, limit=200)
                    logger.debug(f"  - 📞 Found {len(prospects)} prospects\\n")

                    if len(prospects) == 0:
                        options.append({
                            "text": {"type": "plain_text", "text": "No contacts found. Try a different search."},
                            "value": "no_prospects"
                        })
                    else:
                        # Slack has a limit of ~100 options for external_select
                        max_options = 100
                        if len(prospects) > max_options:
                            logger.debug(f"  - Too many results ({len(prospects)}), limiting to {max_options}\\n")

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

                        logger.debug(f"  - Returning {len(options)} options\\n")
                        logger.debug(f"  - Response JSON (first 500 chars): {json.dumps({'options': options}, ensure_ascii=False)[:500]}\\n")
        except Exception as e:
            logger.error(f"🔥🔥🔥 EXCEPTION in crono_prospect_select: {e}\\n")
            import traceback
            traceback.print_exc(file=sys.stderr)

        return jsonify({"options": options})

    return jsonify({"options": []})


def handle_followup_meeting_submission(db, payload: dict):
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

    logger.info(f"📝 Processing meeting {selected_recording_id} for followup modal...")

    # Get channel_id from original modal metadata
    original_metadata = json.loads(view.get('private_metadata', '{}'))
    metadata_channel = original_metadata.get('channel_id')

    # Send "Processing..." message BEFORE starting background thread
    # For DMs, open a conversation first to get the proper channel ID
    if metadata_channel and metadata_channel.startswith('D'):
        # Open/ensure DM conversation exists
        dm_response = slack_web_client.conversations_open(users=user_id)
        channel_id = dm_response['channel']['id']
        logger.debug(f"DEBUG: Opened DM conversation: {channel_id}")
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
    logger.info(f"✅ Sent processing message (ts: {processing_ts})")

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
                logger.error(f"❌ Meeting {selected_recording_id} not found")
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

            logger.info(f"🤖 Generating AI content for: {meeting_title}")

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

            logger.info(f"✅ AI content generated successfully")

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

            # Store data in database for modal handler
            with get_db() as thread_db:
                set_conversation_state(thread_db, selected_recording_id, {
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
                })

            logger.info(f"✅ Content generated, updating message with 'View & Edit' button")

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

            logger.info(f"✅ Message updated with 'View & Edit' button")

        except Exception as e:
            logger.error(f"❌ Error in process_and_update_message: {e}")
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


def handle_crono_task_submission(db, payload: dict):
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
                    logger.warning(f"⚠️  Could not send confirmation message: {notify_error}")

            return jsonify({"response_action": "clear"})
    except Exception as e:
        logger.error(f"🔥🔥🔥 Error in task creation view_submission: {e}\\n")
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
        logger.error(f"Error in get_user_settings: {e}")
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
        logger.error(f"Error in save_user_settings: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================================================
# GOOGLE OAUTH ROUTES
# ============================================================================

@app.route('/oauth/google/start', methods=['GET'])
def google_oauth_start():
    """
    Initiate Google OAuth flow.

    Expected query parameters:
        - slack_user_id: User's Slack ID
        - team_id: Slack team/workspace ID (optional, defaults to hardcoded tenant)

    Redirects user to Google OAuth consent screen.
    """
    slack_user_id = request.args.get('slack_user_id')
    team_id = request.args.get('team_id', 'T02R43CJEMA')  # ASSUMPTION: Default to known tenant

    if not slack_user_id:
        return jsonify({"error": "slack_user_id parameter required"}), 400

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        logger.error("Google OAuth credentials not configured")
        return jsonify({"error": "Google OAuth not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET"}), 500

    try:
        # Create OAuth flow
        flow = create_google_oauth_flow()

        # Encode user context in state parameter
        state_data = {
            "slack_user_id": slack_user_id,
            "team_id": team_id
        }
        state_json = json.dumps(state_data)
        state_encoded = base64.urlsafe_b64encode(state_json.encode()).decode()

        # Generate authorization URL
        authorization_url, state = flow.authorization_url(
            access_type='offline',  # Get refresh token
            prompt='consent',  # Force consent to ensure refresh token
            state=state_encoded,
            include_granted_scopes='true'
        )

        logger.info(f"Starting OAuth flow for user {slack_user_id}")
        return redirect(authorization_url)

    except Exception as e:
        logger.error(f"Error starting OAuth flow: {e}", exc_info=True)
        return jsonify({"error": f"Failed to start OAuth flow: {str(e)}"}), 500


@app.route('/oauth/google/callback', methods=['GET'])
def google_oauth_callback():
    """
    Handle Google OAuth callback.

    Receives authorization code, exchanges it for tokens,
    and saves them to the database.
    """
    # Check for errors from Google
    error = request.args.get('error')
    if error:
        logger.error(f"OAuth error from Google: {error}")
        return render_template('oauth_result.html',
                               success=False,
                               message=f"Authentication failed: {error}"), 400

    # Get authorization code
    code = request.args.get('code')
    state_encoded = request.args.get('state')

    if not code or not state_encoded:
        return jsonify({"error": "Missing code or state parameter"}), 400

    try:
        # Decode state to get user context
        state_json = base64.urlsafe_b64decode(state_encoded.encode()).decode()
        state_data = json.loads(state_json)
        slack_user_id = state_data.get('slack_user_id')
        team_id = state_data.get('team_id', 'T02R43CJEMA')

        if not slack_user_id:
            return jsonify({"error": "Invalid state parameter"}), 400

        # Create OAuth flow
        flow = create_google_oauth_flow()

        # Exchange authorization code for tokens
        flow.fetch_token(code=code)

        # Get credentials
        credentials = flow.credentials

        # Prepare token JSON to store in database
        token_data = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes,
            'expiry': credentials.expiry.isoformat() if credentials.expiry else None
        }
        token_json = json.dumps(token_data)

        # Save to database
        with get_db() as db:
            # Find tenant
            tenant = db.query(Tenant).filter(Tenant.slack_team_id == team_id).first()
            if not tenant:
                logger.error(f"Tenant not found: {team_id}")
                return jsonify({"error": "Tenant not found"}), 404

            # Find or create user
            user = db.query(User).filter(
                User.slack_user_id == slack_user_id,
                User.tenant_id == tenant.id
            ).first()

            if not user:
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

            # Save tokens (same token works for both Gmail and Calendar)
            settings.gmail_token = token_json
            settings.calendar_token = token_json
            db.commit()

            logger.info(f"✅ Saved Google OAuth tokens for user {slack_user_id}")

        # Return success page
        return render_template('oauth_result.html',
                               success=True,
                               message="Successfully connected your Google account! You can close this window and return to Slack.")

    except Exception as e:
        logger.error(f"Error in OAuth callback: {e}", exc_info=True)
        return render_template('oauth_result.html',
                               success=False,
                               message=f"Failed to complete authentication: {str(e)}"), 500


@app.route('/api/google/status', methods=['GET'])
def google_oauth_status():
    """
    Check if user has connected their Google account.

    Expected query parameters:
        - slack_user_id: User's Slack ID
        - team_id: Slack team/workspace ID (optional)

    Returns:
        JSON with connection status and email if available
    """
    slack_user_id = request.args.get('slack_user_id')
    team_id = request.args.get('team_id', 'T02R43CJEMA')

    if not slack_user_id:
        return jsonify({"error": "slack_user_id parameter required"}), 400

    try:
        with get_db() as db:
            # Find tenant
            tenant = db.query(Tenant).filter(Tenant.slack_team_id == team_id).first()
            if not tenant:
                return jsonify({"connected": False, "error": "Tenant not found"}), 200

            # Find user
            user = db.query(User).filter(
                User.slack_user_id == slack_user_id,
                User.tenant_id == tenant.id
            ).first()

            if not user or not user.settings or not user.settings.gmail_token:
                return jsonify({"connected": False}), 200

            # Check if token is valid
            token_json = user.settings.gmail_token
            token_data = json.loads(token_json)

            # ASSUMPTION: If we have a token, consider it connected
            # We'll handle refresh in the actual Gmail/Calendar modules
            response = {
                "connected": True,
                "email": token_data.get('email', 'Connected')  # Email might not be in token
            }

            return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error checking Google OAuth status: {e}")
        return jsonify({"connected": False, "error": str(e)}), 200


@app.route('/api/google/disconnect', methods=['POST'])
def google_oauth_disconnect():
    """
    Disconnect Google account by removing stored tokens.

    Expected JSON body:
        - slack_user_id: User's Slack ID
        - team_id: Slack team/workspace ID (optional)

    Returns:
        Success message
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    slack_user_id = data.get('slack_user_id')
    team_id = data.get('team_id', 'T02R43CJEMA')

    if not slack_user_id:
        return jsonify({"error": "slack_user_id required"}), 400

    try:
        with get_db() as db:
            # Find tenant
            tenant = db.query(Tenant).filter(Tenant.slack_team_id == team_id).first()
            if not tenant:
                return jsonify({"error": "Tenant not found"}), 404

            # Find user
            user = db.query(User).filter(
                User.slack_user_id == slack_user_id,
                User.tenant_id == tenant.id
            ).first()

            if not user or not user.settings:
                return jsonify({"message": "No settings to disconnect"}), 200

            # Clear tokens
            user.settings.gmail_token = None
            user.settings.calendar_token = None
            db.commit()

            logger.info(f"✅ Disconnected Google account for user {slack_user_id}")
            return jsonify({"message": "Google account disconnected successfully"}), 200

    except Exception as e:
        logger.error(f"Error disconnecting Google account: {e}")
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
    logger.info(f"🚀 Starting Slack webhook handler on port {port}...")
    logger.info(f"📡 Webhook URLs:")
    logger.info(f"   Events: http://localhost:{port}/slack/events")
    logger.info(f"   Interactions: http://localhost:{port}/slack/interactions")
    logger.info(f"\n⚠️  Make sure to expose this with ngrok for Slack to reach it:")
    logger.info(f"   ngrok http {port}")
    logger.info(f"\nPress Ctrl+C to stop\n")

    app.run(host='0.0.0.0', port=port, debug=debug)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Start Slack webhook handler')
    parser.add_argument('--port', type=int, default=3000, help='Port to run on (default: 3000)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')

    args = parser.parse_args()

    start_webhook_server(port=args.port, debug=args.debug)
