"""
Gemini Email Generator
Uses Google's Gemini API to generate follow-up emails from meeting transcripts
"""

import os
import google.generativeai as genai
from typing import Optional


class GeminiEmailGenerator:
    def __init__(self, api_key: Optional[str] = None, knowledge_base_path: str = "crono_knowledge_base.txt"):
        """Initialize Gemini client with API key"""
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("Gemini API key is required")

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-pro')
        self.crono_knowledge = self._load_knowledge_base(knowledge_base_path)

    def _load_knowledge_base(self, path: str) -> str:
        """Load Crono company knowledge base"""
        try:
            # Try absolute path first
            if os.path.exists(path):
                with open(path, 'r') as f:
                    return f.read()
            # Try relative to script directory
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            full_path = os.path.join(script_dir, path)
            if os.path.exists(full_path):
                with open(full_path, 'r') as f:
                    return f.read()
            return ""
        except Exception as e:
            print(f"Warning: Could not load knowledge base: {e}")
            return ""

    def generate_followup_email(
        self,
        transcript: str,
        context: Optional[str] = None,
        tone: str = "professional",
        meeting_language: Optional[str] = None
    ) -> str:
        """
        Generate a follow-up email based on meeting transcript

        Args:
            transcript: The meeting transcript text
            context: Additional context about the meeting (optional)
            tone: Email tone (professional, friendly, formal)
            meeting_language: Language code (e.g., 'en', 'it', 'es') or None for auto-detect

        Returns:
            Generated email text
        """
        prompt = self._build_prompt(transcript, context, tone, meeting_language)

        try:
            response = self.model.generate_content(prompt)

            if response.text:
                return response.text
            else:
                return "Error: No response generated"

        except Exception as e:
            return f"Error generating email with Gemini: {e}"

    def _build_prompt(
        self,
        transcript: str,
        context: Optional[str] = None,
        tone: str = "professional",
        meeting_language: Optional[str] = None
    ) -> str:
        """Build the prompt for Gemini"""

        # Language detection instruction
        language_instruction = ""
        if meeting_language:
            language_instruction = f"IMPORTANT: Write the email in {meeting_language}. "
        else:
            language_instruction = "IMPORTANT: Detect the language from the transcript and write the email in THE SAME LANGUAGE. "

        prompt = f"""You are writing a follow-up email after a sales meeting for Crono.one.

{language_instruction}

"""
        # Add Crono knowledge base
        if self.crono_knowledge:
            prompt += f"""COMPANY KNOWLEDGE (use this to reference products, pricing, features, and customer stories):

{self.crono_knowledge}

"""

        prompt += f"""YOUR ROLE & OBJECTIVE:
You are Lorenzo from Crono.one writing a brief follow-up email after a meeting.

FIRST - ANALYZE THE MEETING CAREFULLY:
Before writing, identify the most important points discussed:
- What were the main topics/questions raised?
- What problems or needs did they express?
- What solutions or answers were provided?
- What decisions or next steps were agreed upon?
- What specific details matter (dates, numbers, names, features)?

CRITICAL RULES:
1. **ONLY use information explicitly mentioned in the transcript** - DO NOT invent, assume, or add details
2. **Keep it SHORT** - Maximum 200 words for the entire email body
3. **Be factual, not salesy** - No hype, no excessive enthusiasm, just facts
4. **Stick to what was discussed** - Only reference topics that came up in the conversation
5. **Focus on IMPORTANT points** - Don't include small talk or irrelevant details

FORMATTING REQUIREMENTS:
1. Format in HTML for Gmail (not Markdown)
2. Use <b>bold</b> to highlight KEY information: important decisions, dates, numbers, agreed actions
3. Use simple HTML: <b>, <br>, <p>, <ul>, <li>
4. Minimal emojis (1-2 maximum, only if appropriate)
5. NEVER use double dashes (--) as separators

WRITING GUIDELINES:
1. Tone: {tone}, conversational, helpful
2. Be brief and to the point
3. Reference ONLY what was actually said in the meeting
4. Highlight the most important takeaways with <b>bold</b>
5. Use bullet points for clarity when listing multiple items
6. No aggressive sales language
7. No invented ROI calculations unless specific numbers were discussed

EMAIL STRUCTURE (KEEP IT SHORT):
- Subject line (plain text) - Reflect the main topic discussed
- Brief thank you (1 sentence)
- Key points from our conversation (2-4 bullet points highlighting IMPORTANT items)
  * Use <b>bold</b> for critical info: dates, decisions, numbers, specific features discussed
  * Include context: what they asked + what we discussed
- Next step if one was agreed upon (with <b>specific date/action</b> if mentioned)
- Simple closing

IMPORTANT: If nothing specific was discussed or agreed, just send a brief thank you. Don't invent action items or solutions that weren't mentioned in the meeting.

"""

        if context:
            prompt += f"\nADDITIONAL CONTEXT FROM YOU: {context}\n\n"

        prompt += f"""MEETING TRANSCRIPT:
{transcript}

Now write the follow-up email in HTML format. Start with the subject line (plain text), then a blank line, then the HTML email body."""

        return prompt

    def improve_email_draft(self, draft: str, feedback: str) -> str:
        """
        Improve an existing email draft based on feedback

        Args:
            draft: The current email draft
            feedback: User feedback on what to improve

        Returns:
            Improved email text
        """
        prompt = f"""Please improve the following email draft based on this feedback:

Feedback: {feedback}

Current draft:
{draft}

Please provide an improved version of the email."""

        try:
            response = self.model.generate_content(prompt)

            if response.text:
                return response.text
            else:
                return draft  # Return original if generation fails

        except Exception as e:
            print(f"Error improving email: {e}")
            return draft


if __name__ == "__main__":
    # Test the generator
    from dotenv import load_dotenv
    load_dotenv()

    sample_transcript = """
    Meeting: Product Planning Session
    Date/Time: 2024-01-15 14:00

    [00:00] John: Thanks everyone for joining. Let's discuss the Q1 roadmap.
    [00:15] Sarah: I think we should prioritize the mobile app redesign.
    [00:30] John: Agreed. Can you lead that, Sarah?
    [00:35] Sarah: Yes, I'll put together a proposal by Friday.
    [01:00] Mike: We also need to address the API performance issues.
    [01:15] John: Good point. Mike, can you investigate and report back next week?
    [01:25] Mike: Will do.
    """

    try:
        generator = GeminiEmailGenerator()
        print("Generating follow-up email with Gemini...\n")

        email = generator.generate_followup_email(
            transcript=sample_transcript,
            tone="professional"
        )

        print(email)
    except Exception as e:
        print(f"Error: {e}")
