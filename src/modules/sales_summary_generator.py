"""
Sales Summary Generator
Uses Claude AI to extract structured sales data from meeting transcripts
"""

import os
import anthropic
from typing import Optional, Dict
import json


class SalesSummaryGenerator:
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Claude client with API key"""
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("Anthropic API key is required")

        self.client = anthropic.Anthropic(api_key=self.api_key)

    def extract_sales_data(
        self,
        transcript: str,
        meeting_title: str = "Meeting",
        meeting_language: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Extract structured sales data from meeting transcript

        Args:
            transcript: The meeting transcript text
            meeting_title: Title of the meeting
            meeting_language: Language code (e.g., 'en', 'it', 'es') or None for auto-detect

        Returns:
            Dictionary with keys: tech_stack, pain_points, impact, how_crono_helps, next_steps, roadblocks
        """
        prompt = self._build_extraction_prompt(transcript, meeting_title, meeting_language)

        try:
            import sys
            sys.stderr.write(f"[SalesSummaryGenerator] Calling Claude API for meeting: {meeting_title}\n")
            sys.stderr.write(f"[SalesSummaryGenerator] Transcript length: {len(transcript)} chars\n")

            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                temperature=0.3,  # Lower temperature for more consistent extraction
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            if message.content:
                response_text = message.content[0].text
                sys.stderr.write(f"[SalesSummaryGenerator] Got response from Claude, length: {len(response_text)} chars\n")
                sys.stderr.write(f"[SalesSummaryGenerator] Response preview: {response_text[:200]}...\n")
                result = self._parse_sales_data(response_text)
                sys.stderr.write(f"[SalesSummaryGenerator] Parsed data keys: {list(result.keys())}\n")
                return result
            else:
                sys.stderr.write("[SalesSummaryGenerator] WARNING: No content in Claude response\n")
                return self._get_empty_response()

        except Exception as e:
            import traceback
            sys.stderr.write(f"[SalesSummaryGenerator] ERROR with Claude API: {e}\n")
            traceback.print_exc(file=sys.stderr)

            # Fallback to Gemini
            sys.stderr.write("[SalesSummaryGenerator] Falling back to Gemini API...\n")
            try:
                return self._extract_with_gemini(transcript, meeting_title, meeting_language)
            except Exception as gemini_error:
                sys.stderr.write(f"[SalesSummaryGenerator] ERROR with Gemini fallback: {gemini_error}\n")
                traceback.print_exc(file=sys.stderr)
                return self._get_empty_response()

    def _build_extraction_prompt(
        self,
        transcript: str,
        meeting_title: str,
        meeting_language: Optional[str] = None
    ) -> str:
        """Build the prompt for Claude to extract sales data"""

        # Language instruction
        language_instruction = ""
        if meeting_language:
            language_instruction = f"IMPORTANT: Respond in {meeting_language}. "
        else:
            language_instruction = "IMPORTANT: Detect the language from the transcript and respond in THE SAME LANGUAGE. "

        prompt = f"""You are a B2B Sales Account Executive analyzing a meeting transcript to extract key sales information.

{language_instruction}

MEETING TITLE: {meeting_title}

YOUR TASK:
Analyze the meeting transcript and extract the following information in a structured JSON format:

1. **tech_stack**: What technologies, tools, platforms, or systems does the customer currently use or mention?
   - Include programming languages, frameworks, CRM systems, marketing tools, etc.
   - If not discussed, write "Not discussed" in the meeting language

2. **pain_points**: What problems, challenges, or frustrations did the customer mention?
   - Focus on business problems, not just technical issues
   - Include specific complaints, inefficiencies, or bottlenecks mentioned
   - If not discussed, write "Not discussed" in the meeting language

3. **impact**: What is the business impact of these pain points?
   - Quantify when possible (time wasted, money lost, opportunities missed)
   - Include metrics like: hours per week, revenue impact, team size affected, etc.
   - If not discussed, write "Not discussed" in the meeting language

4. **how_crono_helps**: How can Crono help solve the identified pain points? (OPTIONAL)
   - Link each pain point to a specific Crono solution or feature
   - Only include if information about Crono's capabilities was discussed
   - Focus on concrete solutions, not generic marketing language
   - If Crono was not discussed or no solutions presented, write "Not discussed" in the meeting language

5. **next_steps**: What are the agreed-upon next steps or actions?
   - Include specific commitments: demos, trials, contract reviews, follow-up calls
   - Include dates if mentioned
   - Include who is responsible for each action
   - If not discussed, write "To be determined" in the meeting language

6. **roadblocks**: What potential obstacles or concerns were raised?
   - Budget constraints, approval processes, competing priorities, technical limitations
   - Objections or hesitations mentioned
   - If not discussed, write "None identified" in the meeting language

RESPONSE FORMAT:
Return ONLY a valid JSON object with these exact keys:
{{
    "tech_stack": "...",
    "pain_points": "...",
    "impact": "...",
    "how_crono_helps": "...",
    "next_steps": "...",
    "roadblocks": "..."
}}

GUIDELINES:
- Be concise but specific
- Focus on facts mentioned in the transcript, not assumptions
- Use bullet points or numbered lists within each field if multiple items
- Quantify whenever possible (numbers, percentages, timeframes)
- Keep the language professional and suitable for CRM notes
- Do NOT include markdown formatting (**, ##, etc.) - use plain text
- If something wasn't discussed, explicitly state it rather than leaving blank

MEETING TRANSCRIPT:
{transcript}

Now extract the sales data in JSON format:"""

        return prompt

    def _parse_sales_data(self, response_text: str) -> Dict[str, str]:
        """Parse the AI response into structured data"""
        try:
            # Try to parse as JSON first
            # Sometimes Claude wraps JSON in ```json blocks
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                json_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                json_text = response_text[json_start:json_end].strip()
            else:
                json_text = response_text.strip()

            data = json.loads(json_text)

            # Ensure all required keys exist
            required_keys = ["tech_stack", "pain_points", "impact", "how_crono_helps", "next_steps", "roadblocks"]
            for key in required_keys:
                if key not in data:
                    data[key] = "Not available"

            return data

        except json.JSONDecodeError as e:
            print(f"Warning: Could not parse JSON response: {e}")
            print(f"Response was: {response_text[:200]}...")

            # Fallback: try to extract data manually
            return self._fallback_parse(response_text)

    def _fallback_parse(self, response_text: str) -> Dict[str, str]:
        """Fallback parser if JSON parsing fails"""
        data = self._get_empty_response()

        # Try to extract data based on common patterns
        lines = response_text.split('\n')
        current_key = None
        current_value = []

        for line in lines:
            line = line.strip()

            # Check if line contains a key
            if "tech_stack" in line.lower():
                if current_key and current_value:
                    data[current_key] = ' '.join(current_value).strip()
                current_key = "tech_stack"
                current_value = []
            elif "pain_points" in line.lower() or "pain points" in line.lower():
                if current_key and current_value:
                    data[current_key] = ' '.join(current_value).strip()
                current_key = "pain_points"
                current_value = []
            elif "impact" in line.lower():
                if current_key and current_value:
                    data[current_key] = ' '.join(current_value).strip()
                current_key = "impact"
                current_value = []
            elif "next_steps" in line.lower() or "next steps" in line.lower():
                if current_key and current_value:
                    data[current_key] = ' '.join(current_value).strip()
                current_key = "next_steps"
                current_value = []
            elif "roadblocks" in line.lower():
                if current_key and current_value:
                    data[current_key] = ' '.join(current_value).strip()
                current_key = "roadblocks"
                current_value = []
            elif current_key and line:
                # Extract value after colon if present
                if ':' in line:
                    value = line.split(':', 1)[1].strip()
                    current_value.append(value)
                else:
                    current_value.append(line)

        # Add last key-value pair
        if current_key and current_value:
            data[current_key] = ' '.join(current_value).strip()

        return data

    def _get_empty_response(self) -> Dict[str, str]:
        """Return empty/default response structure"""
        return {
            "tech_stack": "Not discussed",
            "pain_points": "Not discussed",
            "impact": "Not discussed",
            "how_crono_helps": "Not discussed",
            "next_steps": "To be determined",
            "roadblocks": "None identified"
        }

    def _extract_with_gemini(
        self,
        transcript: str,
        meeting_title: str,
        meeting_language: Optional[str] = None
    ) -> Dict[str, str]:
        """Fallback extraction using Gemini API."""
        import google.generativeai as genai
        import sys

        sys.stderr.write("[SalesSummaryGenerator/Gemini] Initializing Gemini API...\n")

        gemini_api_key = os.getenv('GEMINI_API_KEY')
        if not gemini_api_key:
            sys.stderr.write("[SalesSummaryGenerator/Gemini] ERROR: GEMINI_API_KEY not found\n")
            return self._get_empty_response()

        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel('gemini-2.0-flash-exp')

        # Use same prompt as Claude
        prompt = self._build_extraction_prompt(transcript, meeting_title, meeting_language)

        sys.stderr.write(f"[SalesSummaryGenerator/Gemini] Calling Gemini for meeting: {meeting_title}\n")

        response = model.generate_content(prompt)
        response_text = response.text

        sys.stderr.write(f"[SalesSummaryGenerator/Gemini] Got response, length: {len(response_text)} chars\n")
        sys.stderr.write(f"[SalesSummaryGenerator/Gemini] Response preview: {response_text[:200]}...\n")

        result = self._parse_sales_data(response_text)
        sys.stderr.write(f"[SalesSummaryGenerator/Gemini] Parsed data keys: {list(result.keys())}\n")

        return result


if __name__ == "__main__":
    # Test the generator
    from dotenv import load_dotenv
    load_dotenv()

    sample_transcript = """
    Meeting: Discovery Call with Acme Corp
    Date/Time: 2024-01-15 14:00

    [00:00] Lorenzo: Thanks for taking the time today. Tell me about your current lead generation process.
    [00:15] Sarah (Acme): We're using HubSpot CRM and doing a lot of manual prospecting on LinkedIn.
    [00:30] Sarah: The problem is it takes our SDRs about 10 hours per week just to find and research leads.
    [01:00] Lorenzo: That's a significant time investment. What's the impact on your pipeline?
    [01:15] Sarah: We're only generating about 15 qualified meetings per month, and we need at least 30 to hit our Q1 targets.
    [01:30] Sarah: Each missed meeting is potentially €50K in lost pipeline.
    [02:00] Lorenzo: What if we could automate the lead finding and personalization?
    [02:15] Sarah: That would be amazing. Our tech stack is pretty modern - Node.js backend, React frontend, PostgreSQL database.
    [02:30] Lorenzo: Perfect. Crono integrates directly with HubSpot. How about we start a trial next Monday?
    [02:45] Sarah: I need to get approval from our CTO first. He's worried about data quality and integration complexity.
    [03:00] Lorenzo: Understood. I can send over our security docs and schedule a technical deep-dive with your CTO.
    [03:15] Sarah: That works. Let's schedule that for next Wednesday at 3pm.
    """

    try:
        generator = SalesSummaryGenerator()
        print("Extracting sales data from transcript...\n")

        sales_data = generator.extract_sales_data(
            transcript=sample_transcript,
            meeting_title="Discovery Call with Acme Corp",
            meeting_language="en"
        )

        print("EXTRACTED SALES DATA:")
        print("=" * 60)
        print(f"Tech Stack: {sales_data['tech_stack']}")
        print(f"\nPain Points: {sales_data['pain_points']}")
        print(f"\nImpact: {sales_data['impact']}")
        print(f"\nNext Steps: {sales_data['next_steps']}")
        print(f"\nRoadblocks: {sales_data['roadblocks']}")
        print("=" * 60)

    except Exception as e:
        print(f"Error: {e}")
