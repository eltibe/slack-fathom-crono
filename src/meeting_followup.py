#!/usr/bin/env python3
"""
Meeting Follow-up Email Generator

This script:
1. Fetches the latest meeting transcript from Fathom
2. Generates follow-up emails using both Claude and Gemini
3. Creates a Gmail draft with your chosen version
4. Automatically creates a follow-up calendar event with participants

Usage:
    python meeting_followup.py [--model claude|gemini|both] [--to email@example.com]
"""

import argparse
import sys
import json
import os
from dotenv import load_dotenv
from typing import Optional, List
from datetime import datetime
from dateutil import parser as date_parser
import pytz

from modules.fathom_client import FathomClient
from modules.claude_email_generator import ClaudeEmailGenerator
from modules.gemini_email_generator import GeminiEmailGenerator
from modules.gmail_draft_creator import GmailDraftCreator
from modules.date_extractor import DateExtractor
from modules.calendar_event_creator import CalendarEventCreator
from modules.meeting_summary_generator import MeetingSummaryGenerator
from modules.sales_summary_generator import SalesSummaryGenerator
from modules.crono_client import CronoClient
from modules.slack_client import SlackClient


def compare_emails(claude_email: str, gemini_email: str):
    """Display both emails side by side for comparison"""
    print("\n" + "="*80)
    print("CLAUDE'S VERSION:")
    print("="*80)
    print(claude_email)
    print("\n" + "="*80)
    print("GEMINI'S VERSION:")
    print("="*80)
    print(gemini_email)
    print("="*80 + "\n")


def choose_email(claude_email: str, gemini_email: str) -> str:
    """Let user choose which email to use"""
    while True:
        choice = input("Which version would you like to use? (claude/gemini/quit): ").lower().strip()

        if choice in ['c', 'claude']:
            return claude_email
        elif choice in ['g', 'gemini']:
            return gemini_email
        elif choice in ['q', 'quit', 'exit']:
            print("Exiting without creating draft.")
            sys.exit(0)
        else:
            print("Invalid choice. Please enter 'claude', 'gemini', or 'quit'.")


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Generate follow-up emails from meeting transcripts')
    parser.add_argument(
        '--model',
        choices=['claude', 'gemini', 'both'],
        default='both',
        help='Which AI model to use for email generation (default: both)'
    )
    parser.add_argument(
        '--to',
        nargs='+',
        help='Email recipients (optional, can be added later in Gmail)'
    )
    parser.add_argument(
        '--tone',
        default='professional',
        choices=['professional', 'friendly', 'formal'],
        help='Email tone (default: professional)'
    )
    parser.add_argument(
        '--latest',
        action='store_true',
        help='Use the latest meeting (default behavior)'
    )
    parser.add_argument(
        '--context',
        type=str,
        help='Additional context for email generation (e.g., "This was a follow-up call about the Pro plan")'
    )
    parser.add_argument(
        '--meeting-file',
        type=str,
        help='JSON file with meeting_id and create_crono_note flag (used by menu bar app)'
    )
    parser.add_argument(
        '--slack',
        action='store_true',
        help='Send interactive message to Slack instead of executing directly'
    )
    parser.add_argument(
        '--slack-channel',
        type=str,
        help='Slack channel to send message to (e.g., "#sales" or "@username")'
    )

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Check if called from menu bar app with specific meeting
    specific_recording_id = None
    create_calendar_event = True  # Default to True for backward compatibility
    create_crono_note = False

    if args.meeting_file:
        try:
            with open(args.meeting_file, 'r') as f:
                meeting_config = json.load(f)
                specific_recording_id = meeting_config.get('recording_id')
                create_calendar_event = meeting_config.get('create_calendar_event', True)
                create_crono_note = meeting_config.get('create_crono_note', False)
        except Exception as e:
            print(f"❌ Error reading meeting file: {e}")
            sys.exit(1)

    print("🚀 Meeting Follow-up Email Generator")
    print("=" * 50)

    # Step 1: Fetch meeting transcript from Fathom
    print("\n📥 Fetching meeting transcript from Fathom...")
    try:
        fathom = FathomClient()

        if specific_recording_id:
            # Fetch specific meeting with full metadata
            print(f"   Using specific recording: {specific_recording_id}")
            meeting_data = fathom.get_specific_meeting_with_transcript(specific_recording_id)
        else:
            # Fetch latest meeting
            meeting_data = fathom.get_latest_meeting_transcript()

        if not meeting_data:
            print("❌ No meeting found. Exiting.")
            sys.exit(1)

        meeting_title = meeting_data.get('meeting_title') or meeting_data.get('title', 'Untitled Meeting')
        meeting_language = meeting_data.get('transcript_language') or meeting_data.get('language', 'en')
        print(f"✓ Found meeting: {meeting_title}")
        print(f"✓ Meeting language: {meeting_language}")

        # Extract external participant emails (exclude @crono.one)
        external_emails = []
        if not args.to:
            calendar_invitees = meeting_data.get('calendar_invitees', [])
            external_emails = [
                invitee['email']
                for invitee in calendar_invitees
                if invitee.get('is_external', False)
            ]
            if external_emails:
                print(f"✓ Found {len(external_emails)} external participant(s): {', '.join(external_emails)}")
            else:
                print("⚠️  No external participants found")

        transcript = fathom.format_transcript_for_ai(meeting_data)

    except Exception as e:
        print(f"❌ Error fetching meeting: {e}")
        sys.exit(1)

    # Step 2: Generate emails with AI models
    print("\n🤖 Generating follow-up emails...")

    claude_email = None
    gemini_email = None

    if args.model in ['claude', 'both']:
        try:
            print("  → Generating with Claude...")
            claude_gen = ClaudeEmailGenerator()
            claude_email = claude_gen.generate_followup_email(
                transcript=transcript,
                context=args.context,
                tone=args.tone,
                meeting_language=meeting_language
            )
            print("  ✓ Claude email generated")
        except Exception as e:
            print(f"  ❌ Claude error: {e}")
            if args.model == 'claude':
                sys.exit(1)

    if args.model in ['gemini', 'both']:
        try:
            print("  → Generating with Gemini...")
            gemini_gen = GeminiEmailGenerator()
            gemini_email = gemini_gen.generate_followup_email(
                transcript=transcript,
                context=args.context,
                tone=args.tone,
                meeting_language=meeting_language
            )
            print("  ✓ Gemini email generated")
        except Exception as e:
            print(f"  ❌ Gemini error: {e}")
            if args.model == 'gemini':
                sys.exit(1)

    # Step 3: Choose which email to use
    if args.model == 'both' and claude_email and gemini_email:
        compare_emails(claude_email, gemini_email)
        final_email = choose_email(claude_email, gemini_email)
    elif claude_email:
        final_email = claude_email
        print("\n" + "="*80)
        print(final_email)
        print("="*80 + "\n")
    elif gemini_email:
        final_email = gemini_email
        print("\n" + "="*80)
        print(final_email)
        print("="*80 + "\n")
    else:
        print("❌ No email was generated successfully. Exiting.")
        sys.exit(1)

    # SLACK MODE: Send to Slack and let user choose actions
    if args.slack:
        print("\n💬 Sending to Slack for review...")
        try:
            # Extract sales insights
            print("  → Extracting sales insights...")
            sales_generator = SalesSummaryGenerator()
            sales_data = sales_generator.extract_sales_data(
                transcript=transcript,
                meeting_title=meeting_title,
                meeting_language=meeting_language
            )

            # Generate meeting summary
            print("  → Generating meeting summary...")
            summary_generator = MeetingSummaryGenerator()
            meeting_summary = summary_generator.generate_calendar_summary(
                transcript,
                meeting_title,
                meeting_language
            )

            # Get Slack channel
            slack_channel = args.slack_channel or os.getenv('SLACK_CHANNEL', '#sales')

            # Send to Slack
            slack = SlackClient()
            recording_id = meeting_data.get('recording_id')
            meeting_url = f"https://app.fathom.video/meetings/{recording_id}" if recording_id else None

            response = slack.send_meeting_review_message(
                channel=slack_channel,
                meeting_title=meeting_title,
                meeting_summary=meeting_summary,
                proposed_email=final_email,
                sales_insights=sales_data,
                meeting_url=meeting_url,
                external_emails=external_emails
            )

            print(f"\n✅ Message sent to Slack!")
            print(f"   Channel: {slack_channel}")
            print(f"   Timestamp: {response['ts']}")
            print(f"\n   Now go to Slack to review and choose actions.")
            print(f"   Make sure the webhook handler is running:")
            print(f"   python slack_webhook_handler.py")

            # Exit - user will interact via Slack
            sys.exit(0)

        except Exception as e:
            print(f"\n❌ Error sending to Slack: {e}")
            print("   Falling back to normal mode...\n")
            # Continue with normal flow if Slack fails

    # Step 4: Create Gmail draft
    print("\n📧 Creating Gmail draft...")
    try:
        # Use external participant emails if --to was not specified
        recipients = args.to if args.to else external_emails

        gmail = GmailDraftCreator()
        draft_id = gmail.create_draft_from_generated_email(
            email_text=final_email,
            to=recipients
        )

        if draft_id:
            print(f"\n✅ Success! Draft created in Gmail.")
            print(f"   Draft ID: {draft_id}")
            print(f"\n   Open Gmail to review and send your draft:")
            print(f"   https://mail.google.com/mail/#drafts")
        else:
            print("\n❌ Failed to create draft.")
            sys.exit(1)

    except FileNotFoundError as e:
        print(f"\n❌ {e}")
        print("\nPlease set up Gmail API credentials first.")
        print("See README.md for instructions.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error creating draft: {e}")
        sys.exit(1)

    # Step 5: Create follow-up calendar event (only if user wants it and follow-up was discussed)
    if create_calendar_event:
        print("\n📅 Checking if follow-up meeting was discussed...")
    else:
        print("\n📅 Skipping calendar event creation (user chose not to create)")

    if create_calendar_event:
        try:
            # Extract follow-up date from transcript using AI
            date_extractor = DateExtractor()
            original_meeting_time = meeting_data.get('recording_start_time')

            extracted_date, followup_discussed = date_extractor.extract_followup_date(
                transcript=transcript,
                meeting_date=original_meeting_time
            )

            if not followup_discussed:
                print("ℹ️  No follow-up meeting was discussed - skipping calendar event")
                print("   (Email draft was still created successfully)")
            else:
                # Parse original meeting datetime
                original_dt = date_parser.parse(original_meeting_time)
                if original_dt.tzinfo is None:
                    original_dt = pytz.utc.localize(original_dt)

                # Create calendar event
                calendar = CalendarEventCreator()
                followup_datetime = calendar.parse_followup_date(extracted_date, original_dt)

                # Prepare meeting title
                original_title = meeting_data.get('meeting_title') or meeting_data.get('title', 'Meeting')
                followup_title = f"Follow-up: {original_title}"

                # Generate AI summary for calendar event
                print("  → Generating meeting summary...")
                summary_generator = MeetingSummaryGenerator()
                meeting_summary = summary_generator.generate_calendar_summary(transcript, original_title, meeting_language)

                # Create event description with summary
                event_description = f"""Follow-up from meeting on {original_meeting_time}

{meeting_summary}

---
🤖 Generated by Crono Meeting Follow-up Tool"""

                # Create the event
                event_id = calendar.create_followup_meeting(
                    title=followup_title,
                    start_datetime=followup_datetime,
                    duration_minutes=30,
                    attendees=external_emails,
                    description=event_description
                )

                if event_id:
                    print(f"✅ Follow-up meeting created!")
                    print(f"   Date: {followup_datetime.strftime('%Y-%m-%d %H:%M %Z')}")
                    print(f"   Attendees: {', '.join(external_emails)}")
                    if extracted_date:
                        print(f"   📌 Date extracted from transcript: '{extracted_date}'")
                    else:
                        print(f"   📌 No date mentioned, scheduled for same time next week")
                    print(f"\n   View in Google Calendar:")
                    print(f"   https://calendar.google.com/")
                else:
                    print("⚠️  Failed to create calendar event (but email draft was created)")

        except Exception as e:
            print(f"⚠️  Could not create calendar event: {e}")
            print("   (Email draft was still created successfully)")

    # Step 6: Create Crono CRM note (if requested)
    if create_crono_note:
        print("\n📝 Creating meeting note in Crono CRM...")
        try:
            # Extract sales data from transcript
            print("  → Extracting sales insights from transcript...")
            sales_generator = SalesSummaryGenerator()
            sales_data = sales_generator.extract_sales_data(
                transcript=transcript,
                meeting_title=meeting_title,
                meeting_language=meeting_language
            )

            print(f"  ✓ Extracted sales data")
            print(f"     Tech Stack: {sales_data['tech_stack'][:60]}...")
            print(f"     Pain Points: {sales_data['pain_points'][:60]}...")

            # Try to find the company in Crono
            print("  → Finding company in Crono CRM...")
            crono = CronoClient()

            account = None
            account_id = None
            company_name = None

            # Strategy 1: Search by email domain (checks website field in Crono)
            if external_emails:
                email_domain = external_emails[0].split('@')[-1]
                company_name_guess = email_domain.split('.')[0].capitalize()

                print(f"     Searching by email domain: {email_domain}")
                print(f"     (Will check 'website' field in Crono accounts)")

                account = crono.find_account_by_domain(
                    email_domain=email_domain,
                    company_name=company_name_guess
                )

                if account:
                    account_id = account.get('objectId') or account.get('id') or account.get('accountId')
                    company_name = account.get('name', company_name_guess)
                    website = account.get('website', '') or account.get('Website', '')

                    if website and email_domain.lower() in website.lower():
                        print(f"  ✓ Found company by website match: {company_name}")
                        print(f"     Website: {website} matches {email_domain}")
                    else:
                        print(f"  ✓ Found company by name: {company_name}")

            # Strategy 2: Fallback to meeting title
            if not account:
                company_name = meeting_title.split(' ')[0]
                print(f"     No match by domain, trying meeting title: {company_name}")

                account = crono.find_account_by_domain(
                    email_domain="",  # No domain to check
                    company_name=company_name
                )

                if account:
                    account_id = account.get('objectId') or account.get('id') or account.get('accountId')
                    company_name = account.get('name', company_name)
                    print(f"  ✓ Found company by meeting title: {company_name}")

            if account_id:
                print(f"  ✓ Found account: {account_id}")

                # Get Fathom meeting URL
                recording_id = meeting_data.get('recording_id')
                meeting_url = f"https://app.fathom.video/meetings/{recording_id}" if recording_id else None

                # Create the meeting summary note
                note_id = crono.create_meeting_summary(
                    account_id=account_id,
                    meeting_title=meeting_title,
                    summary_data=sales_data,
                    meeting_url=meeting_url
                )

                if note_id:
                    print(f"✅ Meeting note created in Crono!")
                    print(f"   Note ID: {note_id}")
                    print(f"   Account: {company_name}")
                else:
                    print("⚠️  Could not create note - check Crono API endpoint")
            else:
                print(f"⚠️  Could not find company '{company_name}' in Crono")
                print("   You may need to create the account first or search manually")

        except Exception as e:
            print(f"⚠️  Could not create Crono note: {e}")
            print("   (Email draft and calendar event were still created successfully)")


if __name__ == "__main__":
    main()
