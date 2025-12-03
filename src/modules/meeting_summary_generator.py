"""
Meeting Summary Generator
Uses AI to generate concise meeting summaries for calendar events
"""

import os
import logging
from typing import Optional

# Import AI generator with fallback support
from src.modules.ai_generator import AIGenerator

logger = logging.getLogger(__name__)


class MeetingSummaryGenerator:
    def __init__(self, api_key: Optional[str] = None):
        """Initialize AI generator with Claude/Gemini fallback"""
        self.ai_generator = AIGenerator()
        logger.info("📝 Meeting summary generator initialized with AI fallback")

    def generate_calendar_summary(self, transcript: str, meeting_title: str, meeting_language: str = 'en') -> str:
        """
        Generate a concise summary for the calendar event description

        Args:
            transcript: The meeting transcript
            meeting_title: The original meeting title
            meeting_language: Language code for the summary

        Returns:
            Concise HTML summary with scope and key points
        """
        prompt = f"""You are creating a VERY brief summary for a calendar event follow-up meeting.

Original meeting: {meeting_title}
Language: Write in {meeting_language}

Meeting transcript:
{transcript}

Create a CONCISE summary (2-3 bullet points MAXIMUM) in HTML format that includes:
1. The main purpose/scope of the follow-up meeting
2. 1-2 most critical topics to discuss

FORMATTING:
- Use HTML: <b> for important items, <br> for line breaks
- Add 1-2 relevant emojis (📋, 💰, 🚀, ✅, etc.)
- Use <b>bold</b> for key topics, numbers, or outcomes
- Keep it SHORT and actionable

Write in {meeting_language}.

Example format (ITALIAN):
<b>Obiettivo:</b> Follow-up per discutere pricing e partnership 💼<br>
<b>Key topics:</b> Piano Pro (2 utenti, €158/mese), integrazione HubSpot<br>
<b>Azione:</b> Valutare proposta e programmare onboarding ✅

Example format (SPANISH):
<b>Objetivo:</b> Seguimiento para revisar propuesta de partnership 🤝<br>
<b>Temas clave:</b> Comisión 20% recurrente, primeros casos de uso<br>
<b>Siguiente paso:</b> Firma de contrato y onboarding inicial 🚀

Keep it VERY concise - maximum 2-3 lines total.
"""

        try:
            logger.info("🤖 Generating meeting summary with AI...")
            result = self.ai_generator.generate_text(prompt, max_tokens=300)
            logger.info("✅ Meeting summary generated successfully")
            return result.strip()

        except Exception as e:
            logger.error(f"❌ Error generating summary: {e}")
            return f"• Follow-up meeting to discuss next steps from: {meeting_title}"


if __name__ == "__main__":
    # Test the summary generator
    from dotenv import load_dotenv
    load_dotenv()

    test_transcript = """
    [00:15:30] Lorenzo: Thanks for the demo today!
    [00:15:35] Alex: This looks great. We need to discuss with Marco and Laura internally.
    [00:15:40] Lorenzo: Absolutely! For 2 users, the Pro plan would be €158/month.
    [00:15:45] Alex: Perfect. Let's reconnect next week after our internal discussion.
    """

    try:
        generator = MeetingSummaryGenerator()
        summary = generator.generate_calendar_summary(test_transcript, "Crono Demo with Alex")
        print("Generated summary:")
        print(summary)
    except Exception as e:
        print(f"Error: {e}")
