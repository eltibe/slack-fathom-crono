"""
Date Extractor
Uses AI to extract follow-up meeting dates from transcripts
"""

import os
import anthropic
from typing import Optional


class DateExtractor:
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Claude client for date extraction"""
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("Anthropic API key is required")

        self.client = anthropic.Anthropic(api_key=self.api_key)

    def extract_followup_date(self, transcript: str, meeting_date: str) -> tuple[Optional[str], bool]:
        """
        Extract follow-up meeting date/time from transcript and check if follow-up was discussed

        Args:
            transcript: The meeting transcript
            meeting_date: The original meeting date for context

        Returns:
            Tuple of (extracted date string if found, whether follow-up was discussed)
        """
        prompt = f"""Analyze this meeting transcript to determine if a follow-up meeting was discussed.

Original meeting date: {meeting_date}

Transcript:
{transcript}

Task: Determine if a follow-up meeting was mentioned or agreed upon.

Look for:
- Explicit mentions: "Let's schedule a follow-up", "We'll meet again", "Next call"
- Date mentions: "next Tuesday", "in two weeks", "Monday at 10"
- Implicit agreement: "I'll get back to you with a proposal", "Let's reconnect after you discuss internally"

Do NOT consider follow-up mentioned if:
- Only "stay in touch" or "reach out if you have questions"
- No clear intention to meet again
- Just "we'll see" or "maybe later"

Response format - respond with ONE of these:
1. If follow-up mentioned WITH specific date: "DATE: [the date]" (e.g., "DATE: next Tuesday 2:00 PM")
2. If follow-up mentioned WITHOUT specific date: "FOLLOWUP_NO_DATE"
3. If NO follow-up discussed: "NO_FOLLOWUP"

Examples:
- "Let's meet next week" → "FOLLOWUP_NO_DATE"
- "How about Tuesday at 2pm?" → "DATE: Tuesday 2:00 PM"
- "Thanks, bye" → "NO_FOLLOWUP"
- "I'll send you info and we can schedule a call" → "FOLLOWUP_NO_DATE"

Respond with only one of the three options above."""

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=150,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            response_text = message.content[0].text.strip()

            # Parse response
            if response_text.upper() == "NO_FOLLOWUP":
                return None, False
            elif response_text.upper() == "FOLLOWUP_NO_DATE":
                return None, True
            elif response_text.startswith("DATE:"):
                date_str = response_text.replace("DATE:", "").strip()
                return date_str, True
            else:
                # Fallback: assume no follow-up
                return None, False

        except Exception as e:
            print(f"Error extracting date: {e}")
            return None, False


if __name__ == "__main__":
    # Test the date extractor
    from dotenv import load_dotenv
    load_dotenv()

    test_transcript = """
    [00:15:30] Lorenzo: Thanks for the demo today!
    [00:15:35] Alex: This looks great. Can we schedule a follow-up next Tuesday at 2 PM to discuss implementation?
    [00:15:40] Lorenzo: Absolutely! Tuesday at 2 PM works perfectly.
    [00:15:45] Alex: Perfect, talk to you then!
    """

    try:
        extractor = DateExtractor()
        date = extractor.extract_followup_date(test_transcript, "2025-11-18")
        print(f"Extracted date: {date}")
    except Exception as e:
        print(f"Error: {e}")
