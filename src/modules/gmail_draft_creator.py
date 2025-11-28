"""
Gmail Draft Creator
Creates email drafts in Gmail using the Gmail API
"""

import os
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# Gmail and Calendar API scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/calendar'
]


class GmailDraftCreator:
    def __init__(self, credentials_file: str = 'credentials.json', token_file: str = 'token.json'):
        """
        Initialize Gmail client with OAuth credentials

        Args:
            credentials_file: Path to OAuth credentials JSON file from Google Cloud Console
            token_file: Path to store the OAuth token (auto-generated)
        """
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate with Gmail API using OAuth"""
        creds = None

        # Check if we have a saved token
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)

        # If credentials are invalid or don't exist, authenticate
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

            # Save credentials for future use
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())

        # Build the Gmail service
        self.service = build('gmail', 'v1', credentials=creds)

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
    # Test the Gmail draft creator
    try:
        print("Initializing Gmail draft creator...")
        gmail = GmailDraftCreator()

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

    except FileNotFoundError as e:
        print(f"\nError: {e}")
        print("\nTo use Gmail API, you need to:")
        print("1. Go to Google Cloud Console")
        print("2. Create a project and enable Gmail API")
        print("3. Download OAuth credentials as 'credentials.json'")
    except Exception as e:
        print(f"Error: {e}")
