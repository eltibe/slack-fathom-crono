"""
Fathom API Client
Retrieves meeting transcripts from Fathom
"""

import requests
import os
from typing import Optional, Dict, List


class FathomClient:
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Fathom client with API key"""
        self.api_key = api_key or os.getenv('FATHOM_API_KEY')
        if not self.api_key:
            raise ValueError("Fathom API key is required")

        self.base_url = "https://api.fathom.ai/external/v1"
        self.headers = {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json"
        }

    def get_recent_meetings(self, limit: int = 10) -> List[Dict]:
        """
        Fetch recent meetings

        Args:
            limit: Number of meetings to retrieve

        Returns:
            List of meeting objects
        """
        try:
            response = requests.get(
                f"{self.base_url}/meetings",
                headers=self.headers,
                params={"limit": limit}
            )
            response.raise_for_status()
            data = response.json()
            return data.get('items', [])
        except requests.exceptions.RequestException as e:
            print(f"Error fetching meetings: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response status: {e.response.status_code}")
                print(f"Response body: {e.response.text}")
            return []

    def get_all_recordings(self, limit: int = 100) -> List[Dict]:
        """
        Fetch all recent recordings (for filtering by date).

        Args:
            limit: Maximum number of recordings to retrieve (default: 100)

        Returns:
            List of recording objects
        """
        return self.get_recent_meetings(limit=limit)

    def get_meeting_transcript(self, recording_id: int) -> Optional[Dict]:
        """
        Fetch transcript for a specific meeting

        Args:
            recording_id: The Fathom recording ID

        Returns:
            Dict containing transcript data
        """
        try:
            response = requests.get(
                f"{self.base_url}/recordings/{recording_id}/transcript",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching transcript: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response status: {e.response.status_code}")
                print(f"Response body: {e.response.text}")
            return None

    def get_specific_meeting_with_transcript(self, recording_id: int) -> Optional[Dict]:
        """
        Get a specific meeting by recording_id with full metadata and transcript

        Args:
            recording_id: The Fathom recording ID

        Returns:
            Dict containing the meeting data and transcript
        """
        # Search in recent meetings (increased limit to ensure we find it)
        # Fathom API doesn't have a direct endpoint for /recordings/{id}
        meetings = self.get_recent_meetings(limit=200)

        # Find the meeting with matching recording_id
        target_meeting = None
        for meeting in meetings:
            # Compare as strings to handle both int and str types
            if str(meeting.get('recording_id')) == str(recording_id):
                target_meeting = meeting
                break

        if not target_meeting:
            print(f"Meeting with recording_id {recording_id} not found in recent 200 meetings")
            return None

        # Fetch the transcript for this meeting
        transcript_data = self.get_meeting_transcript(recording_id)
        if transcript_data:
            # Combine meeting metadata with transcript
            target_meeting['transcript'] = transcript_data
            return target_meeting

        return None

    def get_latest_meeting_transcript(self) -> Optional[Dict]:
        """
        Get the most recent meeting's transcript

        Returns:
            Dict containing the latest meeting data and transcript
        """
        meetings = self.get_recent_meetings(limit=1)
        if not meetings:
            print("No meetings found")
            return None

        latest_meeting = meetings[0]
        recording_id = latest_meeting.get('recording_id')

        if recording_id:
            transcript_data = self.get_meeting_transcript(recording_id)
            if transcript_data:
                # Combine meeting metadata with transcript
                latest_meeting['transcript'] = transcript_data
                return latest_meeting

        return None

    def format_transcript_for_ai(self, meeting_data: Dict) -> str:
        """
        Format the meeting data into a readable transcript for AI processing

        Args:
            meeting_data: Raw meeting data from Fathom API

        Returns:
            Formatted transcript string
        """
        if not meeting_data:
            return ""

        # Extract meeting metadata
        title = meeting_data.get('meeting_title') or meeting_data.get('title', 'Untitled Meeting')
        start_time = meeting_data.get('recording_start_time', 'Unknown time')
        participants = meeting_data.get('calendar_invitees', [])

        # The transcript data has a nested 'transcript' key
        transcript_obj = meeting_data.get('transcript', {})
        transcript_segments = transcript_obj.get('transcript', []) if isinstance(transcript_obj, dict) else []

        # Build formatted transcript
        formatted = f"Meeting: {title}\n"
        formatted += f"Date/Time: {start_time}\n"

        if participants:
            formatted += f"Participants: {', '.join([p.get('name', 'Unknown') for p in participants])}\n"

        formatted += "\n--- TRANSCRIPT ---\n\n"

        # Format transcript segments
        for segment in transcript_segments:
            # Speaker is now a dictionary with display_name
            speaker_obj = segment.get('speaker', {})
            speaker = speaker_obj.get('display_name', 'Unknown') if isinstance(speaker_obj, dict) else str(speaker_obj)
            text = segment.get('text', '')
            timestamp = segment.get('timestamp', '')

            formatted += f"[{timestamp}] {speaker}: {text}\n"

        return formatted


if __name__ == "__main__":
    # Test the client
    from dotenv import load_dotenv
    load_dotenv()

    try:
        client = FathomClient()
        print("Fetching latest meeting...")
        meeting = client.get_latest_meeting_transcript()

        if meeting:
            print(f"\nFound meeting: {meeting.get('title')}")
            formatted = client.format_transcript_for_ai(meeting)
            print(f"\nFormatted transcript preview (first 500 chars):")
            print(formatted[:500])
        else:
            print("No meeting found")
    except Exception as e:
        print(f"Error: {e}")
