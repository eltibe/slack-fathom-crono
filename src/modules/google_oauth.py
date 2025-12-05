"""
Google OAuth Service
Manages Google OAuth2 authentication flow for Gmail and Google Calendar
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Tuple
from urllib.parse import urlencode

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


class GoogleOAuthService:
    """Service for managing Google OAuth2 authentication"""

    # Google OAuth scopes for Gmail and Calendar
    SCOPES = [
        'https://www.googleapis.com/auth/gmail.send',
        'https://www.googleapis.com/auth/gmail.compose',
        'https://www.googleapis.com/auth/calendar.events',
        'https://www.googleapis.com/auth/userinfo.email',
        'https://www.googleapis.com/auth/userinfo.profile',
    ]

    def __init__(self):
        """Initialize Google OAuth service"""
        self.client_id = os.getenv('GOOGLE_CLIENT_ID')
        self.client_secret = os.getenv('GOOGLE_CLIENT_SECRET')

        if not self.client_id or not self.client_secret:
            raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in environment")

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """
        Generate Google OAuth authorization URL

        Args:
            redirect_uri: Callback URL after OAuth
            state: State parameter for CSRF protection (include slack_user_id and tenant_id)

        Returns:
            Authorization URL to redirect user to
        """
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=self.SCOPES,
            redirect_uri=redirect_uri
        )

        # Add additional parameters for better UX
        authorization_url, _ = flow.authorization_url(
            access_type='offline',  # Get refresh token
            prompt='consent',  # Force consent to ensure we get refresh_token
            state=state
        )

        return authorization_url

    def exchange_code_for_tokens(self, code: str, redirect_uri: str) -> Dict[str, any]:
        """
        Exchange authorization code for access and refresh tokens

        Args:
            code: Authorization code from Google
            redirect_uri: Must match the redirect_uri used in authorization URL

        Returns:
            Dictionary with:
                - access_token: str
                - refresh_token: str
                - token_expiry: datetime
                - email: str
        """
        try:
            import requests

            # Exchange code for tokens using Google's token endpoint directly
            # This bypasses Flow's scope validation which causes "Scope has changed" errors
            token_url = "https://oauth2.googleapis.com/token"
            token_data = {
                'code': code,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'redirect_uri': redirect_uri,
                'grant_type': 'authorization_code'
            }

            response = requests.post(token_url, data=token_data)
            response.raise_for_status()
            token_response = response.json()

            access_token = token_response['access_token']
            refresh_token = token_response.get('refresh_token')
            expires_in = token_response.get('expires_in', 3600)

            # Calculate token expiry (timezone-aware)
            token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            # Create credentials object to get user email
            credentials = Credentials(token=access_token)
            email = self._get_user_email(credentials)

            sys.stderr.write(f"[GoogleOAuthService] Successfully exchanged code for tokens\n")
            sys.stderr.write(f"[GoogleOAuthService] User email: {email}\n")
            sys.stderr.write(f"[GoogleOAuthService] Token expiry: {token_expiry}\n")

            return {
                'access_token': access_token,
                'refresh_token': refresh_token,
                'token_expiry': token_expiry,
                'email': email
            }

        except Exception as e:
            sys.stderr.write(f"[GoogleOAuthService] ERROR exchanging code: {e}\n")
            raise

    def refresh_access_token(
        self,
        refresh_token: str
    ) -> Tuple[str, datetime]:
        """
        Refresh an expired access token using refresh token

        Args:
            refresh_token: The refresh token

        Returns:
            Tuple of (new_access_token, new_expiry_datetime)
        """
        try:
            credentials = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=self.SCOPES
            )

            # Refresh the token
            credentials.refresh(Request())

            # Typically 1 hour (timezone-aware)
            token_expiry = datetime.now(timezone.utc) + timedelta(seconds=3600)

            sys.stderr.write(f"[GoogleOAuthService] Successfully refreshed access token\n")
            sys.stderr.write(f"[GoogleOAuthService] New token expiry: {token_expiry}\n")

            return credentials.token, token_expiry

        except Exception as e:
            sys.stderr.write(f"[GoogleOAuthService] ERROR refreshing token: {e}\n")
            raise

    def get_valid_credentials(
        self,
        access_token: str,
        refresh_token: str,
        token_expiry: Optional[datetime]
    ) -> Tuple[str, datetime]:
        """
        Get valid access token, refreshing if necessary

        Args:
            access_token: Current access token
            refresh_token: Refresh token
            token_expiry: When current access token expires

        Returns:
            Tuple of (valid_access_token, expiry_datetime)
        """
        # Check if token is expired or about to expire (5 min buffer)
        now = datetime.now(timezone.utc)
        buffer = timedelta(minutes=5)

        if token_expiry is None or token_expiry <= (now + buffer):
            sys.stderr.write(f"[GoogleOAuthService] Access token expired or expiring soon, refreshing...\n")
            return self.refresh_access_token(refresh_token)

        return access_token, token_expiry

    def _get_user_email(self, credentials: Credentials) -> str:
        """Get user's email from Google OAuth credentials"""
        try:
            service = build('oauth2', 'v2', credentials=credentials)
            user_info = service.userinfo().get().execute()
            return user_info.get('email', '')
        except Exception as e:
            sys.stderr.write(f"[GoogleOAuthService] WARNING: Could not fetch user email: {e}\n")
            return ''

    def build_gmail_service(self, access_token: str):
        """
        Build Gmail API service with access token

        Args:
            access_token: Valid Google OAuth access token

        Returns:
            Gmail API service object
        """
        credentials = Credentials(token=access_token)
        return build('gmail', 'v1', credentials=credentials)

    def build_calendar_service(self, access_token: str):
        """
        Build Google Calendar API service with access token

        Args:
            access_token: Valid Google OAuth access token

        Returns:
            Calendar API service object
        """
        credentials = Credentials(token=access_token)
        return build('calendar', 'v3', credentials=credentials)
