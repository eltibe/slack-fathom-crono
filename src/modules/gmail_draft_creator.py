"""
Gmail Draft Creator
Creates email drafts in Gmail using the Gmail API
"""

import json
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List, Callable
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# Gmail and Calendar API scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/calendar'
]


class GmailDraftCreator:
    def __init__(self, token_json: str, token_save_callback: Optional[Callable[[str], None]] = None):
        """
        Initialize Gmail client with OAuth credentials from database.

        Args:
            token_json: JSON string containing OAuth token data from database
            token_save_callback: Optional callback function to save refreshed tokens back to database.
                                 Should accept a single argument: the updated token JSON string.

        Example:
            def save_token(new_token_json):
                # Save new_token_json back to database
                user.settings.gmail_token = new_token_json
                db.commit()

            gmail = GmailDraftCreator(user.settings.gmail_token, save_token)
        """
        self.token_json = token_json
        self.token_save_callback = token_save_callback
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """
        Authenticate with Gmail API using OAuth tokens from database.

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

            # Build the Gmail service
            self.service = build('gmail', 'v1', credentials=creds)

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid token JSON format: {e}")
        except Exception as e:
            raise Exception(f"Failed to authenticate with Gmail: {e}")

    def create_draft(
        self,
        subject: str,
        body: str,
        to: Optional[List[str]] = None,
        cc: Optional[List[str]] = None,
        is_html: bool = True
    ) -> Optional[str]:
        """
        Create a draft email in Gmail

        Args:
            subject: Email subject line
            body: Email body text (can be HTML)
            to: List of recipient email addresses (optional for draft)
            cc: List of CC email addresses (optional)
            is_html: Whether the body is HTML (default: True)

        Returns:
            Draft ID if successful, None otherwise
        """
        try:
            # Create the email message with HTML support
            if is_html:
                message = MIMEMultipart('alternative')
                # Add plain text version (fallback)
                text_part = MIMEText(body.replace('<b>', '').replace('</b>', '').replace('<br>', '\n').replace('<p>', '').replace('</p>', '\n'), 'plain')
                # Add HTML version
                html_part = MIMEText(body, 'html')
                message.attach(text_part)
                message.attach(html_part)
            else:
                message = MIMEText(body)

            message['Subject'] = subject

            if to:
                message['To'] = ', '.join(to)

            if cc:
                message['Cc'] = ', '.join(cc)

            # Encode the message
            encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            # Create the draft
            draft_body = {
                'message': {
                    'raw': encoded_message
                }
            }

            draft = self.service.users().drafts().create(
                userId='me',
                body=draft_body
            ).execute()

            draft_id = draft['id']
            print(f"Draft created successfully! Draft ID: {draft_id}")
            return draft_id

        except HttpError as error:
            print(f"An error occurred: {error}")
            return None

    def parse_email_content(self, email_text: str) -> tuple[str, str]:
        """
        Parse generated email text to extract subject and body

        Args:
            email_text: The full email text (including subject line)

        Returns:
            Tuple of (subject, body)
        """
        lines = email_text.strip().split('\n')

        subject = ""
        body_lines = []
        found_subject = False

        for line in lines:
            # Look for subject line
            if line.lower().startswith('subject:'):
                subject = line.split(':', 1)[1].strip()
                found_subject = True
            elif found_subject:
                body_lines.append(line)

        body = '\n'.join(body_lines).strip()

        # If no subject found, use first line as subject
        if not subject and lines:
            subject = lines[0].strip()
            body = '\n'.join(lines[1:]).strip()

        return subject, body

    def create_draft_from_generated_email(
        self,
        email_text: str,
        to: Optional[List[str]] = None,
        cc: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Create a draft from AI-generated email text

        Args:
            email_text: The complete email text (including subject)
            to: List of recipient email addresses (optional)
            cc: List of CC email addresses (optional)

        Returns:
            Draft ID if successful, None otherwise
        """
        subject, body = self.parse_email_content(email_text)

        if not subject:
            subject = "Follow-up from our meeting"

        if not body:
            print("Warning: Email body is empty")
            body = email_text

        return self.create_draft(subject=subject, body=body, to=to, cc=cc)

    def list_recent_drafts(self, max_results: int = 5):
        """
        List recent drafts (for debugging/verification)

        Args:
            max_results: Maximum number of drafts to retrieve
        """
        try:
            results = self.service.users().drafts().list(
                userId='me',
                maxResults=max_results
            ).execute()

            drafts = results.get('drafts', [])

            if not drafts:
                print('No drafts found.')
                return

            print(f'Recent drafts ({len(drafts)}):')
            for draft in drafts:
                draft_id = draft['id']
                print(f'  - Draft ID: {draft_id}')

        except HttpError as error:
            print(f'An error occurred: {error}')


if __name__ == "__main__":
    # Test the Gmail draft creator with database-backed tokens
    import os
    from dotenv import load_dotenv

    load_dotenv()

    print("=" * 60)
    print("Gmail Draft Creator - Database Token Test")
    print("=" * 60)
    print("\nNOTE: This test requires you to:")
    print("1. Authenticate via the web OAuth flow (/oauth/google/start)")
    print("2. Provide the token JSON from your database")
    print("\nFor production usage, tokens are loaded from the database")
    print("via UserSettings.gmail_token")
    print("=" * 60)

    # ASSUMPTION: For testing, we expect the token to be provided via environment variable
    # In production, this would come from the database
    token_json = os.getenv('TEST_GMAIL_TOKEN_JSON')

    if not token_json:
        print("\n❌ No token found for testing.")
        print("Please set TEST_GMAIL_TOKEN_JSON environment variable")
        print("or authenticate via the web OAuth flow first.")
        exit(1)

    try:
        print("\nInitializing Gmail draft creator with database token...")

        # Example of how to use with a save callback
        def save_token_callback(new_token_json):
            print(f"\n✓ Token refreshed! New token would be saved to database.")
            # In production: user.settings.gmail_token = new_token_json; db.commit()

        gmail = GmailDraftCreator(token_json, token_save_callback=save_token_callback)

        sample_email = """Subject: Follow-up: Product Planning Meeting

Hi Team,

Thank you for attending today's product planning session. Here's a quick summary:

Key Points:
- Prioritizing mobile app redesign for Q1
- Addressing API performance issues

Action Items:
- Sarah: Prepare proposal for mobile redesign by Friday
- Mike: Investigate API performance and report next week

Let's reconnect next Monday to review progress.

Best regards"""

        print("\nCreating draft...")
        draft_id = gmail.create_draft_from_generated_email(sample_email)

        if draft_id:
            print("\n✓ Draft created successfully!")
            print("Check your Gmail drafts folder.")

    except ValueError as e:
        print(f"\n❌ Configuration Error: {e}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
