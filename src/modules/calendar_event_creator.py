"""
Google Calendar Event Creator
Creates follow-up meeting events from Fathom meetings
"""

import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Callable
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from dateutil import parser as date_parser
import pytz


# Combined scopes for Gmail and Calendar (shared with gmail_draft_creator.py)
SCOPES = [
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/calendar'
]


class CalendarEventCreator:
    def __init__(self, token_json: str, token_save_callback: Optional[Callable[[str], None]] = None):
        """
        Initialize Google Calendar client with OAuth credentials from database.

        Args:
            token_json: JSON string containing OAuth token data from database
            token_save_callback: Optional callback function to save refreshed tokens back to database.
                                 Should accept a single argument: the updated token JSON string.

        Example:
            def save_token(new_token_json):
                # Save new_token_json back to database
                user.settings.calendar_token = new_token_json
                db.commit()

            calendar = CalendarEventCreator(user.settings.calendar_token, save_token)
        """
        self.token_json = token_json
        self.token_save_callback = token_save_callback
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """
        Authenticate with Google Calendar API using OAuth tokens from database.

        Handles token refresh automatically and calls the save callback
        if tokens are refreshed.
        """
        if not self.token_json:
            raise ValueError("No OAuth token provided. Please authenticate via /oauth/google/start")

        try:
            # Parse token JSON from database
            token_data = json.loads(self.token_json)

            # Parse expiry datetime if present
            expiry = None
            if token_data.get('expiry'):
                try:
                    expiry = datetime.fromisoformat(token_data['expiry'])
                except (ValueError, TypeError):
                    # If expiry parsing fails, let it be None and token will refresh if needed
                    pass

            # Create credentials object from token data
            creds = Credentials(
                token=token_data.get('token'),
                refresh_token=token_data.get('refresh_token'),
                token_uri=token_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
                client_id=token_data.get('client_id'),
                client_secret=token_data.get('client_secret'),
                scopes=token_data.get('scopes', SCOPES)
            )

            # Set expiry if available
            if expiry:
                creds.expiry = expiry

            # Check if token needs refresh
            if not creds.valid and creds.expired and creds.refresh_token:
                # Refresh the token
                creds.refresh(Request())

                # Update token data with new values
                token_data['token'] = creds.token
                token_data['expiry'] = creds.expiry.isoformat() if creds.expiry else None

                # Save refreshed token back to database via callback
                if self.token_save_callback:
                    updated_token_json = json.dumps(token_data)
                    self.token_save_callback(updated_token_json)
                    self.token_json = updated_token_json

            # Build the Calendar service
            self.service = build('calendar', 'v3', credentials=creds)

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid token JSON format: {e}")
        except Exception as e:
            raise Exception(f"Failed to authenticate with Google Calendar: {e}")

    def create_followup_meeting(
        self,
        title: str,
        start_datetime: datetime,
        duration_minutes: int = 30,
        attendees: List[str] = None,
        description: str = "",
        location: str = ""
    ) -> Optional[str]:
        """
        Create a follow-up meeting in Google Calendar

        Args:
            title: Meeting title
            start_datetime: Start date and time (timezone-aware)
            duration_minutes: Meeting duration in minutes
            attendees: List of attendee email addresses
            description: Meeting description
            location: Meeting location (e.g., Google Meet link)

        Returns:
            Event ID if successful, None otherwise
        """
        try:
            # Calculate end time
            end_datetime = start_datetime + timedelta(minutes=duration_minutes)

            # Prepare attendees list
            attendees_list = []
            if attendees:
                attendees_list = [{'email': email} for email in attendees]

            # Get proper timezone string
            if hasattr(start_datetime.tzinfo, 'zone'):
                tz_string = start_datetime.tzinfo.zone
            else:
                # Default to UTC if timezone is not recognized
                tz_string = 'UTC'
                # Convert to UTC if needed
                if start_datetime.tzinfo is not None:
                    start_datetime = start_datetime.astimezone(pytz.UTC)
                    end_datetime = end_datetime.astimezone(pytz.UTC)
                else:
                    start_datetime = pytz.UTC.localize(start_datetime)
                    end_datetime = pytz.UTC.localize(end_datetime)

            # Create event
            event = {
                'summary': title,
                'description': description,
                'start': {
                    'dateTime': start_datetime.isoformat(),
                    'timeZone': tz_string,
                },
                'end': {
                    'dateTime': end_datetime.isoformat(),
                    'timeZone': tz_string,
                },
                'attendees': attendees_list,
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': 24 * 60},  # 1 day before
                        {'method': 'popup', 'minutes': 30},        # 30 minutes before
                    ],
                },
                'conferenceData': {
                    'createRequest': {
                        'requestId': f"follow-up-{datetime.now().timestamp()}",
                        'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                    }
                }
            }

            if location:
                event['location'] = location

            # Create the event
            created_event = self.service.events().insert(
                calendarId='primary',
                body=event,
                conferenceDataVersion=1,
                sendUpdates='all'  # Send email invitations to attendees
            ).execute()

            return created_event.get('id')

        except Exception as e:
            print(f"Error creating calendar event: {e}")
            return None

    def parse_followup_date(
        self,
        extracted_date_str: Optional[str],
        original_meeting_datetime: datetime
    ) -> datetime:
        """
        Parse the extracted follow-up date or default to 1 week later

        Args:
            extracted_date_str: Date string extracted from transcript (can be None)
            original_meeting_datetime: Original meeting start time

        Returns:
            datetime object for the follow-up meeting
        """
        if extracted_date_str:
            try:
                # Try to parse the extracted date
                parsed_date = date_parser.parse(extracted_date_str, fuzzy=True)

                # If only date is provided (no time), use original meeting time
                if parsed_date.hour == 0 and parsed_date.minute == 0:
                    parsed_date = parsed_date.replace(
                        hour=original_meeting_datetime.hour,
                        minute=original_meeting_datetime.minute
                    )

                # Ensure timezone
                if parsed_date.tzinfo is None:
                    # Try to use the original meeting's timezone
                    if hasattr(original_meeting_datetime.tzinfo, 'localize'):
                        parsed_date = original_meeting_datetime.tzinfo.localize(parsed_date)
                    else:
                        # If localize not available, use replace
                        parsed_date = parsed_date.replace(tzinfo=original_meeting_datetime.tzinfo)

                return parsed_date
            except Exception as e:
                print(f"Could not parse date '{extracted_date_str}': {e}")
                print("Falling back to 1 week from original meeting time")

        # Default: same time next week
        return original_meeting_datetime + timedelta(weeks=1)


if __name__ == "__main__":
    # Test the calendar creator with database-backed tokens
    import os
    from dotenv import load_dotenv

    load_dotenv()

    print("=" * 60)
    print("Calendar Event Creator - Database Token Test")
    print("=" * 60)
    print("\nNOTE: This test requires you to:")
    print("1. Authenticate via the web OAuth flow (/oauth/google/start)")
    print("2. Provide the token JSON from your database")
    print("\nFor production usage, tokens are loaded from the database")
    print("via UserSettings.calendar_token")
    print("=" * 60)

    # ASSUMPTION: For testing, we expect the token to be provided via environment variable
    # In production, this would come from the database
    token_json = os.getenv('TEST_CALENDAR_TOKEN_JSON')

    if not token_json:
        print("\n❌ No token found for testing.")
        print("Please set TEST_CALENDAR_TOKEN_JSON environment variable")
        print("or authenticate via the web OAuth flow first.")
        exit(1)

    try:
        print("\nInitializing Calendar event creator with database token...")

        # Example of how to use with a save callback
        def save_token_callback(new_token_json):
            print(f"\n✓ Token refreshed! New token would be saved to database.")
            # In production: user.settings.calendar_token = new_token_json; db.commit()

        calendar = CalendarEventCreator(token_json, token_save_callback=save_token_callback)

        # Test creating an event 1 week from now
        test_date = datetime.now(pytz.timezone('Europe/Rome')) + timedelta(weeks=1)

        print("\nCreating test calendar event...")
        event_id = calendar.create_followup_meeting(
            title="Test Follow-up: Crono Demo",
            start_datetime=test_date,
            duration_minutes=30,
            attendees=['test@example.com'],
            description="Follow-up from our Crono demo to discuss next steps"
        )

        if event_id:
            print(f"\n✓ Test event created successfully!")
            print(f"  Event ID: {event_id}")
            print("Check your Google Calendar!")
        else:
            print("\n✗ Failed to create test event")

    except ValueError as e:
        print(f"\n❌ Configuration Error: {e}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
