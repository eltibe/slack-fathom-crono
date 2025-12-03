#!/usr/bin/env python3
"""
Code Review Script using Gemini
Reviews the codebase for inconsistencies, bugs, and improvements
"""

import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

def read_file(filepath):
    """Read file contents"""
    try:
        with open(filepath, 'r') as f:
            return f.read()
    except Exception as e:
        return f"Error reading {filepath}: {e}"

def review_codebase():
    """Send codebase to Gemini for review"""
    
    print("🔍 Starting code review with Gemini...")
    print("=" * 60)
    
    # Key files to review
    files_to_review = [
        'menu_bar_app.py',
        'meeting_followup.py',
        'cli_followup.py',
        'modules/fathom_client.py',
        'modules/claude_email_generator.py',
        'modules/gemini_email_generator.py',
        'modules/gmail_draft_creator.py',
        'modules/calendar_event_creator.py',
        'modules/crono_client.py',
        'modules/sales_summary_generator.py'
    ]
    
    # Collect all code
    codebase = ""
    for filepath in files_to_review:
        if os.path.exists(filepath):
            codebase += f"\n\n# FILE: {filepath}\n"
            codebase += "=" * 60 + "\n"
            codebase += read_file(filepath)
        else:
            print(f"⚠️  File not found: {filepath}")
    
    # Create review prompt
    prompt = f"""You are an expert code reviewer. Please review this Python codebase for:

1. **INCONSISTENCIES**: Variables, functions, or logic that don't match across files
2. **BUGS**: Potential errors, edge cases not handled, race conditions
3. **CODE QUALITY**: Duplicate code, unused imports, inefficient patterns
4. **SECURITY**: API key handling, input validation, injection risks
5. **NAMING**: Inconsistent naming conventions (snake_case vs camelCase)
6. **ERROR HANDLING**: Missing try/catch blocks, unhandled exceptions
7. **LOGIC ERRORS**: Functions that might not work as intended
8. **INTEGRATION ISSUES**: Mismatched field names between modules

Be specific and cite line numbers or function names when pointing out issues.

CODEBASE TO REVIEW:
{codebase}

Please provide:
1. Critical issues (bugs, security)
2. Inconsistencies found
3. Code quality improvements
4. Overall assessment
"""

    # Send to Gemini
    print("\n📤 Sending code to Gemini for analysis...")
    print("⏳ This may take a minute...\n")
    
    try:
        model = genai.GenerativeModel('gemini-pro-latest')
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,  # Lower temperature for more focused analysis
                max_output_tokens=4000
            )
        )
        
        print("=" * 60)
        print("📋 GEMINI CODE REVIEW REPORT")
        print("=" * 60)
        print()
        print(response.text)
        print()
        print("=" * 60)
        print("✅ Review complete!")
        
    except Exception as e:
        print(f"❌ Error during review: {e}")

if __name__ == "__main__":
    review_codebase()
