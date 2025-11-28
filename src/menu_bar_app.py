#!/usr/bin/env python3
"""
Crono Follow-up Menu Bar App
A macOS menu bar application for generating follow-up emails
"""

import rumps
import subprocess
import threading
import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
from modules.fathom_client import FathomClient
from modules.sales_summary_generator import SalesSummaryGenerator
from modules.crono_client import CronoClient

# Load environment variables
load_dotenv()


class CronoFollowupApp(rumps.App):
    def __init__(self):
        super(CronoFollowupApp, self).__init__(
            "CR",  # Use text instead of emoji for better compatibility
            icon=None,
            quit_button=None  # Custom quit button
        )

        # State
        self.processing = False
        self.last_check = None
        self.today_meetings = []

        # Menu items
        self.menu = [
            rumps.MenuItem("📧 Generate Follow-up Email", callback=self.show_meeting_selector),
            rumps.separator,
            rumps.MenuItem("📊 Today's Meetings", callback=self.show_meetings),
            rumps.MenuItem("📅 Open Calendar", callback=self.open_calendar),
            rumps.MenuItem("✉️  Open Gmail Drafts", callback=self.open_gmail),
            rumps.separator,
            rumps.MenuItem("🔄 Refresh Badge", callback=self.update_badge),
            rumps.separator,
            rumps.MenuItem("❌ Quit Crono", callback=self.quit_app)
        ]

        # Update badge on start
        self.update_badge(None)

    def update_badge(self, sender):
        """Update the badge with today's meeting count"""
        try:
            fathom = FathomClient()
            meetings = fathom.get_recent_meetings(limit=50)

            # Count meetings from today
            today = datetime.now().date()
            self.today_meetings = []

            for meeting in meetings:
                meeting_time_str = meeting.get('recording_start_time', '')
                if meeting_time_str:
                    try:
                        from dateutil import parser as date_parser
                        meeting_date = date_parser.parse(meeting_time_str).date()
                        if meeting_date == today:
                            self.today_meetings.append(meeting)
                    except:
                        pass

            count = len(self.today_meetings)
            if count > 0:
                self.title = f"CR({count})"
            else:
                self.title = "CR"

            self.last_check = datetime.now()

        except Exception as e:
            print(f"Error updating badge: {e}")
            self.title = "CR"
            self.today_meetings = []

    def show_meeting_selector(self, sender):
        """Show meeting selection dialog with action choices"""
        # Refresh meetings list
        self.update_badge(None)

        if not self.today_meetings:
            rumps.alert(
                title="No Meetings Today",
                message="No meetings found for today. The follow-up tool works with today's meetings from Fathom."
            )
            return

        # Build meeting selection message with instructions
        meetings_list = []
        for i, meeting in enumerate(self.today_meetings, 1):
            title = meeting.get('meeting_title', 'Untitled Meeting')
            time = meeting.get('recording_start_time', '')
            if time:
                try:
                    from dateutil import parser as date_parser
                    dt = date_parser.parse(time)
                    time_str = dt.strftime('%H:%M')
                    meetings_list.append(f"{i}. [{time_str}] {title}")
                except:
                    meetings_list.append(f"{i}. {title}")
            else:
                meetings_list.append(f"{i}. {title}")

        meetings_text = "\n".join(meetings_list)

        instructions = """📧 = Email draft
📅 = Calendar event
📝 = Crono note

Format: number:actions
Examples:
  1:ec   → Meeting 1: Email + Calendar
  2:e    → Meeting 2: Email only
  3:ecn  → Meeting 3: All (Email+Calendar+Note)
  1:en   → Meeting 1: Email + Note

Enter your choice:"""

        # Ask for selection with actions
        response = rumps.Window(
            message=f"{meetings_text}\n\n{instructions}",
            title="Choose Meeting & Actions",
            default_text="1:ec",
            ok="Process",
            cancel="Cancel",
            dimensions=(400, 150)
        ).run()

        if not response.clicked:
            return  # User cancelled

        # Parse selection
        try:
            user_input = response.text.strip().lower()

            # Parse format: "number:actions"
            if ':' not in user_input:
                rumps.alert(
                    title="Invalid Format",
                    message="Please use format: number:actions\nExample: 1:ec"
                )
                return

            meeting_num, actions = user_input.split(':', 1)
            meeting_num = int(meeting_num.strip())
            actions = actions.strip()

            if meeting_num < 1 or meeting_num > len(self.today_meetings):
                rumps.alert(
                    title="Invalid Meeting Number",
                    message=f"Please enter a number between 1 and {len(self.today_meetings)}"
                )
                return

            # Parse actions
            create_email = 'e' in actions
            create_calendar = 'c' in actions
            create_note = 'n' in actions

            if not create_email and not create_calendar and not create_note:
                rumps.alert(
                    title="No Actions Selected",
                    message="Please specify at least one action:\ne=email, c=calendar, n=note\n\nExample: 1:ec"
                )
                return

            # Get selected meeting
            selected_meeting = self.today_meetings[meeting_num - 1]

            # Show confirmation
            actions_text = []
            if create_email:
                actions_text.append("📧 Email draft")
            if create_calendar:
                actions_text.append("📅 Calendar event")
            if create_note:
                actions_text.append("📝 Crono note")

            meeting_title = selected_meeting.get('meeting_title', 'Meeting')
            confirm_response = rumps.alert(
                title="Confirm Actions",
                message=f"Meeting: {meeting_title}\n\nWill create:\n" + "\n".join(actions_text),
                ok="Confirm",
                cancel="Cancel"
            )

            if confirm_response != 1:
                return  # User cancelled

            # Process meeting
            self.generate_followup(selected_meeting, create_calendar, create_note)

        except ValueError as e:
            rumps.alert(
                title="Invalid Input",
                message="Please use format: number:actions\nExample: 1:ec\n\ne=email, c=calendar, n=note"
            )
            return
        except Exception as e:
            rumps.alert(
                title="Error",
                message=f"Error processing selection: {str(e)}"
            )
            return

    def generate_followup(self, meeting_data, create_calendar_event=True, create_crono_note=False):
        """Generate follow-up email in background"""
        if self.processing:
            rumps.notification(
                title="Crono Follow-up",
                subtitle="Already Processing",
                message="Please wait for the current operation to complete"
            )
            return

        # Run in background thread
        thread = threading.Thread(
            target=self._run_followup_script,
            args=(meeting_data, create_calendar_event, create_crono_note)
        )
        thread.daemon = True
        thread.start()

    def _run_followup_script(self, meeting_data, create_calendar_event=True, create_crono_note=False):
        """Run the follow-up script for a specific meeting"""
        try:
            self.processing = True
            self.title = "CR..."  # Show processing state

            meeting_title = meeting_data.get('meeting_title', 'Meeting')

            # Show start notification
            rumps.notification(
                title="Crono Follow-up",
                subtitle="Processing...",
                message=f"🔄 Processing: {meeting_title}"
            )

            # Get script directory
            script_dir = os.path.dirname(os.path.abspath(__file__))
            script_path = os.path.join(script_dir, "meeting_followup.py")

            # Save meeting ID to temp file for the script to use
            import tempfile
            import json

            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                temp_file = f.name
                json.dump({
                    'recording_id': meeting_data.get('recording_id'),
                    'create_calendar_event': create_calendar_event,
                    'create_crono_note': create_crono_note
                }, f)

            # Run the script with temp file path
            result = subprocess.run(
                ["python3", script_path, "--model", "claude", "--meeting-file", temp_file],
                cwd=script_dir,
                capture_output=True,
                text=True,
                timeout=180  # 3 minutes timeout
            )

            # Clean up temp file
            try:
                os.unlink(temp_file)
            except:
                pass

            # Check result
            if result.returncode == 0:
                # Success notification
                success_msg = "Draft created in Gmail!"
                if create_calendar_event:
                    success_msg += " Calendar event added!"
                if create_crono_note:
                    success_msg += " Crono data extracted!"

                rumps.notification(
                    title="Crono Follow-up",
                    subtitle="✅ Success!",
                    message=success_msg,
                    sound=True
                )
            else:
                # Error notification
                error_msg = result.stderr[-200:] if result.stderr else "Unknown error"
                rumps.notification(
                    title="Crono Follow-up",
                    subtitle="❌ Error",
                    message=f"Failed to generate follow-up: {error_msg}"
                )

        except subprocess.TimeoutExpired:
            rumps.notification(
                title="Crono Follow-up",
                subtitle="⏱️  Timeout",
                message="Operation took too long. Please try again."
            )
        except Exception as e:
            rumps.notification(
                title="Crono Follow-up",
                subtitle="❌ Error",
                message=f"Error: {str(e)}"
            )
        finally:
            self.processing = False
            self.update_badge(None)  # Update badge after processing

    def show_meetings(self, sender):
        """Show today's meetings"""
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
                        from dateutil import parser as date_parser
                        meeting_date = date_parser.parse(meeting_time_str).date()
                        if meeting_date == today:
                            title = meeting.get('meeting_title', 'Untitled')
                            today_meetings.append(title)
                    except:
                        pass

            if today_meetings:
                meetings_text = "\n".join([f"• {m}" for m in today_meetings])
                rumps.alert(
                    title=f"📊 Today's Meetings ({len(today_meetings)})",
                    message=meetings_text
                )
            else:
                rumps.alert(
                    title="📊 Today's Meetings",
                    message="No meetings recorded today"
                )
        except Exception as e:
            rumps.alert(
                title="Error",
                message=f"Could not fetch meetings: {str(e)}"
            )

    def open_calendar(self, sender):
        """Open Google Calendar"""
        subprocess.run(["open", "https://calendar.google.com/"])

    def open_gmail(self, sender):
        """Open Gmail drafts"""
        subprocess.run(["open", "https://mail.google.com/mail/#drafts"])

    def quit_app(self, sender):
        """Quit the application"""
        rumps.quit_application()


if __name__ == "__main__":
    app = CronoFollowupApp()
    app.run()
