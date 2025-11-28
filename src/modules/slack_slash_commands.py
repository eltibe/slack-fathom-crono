#!/usr/bin/env python3
"""
Slack Slash Commands Handler

Handles /followup command to show today's meetings and process selected one.
"""

import os
from typing import Dict, List, Optional
from datetime import datetime, timezone
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from modules.fathom_client import FathomClient


class SlackSlashCommandHandler:
    """
    Handler for Slack slash commands.
    """

    def __init__(self, bot_token: Optional[str] = None):
        """
        Initialize slash command handler.

        Args:
            bot_token: Slack Bot Token. If not provided, reads from SLACK_BOT_TOKEN env var.
        """
        self.bot_token = bot_token or os.getenv('SLACK_BOT_TOKEN')
        if not self.bot_token:
            raise ValueError("Slack Bot Token is required")

        self.client = WebClient(token=self.bot_token)
        self.fathom = FathomClient()

    def handle_followup_command(self, user_id: str, channel_id: str, response_url: str) -> Dict:
        """
        Handle /followup slash command.
        Shows list of today's meetings for user to select.
        If no meetings today, shows yesterday's meetings instead.

        Args:
            user_id: Slack user ID who invoked the command
            channel_id: Channel where command was invoked
            response_url: URL to send delayed response

        Returns:
            Dict with immediate response
        """
        try:
            # Get today's meetings from Fathom
            meetings = self._get_todays_meetings()
            day_label = "Today"

            # If no meetings today, try yesterday
            if not meetings:
                meetings = self._get_yesterdays_meetings()
                day_label = "Yesterday"

            if not meetings:
                return {
                    "response_type": "ephemeral",
                    "text": "📭 No meetings found.",
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "📭 *No meetings found today or yesterday.*\n\nNo Fathom recordings found for the last 2 days. Make sure you have recorded meetings in Fathom."
                            }
                        }
                    ]
                }

            # Build interactive message with meeting list
            blocks = self._build_meeting_selection_blocks(meetings, day_label=day_label)

            return {
                "response_type": "ephemeral",  # Only visible to you
                "text": f"Found {len(meetings)} meeting(s) from {day_label.lower()}",
                "blocks": blocks
            }

        except Exception as e:
            return {
                "response_type": "ephemeral",
                "text": f"❌ Error: {str(e)}"
            }

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

    def _build_meeting_selection_blocks(self, meetings: List[Dict], day_label: str = "Today") -> List[Dict]:
        """
        Build Slack blocks for meeting selection.

        Args:
            meetings: List of meeting dicts
            day_label: Label for the day ("Today" or "Yesterday")

        Returns:
            List of Slack Block Kit blocks
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
                    "text": "Select a meeting to generate follow-up email and notes:"
                }
            },
            {
                "type": "divider"
            }
        ]

        # Add radio buttons for each meeting
        options = []
        for i, meeting in enumerate(meetings):
            # Format start time
            try:
                start_dt = datetime.fromisoformat(meeting['start_time'].replace('Z', '+00:00'))
                time_str = start_dt.strftime('%H:%M')
            except:
                time_str = "Unknown time"

            # Format duration
            duration = meeting.get('duration', 0)
            duration_str = f"{duration}min" if duration else ""

            # Create option text
            option_text = f"*{meeting['title']}*\n{time_str}"
            if duration_str:
                option_text += f" • {duration_str}"

            options.append({
                "text": {
                    "type": "mrkdwn",
                    "text": option_text
                },
                "value": str(meeting['recording_id'])  # Must be string for Slack
            })

        # Add radio button group
        blocks.append({
            "type": "actions",
            "block_id": "meeting_selection",
            "elements": [
                {
                    "type": "radio_buttons",
                    "action_id": "select_meeting",
                    "options": options
                }
            ]
        })

        blocks.append({
            "type": "divider"
        })

        # Add process button
        blocks.append({
            "type": "actions",
            "block_id": "process_meeting",
            "elements": [
                {
                    "type": "button",
                    "action_id": "process_meeting_button",
                    "text": {
                        "type": "plain_text",
                        "text": "Generate Follow-up"
                    },
                    "style": "primary",
                    "value": "process"
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
