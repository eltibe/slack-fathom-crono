#!/usr/bin/env python3
"""
Command-line version of meeting follow-up tool
Works reliably without menu bar dependencies
"""

import os
import sys
from dotenv import load_dotenv
from datetime import datetime
from dateutil import parser as date_parser

from modules.fathom_client import FathomClient

# Load environment variables
load_dotenv()


def main():
    print("🚀 Crono Meeting Follow-up Tool")
    print("=" * 50)
    print()

    # Fetch today's meetings
    print("📥 Fetching today's meetings from Fathom...")
    try:
        fathom = FathomClient()
        meetings = fathom.get_recent_meetings(limit=50)

        # Filter today's meetings
        today = datetime.now().date()
        today_meetings = []

        for meeting in meetings:
            meeting_time_str = meeting.get('recording_start_time', '')
            if meeting_time_str:
                try:
                    meeting_date = date_parser.parse(meeting_time_str).date()
                    if meeting_date == today:
                        today_meetings.append(meeting)
                except:
                    pass

        if not today_meetings:
            print("❌ No meetings found for today")
            sys.exit(0)

        print(f"✓ Found {len(today_meetings)} meeting(s) today\n")

        # Display meetings
        print("Today's Meetings:")
        print("-" * 50)
        for i, meeting in enumerate(today_meetings, 1):
            title = meeting.get('meeting_title', 'Untitled Meeting')
            time = meeting.get('recording_start_time', '')
            if time:
                try:
                    dt = date_parser.parse(time)
                    time_str = dt.strftime('%H:%M')
                    print(f"{i}. [{time_str}] {title}")
                except:
                    print(f"{i}. {title}")
            else:
                print(f"{i}. {title}")

        print()
        print("Actions:")
        print("  e = Email draft (Gmail)")
        print("  c = Calendar event")
        print("  n = Crono note extraction")
        print()
        print("Examples:")
        print("  1:ec   → Meeting 1: Email + Calendar")
        print("  2:e    → Meeting 2: Email only")
        print("  3:ecn  → Meeting 3: Email + Calendar + Note")
        print()

        # Get user input
        while True:
            user_input = input("Enter your choice (e.g., 1:ec) or 'q' to quit: ").strip().lower()

            if user_input == 'q':
                print("Goodbye!")
                sys.exit(0)

            if ':' not in user_input:
                print("❌ Invalid format. Use: number:actions (e.g., 1:ec)")
                continue

            try:
                meeting_num, actions = user_input.split(':', 1)
                meeting_num = int(meeting_num.strip())
                actions = actions.strip()

                if meeting_num < 1 or meeting_num > len(today_meetings):
                    print(f"❌ Invalid meeting number. Choose 1-{len(today_meetings)}")
                    continue

                # Parse actions
                create_email = 'e' in actions
                create_calendar = 'c' in actions
                create_note = 'n' in actions

                if not any([create_email, create_calendar, create_note]):
                    print("❌ Specify at least one action: e, c, or n")
                    continue

                # Get selected meeting
                selected_meeting = today_meetings[meeting_num - 1]
                recording_id = selected_meeting.get('recording_id')

                # Show confirmation
                meeting_title = selected_meeting.get('meeting_title', 'Meeting')
                print()
                print(f"Meeting: {meeting_title}")
                print("Will create:")
                if create_email:
                    print("  📧 Email draft")
                if create_calendar:
                    print("  📅 Calendar event")
                if create_note:
                    print("  📝 Crono note extraction")
                print()

                confirm = input("Proceed? (y/n): ").strip().lower()
                if confirm != 'y':
                    print("Cancelled.")
                    continue

                # Create temp config file
                import tempfile
                import json

                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                    temp_file = f.name
                    json.dump({
                        'recording_id': recording_id,
                        'create_calendar_event': create_calendar,
                        'create_crono_note': create_note
                    }, f)

                # Run the main script
                print()
                print("🔄 Processing...")
                print()

                import subprocess
                result = subprocess.run(
                    ["python3", "meeting_followup.py", "--model", "claude", "--meeting-file", temp_file],
                    cwd=os.path.dirname(os.path.abspath(__file__))
                )

                # Clean up temp file
                try:
                    os.unlink(temp_file)
                except:
                    pass

                if result.returncode == 0:
                    print()
                    print("✅ Success! Check:")
                    if create_email:
                        print("  📧 Gmail drafts: https://mail.google.com/mail/#drafts")
                    if create_calendar:
                        print("  📅 Google Calendar: https://calendar.google.com/")
                    if create_note:
                        print("  📝 Crono note data shown above (copy to Crono CRM)")
                    print()
                else:
                    print()
                    print("❌ Failed. Check errors above.")
                    print()

                # Ask if user wants to process another
                another = input("Process another meeting? (y/n): ").strip().lower()
                if another != 'y':
                    print("Goodbye!")
                    break

            except ValueError:
                print("❌ Invalid format. Use: number:actions (e.g., 1:ec)")
            except Exception as e:
                print(f"❌ Error: {e}")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
