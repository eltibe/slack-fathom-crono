"""
Google Calendar Event Creator
Creates follow-up meeting events from Fathom meetings
"""

import os
import pickle
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from dateutil import parser as date_parser
import pytz


# If modifying these scopes, delete the token.json file.
# Combined scopes for Gmail and Calendar (shared with gmail_draft_creator.py)
SCOPES = [
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/calendar'
]


class CalendarEventCreator:
    def __init__(self, credentials_file: str = 'credentials.json', token_file: str = 'token.json'):
        """Initialize Google Calendar client"""
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate with Google Calendar API"""
        creds = None

        # Token file stores the user's access and refresh tokens
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)

        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_file):
                    raise FileNotFoundError(
                        f"Credentials file '{self.credentials_file}' not found. "
                        "Please download it from Google Cloud Console."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save the credentials for the next run
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())

        self.service = build('calendar', 'v3', credentials=creds)

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
    # Test the calendar creator
    from dotenv import load_dotenv
    load_dotenv()

    try:
        calendar = CalendarEventCreator()

        # Test creating an event 1 week from now
        test_date = datetime.now(pytz.timezone('Europe/Rome')) + timedelta(weeks=1)

        event_id = calendar.create_followup_meeting(
            title="Test Follow-up: Crono Demo",
            start_datetime=test_date,
            duration_minutes=30,
            attendees=['test@example.com'],
            description="Follow-up from our Crono demo to discuss next steps"
        )

        if event_id:
            print(f"✓ Test event created successfully!")
            print(f"  Event ID: {event_id}")
        else:
            print("✗ Failed to create test event")

    except Exception as e:
        print(f"Error: {e}")
