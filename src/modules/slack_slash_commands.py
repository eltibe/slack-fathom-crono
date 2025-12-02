#!/usr/bin/env python3
"""
Slack Slash Commands Handler

Handles /followup command to show today's meetings and process selected one.
"""

import os
import json
from typing import Dict, List, Optional
from datetime import datetime, timezone, date
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from src.modules.fathom_client import FathomClient


class SlackSlashCommandHandler:
    """
    Handler for Slack slash commands.
    """

    def __init__(self, bot_token: Optional[str] = None, fathom_api_key: Optional[str] = None):
        """
        Initialize slash command handler.

        Args:
            bot_token: Slack Bot Token. If not provided, reads from SLACK_BOT_TOKEN env var.
            fathom_api_key: Fathom API key for the user. If not provided, uses env var.
        """
        self.bot_token = bot_token or os.getenv('SLACK_BOT_TOKEN')
        if not self.bot_token:
            raise ValueError("Slack Bot Token is required")

        self.client = WebClient(token=self.bot_token)
        self.fathom = FathomClient(api_key=fathom_api_key) if fathom_api_key else FathomClient()

    def handle_followup_command(self, user_id: str, channel_id: str, trigger_id: str, slack_web_client: WebClient):
        """
        Handle /followup slash command by opening a modal to select a meeting.

        Args:
            user_id: The ID of the user invoking the command.
            channel_id: Channel where command was invoked.
            trigger_id: Trigger ID for opening a modal.
            slack_web_client: The Slack WebClient to interact with the API.
        """
        try:
            meetings = self._get_todays_meetings()
            day_label = "Today"

            if not meetings:
                meetings = self._get_yesterdays_meetings()
                day_label = "Yesterday"

            if not meetings:
                # Open modal with "no meetings" message instead of ephemeral
                slack_web_client.views_open(
                    trigger_id=trigger_id,
                    view={
                        "type": "modal",
                        "callback_id": "no_meetings_modal",
                        "title": {"type": "plain_text", "text": "Meeting Follow-up"},
                        "close": {"type": "plain_text", "text": "Close"},
                        "blocks": [
                            {
                                "type": "header",
                                "text": {
                                    "type": "plain_text",
                                    "text": "📭 No Meetings Found",
                                    "emoji": True
                                }
                            },
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": "No meetings found for today or yesterday.\n\nTry recording a meeting with Fathom first!"
                                }
                            }
                        ]
                    }
                )
                return

            blocks = self._build_meeting_selection_modal_blocks(meetings, day_label=day_label)
            
            slack_web_client.views_open(
                trigger_id=trigger_id,
                view={
                    "type": "modal",
                    "callback_id": "followup_meeting_select_modal",
                    "title": {"type": "plain_text", "text": "Meeting Follow-up"},
                    "submit": {"type": "plain_text", "text": "Next"},
                    "close": {"type": "plain_text", "text": "Cancel"},
                    "blocks": blocks,
                    "private_metadata": json.dumps({"channel_id": channel_id})
                }
            )

        except Exception as e:
            import sys
            sys.stderr.write(f"❌ Error in handle_followup_command: {e}\n")
            import traceback
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
            try:
                slack_web_client.chat_postEphemeral(
                    channel=channel_id,
                    user=user_id,
                    text=f"❌ An error occurred: {e}"
                )
            except Exception as slack_err:
                sys.stderr.write(f"❌ Error sending error message to Slack: {slack_err}\n")
                sys.stderr.flush()

    def _get_meetings_by_date(self, target_date: date) -> List[Dict]:
        """
        Get all meetings from a specific date.

        Args:
            target_date: The date to filter meetings by

        Returns:
            List of meeting dicts with id, title, start_time
        """
        try:
            # Get all recordings
            all_recordings = self.fathom.get_all_recordings()

            if not all_recordings:
                return []

            meetings = []

            for recording in all_recordings:
                # Parse recording start time
                start_time = recording.get('recording_start_time') or recording.get('start_time')
                if not start_time:
                    continue

                try:
                    # Parse ISO format datetime
                    meeting_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    meeting_date = meeting_dt.date()

                    if meeting_date == target_date:
                        meetings.append({
                            'recording_id': recording.get('recording_id') or recording.get('id'),
                            'title': recording.get('meeting_title') or recording.get('title', 'Untitled Meeting'),
                            'start_time': start_time,
                            'duration': recording.get('duration_minutes', 0)
                        })
                except Exception as e:
                    print(f"Error parsing meeting time: {e}")
                    continue

            # Sort by start time (most recent first)
            meetings.sort(key=lambda x: x['start_time'], reverse=True)

            return meetings

        except Exception as e:
            print(f"Error getting meetings for {target_date}: {e}")
            return []

    def _get_todays_meetings(self) -> List[Dict]:
        """
        Get all meetings from today.

        Returns:
            List of meeting dicts with id, title, start_time
        """
        today = datetime.now(timezone.utc).date()
        return self._get_meetings_by_date(today)

    def _get_yesterdays_meetings(self) -> List[Dict]:
        """
        Get all meetings from yesterday.

        Returns:
            List of meeting dicts with id, title, start_time
        """
        from datetime import timedelta
        yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
        return self._get_meetings_by_date(yesterday)

    def _build_meeting_selection_modal_blocks(self, meetings: List[Dict], day_label: str = "Today", show_load_more: bool = True) -> List[Dict]:
        """
        Build Slack modal blocks for meeting selection.

        Args:
            meetings: List of meeting dicts
            day_label: Label for the day ("Today" or "Yesterday")
            show_load_more: Whether to show "Load Previous Meetings" button

        Returns:
            List of Slack Block Kit blocks for a modal
        """
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📅 {day_label}'s Meetings ({len(meetings)})",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Select a meeting to generate a follow-up."
                }
            }
        ]

        # Create options for the static select menu
        options = []
        for meeting in meetings:
            try:
                start_dt = datetime.fromisoformat(meeting['start_time'].replace('Z', '+00:00'))
                time_str = start_dt.strftime('%H:%M')
            except:
                time_str = "Unknown time"

            duration = meeting.get('duration', 0)
            duration_str = f"({duration} min)" if duration else ""

            option_text = f"{time_str} - {meeting['title']} {duration_str}"

            options.append({
                "text": {
                    "type": "plain_text",
                    "text": option_text[:75]  # Max 75 chars for option text
                },
                "value": str(meeting['recording_id'])
            })

        # Add a select menu for meetings
        if options:
            blocks.append({
                "type": "input",
                "block_id": "meeting_selection_block",
                "label": {
                    "type": "plain_text",
                    "text": "Select a meeting"
                },
                "element": {
                    "type": "static_select",
                    "action_id": "selected_meeting_id",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Choose a meeting..."
                    },
                    "options": options
                }
            })

        # Add "Load Previous Meetings" button if this is today's view
        if show_load_more and day_label == "Today":
            blocks.append({
                "type": "actions",
                "block_id": "load_previous_meetings_block",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "⏮️ Load Previous Meetings"
                        },
                        "action_id": "load_previous_meetings",
                        "style": "primary"
                    }
                ]
            })

        return blocks

    def send_processing_message(self, channel: str, meeting_title: str) -> Dict:
        """
        Send a "processing..." message while generating content.

        Args:
            channel: Slack channel/user ID
            meeting_title: Title of meeting being processed

        Returns:
            Dict with message timestamp
        """
        try:
            response = self.client.chat_postMessage(
                channel=channel,
                text=f"Processing {meeting_title}...",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"⏳ *Processing meeting: {meeting_title}*\n\nGenerating follow-up email and extracting insights... This may take 30-60 seconds."
                        }
                    }
                ]
            )

            return {'ts': response['ts'], 'channel': response['channel']}

        except SlackApiError as e:
            print(f"Error sending processing message: {e.response['error']}")
            raise


def test_slash_command():
    """Test function to verify slash command handler."""
    from dotenv import load_dotenv
    load_dotenv()

    print("🧪 Testing Slash Command Handler...")

    try:
        handler = SlackSlashCommandHandler()

        # Test getting today's meetings
        print("\n📅 Fetching today's meetings...")
        meetings = handler._get_todays_meetings()

        print(f"✅ Found {len(meetings)} meeting(s) today:")
        for meeting in meetings:
            print(f"  - {meeting['title']} at {meeting['start_time']}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_slash_command()
