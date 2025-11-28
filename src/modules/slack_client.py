#!/usr/bin/env python3
"""
Slack Client for Meeting Follow-up Tool

Sends interactive messages to Slack with meeting summaries and
allows users to choose which actions to execute (Gmail, Calendar, Crono).
"""

import os
import json
from typing import Dict, List, Optional
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


class SlackClient:
    """
    Client for sending interactive meeting follow-up messages to Slack.
    """

    def __init__(self, bot_token: Optional[str] = None):
        """
        Initialize Slack client.

        Args:
            bot_token: Slack Bot Token (xoxb-...). If not provided, reads from SLACK_BOT_TOKEN env var.
        """
        self.bot_token = bot_token or os.getenv('SLACK_BOT_TOKEN')
        if not self.bot_token:
            raise ValueError("Slack Bot Token is required. Set SLACK_BOT_TOKEN in .env file.")

        self.client = WebClient(token=self.bot_token)

    def send_meeting_review_message(
        self,
        channel: str,
        meeting_title: str,
        meeting_summary: str,
        proposed_email: str,
        sales_insights: Dict[str, str],
        meeting_url: Optional[str] = None,
        external_emails: Optional[List[str]] = None
    ) -> Dict:
        """
        Send an interactive message to Slack for meeting review.

        Args:
            channel: Slack channel ID or name (e.g., "#sales" or "C1234567890")
            meeting_title: Title of the meeting
            meeting_summary: AI-generated summary of the meeting
            proposed_email: The AI-generated follow-up email
            sales_insights: Dict with tech_stack, pain_points, impact, next_steps, roadblocks
            meeting_url: Optional Fathom meeting URL
            external_emails: List of external participant emails

        Returns:
            Dict with message timestamp and channel
        """
        try:
            # Build the blocks for the message
            blocks = self._build_message_blocks(
                meeting_title=meeting_title,
                meeting_summary=meeting_summary,
                proposed_email=proposed_email,
                sales_insights=sales_insights,
                meeting_url=meeting_url,
                external_emails=external_emails
            )

            # Send the message
            response = self.client.chat_postMessage(
                channel=channel,
                text=f"📋 Meeting Follow-up: {meeting_title}",
                blocks=blocks,
                unfurl_links=False,
                unfurl_media=False
            )

            return {
                'ts': response['ts'],
                'channel': response['channel']
            }

        except SlackApiError as e:
            print(f"Error sending Slack message: {e.response['error']}")
            raise

    def _build_message_blocks(
        self,
        meeting_title: str,
        meeting_summary: str,
        proposed_email: str,
        sales_insights: Dict[str, str],
        meeting_url: Optional[str],
        external_emails: Optional[List[str]]
    ) -> List[Dict]:
        """Build Slack Block Kit message blocks."""

        blocks = [
            # Header
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📋 {meeting_title}",
                    "emoji": True
                }
            },
            {
                "type": "divider"
            },
            # Meeting Summary Section
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Meeting Summary*\n{meeting_summary}"
                }
            }
        ]

        # Add meeting URL if available
        if meeting_url:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🎥 <{meeting_url}|View recording in Fathom>"
                }
            })

        # Add participants if available
        if external_emails:
            participants_text = ", ".join(external_emails)
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Participants:* {participants_text}"
                }
            })

        blocks.append({"type": "divider"})

        # Proposed Email Section
        # Truncate email if too long (Slack has 3000 char limit per block)
        email_preview = proposed_email[:2800] + "..." if len(proposed_email) > 2800 else proposed_email

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*📧 Proposed Follow-up Email*\n```{email_preview}```"
            }
        })

        blocks.append({"type": "divider"})

        # Sales Insights Section
        insights_text = self._format_sales_insights(sales_insights)
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*💡 Sales Insights*\n{insights_text}"
            }
        })

        blocks.append({"type": "divider"})

        # Action Selection Section
        blocks.extend([
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Select actions to execute:*"
                }
            },
            {
                "type": "actions",
                "block_id": "action_selection",
                "elements": [
                    {
                        "type": "checkboxes",
                        "action_id": "actions_checkbox",
                        "options": [
                            {
                                "text": {
                                    "type": "mrkdwn",
                                    "text": "📧 *Create Gmail Draft*"
                                },
                                "value": "gmail_draft"
                            },
                            {
                                "text": {
                                    "type": "mrkdwn",
                                    "text": "📅 *Add Calendar Event*"
                                },
                                "value": "calendar_event"
                            },
                            {
                                "text": {
                                    "type": "mrkdwn",
                                    "text": "📝 *Save to Crono CRM*"
                                },
                                "value": "crono_note"
                            }
                        ],
                        # Pre-select all by default
                        "initial_options": [
                            {
                                "text": {
                                    "type": "mrkdwn",
                                    "text": "📧 *Create Gmail Draft*"
                                },
                                "value": "gmail_draft"
                            },
                            {
                                "text": {
                                    "type": "mrkdwn",
                                    "text": "📅 *Add Calendar Event*"
                                },
                                "value": "calendar_event"
                            },
                            {
                                "text": {
                                    "type": "mrkdwn",
                                    "text": "📝 *Save to Crono CRM*"
                                },
                                "value": "crono_note"
                            }
                        ]
                    }
                ]
            },
            {
                "type": "actions",
                "block_id": "execute_actions",
                "elements": [
                    {
                        "type": "button",
                        "action_id": "execute_button",
                        "text": {
                            "type": "plain_text",
                            "text": "Execute Selected Actions"
                        },
                        "style": "primary",
                        "value": "execute"
                    },
                    {
                        "type": "button",
                        "action_id": "cancel_button",
                        "text": {
                            "type": "plain_text",
                            "text": "Cancel"
                        },
                        "style": "danger",
                        "value": "cancel"
                    }
                ]
            }
        ])

        return blocks

    def _format_sales_insights(self, insights: Dict[str, str]) -> str:
        """Format sales insights as markdown text."""
        parts = []

        if insights.get('tech_stack'):
            parts.append(f"💻 *Tech Stack:* {insights['tech_stack']}")

        if insights.get('pain_points'):
            parts.append(f"⚠️ *Pain Points:* {insights['pain_points']}")

        if insights.get('impact'):
            parts.append(f"📊 *Impact:* {insights['impact']}")

        if insights.get('next_steps'):
            parts.append(f"✅ *Next Steps:* {insights['next_steps']}")

        if insights.get('roadblocks'):
            parts.append(f"🚧 *Roadblocks:* {insights['roadblocks']}")

        return "\n".join(parts) if parts else "_No sales insights extracted_"

    def send_confirmation_request(
        self,
        channel: str,
        thread_ts: str,
        selected_actions: List[str]
    ) -> Dict:
        """
        Send a confirmation message asking user to confirm actions.

        Args:
            channel: Slack channel ID
            thread_ts: Thread timestamp to reply in
            selected_actions: List of action values selected (e.g., ['gmail_draft', 'calendar_event'])

        Returns:
            Dict with message timestamp
        """
        # Format action names
        action_names = {
            'gmail_draft': '✅ Gmail Draft',
            'calendar_event': '✅ Calendar Event',
            'crono_note': '✅ Crono Note'
        }

        actions_text = "\n".join([action_names.get(a, a) for a in selected_actions])

        message = f"Vuoi procedere con:\n{actions_text}\n\nRispondere *'sì'* per confermare o *'no'* per annullare"

        try:
            response = self.client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=message
            )

            return {'ts': response['ts']}

        except SlackApiError as e:
            print(f"Error sending confirmation: {e.response['error']}")
            raise

    def send_execution_result(
        self,
        channel: str,
        thread_ts: str,
        results: Dict[str, bool],
        details: Optional[Dict[str, str]] = None
    ) -> Dict:
        """
        Send execution results message.

        Args:
            channel: Slack channel ID
            thread_ts: Thread timestamp to reply in
            results: Dict mapping action names to success status
            details: Optional dict with additional details (URLs, IDs, etc.)

        Returns:
            Dict with message timestamp
        """
        lines = []

        for action, success in results.items():
            if success:
                icon = "✅"
                status = "completed"
            else:
                icon = "❌"
                status = "failed"

            action_names = {
                'gmail_draft': 'Gmail Draft',
                'calendar_event': 'Calendar Event',
                'crono_note': 'Crono Note'
            }

            action_name = action_names.get(action, action)
            line = f"{icon} {action_name} {status}"

            # Add details if available
            if details and action in details:
                line += f"\n   _{details[action]}_"

            lines.append(line)

        message = "\n".join(lines) + "\n\nTutto fatto! 🎉"

        try:
            response = self.client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=message
            )

            return {'ts': response['ts']}

        except SlackApiError as e:
            print(f"Error sending results: {e.response['error']}")
            raise

    def send_cancellation_message(
        self,
        channel: str,
        thread_ts: str
    ) -> Dict:
        """
        Send cancellation message.

        Args:
            channel: Slack channel ID
            thread_ts: Thread timestamp to reply in

        Returns:
            Dict with message timestamp
        """
        try:
            response = self.client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text="Operazione annullata. Nessuna azione eseguita."
            )

            return {'ts': response['ts']}

        except SlackApiError as e:
            print(f"Error sending cancellation: {e.response['error']}")
            raise


def test_slack_client():
    """Test function to verify Slack integration."""
    from dotenv import load_dotenv
    load_dotenv()

    print("🧪 Testing Slack Client...")

    try:
        client = SlackClient()

        # Test data
        test_channel = os.getenv('SLACK_CHANNEL', '#sales')

        response = client.send_meeting_review_message(
            channel=test_channel,
            meeting_title="Test Meeting - Acme Corp",
            meeting_summary="Discussed implementation timeline and pricing for 10 users on Ultra plan.",
            proposed_email="""Subject: Follow-up from our call

Hi John,

Thanks for taking the time to discuss Crono with me today!

Based on our conversation, I wanted to confirm:
- Implementation timeline: 2-3 weeks
- Pricing: 10 users on Ultra plan (€1,190/month annual)

Let me know if you'd like to schedule a demo for your team.

Best regards,
Lorenzo""",
            sales_insights={
                'tech_stack': 'Salesforce, HubSpot, Outreach',
                'pain_points': 'Manual data entry, slow lead response time',
                'impact': 'Spending 10 hours/week on manual tasks',
                'next_steps': 'Demo scheduled for next Tuesday',
                'roadblocks': 'Need approval from VP of Sales'
            },
            meeting_url="https://app.fathom.video/meetings/test123",
            external_emails=["john@acmecorp.com"]
        )

        print(f"✅ Message sent successfully!")
        print(f"   Timestamp: {response['ts']}")
        print(f"   Channel: {response['channel']}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_slack_client()
