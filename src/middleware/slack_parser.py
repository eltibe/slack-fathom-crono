"""
Slack request parser for extracting tenant information from webhook requests.

This module handles parsing of different Slack webhook request types:
- Slash commands (form data)
- Interactive components (JSON payload in form data)
- Events API (JSON body)

Security:
- Validates Slack signing secret on all requests
- Protects against replay attacks (timestamp validation)
- Prevents request tampering

Supported Request Types:
1. Slash Commands: POST with application/x-www-form-urlencoded
   - team_id field directly in form data

2. Interactions: POST with application/x-www-form-urlencoded
   - payload field containing JSON with team.id

3. Events API: POST with application/json
   - team_id field in JSON body (or team.id for some events)
"""

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Optional, Dict, Any

from flask import Request
from dotenv import load_dotenv

from src.middleware.exceptions import InvalidSlackRequestError

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Slack configuration
SLACK_SIGNING_SECRET = os.getenv('SLACK_SIGNING_SECRET')
SLACK_REQUEST_TIMESTAMP_MAX_DIFF = 60 * 5  # 5 minutes


def verify_slack_signature(
    request: Request,
    signing_secret: str = None
) -> bool:
    """
    Verify that a request came from Slack by validating its signature.

    Slack signs all requests with HMAC-SHA256 using your signing secret.
    This prevents request forgery and tampering.

    Args:
        request: Flask request object
        signing_secret: Slack signing secret (defaults to env var)

    Returns:
        True if signature is valid, False otherwise

    Security:
        - Checks timestamp to prevent replay attacks (5 minute window)
        - Uses constant-time comparison to prevent timing attacks
        - Validates signature format and presence

    Example:
        if not verify_slack_signature(request):
            return jsonify({'error': 'Invalid signature'}), 403
    """
    if signing_secret is None:
        signing_secret = SLACK_SIGNING_SECRET

    if not signing_secret:
        logger.error("SLACK_SIGNING_SECRET not configured")
        return False

    # Get signature components from headers
    timestamp = request.headers.get('X-Slack-Request-Timestamp')
    signature = request.headers.get('X-Slack-Signature')

    if not timestamp or not signature:
        logger.warning("Missing Slack signature headers")
        return False

    # Check timestamp to prevent replay attacks
    try:
        request_time = int(timestamp)
        current_time = int(time.time())

        if abs(current_time - request_time) > SLACK_REQUEST_TIMESTAMP_MAX_DIFF:
            logger.warning(
                f"Request timestamp too old: {abs(current_time - request_time)} seconds"
            )
            return False
    except ValueError:
        logger.warning(f"Invalid timestamp format: {timestamp}")
        return False

    # Get raw request body
    body = request.get_data(as_text=True)

    # Compute expected signature
    sig_basestring = f"v0:{timestamp}:{body}"
    expected_signature = 'v0=' + hmac.new(
        signing_secret.encode('utf-8'),
        sig_basestring.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(expected_signature, signature):
        logger.warning("Signature verification failed")
        return False

    return True


def extract_tenant_id_from_request(request: Request) -> Optional[str]:
    """
    Extract Slack team_id from various types of Slack webhook requests.

    Handles multiple request formats:
    1. Slash commands: team_id in form data
    2. Interactions: team.id in JSON payload field
    3. Events API: team_id in JSON body

    Args:
        request: Flask request object

    Returns:
        Slack team ID (e.g., "T0123456789") or None if not found

    Example:
        team_id = extract_tenant_id_from_request(request)
        if not team_id:
            return jsonify({'error': 'Cannot determine workspace'}), 400
    """
    try:
        content_type = request.content_type or ''

        # Handle form-encoded requests (slash commands and interactions)
        if 'application/x-www-form-urlencoded' in content_type:
            return _extract_from_form_data(request)

        # Handle JSON requests (events API)
        elif 'application/json' in content_type:
            return _extract_from_json(request)

        else:
            logger.warning(f"Unknown content type: {content_type}")
            return None

    except Exception as e:
        logger.error(f"Error extracting team_id from request: {e}", exc_info=True)
        return None


def _extract_from_form_data(request: Request) -> Optional[str]:
    """
    Extract team_id from form-encoded request.

    Handles:
    1. Slash commands: team_id field
    2. Interactions: payload field with JSON containing team.id

    Args:
        request: Flask request object

    Returns:
        Slack team ID or None
    """
    # Check for direct team_id field (slash commands)
    team_id = request.form.get('team_id')
    if team_id:
        logger.debug(f"Extracted team_id from form data: {team_id}")
        return team_id

    # Check for payload field (interactive components)
    payload_str = request.form.get('payload')
    if payload_str:
        try:
            payload = json.loads(payload_str)
            return _extract_team_id_from_payload(payload)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse interaction payload: {e}")
            return None

    logger.warning("No team_id found in form data")
    return None


def _extract_from_json(request: Request) -> Optional[str]:
    """
    Extract team_id from JSON request body.

    Handles Events API and other JSON-based webhooks.

    Args:
        request: Flask request object

    Returns:
        Slack team ID or None
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            logger.warning("Empty JSON body")
            return None

        return _extract_team_id_from_payload(data)

    except Exception as e:
        logger.error(f"Error parsing JSON request: {e}")
        return None


def _extract_team_id_from_payload(payload: Dict[str, Any]) -> Optional[str]:
    """
    Extract team_id from a parsed payload dictionary.

    Tries multiple possible locations:
    - payload['team_id'] (most common)
    - payload['team']['id'] (interactions, events)
    - payload['authorizations'][0]['team_id'] (events API v2)

    Args:
        payload: Parsed JSON payload

    Returns:
        Slack team ID or None
    """
    # Direct team_id field
    if 'team_id' in payload:
        team_id = payload['team_id']
        logger.debug(f"Extracted team_id from payload: {team_id}")
        return team_id

    # Nested team object
    if 'team' in payload and isinstance(payload['team'], dict):
        team_id = payload['team'].get('id')
        if team_id:
            logger.debug(f"Extracted team.id from payload: {team_id}")
            return team_id

    # Events API v2 with authorizations
    if 'authorizations' in payload and isinstance(payload['authorizations'], list):
        if len(payload['authorizations']) > 0:
            auth = payload['authorizations'][0]
            team_id = auth.get('team_id')
            if team_id:
                logger.debug(f"Extracted team_id from authorizations: {team_id}")
                return team_id

    # Check in event object (for event callbacks)
    if 'event' in payload and isinstance(payload['event'], dict):
        event = payload['event']
        team_id = event.get('team')  # Some events use 'team' instead of 'team_id'
        if team_id:
            logger.debug(f"Extracted team from event: {team_id}")
            return team_id

    logger.warning(f"Could not find team_id in payload. Keys: {list(payload.keys())}")
    return None


def parse_slash_command(request: Request) -> Dict[str, Any]:
    """
    Parse a slash command request into a structured dictionary.

    Args:
        request: Flask request object

    Returns:
        Dictionary with parsed slash command data

    Example:
        cmd_data = parse_slash_command(request)
        print(f"Command: {cmd_data['command']}")
        print(f"User: {cmd_data['user_id']}")
        print(f"Text: {cmd_data['text']}")
    """
    return {
        'command': request.form.get('command'),
        'text': request.form.get('text', ''),
        'user_id': request.form.get('user_id'),
        'user_name': request.form.get('user_name'),
        'channel_id': request.form.get('channel_id'),
        'channel_name': request.form.get('channel_name'),
        'team_id': request.form.get('team_id'),
        'team_domain': request.form.get('team_domain'),
        'response_url': request.form.get('response_url'),
        'trigger_id': request.form.get('trigger_id'),
    }


def parse_interaction(request: Request) -> Dict[str, Any]:
    """
    Parse an interaction request (buttons, menus, etc.) into a structured dictionary.

    Args:
        request: Flask request object

    Returns:
        Parsed interaction payload

    Example:
        interaction = parse_interaction(request)
        action_id = interaction['actions'][0]['action_id']
        user_id = interaction['user']['id']
    """
    payload_str = request.form.get('payload')
    if not payload_str:
        raise InvalidSlackRequestError("Missing payload field in interaction request")

    try:
        return json.loads(payload_str)
    except json.JSONDecodeError as e:
        raise InvalidSlackRequestError(
            "Invalid JSON in interaction payload",
            details=str(e)
        )


def parse_event(request: Request) -> Dict[str, Any]:
    """
    Parse an Events API request into a structured dictionary.

    Args:
        request: Flask request object

    Returns:
        Parsed event data

    Example:
        event_data = parse_event(request)
        if event_data['type'] == 'url_verification':
            return jsonify({'challenge': event_data['challenge']})
    """
    data = request.get_json(silent=True)
    if not data:
        raise InvalidSlackRequestError("Empty or invalid JSON body in event request")

    return data


def get_request_type(request: Request) -> str:
    """
    Determine the type of Slack request.

    Args:
        request: Flask request object

    Returns:
        Request type: 'slash_command', 'interaction', 'event', or 'unknown'

    Example:
        req_type = get_request_type(request)
        if req_type == 'slash_command':
            handle_slash_command(request)
        elif req_type == 'interaction':
            handle_interaction(request)
    """
    content_type = request.content_type or ''

    if 'application/x-www-form-urlencoded' in content_type:
        # Check if it's an interaction (has payload field) or slash command
        if 'payload' in request.form:
            return 'interaction'
        elif 'command' in request.form:
            return 'slash_command'

    elif 'application/json' in content_type:
        return 'event'

    return 'unknown'


def log_request_info(request: Request) -> None:
    """
    Log information about a Slack request for debugging.

    Args:
        request: Flask request object

    Example:
        @app.before_request
        def log_slack_requests():
            if request.path.startswith('/slack/'):
                log_request_info(request)
    """
    team_id = extract_tenant_id_from_request(request)
    req_type = get_request_type(request)

    logger.info(
        f"Slack request: type={req_type}, team_id={team_id}, path={request.path}",
        extra={
            'request_type': req_type,
            'team_id': team_id,
            'path': request.path,
            'method': request.method,
            'content_type': request.content_type,
        }
    )
