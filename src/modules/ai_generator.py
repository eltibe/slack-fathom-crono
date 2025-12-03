"""
AI Generator with fallback support
Tries Claude first, falls back to Gemini if Claude fails
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AIGenerator:
    """Unified AI generator with Claude/Gemini fallback"""

    def __init__(self):
        """Initialize both Claude and Gemini clients"""
        self.claude_available = False
        self.gemini_available = False

        # Try to initialize Claude
        try:
            import anthropic
            anthropic_key = os.getenv('ANTHROPIC_API_KEY')
            if anthropic_key:
                self.claude_client = anthropic.Anthropic(api_key=anthropic_key)
                self.claude_available = True
                logger.info("✅ Claude API initialized")
        except Exception as e:
            logger.warning(f"⚠️  Claude API not available: {e}")

        # Try to initialize Gemini
        try:
            import google.generativeai as genai
            gemini_key = os.getenv('GEMINI_API_KEY')
            if gemini_key:
                genai.configure(api_key=gemini_key)
                self.gemini_client = genai.GenerativeModel('gemini-pro-latest')
                self.gemini_available = True
                logger.info("✅ Gemini API initialized (using gemini-pro-latest)")
        except Exception as e:
            logger.warning(f"⚠️  Gemini API not available: {e}")

        if not self.claude_available and not self.gemini_available:
            logger.error("❌ No AI APIs available!")

    def generate_text(self, prompt: str, max_tokens: int = 2000) -> str:
        """
        Generate text using AI (tries Claude first, falls back to Gemini)

        Args:
            prompt: The prompt to generate from
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text
        """
        # Try Claude first
        if self.claude_available:
            try:
                logger.info("🤖 Generating with Claude...")
                message = self.claude_client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}]
                )
                result = message.content[0].text.strip()
                logger.info("✅ Claude generation successful")
                return result
            except Exception as e:
                logger.warning(f"⚠️  Claude failed: {e}. Trying Gemini...")

        # Fall back to Gemini
        if self.gemini_available:
            try:
                logger.info("🤖 Generating with Gemini...")
                response = self.gemini_client.generate_content(prompt)
                result = response.text.strip()
                logger.info("✅ Gemini generation successful")
                return result
            except Exception as e:
                logger.error(f"❌ Gemini also failed: {e}")
                return f"Error: Both AI services failed. Claude: unavailable, Gemini: {str(e)}"

        # No AI available
        return "Error: No AI services available. Please check API keys."
